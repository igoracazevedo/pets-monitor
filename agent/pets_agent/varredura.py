import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import cv2
import numpy as np

from . import capture
from .identify import Identificador, caracteristica
from .noturno import MemoriaTamanhos, area_relativa, eh_noturno, por_tamanho
from .store import Supabase, agora


def slug(nome: str) -> str:
    """Nome de câmera vira nome de arquivo seguro (sem acento, espaço ou símbolo)."""
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower() or "camera"


def _jpeg(frame: np.ndarray, largura: int) -> bytes:
    h, w = frame.shape[:2]
    if w > largura:
        frame = cv2.resize(frame, (largura, int(h * largura / w)))
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return buf.tobytes()


def _anotar(frame: np.ndarray, marcas: list[tuple[tuple[int, int, int, int], str]]) -> np.ndarray:
    img = frame.copy()
    for (x1, y1, x2, y2), texto in marcas:
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 98, 255), 3)
        cv2.putText(img, texto, (x1 + 4, max(24, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 98, 255), 2, cv2.LINE_AA)
    return img


class Varredura:
    def __init__(self, cfg: dict, db: Supabase, detector):
        self.cfg = cfg
        self.db = db
        self.detector = detector
        self.pets = db.pets()
        self.ident = Identificador(self.pets, cfg["identificacao"]["pontuacao_minima"], cfg["identificacao"]["margem_minima"])
        self.fixas = []
        for i, c in enumerate(cfg["cameras"]):
            self.fixas.append((c, db.garantir_camera(c["nome"], c.get("ambiente"), i)))
        self.cameras = list(self.fixas)
        # câmeras Intelbras achadas na rede (pelo número de série); o apelido vem do app
        self.cred = cfg.get("credencial_intelbras")
        self.achadas: dict[str, tuple[dict, dict]] = {}
        self.ignorados: set[str] = set()
        self.relatado: set[str] = set()
        self.ultima_descoberta = 0.0
        self.ultimo_nomes = 0.0
        # estado em memória: onde cada pet foi visto por último (para não encher o histórico)
        self.ultimo: dict[str, dict] = {}
        self.tamanhos = MemoriaTamanhos(cfg.get("arquivo_tamanhos", "tamanhos.json"))
        self.ultimo_quadro: dict[str, float] = {}
        self.falhas: dict[str, tuple[int, float]] = {}  # câmera -> (falhas seguidas, só tenta de novo depois de)

    def recarregar_pets(self):
        self.pets = self.db.pets()
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

    def atualizar_nomes(self):
        """Pega do banco o apelido e o liga/desliga de cada câmera (você muda no app)."""
        if time.time() - self.ultimo_nomes < 60:
            return
        self.ultimo_nomes = time.time()
        try:
            atuais = {c["id"]: c for c in self.db.cameras()}
        except Exception:
            return
        self.cameras = [(c, {**reg, **{k: atuais[reg["id"]].get(k, reg.get(k)) for k in ("nome", "ativo")}} if reg["id"] in atuais else reg) for c, reg in self.cameras]

    def analisar(self, frame, cid: str, aprender: bool = True):
        """Acha cães/gatos no quadro e diz quem é cada um: pela cor de dia; pelo tamanho no infravermelho.
        Detecção duvidosa (ex.: "urso de pelúcia" = spitz pequeno) só vale de dia e se a cor bater com um pet."""
        noite = eh_noturno(frame)
        dets = [d for d in self.detector.detectar(frame) if not (noite and d.fraca)]
        if dets and noite:  # infravermelho: sem cor, decide pelo tamanho
            return dets, por_tamanho([d.caixa for d in dets], frame.shape, cid, self.pets, self.tamanhos)
        usados: set[str] = set()
        dets_ok, palpites = [], []
        for d in dets:
            p = self.ident.palpite(caracteristica(frame, d.caixa), usados)
            if d.fraca and not (p.pet_id and p.pontuacao >= 0.6):
                continue  # brinquedo ou coisa parecida
            if p.pet_id:
                usados.add(p.pet_id)  # um pet aparece uma vez por quadro
                if aprender and p.como == "cor" and len(self.pets) > 1:  # aprende o tamanho dele nesta câmera para usar à noite
                    self.tamanhos.atualizar(cid, p.pet_id, area_relativa(d.caixa, frame.shape))
            dets_ok.append(d)
            palpites.append(p)
        return dets_ok, palpites

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
        dets, palpites = self.analisar(frame, cid)
        marcas, achados = [], []
        for d, p in zip(dets, palpites):
            achados.append((d, p))
            marcas.append((d.caixa, p.nome or "?"))

        agora_ts = time.time()
        quadro_path = None
        if agora_ts - self.ultimo_quadro.get(cid, 0) >= self.cfg["quadro_da_camera_a_cada_s"]:
            quadro_path = f"cameras/{cid}.jpg"
            self.db.enviar_foto(quadro_path, _jpeg(_anotar(frame, marcas), self.cfg["largura_foto"]))
            self.ultimo_quadro[cid] = agora_ts
        self.db.status_camera(reg["id"], True, quadro_path=quadro_path)

        foto = None
        for d, p in achados:
            chave = p.pet_id or f"?{cid}"
            x1, y1, x2, y2 = d.caixa
            linha = {
                "camera_id": reg["id"],
                "confianca": round(min(d.confianca, 0.999), 3),
                "identificacao": p.como,
                "x": round(x1 / w, 4), "y": round(y1 / h, 4), "w": round((x2 - x1) / w, 4), "h": round((y2 - y1) / h, 4),
            }
            ant = self.ultimo.get(chave)
            mudou = not ant or ant["camera"] != cid or agora_ts - ant["ts"] >= self.cfg["historico_a_cada_s"]
            if mudou:
                if foto is None:
                    foto = f"avistamentos/{datetime.now():%Y/%m/%d}/{cid[:8]}-{datetime.now():%H%M%S}.jpg"
                    self.db.enviar_foto(foto, _jpeg(_anotar(frame, marcas), self.cfg["largura_foto"]))
                self.db.avistamento({**linha, "pet_id": p.pet_id, "especie": d.especie, "snapshot_path": foto})
                self.ultimo[chave] = {"camera": cid, "ts": agora_ts, "foto": foto}
            else:
                ant["ts"] = ant["ts"]  # mantém a hora do último registro no histórico
            if p.pet_id:
                self.db.ultima_posicao({**linha, "pet_id": p.pet_id, "visto_em": agora(), "snapshot_path": self.ultimo[chave]["foto"]})
        nomes = ", ".join(p.nome or "animal não identificado" for _, p in achados) or "ninguém"
        return f"{nome}: {nomes}"

    def todas(self, forcar: bool = False) -> list[str]:
        if forcar:  # pedido "onde estão agora?": grava foto nova de cada cão visto, mesmo sem ter mudado de câmera
            self.ultimo.clear()
            self.ultimo_quadro.clear()
        self.atualizar_nomes()
        return [self.uma_camera(c, r) for c, r in self.cameras]

    def fotos_agora(self) -> int:
        """Uma foto nova de cada câmera, em paralelo (botão 'Ver ao vivo' do site). Guarda a hora em foto_em."""

        def um(par):
            c, reg = par
            if reg.get("ativo") is False:
                return 0
            try:
                caminho = f"ao-vivo/{reg['id']}.jpg"
                self.db.enviar_foto(caminho, _jpeg(capture.capturar(c), self.cfg["largura_foto"]))
                self.db.status_camera(reg["id"], True, quadro_path=caminho)
                return 1
            except Exception as e:
                self.db.status_camera(reg["id"], False, str(e))
                print(f"  foto {reg['nome']}: {e}", flush=True)
                return 0

        with ThreadPoolExecutor(max_workers=max(1, min(8, len(self.cameras)))) as ex:
            return sum(ex.map(um, self.cameras))
