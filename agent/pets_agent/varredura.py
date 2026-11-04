import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import cv2
import numpy as np

from . import capture
from .detect import _iou
from .identify import Identificador, Palpite, caracteristica
from .privacidade import desfocar_pessoas
from .noturno import MemoriaTamanhos, area_relativa, eh_noturno, por_tamanho
from .store import Supabase, agora


def slug(nome: str) -> str:
    """Nome de câmera vira nome de arquivo seguro (sem acento, espaço ou símbolo)."""
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower() or "camera"


def iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """Sobreposição entre duas caixas (x1, y1, x2, y2). 1 = mesma caixa, 0 = sem contato."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    uni = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / uni if uni > 0 else 0.0


# Onde fica o bebedouro/vasilha em cada câmera (x, y, largura, altura de 0 a 1), procurado pelo trecho do nome da câmera.
# Mais específico primeiro. Pode ser trocado no config.yaml em `zonas_agua`.
ZONAS_AGUA = {
    "banheiro": [0.12, 0.34, 0.09, 0.12],        # vasilha rosa à esquerda
    "quarto varanda": [0.37, 0.43, 0.13, 0.12],  # bebedouro lilás + vasilha branca ao lado do cercadinho
    "quarto": [0.38, 0.84, 0.14, 0.16],          # visto de cima, na borda de baixo
}


def _sem_acento(t: str) -> str:
    return unicodedata.normalize("NFD", t).encode("ascii", "ignore").decode().lower()


def _jpeg(frame: np.ndarray, largura: int) -> bytes:
    h, w = frame.shape[:2]
    if w > largura:
        frame = cv2.resize(frame, (largura, int(h * largura / w)))
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return buf.tobytes()


PALETA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
CORES: dict[str, tuple[int, int, int]] = {}  # nome -> cor BGR da marcação (escolhida no app)


def _bgr(hexa: str) -> tuple[int, int, int]:
    return int(hexa[5:7], 16), int(hexa[3:5], 16), int(hexa[1:3], 16)


def _cor_valida(c) -> bool:
    return isinstance(c, str) and len(c) == 7 and c[0] == "#" and all(x in "0123456789abcdefABCDEF" for x in c[1:])


def _anotar(frame: np.ndarray, marcas: list[tuple[tuple[int, int, int, int], str]]) -> np.ndarray:
    img = frame.copy()
    for (x1, y1, x2, y2), texto in marcas:
        cor = CORES.get(texto, (0, 98, 255))
        cv2.rectangle(img, (x1, y1), (x2, y2), cor, 3)
        cv2.putText(img, texto, (x1 + 4, max(24, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, cor, 2, cv2.LINE_AA)
    return img


class Varredura:
    def __init__(self, cfg: dict, db: Supabase, detector):
        self.cfg = cfg
        self.db = db
        self.detector = detector
        self.pets = db.pets()
        self.ident = Identificador(self.pets, cfg["identificacao"]["pontuacao_minima"], cfg["identificacao"]["margem_minima"])
        self.atualizar_cores()
        self.fixas = []
        for i, c in enumerate(cfg["cameras"]):
            ip = c.get("host") or c.get("url", "").split("@")[-1].split("/")[0].split(":")[0] or None
            self.fixas.append((c, db.garantir_camera(c["nome"], c.get("ambiente"), i, None, ip)))
        self.cameras = list(self.fixas)
        # câmeras Intelbras achadas na rede (pelo número de série); o apelido vem do app
        self.cred = cfg.get("credencial_intelbras")
        self.achadas: dict[str, tuple[dict, dict]] = {}
        self.ignorados: set[str] = set()
        self.relatado: set[str] = set()
        self.ultima_descoberta = 0.0
        self.ultimo_nomes = 0.0
        self.estado_presenca: dict[str, tuple[int, float, str]] = {}
        from .banheiro import Banheiro

        self.banheiro = Banheiro(db)
        self.estado_banheiro: dict[str, str] = {}
        self.zonas: dict[str, list[dict]] = {}
        self.ultimas_zonas = 0.0
        self.ultima_agua: dict[str, float] = {}
        self.caixa_agua: dict[str, tuple[float, tuple[int, int, int, int]]] = {}
        from .notificar import Notificador

        self.notificador = Notificador(db) if hasattr(db, "assinaturas_push") else None
        self.nomes_notificar: dict[str, bool] = {}
        self.rostos = None            # carregado só se houver pessoas cadastradas
        self.conhecidos: list[dict] = []
        self.ignorar: dict[str, list[tuple[float, float, float, float]]] = {}
        # estado em memória: onde cada pet foi visto por último (para não encher o histórico)
        self.ultimo: dict[str, dict] = {}
        self.tamanhos = MemoriaTamanhos(cfg.get("arquivo_tamanhos", "tamanhos.json"))
        self.ultimo_quadro: dict[str, float] = {}
        self.falhas: dict[str, tuple[int, float]] = {}  # câmera -> (falhas seguidas, só tenta de novo depois de)

    def proteger(self, frame, cid: str | None = None):
        """Imagem que pode sair do PC: corpo das pessoas desfocado, só o rosto nítido (desligue com proteger_pessoas: false)."""
        if not self.cfg.get("proteger_pessoas", True):
            return frame
        try:
            caixas = self.detector.pessoas_na_imagem(frame) if hasattr(self.detector, "pessoas_na_imagem") else []
            h, w = frame.shape[:2]
            # lugares que você marcou "Não é pessoa" (cama, cobertor, bicho de pelúcia) não são escondidos
            ign = [(a * w, b * h, c * w, d * h) for a, b, c, d in self.ignorar.get(cid, [])] if cid else []
            caixas = [c for c in caixas if not any(_iou(c, g) > 0.4 for g in ign)]
            if not caixas:
                return frame
            if self.rostos is None:
                from .rostos import Rostos

                self.rostos = Rostos()
            return desfocar_pessoas(frame, caixas, self.rostos)
        except Exception as e:  # sem a proteção a imagem NÃO é enviada: melhor sem foto do que com a pessoa à mostra
            raise RuntimeError(f"não consegui proteger a imagem ({e})")

    def atualizar_cores(self):
        """Cor de cada pet/pessoa para a marcação nas fotos: a escolhida no app; sem escolha, a mesma regra do app (pets de frente para trás, pessoas de trás para frente)."""
        CORES.clear()
        for i, p in enumerate(self.pets):
            CORES[p["nome"]] = _bgr(p["cor"] if _cor_valida(p.get("cor")) else PALETA[i % 8])
        try:
            for j, p in enumerate(self.db.pessoas()):
                CORES[p["nome"]] = _bgr(p["cor"] if _cor_valida(p.get("cor")) else PALETA[7 - (j % 8)])
        except Exception:
            pass

    def recarregar_pets(self):
        self.pets = self.db.pets()
        self.atualizar_cores()
        i = self.cfg["identificacao"]
        self.ident = Identificador(self.pets, i["pontuacao_minima"], i["margem_minima"])

    def precisa_redescobrir(self) -> bool:
        if not self.cred:
            return False
        idade = time.time() - self.ultima_descoberta
        com_falha = any(cid in self.falhas for _, reg in self.achadas.values() for cid in [reg["id"]])
        return idade >= 300 or (idade >= 60 and (com_falha or not self.achadas))

    def redescobrir(self) -> int:
        """Procura as câmeras Intelbras na rede e atualiza o IP de cada uma. Câmera nova entra com o nome 'Câmera xxxx' para você renomear no app."""
        from . import descoberta

        self.ultima_descoberta = time.time()
        base = ".".join(descoberta.ip_local().split(".")[:3])
        fixos = {c.get("host") or c.get("url", "").split("@")[-1].split("/")[0].split(":")[0] for c, _ in self.fixas}
        relatorio: list[str] = []
        achadas = descoberta.descobrir(base, self.cred["usuario"], self.cred["senha"], fixos, self.ignorados, relatorio)
        for linha in relatorio:
            if linha not in self.relatado:
                self.relatado.add(linha)
                print("  [rede]", linha, flush=True)
        for a in achadas:
            ident = a["identificador"]
            reg = self.db.garantir_camera(f"Câmera {ident[-4:]}", None, 100 + len(self.achadas), ident, a["ip"])
            if ident in self.achadas:
                reg = {**self.achadas[ident][1], "ip_atual": a["ip"]}
            cfg_cam = {"nome": reg["nome"], "fonte": "intelbras", "host": a["ip"], "usuario": self.cred["usuario"], "senha": self.cred["senha"]}
            self.achadas[ident] = (cfg_cam, reg)
            self.falhas.pop(reg["id"], None)  # IP novo: tenta já
        self.cameras = self.fixas + list(self.achadas.values())
        return len(self.achadas)

    def carregar_pessoas(self):
        """Pessoas cadastradas no site com rosto já aprendido (a conta de quem entra: só no PC, o site nunca vê os vetores)."""
        if not self.cfg.get("reconhecer_pessoas", True) or not self.cfg.get("detectar_pessoas", True):
            return
        try:
            embs = self.db.rostos_das_pessoas()
            pessoas = self.db.pessoas()
        except Exception:
            return  # SQL ainda não rodado
        self.nomes_notificar = {p["id"]: bool(p.get("notificar")) for p in pessoas}
        self.conhecidos = [
            {"id": p["id"], "nome": p["nome"], "embs": [np.array(e, dtype=np.float32) for e in embs.get(p["id"], [])]}
            for p in pessoas
            if embs.get(p["id"])
        ]
        if self.conhecidos and self.rostos is None:
            from .rostos import Rostos

            self.rostos = Rostos()

    def quem_e(self, frame, caixa, alta):
        """Tenta reconhecer o rosto de uma pessoa detectada. Primeiro no quadro atual; se não der, no quadro em resolução cheia."""
        if not (self.rostos and self.conhecidos):
            return None

        def recorte(img, c, escala=1.0):
            x1, y1, x2, y2 = (int(v * escala) for v in c)
            mx, my = int((x2 - x1) * 0.15), int((y2 - y1) * 0.1)
            return img[max(0, y1 - my) : y2 + my, max(0, x1 - mx) : x2 + mx]

        try:
            r = self.rostos.identificar(recorte(frame, caixa), self.conhecidos)
            if r is None and alta is not None:
                grande = alta()
                esc = grande.shape[1] / frame.shape[1]
                if esc > 1.2:
                    r = self.rostos.identificar(recorte(grande, caixa, esc), self.conhecidos)
            return r
        except Exception as e:
            print(f"  reconhecimento: {e}", flush=True)
            return None

    def carregar_zonas(self):
        """Locais marcados no app (banheiro, bebedouro, cama de cada um)."""
        if time.time() - self.ultimas_zonas < 120:
            return
        self.ultimas_zonas = time.time()
        try:
            self.zonas = {}
            for z in self.db.zonas():
                self.zonas.setdefault(z["camera_id"], []).append(z)
        except Exception:
            pass  # SQL ainda não rodado

    def atualizar_nomes(self):
        """Pega do banco o apelido e o liga/desliga de cada câmera (você muda no app)."""
        if time.time() - self.ultimo_nomes < 60:
            return
        self.ultimo_nomes = time.time()
        self.carregar_pessoas()
        try:
            self.ignorar = {}
            for r in self.db.ignorar():
                self.ignorar.setdefault(r["camera_id"], []).append((float(r["x"]), float(r["y"]), float(r["x"]) + float(r["w"]), float(r["y"]) + float(r["h"])))
        except Exception:
            pass  # SQL ainda não rodado: segue sem a lista
        try:
            atuais = {c["id"]: c for c in self.db.cameras()}
        except Exception:
            return
        self.cameras = [(c, {**reg, **{k: atuais[reg["id"]].get(k, reg.get(k)) for k in ("nome", "ativo")}} if reg["id"] in atuais else reg) for c, reg in self.cameras]

    def analisar(self, frame, cid: str, aprender: bool = True, alta=None):
        """Acha cães/gatos no quadro e diz quem é cada um: pela cor de dia; pelo tamanho no infravermelho.
        Detecção duvidosa (ex.: "urso de pelúcia" = spitz pequeno) só vale de dia e se a cor bater com um pet."""
        noite = eh_noturno(frame)
        h, w = frame.shape[:2]
        marcados = self.ignorar.get(cid, [])  # lugares que você disse "não é pet" (ex.: urso de pelúcia grande)

        def objeto(d) -> bool:
            x1, y1, x2, y2 = d.caixa
            return any(iou((x1 / w, y1 / h, x2 / w, y2 / h), m) > 0.4 for m in marcados)

        todas = [d for d in self.detector.detectar(frame) if not (noite and d.fraca) and not objeto(d)]
        gente = [d for d in todas if d.especie == "pessoa"]
        dets = [d for d in todas if d.especie != "pessoa"]
        extra_d = gente
        extra_p = []
        tentou_alta = False
        for d in gente:
            r = self.quem_e(frame, d.caixa, None if tentou_alta else alta)
            tentou_alta = tentou_alta or (alta is not None and self.rostos is not None)
            extra_p.append(Palpite(None, r[0]["nome"], r[1], "rosto", r[0]["id"]) if r else Palpite(None, "Pessoa", 1.0, "pessoa"))
        if dets and noite:  # infravermelho: sem cor, decide pelo tamanho
            return dets + extra_d, por_tamanho([d.caixa for d in dets], frame.shape, cid, self.pets, self.tamanhos) + extra_p
        usados: set[str] = set()
        dets_ok, palpites = [], []
        for d in dets:
            p = self.ident.palpite(caracteristica(frame, d.caixa), usados)
            if d.fraca and (area_relativa(d.caixa, frame.shape) > 0.05 or not (p.pet_id and p.pontuacao >= 0.6)):
                continue  # brinquedo ou coisa parecida (urso de pelúcia grande na cama: grande demais e/ou cor diferente)
            if p.pet_id:
                usados.add(p.pet_id)  # um pet aparece uma vez por quadro
                if aprender and p.como == "cor" and len(self.pets) > 1:  # aprende o tamanho dele nesta câmera para usar à noite
                    self.tamanhos.atualizar(cid, p.pet_id, area_relativa(d.caixa, frame.shape))
            dets_ok.append(d)
            palpites.append(p)
        return dets_ok + extra_d, palpites + extra_p

    def uma_camera(self, cfg_cam: dict, reg: dict) -> str:
        nome, cid = reg["nome"], reg["id"]  # nome = apelido dado no app; cid = identidade estável da câmera
        if reg.get("ativo") is False:
            return f"{nome}: desativada"
        n_falhas, ate = self.falhas.get(cid, (0, 0.0))
        if n_falhas and time.time() < ate:  # câmera fora do ar: não segura as outras a cada volta
            return f"{nome}: sem sinal (tenta de novo em {int(ate - time.time())} s)"
        try:
            frame = capture.capturar(cfg_cam)
            self.falhas.pop(cid, None)
        except Exception as e:  # câmera fora do ar não derruba as outras
            self.falhas[cid] = (n_falhas + 1, time.time() + min(300, 20 * 2**n_falhas))
            self.db.status_camera(reg["id"], False, str(e))
            return f"{nome}: ERRO {e}"

        h, w = frame.shape[:2]
        dets, palpites = self.analisar(frame, cid, alta=lambda: capture.capturar_alta(cfg_cam))
        marcas, achados = [], []
        for d, p in zip(dets, palpites):
            achados.append((d, p))
            marcas.append((d.caixa, p.nome or "?"))

        zs = getattr(self, "zonas", {}).get(cid, [])
        tem = lambda t: any(z.get("tipo") == t for z in zs)
        if "banheiro" in _sem_acento(nome) or "quarto" in _sem_acento(nome) or tem("bebedouro") or tem("comedouro") or tem("banheiro"):
            try:
                self.vigiar_agua(cid, nome, frame, achados)
                self.vigiar_comida(cid, nome, frame, achados)
                if "banheiro" in _sem_acento(nome) or tem("banheiro"):
                    self.vigiar_banheiro(cid, nome, frame, dets)
            except Exception as e:
                print(f"  banheiro {nome}: {e}", flush=True)

        agora_ts = time.time()
        publico = []  # imagem protegida, calculada só se alguma foto for mesmo enviada

        def imagem_publica():
            if not publico:
                publico.append(_anotar(self.proteger(frame, cid), marcas))
            return publico[0]

        quadro_path = None
        if agora_ts - self.ultimo_quadro.get(cid, 0) >= self.cfg["quadro_da_camera_a_cada_s"]:
            quadro_path = f"cameras/{cid}.jpg"
            self.db.enviar_foto(quadro_path, _jpeg(imagem_publica(), self.cfg["largura_foto"]))
            self.ultimo_quadro[cid] = agora_ts
        self.db.status_camera(reg["id"], True, quadro_path=quadro_path)

        foto = None
        n_pessoas = sum(1 for d, _ in achados if d.especie == "pessoa")
        quem = sorted({p.nome for d, p in achados if d.especie == "pessoa" and p.como == "rosto"})
        desconhecidas = sum(1 for d, p in achados if d.especie == "pessoa" and p.como != "rosto")
        chaves_vistas: set[str] = set()
        for d, p in achados:
            eh_pessoa = d.especie == "pessoa"
            chave = f"pessoa:{p.pessoa_id or 'anon'}:{cid}" if eh_pessoa else (p.pet_id or f"?{cid}")
            if eh_pessoa and chave in chaves_vistas:
                continue  # várias pessoas sem nome no quadro: um registro só (a contagem vai na presença)
            chaves_vistas.add(chave)
            x1, y1, x2, y2 = d.caixa
            pos = {
                "camera_id": cid,
                "confianca": round(min(d.confianca, 0.999), 3),
                "x": round(x1 / w, 4), "y": round(y1 / h, 4), "w": round((x2 - x1) / w, 4), "h": round((y2 - y1) / h, 4),
            }
            ant = self.ultimo.get(chave)
            # só vira item do histórico (e foto nova) quando é relevante: apareceu, mudou de câmera ou andou de verdade
            # (ou quando você pede "Onde estão agora?", que limpa a memória e força um registro)
            relevante = not ant or ant["camera"] != cid or iou(d.caixa, ant["caixa"]) < self.cfg.get("movimento_iou", 0.5)
            if eh_pessoa and ant:  # gente se mexe o tempo todo: no máximo um registro a cada alguns minutos por câmera
                relevante = relevante and agora_ts - ant["ts"] >= self.cfg.get("pessoas_intervalo_s", 180)
            if relevante:
                if foto is None:
                    foto = f"avistamentos/{datetime.now():%Y/%m/%d}/{cid[:8]}-{datetime.now():%H%M%S}.jpg"
                    self.db.enviar_foto(foto, _jpeg(imagem_publica(), self.cfg["largura_foto"]))
                self.db.avistamento({**pos, "identificacao": p.como, "pet_id": p.pet_id, "pessoa_id": p.pessoa_id, "especie": d.especie, "snapshot_path": foto})
                self.ultimo[chave] = {"camera": cid, "ts": agora_ts, "foto": foto, "foto_em": agora(), "caixa": d.caixa}
                self.avisar(p, nome, foto)
            else:
                # parado no mesmo lugar: não grava nada novo, só atualiza a caixa de referência aos poucos (evita "arrastar" lentamente)
                ant["caixa"] = d.caixa if iou(d.caixa, ant["caixa"]) > 0.8 else ant["caixa"]
            if p.pet_id:
                ref = self.ultimo[chave]
                # "visto_em" = última vez que o vi; "foto_em" = quando a foto foi tirada (a foto só muda quando a posição muda)
                self.db.ultima_posicao({**pos, "pet_id": p.pet_id, "visto_em": agora(), "snapshot_path": ref["foto"], "foto_em": ref["foto_em"]})
        ref = next((self.ultimo[k] for k in sorted(self.ultimo) if k.startswith("pessoa:") and k.endswith(f":{cid}")), None)
        self.presenca(cid, n_pessoas, ref, ", ".join(quem + ([f"{desconhecidas} sem nome"] if desconhecidas and quem else [])))
        nomes = ", ".join(p.nome or "animal não identificado" for _, p in achados if p.como != "pessoa")
        if n_pessoas:
            nomes = (nomes + ", " if nomes else "") + (", ".join(quem) + (" + " if quem and desconhecidas else "") if quem else "") + (f"{desconhecidas} pessoa(s)" if desconhecidas or not quem else "")
        return f"{nome}: {nomes or 'ninguém'}"

    def vigiar_agua(self, cid: str, nome: str, frame, achados):
        """Bicho com o corpo em cima da zona da vasilha de água (config `zona_agua`: x, y, largura, altura de 0 a 1) = bebeu água."""
        marcadas = [(float(z["x"]), float(z["y"]), float(z["w"]), float(z["h"])) for z in getattr(self, "zonas", {}).get(cid, []) if z.get("tipo") == "bebedouro"]
        if marcadas:  # os bebedouros que você marcou nas fotos do Histórico valem mais que o padrão
            lista = marcadas
        else:
            zonas = {**ZONAS_AGUA, **{k.lower(): v for k, v in (self.cfg.get("zonas_agua") or {}).items()}}
            chave_zona = next((k for k in sorted(zonas, key=len, reverse=True) if k in _sem_acento(nome)), None)
            if not chave_zona:
                return
            lista = [tuple(zonas[chave_zona])]
        self._evento_por_zona("agua", cid, nome, frame, achados, lista, intervalo=600, parado=3600)

    def vigiar_comida(self, cid: str, nome: str, frame, achados):
        """Bicho com a boca nos comedouros que você marcou nas fotos (em qualquer câmera) = comendo."""
        lista = [(float(z["x"]), float(z["y"]), float(z["w"]), float(z["h"])) for z in getattr(self, "zonas", {}).get(cid, []) if z.get("tipo") == "comedouro"]
        if lista:
            self._evento_por_zona("comeu", cid, nome, frame, achados, lista, intervalo=900, parado=1200)

    def _evento_por_zona(self, tipo: str, cid: str, nome: str, frame, achados, lista, intervalo: int, parado: int):
        """Corpo do bicho sobre a região (bebedouro/comedouro): registra o evento com foto, no máximo 1 a cada `intervalo` s por bicho
        e sem repetir enquanto ele continua exatamente parado no mesmo lugar (dormindo ao lado) por até `parado` s."""
        h, w = frame.shape[:2]
        for d, p in achados:
            if d.especie == "pessoa":
                continue
            x1, y1, x2, y2 = (d.caixa[0] / w, d.caixa[1] / h, d.caixa[2] / w, d.caixa[3] / h)
            if not any(max(0.0, min(x2, zx + zw) - max(x1, zx)) * max(0.0, min(y2, zy + zh) - max(y1, zy)) >= 0.35 * zw * zh for zx, zy, zw, zh in lista):
                continue
            chave = f"{tipo}:{p.pet_id or '?' + cid}"
            if time.time() - self.ultima_agua.get(chave, 0) < intervalo:
                continue
            antes = self.caixa_agua.get(chave)
            if antes and time.time() - antes[0] < parado and _iou(d.caixa, antes[1]) > 0.7:
                continue
            self.ultima_agua[chave] = time.time()
            self.caixa_agua[chave] = (time.time(), d.caixa)
            pet = next((x for x in self.pets if x["id"] == p.pet_id), None) if p.pet_id else None
            foto = f"avistamentos/{datetime.now():%Y/%m/%d}/{tipo}-{cid[:8]}-{datetime.now():%H%M%S}.jpg"
            self.db.enviar_foto(foto, _jpeg(_anotar(self.proteger(frame, cid), [(d.caixa, pet["nome"] if pet else "?")]), self.cfg["largura_foto"]))
            self.db.evento_banheiro({"camera_id": cid, "tipo": tipo, "pet_id": pet["id"] if pet else None, "snapshot_path": foto, "visto_em": agora()})
            frase = "bebeu água" if tipo == "agua" else "comendo"
            print(f"  {nome}: {pet['nome'] if pet else 'um bicho'} {frase}", flush=True)
            if self.notificador and self.notificador.ativo:  # todo evento vai para o celular
                if tipo == "agua":
                    titulo = f"{pet['nome']} bebeu água" if pet else "Uma das cachorras bebeu água"
                else:
                    titulo = f"{pet['nome']} comendo" if pet else "Uma das cachorras comendo"
                try:
                    self.notificador.enviar(titulo, f"Visto no {nome} às {datetime.now():%H:%M}", self.db.url_assinada(foto), f"{tipo}-{int(time.time())}")
                except Exception as e:
                    print(f"  aviso: {e}", flush=True)

    def vigiar_banheiro(self, cid: str, nome: str, frame, dets):
        """Câmera do banheiro: com o tapete livre (sem bicho nem gente), vê se tem xixi ou coco novo e registra quem foi."""
        marcadas = [z for z in getattr(self, "zonas", {}).get(cid, []) if z.get("tipo") == "banheiro"]
        recorte = None
        if marcadas:  # banheiro marcado nas fotos: olha só a região dele (a câmera pode ser de qualquer cômodo)
            xs = [float(z["x"]) for z in marcadas]; ys = [float(z["y"]) for z in marcadas]
            xe = [float(z["x"]) + float(z["w"]) for z in marcadas]; ye = [float(z["y"]) + float(z["h"]) for z in marcadas]
            recorte = (min(xs), min(ys), max(xe) - min(xs), max(ye) - min(ys))
        h, w = frame.shape[:2]

        def sobre_o_tapete(d) -> bool:
            if not recorte:
                return True
            x1, y1, x2, y2 = d.caixa[0] / w, d.caixa[1] / h, d.caixa[2] / w, d.caixa[3] / h
            return min(x2, recorte[0] + recorte[2]) > max(x1, recorte[0]) and min(y2, recorte[1] + recorte[3]) > max(y1, recorte[1])

        if any(sobre_o_tapete(d) for d in dets):  # alguém em cima do tapete: a mudança é o próprio corpo, não vale
            return
        r = self.banheiro.classificar(cid, frame, recorte)
        if r is None:
            return
        rot, _ = r
        antes = self.estado_banheiro.get(cid)
        if rot == "desconhecido" or rot == antes:
            return
        self.estado_banheiro[cid] = rot
        if antes is None:  # primeira leitura depois de ligar: só anota o estado
            return
        if rot == "limpo":  # alguém limpou: o aviso da tela Início volta a "limpo"
            self.db.evento_banheiro({"camera_id": cid, "tipo": "limpo", "visto_em": agora()})
            if self.notificador and self.notificador.ativo:
                try:
                    self.notificador.enviar("Tapete limpo", f"Visto no {nome} às {datetime.now():%H:%M}", None, f"limpo-{int(time.time())}")
                except Exception as e:
                    print(f"  aviso: {e}", flush=True)
            return
        pet = None
        for pid, ref in self.ultimo.items():  # quem estava por ali nos últimos 15 minutos
            if ref.get("camera") == cid and time.time() - ref["ts"] < 900:
                pet = next((x for x in self.pets if x["id"] == pid), None)
        foto = f"avistamentos/{datetime.now():%Y/%m/%d}/banheiro-{cid[:8]}-{datetime.now():%H%M%S}.jpg"
        self.db.enviar_foto(foto, _jpeg(self.proteger(frame, cid), self.cfg["largura_foto"]))
        self.db.evento_banheiro({"camera_id": cid, "tipo": rot, "pet_id": pet["id"] if pet else None, "snapshot_path": foto, "visto_em": agora()})
        print(f"  {nome}: {rot}{' (' + pet['nome'] + ')' if pet else ''}", flush=True)
        if self.notificador and self.notificador.ativo:  # sempre avisa: xixi/cocô novo no banheiro
            algo = "xixi" if rot == "xixi" else "cocô"
            titulo = f"{pet['nome']} fez {algo}" if pet else f"As cachorras fizeram {algo}"
            try:
                self.notificador.enviar(titulo, f"Visto no {nome} às {datetime.now():%H:%M}", self.db.url_assinada(foto), f"banheiro-{int(time.time())}")
            except Exception as e:
                print(f"  aviso: {e}", flush=True)

    def ensinar_banheiro(self, camera_id: str, rotulo: str) -> str:
        """Pedido do app ("coco no Banheiro"): a foto de agora vira exemplo de limpo/xixi/coco."""
        alvo = next(((c, reg) for c, reg in self.cameras if reg["id"] == camera_id), None)
        if not alvo:
            return "câmera não encontrada"
        cfg_cam, reg = alvo
        frame = capture.capturar(cfg_cam)
        caminho = self.banheiro.ensinar(camera_id, rotulo, self.proteger(frame, camera_id), lambda f: _jpeg(f, self.cfg["largura_foto"]))
        self.db.evento_banheiro({"camera_id": camera_id, "tipo": rotulo, "snapshot_path": caminho, "visto_em": agora()})  # o estado atual do tapete aparece nos avisos
        self.estado_banheiro[camera_id] = rotulo  # o que já está lá não conta como evento novo
        c = self.banheiro.cache.get(camera_id) or {}
        n = {r: sum(1 for x, _ in c.get("exemplos", []) if x == r) for r in ("limpo", "xixi", "coco")}
        falta = " Falta ensinar 'limpo' (tapete limpo) para eu poder comparar." if c.get("base") is None else ""
        return f"Aprendi '{rotulo}' em {reg['nome']}. Exemplos: {n['limpo']} limpo, {n['xixi']} xixi, {n['coco']} coco.{falta}"

    def identificar(self, pet_id: str, camera_id: str) -> str:
        """Pedido por texto no site ("Mavi na Sala"): tira a foto de agora, marca o pet no animal achado e aprende com ela."""
        pet = next((x for x in self.pets if x["id"] == pet_id), None) or self.db.pet_por_id(pet_id)
        alvo = next(((c, reg) for c, reg in self.cameras if reg["id"] == camera_id), None)
        if not pet or not alvo:
            return "pet ou câmera não encontrados"
        cfg_cam, reg = alvo
        try:
            frame = capture.capturar(cfg_cam)
        except Exception as e:
            return f"não consegui abrir a câmera {reg['nome']}: {e}"
        h, w = frame.shape[:2]
        dets = [d for d in self.detector.detectar(frame) if d.especie != "pessoa"]
        fortes = [d for d in dets if not d.fraca]
        dets = fortes or dets
        if not dets:  # segunda chance: aceita até palpite fraco (bicho deitado, escuro, atrás de cobertor)
            antiga = self.detector.confianca
            self.detector.confianca = 0.08
            try:
                dets = [d for d in self.detector.detectar(frame) if d.especie != "pessoa"]
            finally:
                self.detector.confianca = antiga
        if not dets:
            foto = f"avistamentos/{datetime.now():%Y/%m/%d}/{camera_id[:8]}-{datetime.now():%H%M%S}.jpg"
            self.db.enviar_foto(foto, _jpeg(self.proteger(frame, camera_id), self.cfg["largura_foto"]))
            self.db.avistamento({"camera_id": camera_id, "confianca": 0, "identificacao": "manual", "pet_id": None, "pessoa_id": None, "especie": pet.get("especie") or "cachorro", "snapshot_path": foto})
            return (f"Não consegui enxergar {pet['nome']} sozinho em {reg['nome']}. Guardei a foto no Histórico: abra, toque em Marcar quem é, "
                    f"desenhe um quadrado em volta dela e escolha {pet['nome']}. Assim eu aprendo e atualizo a posição.")
        area = lambda d: (d.caixa[2] - d.caixa[0]) * (d.caixa[3] - d.caixa[1])
        if len(dets) > 1 and pet.get("porte") == "grande":
            d = max(dets, key=area)
        elif len(dets) > 1 and pet.get("porte") == "pequeno":
            d = min(dets, key=area)
        else:
            d = max(dets, key=lambda x: x.confianca)
        x1, y1, x2, y2 = d.caixa
        box = {"x": round(x1 / w, 4), "y": round(y1 / h, 4), "w": round((x2 - x1) / w, 4), "h": round((y2 - y1) / h, 4)}
        foto = f"avistamentos/{datetime.now():%Y/%m/%d}/{camera_id[:8]}-{datetime.now():%H%M%S}.jpg"
        self.db.enviar_foto(foto, _jpeg(_anotar(self.proteger(frame, camera_id), [(d.caixa, pet["nome"])]), self.cfg["largura_foto"]))
        self.db.avistamento({"camera_id": camera_id, "confianca": 1, **box, "identificacao": "manual", "pet_id": pet_id, "pessoa_id": None, "especie": pet.get("especie") or d.especie, "snapshot_path": foto})
        agora_s = agora()
        self.db.ultima_posicao({"camera_id": camera_id, "confianca": 1, **box, "pet_id": pet_id, "visto_em": agora_s, "snapshot_path": foto, "foto_em": agora_s})
        self.db.correcao({"camera_id": camera_id, "snapshot_path": foto, **box, "pet_id": pet_id})  # vira amostra de aprendizado
        self.ultimo[pet_id] = {"camera": camera_id, "ts": time.time(), "foto": foto, "foto_em": agora_s, "caixa": d.caixa}
        self.db.status_camera(camera_id, True)
        extra = f" (havia {len(dets)} animais; usei o de porte {pet.get('porte') or 'maior confiança'})" if len(dets) > 1 else ""
        return f"{pet['nome']} marcada(o) em {reg['nome']}{extra}"

    def avisar(self, p, camera: str, foto: str | None):
        """Aviso no celular quando um pet/pessoa marcado com 'Avisar' é encontrado num lugar novo (ou quando você pede 'Onde estão agora?')."""
        if not self.notificador or not self.notificador.ativo:
            return
        pet = next((x for x in self.pets if x["id"] == p.pet_id), None) if p.pet_id else None
        if pet and pet.get("notificar"):
            quem, id_ = pet["nome"], pet["id"]
        elif p.pessoa_id and self.nomes_notificar.get(p.pessoa_id):
            quem, id_ = p.nome, p.pessoa_id
        else:
            return
        try:
            imagem = self.db.url_assinada(foto) if foto else None
            self.notificador.enviar(f"{quem} foi encontrado(a)", f"Visto(a) em {camera}", imagem, f"achado-{id_}")
        except Exception as e:
            print(f"  aviso: {e}", flush=True)

    def presenca(self, cid: str, n: int, ref: dict | None, quem: str = ""):
        """Quantas pessoas há agora em cada câmera (para a tela Início). Só grava quando muda ou a cada 60 s com gente presente."""
        antes, ts, quem_antes = self.estado_presenca.get(cid, (0, 0.0, ""))
        agora_ts = time.time()
        if n == antes and quem == quem_antes and (n == 0 or agora_ts - ts < 60):
            return
        self.estado_presenca[cid] = (n, agora_ts, quem)
        linha = {"camera_id": cid, "pessoas": n, "quem": quem or None}
        if n:
            linha["ultima_vez"] = agora()
            if ref:
                linha["snapshot_path"] = ref["foto"]
                linha["foto_em"] = ref["foto_em"]
        try:
            self.db.presenca(linha)
        except Exception as e:
            print(f"  presença {cid[:6]}: {e}", flush=True)

    def todas(self, forcar: bool = False) -> list[str]:
        if forcar:  # pedido "onde estão agora?": grava foto nova de cada cão visto, mesmo sem ter mudado de câmera
            self.ultimo.clear()
            self.ultimo_quadro.clear()
        self.atualizar_nomes()
        self.carregar_zonas()
        saida = []
        for c, r in self.cameras:
            try:
                saida.append(self.uma_camera(c, r))
            except Exception as e:  # um erro numa câmera (ex.: banco recusou) não pode parar as outras
                saida.append(f"{r['nome']}: ERRO {e}")
        return saida

    def fotos_agora(self, apenas: set[str] | None = None) -> int:
        """Uma foto nova de cada câmera, em paralelo (botão 'Ver ao vivo' do site). Guarda a hora em foto_em."""

        def um(par):
            c, reg = par
            if reg.get("ativo") is False or (apenas is not None and reg["id"] not in apenas):
                return 0
            try:
                caminho = f"ao-vivo/{reg['id']}.jpg"
                self.db.enviar_foto(caminho, _jpeg(self.proteger(capture.capturar(c), reg["id"]), self.cfg["largura_foto"]))
                self.db.status_camera(reg["id"], True, quadro_path=caminho)
                return 1
            except Exception as e:
                self.db.status_camera(reg["id"], False, str(e))
                print(f"  foto {reg['nome']}: {e}", flush=True)
                return 0

        with ThreadPoolExecutor(max_workers=max(1, min(8, len(self.cameras)))) as ex:
            return sum(ex.map(um, self.cameras))
