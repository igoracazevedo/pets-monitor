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


def mascara(poly_rel, forma) -> np.ndarray | None:
    """Máscara (255 dentro) do contorno livre, em pontos relativos (0 a 1) ao retângulo do objeto. None = retângulo inteiro."""
    if not poly_rel or len(poly_rel) < 3:
        return None
    h, w = forma[:2]
    m = np.zeros((h, w), np.uint8)
    pts = np.array([[min(w - 1, max(0, round(x * (w - 1)))), min(h - 1, max(0, round(y * (h - 1))))] for x, y in poly_rel], np.int32)
    cv2.fillPoly(m, [pts], 255)
    return m if m.sum() > 0 else None


def cobertura(zona: tuple, animal: tuple) -> float:
    """Que parte da zona (x, y, w, h[, contorno relativo]) está coberta pela caixa do animal (x1, y1, x2, y2 de 0 a 1)?"""
    zx, zy, zw, zh = zona[:4]
    ax1, ay1, ax2, ay2 = animal
    poly = zona[4] if len(zona) > 4 else None
    if not poly:
        return max(0.0, min(ax2, zx + zw) - max(ax1, zx)) * max(0.0, min(ay2, zy + zh) - max(ay1, zy)) / max(1e-9, zw * zh)
    m = mascara(poly, (48, 48))
    if m is None:
        return 0.0
    c1, c2 = max(0, int((ax1 - zx) / zw * 48)), min(48, int(np.ceil((ax2 - zx) / zw * 48)))
    r1, r2 = max(0, int((ay1 - zy) / zh * 48)), min(48, int(np.ceil((ay2 - zy) / zh * 48)))
    if c2 <= c1 or r2 <= r1:
        return 0.0
    return float((m[r1:r2, c1:c2] > 0).sum()) / float((m > 0).sum())


def _hist(img: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    h = cv2.calcHist([cv2.cvtColor(img, cv2.COLOR_BGR2HSV)], [0, 1], mask, [18, 16], [0, 180, 0, 256])
    cv2.normalize(h, h, 0, 1, cv2.NORM_MINMAX)
    return h


@dataclass
class Modelo:
    """Aparência de um objeto: contraste (vale de dia e à noite) e cor (só de dia)."""
    cinza: np.ndarray
    hist: np.ndarray | None
    mask: np.ndarray | None = None  # contorno livre: só estes pontos contam na comparação

    @staticmethod
    def de(recorte: np.ndarray, noite: bool, poly_rel=None) -> "Modelo":
        m = mascara(poly_rel, recorte.shape)
        return Modelo(_cinza(recorte), None if noite else _hist(recorte, m), m)


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
        res = None
        if modelo.mask is not None:
            try:  # só os pontos dentro do contorno livre contam (nem todo opencv aceita máscara aqui: cai para o retângulo)
                res = cv2.matchTemplate(reg, t, cv2.TM_CCOEFF_NORMED, mask=cv2.resize(modelo.mask, (tw, th), interpolation=cv2.INTER_NEAREST))
            except cv2.error:
                res = None
        if res is None:
            res = cv2.matchTemplate(reg, t, cv2.TM_CCOEFF_NORMED)
        _, mx, _, loc = cv2.minMaxLoc(np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0))
        if mx > melhor:
            melhor, caixa = float(mx), (x0 + loc[0], y0 + loc[1], tw, th)
    if caixa is None:
        return 0.0, None
    x, y, w, h = caixa
    nota = melhor
    if modelo.hist is not None and not noite:
        mk = cv2.resize(modelo.mask, (w, h), interpolation=cv2.INTER_NEAREST) if modelo.mask is not None else None
        cor = max(0.0, float(cv2.compareHist(modelo.hist, _hist(peq[y : y + h, x : x + w], mk), cv2.HISTCMP_CORREL)))
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
    id: str
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
    imagem: str | None = None           # recorte guardado no banco
    poly: list | None = None            # contorno livre, em pontos relativos ao retângulo do objeto


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

    def _carregar_modelo(self, caminho: Path, noite: bool, poly=None) -> Modelo | None:
        img = cv2.imread(str(caminho)) if caminho.exists() else None
        return Modelo.de(img, noite, poly) if img is not None else None

    def sincronizar(self, linhas: list[dict]):
        """Os objetos vêm da tabela pm_objetos (criados ao marcar um local no app). Continuam existindo mesmo que o desenho na foto seja apagado:
        só saem quando você apaga o objeto na lista de Objetos."""
        vistos = set()
        for r in linhas:
            if r.get("tipo") not in TIPOS or r.get("x") is None:
                continue
            oid = r["id"]
            vistos.add(oid)
            o = self.objetos.get(oid)
            if o:
                o.pet_id, o.tipo = r.get("pet_id"), r["tipo"]
                continue
            box = (float(r["x"]), float(r["y"]), float(r["w"]), float(r["h"]))
            home = r.get("camera_origem") or r.get("camera_id")
            o = Objeto(oid, r.get("pet_id"), r["tipo"], home, box, cam=r.get("camera_id") or home, box=box)
            o.sumido = bool(r.get("sumido"))
            pol = r.get("poligono")
            if pol and len(pol) >= 3 and box[2] > 0 and box[3] > 0:  # contorno livre desenhado no app: guarda relativo ao retângulo que o envolve
                o.poly = [((float(px) - box[0]) / box[2], (float(py) - box[1]) / box[3]) for px, py in pol]
            o.dia = self._modelo_do_banco(o, r)
            o.noite = self._carregar_modelo(self.pasta / f"{oid}-noite.jpg", True, o.poly)
            self.objetos[oid] = o
        for oid in [k for k in self.objetos if k not in vistos]:
            del self.objetos[oid]
            for f in (self.pasta / f"{oid}.jpg", self.pasta / f"{oid}-noite.jpg"):
                f.unlink(missing_ok=True)

    def _modelo_do_banco(self, o: Objeto, r: dict) -> Modelo | None:
        """Recorte guardado no banco (tirado da foto no momento da marcação). Sem ele, o programa aprende pela câmera, mais tarde."""
        local = self.pasta / f"{o.id}.jpg"
        if not local.exists() and r.get("imagem_path"):
            try:
                img = cv2.imdecode(np.frombuffer(self.db.baixar_snapshot(r["imagem_path"]), np.uint8), cv2.IMREAD_COLOR)
                ref = r.get("largura_ref")
                if img is not None and ref and int(ref) > LARGURA:  # a foto do app é maior que as imagens de 640 px comparadas aqui
                    k = LARGURA / int(ref)
                    img = cv2.resize(img, (max(1, int(img.shape[1] * k)), max(1, int(img.shape[0] * k))), interpolation=cv2.INTER_AREA)
                if img is not None:
                    cv2.imwrite(str(local), img)
            except Exception as e:
                print(f"  catálogo: não consegui baixar o recorte de {self.rotulo(o)} ({e})", flush=True)
        return self._carregar_modelo(local, False, o.poly)

    def tem_tipo(self, tipo: str) -> bool:
        return any(o.tipo == tipo for o in self.objetos.values())

    def caixas(self, cid: str, tipo: str) -> list[tuple]:
        """Onde está agora cada objeto desse tipo, na câmera `cid` (x, y, w, h de 0 a 1)."""
        return [o.box for o in self.objetos.values() if o.tipo == tipo and o.cam == cid and not o.sumido]

    def alvos(self, cid: str, tipo: str) -> list[tuple]:
        """Como `caixas`, mas com o contorno livre (relativo) quando houver: (x, y, w, h) ou (x, y, w, h, contorno)."""
        return [(*o.box, o.poly) if o.poly else tuple(o.box) for o in self.objetos.values() if o.tipo == tipo and o.cam == cid and not o.sumido]

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
                o.noite = Modelo.de(recorte, True, o.poly)
                cv2.imwrite(str(self.pasta / f"{o.id}-noite.jpg"), recorte)
                continue
            o.dia = Modelo.de(recorte, False, o.poly)
            cv2.imwrite(str(self.pasta / f"{o.id}.jpg"), recorte)
            o.gravado = 0.0
            print(f"  [catálogo] aprendi o {self.rotulo(o)} ({self.nome_camera(cid)})", flush=True)
            try:
                ok, buf = cv2.imencode(".jpg", recorte)
                self.db.enviar_foto(f"objetos/{o.id}.jpg", buf.tobytes())
                o.imagem = f"objetos/{o.id}.jpg"
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
        """Guarda no banco onde o objeto está agora (o app mostra); se a tabela ainda não existe, segue só localmente."""
        if time.time() < self.banco_ok_em:
            return
        o.gravado = agora
        try:
            from .store import agora as iso

            campos = {
                "camera_id": o.cam, "x": round(o.box[0], 4), "y": round(o.box[1], 4), "w": round(o.box[2], 4), "h": round(o.box[3], 4),
                "sumido": o.sumido, "visto_em": iso(),
            }
            if o.imagem:
                campos["imagem_path"] = o.imagem
            self.db.objeto(o.id, campos)
        except Exception:
            self.banco_ok_em = time.time() + 600
