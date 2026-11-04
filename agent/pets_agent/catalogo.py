"""Catálogo dos objetos de cada pet (bebedouro, comedouro, banheiro, cama).

Cada local marcado no app vira um objeto com a aparência aprendida (recorte da imagem). O programa passa a PROCURAR o objeto
pela aparência, e não pelo lugar: se a vasilha mudar de posição, ou for para outra câmera, o catálogo acompanha e os
eventos (bebeu água, comendo) passam a valer no lugar novo.
"""
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .noturno import eh_noturno

LARGURA = 640                    # tudo é comparado numa imagem de 640 px de largura
ESCALAS = (0.5, 0.7, 1.0, 1.4, 2.0)  # o mesmo objeto aparece maior/menor conforme a câmera
ACHADO = 0.60                    # nota mínima para dizer "está aí" (perto de onde estava)
MUDOU = 0.72                     # nota mínima para dizer "foi para outro lugar/câmera" (mais rígida)
CONFIRMACOES = 3                 # vezes seguidas vendo no lugar novo, ao longo de pelo menos 90 s
SUMIU_APOS = 8                   # conferências seguidas sem achar (sem bicho na frente) até considerar que sumiu
TIPOS = {"bebedouro": "bebedouro", "comedouro": "comedouro", "banheiro": "banheiro", "cama": "cama"}


def _pequeno(frame: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]
    if w <= LARGURA:
        return frame
    return cv2.resize(frame, (LARGURA, int(h * LARGURA / w)), interpolation=cv2.INTER_AREA)


def _cinza(img: np.ndarray) -> np.ndarray:
    """Cinza com contraste local equilibrado: serve de dia e no infravermelho."""
    return cv2.createCLAHE(2.0, (4, 4)).apply(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))


def _hist(img: np.ndarray) -> np.ndarray:
    h = cv2.calcHist([cv2.cvtColor(img, cv2.COLOR_BGR2HSV)], [0, 1], None, [18, 16], [0, 180, 0, 256])
    cv2.normalize(h, h, 0, 1, cv2.NORM_MINMAX)
    return h


@dataclass
class Modelo:
    """Aparência de um objeto: contraste (vale de dia e à noite) e cor (só de dia)."""
    cinza: np.ndarray
    hist: np.ndarray | None

    @staticmethod
    def de(recorte: np.ndarray, noite: bool) -> "Modelo":
        return Modelo(_cinza(recorte), None if noite else _hist(recorte))


def procurar(cinza: np.ndarray, peq: np.ndarray, modelo: Modelo, janela=None, noite: bool = False):
    """-> (nota 0-1, (x, y, w, h) de 0 a 1) do melhor lugar onde o modelo aparece. `janela` = (x0, y0, x1, y1) de 0 a 1."""
    H, W = cinza.shape
    x0 = y0 = 0
    reg = cinza
    if janela:
        a, b, c, d = janela
        x0, y0, x1, y1 = max(0, int(a * W)), max(0, int(b * H)), min(W, int(c * W)), min(H, int(d * H))
        reg = cinza[y0:y1, x0:x1]
    th0, tw0 = modelo.cinza.shape
    if float(modelo.cinza.std()) < 4:  # recorte liso demais: não dá para comparar
        return 0.0, None
    melhor, caixa = 0.0, None
    for s in ESCALAS:
        tw, th = int(round(tw0 * s)), int(round(th0 * s))
        if tw < 12 or th < 12 or tw >= reg.shape[1] or th >= reg.shape[0]:
            continue
        t = cv2.resize(modelo.cinza, (tw, th), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
        _, mx, _, loc = cv2.minMaxLoc(cv2.matchTemplate(reg, t, cv2.TM_CCOEFF_NORMED))
        if mx > melhor:
            melhor, caixa = float(mx), (x0 + loc[0], y0 + loc[1], tw, th)
    if caixa is None:
        return 0.0, None
    x, y, w, h = caixa
    nota = melhor
    if modelo.hist is not None and not noite:
        cor = max(0.0, float(cv2.compareHist(modelo.hist, _hist(peq[y : y + h, x : x + w]), cv2.HISTCMP_CORREL)))
        nota = 0.7 * melhor + 0.3 * cor
    return nota, (x / W, y / H, w / W, h / H)


def _inter(a, b) -> float:
    """Fração da caixa `a` (x, y, w, h) que está coberta pela caixa `b`."""
    ix = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    return ix * iy / max(1e-9, a[2] * a[3])


def _iou(a, b) -> float:
    inter = _inter(a, b) * a[2] * a[3]
    return inter / max(1e-9, a[2] * a[3] + b[2] * b[3] - inter)


@dataclass
class Objeto:
    zona_id: str
    pet_id: str | None
    tipo: str
    camera_id: str                      # câmera onde foi marcado
    box0: tuple                         # onde foi marcado (x, y, w, h de 0 a 1)
    dia: Modelo | None = None
    noite: Modelo | None = None
    cam: str = ""                       # onde está agora
    box: tuple = ()
    visto: float = 0.0
    perdas: int = 0
    sumido: bool = False
    cand: dict | None = None
    buscou: dict = field(default_factory=dict)
    gravado: float = 0.0


class Catalogo:
    def __init__(self, db, pasta: Path, nome_pet=lambda pid: None, nome_camera=lambda cid: cid[:6]):
        self.db = db
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.nome_pet = nome_pet
        self.nome_camera = nome_camera
        self.objetos: dict[str, Objeto] = {}
        self.banco_ok_em = 0.0   # se a tabela ainda não existe, tenta de novo só daqui a pouco

    # --- cadastro ---
    def rotulo(self, o: Objeto) -> str:
        pet = self.nome_pet(o.pet_id) if o.pet_id else None
        return f"{TIPOS.get(o.tipo, o.tipo)} {'da ' + pet if pet else ''}".strip()

    def _carregar_modelo(self, caminho: Path, noite: bool) -> Modelo | None:
        img = cv2.imread(str(caminho)) if caminho.exists() else None
        return Modelo.de(img, noite) if img is not None else None

    def sincronizar(self, zonas: dict[str, list[dict]]):
        """Cada local marcado no app (qualquer câmera) vira um objeto do catálogo."""
        vistos = set()
        for cid, lista in zonas.items():
            for z in lista:
                if z.get("tipo") not in TIPOS:
                    continue
                zid = z["id"]
                vistos.add(zid)
                box0 = (float(z["x"]), float(z["y"]), float(z["w"]), float(z["h"]))
                o = self.objetos.get(zid)
                if o:
                    o.pet_id = z.get("pet_id")  # trocar o dono não muda a aparência: não precisa aprender de novo
                if o and (o.tipo != z["tipo"] or _iou(o.box0, box0) < 0.9):
                    del self.objetos[zid]  # você redesenhou/trocou o local: aprende de novo
                    o = None
                    for f in (self.pasta / f"{zid}.jpg", self.pasta / f"{zid}-noite.jpg"):
                        f.unlink(missing_ok=True)
                if not o:
                    o = Objeto(zid, z.get("pet_id"), z["tipo"], cid, box0, cam=cid, box=box0)
                    o.dia = self._carregar_modelo(self.pasta / f"{zid}.jpg", False)
                    o.noite = self._carregar_modelo(self.pasta / f"{zid}-noite.jpg", True)
                    self.objetos[zid] = o
        for zid in [k for k in self.objetos if k not in vistos]:
            del self.objetos[zid]
            for f in (self.pasta / f"{zid}.jpg", self.pasta / f"{zid}-noite.jpg"):
                f.unlink(missing_ok=True)

    def tem_tipo(self, tipo: str) -> bool:
        return any(o.tipo == tipo for o in self.objetos.values())

    def caixas(self, cid: str, tipo: str) -> list[tuple]:
        """Onde está agora cada objeto desse tipo, na câmera `cid` (x, y, w, h de 0 a 1)."""
        return [o.box for o in self.objetos.values() if o.tipo == tipo and o.cam == cid and not o.sumido]

    def tem_na_camera(self, cid: str) -> bool:
        return any(o.cam == cid and o.tipo in ("bebedouro", "comedouro", "banheiro") and not o.sumido for o in self.objetos.values())

    # --- aprendizado ---
    def aprender(self, cid: str, frame: np.ndarray, ocupados: list[tuple]):
        """Tira o recorte do objeto na imagem de agora (se não houver bicho/pessoa em cima e ele estiver no lugar marcado)."""
        noite = eh_noturno(frame)
        peq = None
        for o in self.objetos.values():
            if o.camera_id != cid or o.cam != cid or (o.noite if noite else o.dia) is not None:
                continue
            if _iou(o.box, o.box0) < 0.5 or any(_inter(o.box0, b) > 0 for b in ocupados):
                continue
            peq = _pequeno(frame) if peq is None else peq
            H, W = peq.shape[:2]
            x, y, w, h = o.box0
            recorte = peq[int(y * H) : int((y + h) * H), int(x * W) : int((x + w) * W)]
            if recorte.shape[0] < 14 or recorte.shape[1] < 14:
                continue
            if noite:
                o.noite = Modelo.de(recorte, True)
                cv2.imwrite(str(self.pasta / f"{o.zona_id}-noite.jpg"), recorte)
                continue
            o.dia = Modelo.de(recorte, False)
            cv2.imwrite(str(self.pasta / f"{o.zona_id}.jpg"), recorte)
            o.gravado = 0.0
            print(f"  [catálogo] aprendi o {self.rotulo(o)} ({self.nome_camera(cid)})", flush=True)
            try:
                ok, buf = cv2.imencode(".jpg", recorte)
                self.db.enviar_foto(f"objetos/{o.zona_id}.jpg", buf.tobytes())
            except Exception:
                pass
            self._gravar(o, time.time())

    # --- acompanhamento ---
    def atualizar(self, cid: str, frame: np.ndarray, ocupados: list[tuple], tem_animal: bool, agora: float | None = None):
        """Confere onde cada objeto está nesta imagem. `ocupados` = caixas (x, y, w, h de 0 a 1) de bichos e gente."""
        agora = agora or time.time()
        if not any(o.dia or o.noite for o in self.objetos.values()):
            return
        peq = _pequeno(frame)
        cz = _cinza(peq)
        noite = eh_noturno(frame)
        for o in list(self.objetos.values()):
            modelo = o.noite if noite else o.dia
            if modelo is None:
                continue  # sem a aparência deste horário (dia/noite): não dá para conferir, fica onde estava
            try:
                self._um(o, modelo, cid, peq, cz, noite, ocupados, tem_animal, agora)
            except Exception as e:
                print(f"  catálogo: {e}", flush=True)

    def _um(self, o: Objeto, modelo: Modelo, cid, peq, cz, noite, ocupados, tem_animal, agora):
        if o.cam == cid:
            if any(_inter(o.box, b) >= 0.25 for b in ocupados):
                return  # bicho em cima: não dá para conferir, vale o último lugar
            x, y, w, h = o.box
            nota, caixa = procurar(cz, peq, modelo, (x - 0.6 * w, y - 0.6 * h, x + 1.6 * w, y + 1.6 * h), noite)
            if caixa and nota >= ACHADO:
                o.box = tuple((a + b) / 2 for a, b in zip(o.box, caixa))
                o.visto, o.perdas, o.cand, o.sumido = agora, 0, None, False
                if agora - o.gravado > 600:
                    self._gravar(o, agora)
                return
            o.perdas += 1
            if o.perdas < 3:
                return
            nota, caixa = procurar(cz, peq, modelo, None, noite)  # sumiu daqui: procura na imagem toda
            if o.perdas >= SUMIU_APOS and not o.sumido and not (caixa and nota >= MUDOU):
                o.sumido = True
                print(f"  [catálogo] não vejo mais o {self.rotulo(o)} em {self.nome_camera(cid)}", flush=True)
                self._gravar(o, agora)
            self._candidato(o, cid, nota, caixa, agora)
        else:
            periodo = 240 if (tem_animal and o.tipo in ("bebedouro", "comedouro")) else 1800
            if agora - o.buscou.get(cid, 0) < periodo:
                return
            o.buscou[cid] = agora
            nota, caixa = procurar(cz, peq, modelo, None, noite)
            self._candidato(o, cid, nota, caixa, agora)

    def _candidato(self, o: Objeto, cid: str, nota: float, caixa, agora: float):
        c = o.cand
        if c and agora - c["ult"] > 1800:
            c = o.cand = None
        if not caixa or nota < MUDOU:
            return
        if c and c["cam"] == cid and _iou(c["box"], caixa) > 0.3:
            c["n"] += 1
            c["ult"], c["box"] = agora, caixa
        else:
            o.cand = {"cam": cid, "box": caixa, "n": 1, "ini": agora, "ult": agora}
            return
        if c["n"] >= CONFIRMACOES and c["ult"] - c["ini"] >= 90:
            antes = o.cam
            o.cam, o.box, o.visto, o.perdas, o.cand, o.sumido = cid, caixa, agora, 0, None, False
            if antes != cid:
                print(f"  [catálogo] o {self.rotulo(o)} mudou de {self.nome_camera(antes)} para {self.nome_camera(cid)}", flush=True)
            else:
                print(f"  [catálogo] o {self.rotulo(o)} mudou de lugar em {self.nome_camera(cid)}", flush=True)
            self._gravar(o, agora)

    def _gravar(self, o: Objeto, agora: float):
        """Mostra o catálogo no app (tabela pm_objetos); se a tabela ainda não existe, segue só localmente."""
        if time.time() < self.banco_ok_em:
            return
        o.gravado = agora
        try:
            from .store import agora as iso

            self.db.objeto({
                "zona_id": o.zona_id, "pet_id": o.pet_id, "tipo": o.tipo, "camera_id": o.cam,
                "x": round(o.box[0], 4), "y": round(o.box[1], 4), "w": round(o.box[2], 4), "h": round(o.box[3], 4),
                "imagem_path": f"objetos/{o.zona_id}.jpg" if o.dia else None, "sumido": o.sumido, "visto_em": iso(),
            })
        except Exception:
            self.banco_ok_em = time.time() + 600
