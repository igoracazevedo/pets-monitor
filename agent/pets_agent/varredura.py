import time
from datetime import datetime

import cv2
import numpy as np

from . import capture
from .identify import Identificador, caracteristica
from .store import Supabase, agora


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
        self.cameras = []
        for i, c in enumerate(cfg["cameras"]):
            reg = db.garantir_camera(c["nome"], c.get("ambiente"), i)
            self.cameras.append((c, reg))
        # estado em memória: onde cada pet foi visto por último (para não encher o histórico)
        self.ultimo: dict[str, dict] = {}
        self.ultimo_quadro: dict[str, float] = {}

    def uma_camera(self, cfg_cam: dict, reg: dict) -> str:
        nome = cfg_cam["nome"]
        try:
            frame = capture.capturar(cfg_cam)
        except Exception as e:  # câmera fora do ar não derruba as outras
            self.db.status_camera(reg["id"], False, str(e))
            return f"{nome}: ERRO {e}"

        h, w = frame.shape[:2]
        dets = self.detector.detectar(frame)
        usados: set[str] = set()
        marcas, achados = [], []
        for d in dets:
            feat = caracteristica(frame, d.caixa)
            p = self.ident.palpite(feat, usados)
            if p.pet_id:
                usados.add(p.pet_id)  # um pet aparece uma vez por quadro
            achados.append((d, p))
            marcas.append((d.caixa, p.nome or "?"))

        agora_ts = time.time()
        quadro_path = None
        if agora_ts - self.ultimo_quadro.get(nome, 0) >= self.cfg["quadro_da_camera_a_cada_s"]:
            quadro_path = f"cameras/{nome}.jpg"
            self.db.enviar_foto(quadro_path, _jpeg(_anotar(frame, marcas), self.cfg["largura_foto"]))
            self.ultimo_quadro[nome] = agora_ts
        self.db.status_camera(reg["id"], True, quadro_path=quadro_path)

        foto = None
        for d, p in achados:
            chave = p.pet_id or f"?{nome}"
            x1, y1, x2, y2 = d.caixa
            linha = {
                "camera_id": reg["id"],
                "confianca": round(min(d.confianca, 0.999), 3),
                "identificacao": p.como,
                "x": round(x1 / w, 4), "y": round(y1 / h, 4), "w": round((x2 - x1) / w, 4), "h": round((y2 - y1) / h, 4),
            }
            ant = self.ultimo.get(chave)
            mudou = not ant or ant["camera"] != nome or agora_ts - ant["ts"] >= self.cfg["historico_a_cada_s"]
            if mudou:
                if foto is None:
                    foto = f"avistamentos/{datetime.now():%Y/%m/%d}/{nome}-{datetime.now():%H%M%S}.jpg"
                    self.db.enviar_foto(foto, _jpeg(_anotar(frame, marcas), self.cfg["largura_foto"]))
                self.db.avistamento({**linha, "pet_id": p.pet_id, "especie": d.especie, "snapshot_path": foto})
                self.ultimo[chave] = {"camera": nome, "ts": agora_ts, "foto": foto}
            else:
                ant["ts"] = ant["ts"]  # mantém a hora do último registro no histórico
            if p.pet_id:
                self.db.ultima_posicao({**linha, "pet_id": p.pet_id, "visto_em": agora(), "snapshot_path": self.ultimo[chave]["foto"]})
        nomes = ", ".join(p.nome or "animal não identificado" for _, p in achados) or "ninguém"
        return f"{nome}: {nomes}"

    def todas(self) -> list[str]:
        return [self.uma_camera(c, r) for c, r in self.cameras]
