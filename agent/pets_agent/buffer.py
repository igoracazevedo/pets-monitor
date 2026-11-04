"""Guarda as imagens das câmeras por algumas horas, só neste PC, para uma segunda leitura em segundo plano.

Fica FORA do OneDrive (as imagens aqui não são protegidas: o corpo das pessoas aparece). Apaga sozinho o que passa de `horas`.
Nome do arquivo = hora da imagem; terminar em 'r' = já foi lida.
"""
import os
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from . import capture


def pasta_padrao() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "pets-monitor" / "buffer"


class Buffer:
    def __init__(self, pasta: Path | None = None, horas: float = 12, max_mb: int = 2000, largura: int = 960):
        self.pasta = Path(pasta) if pasta else pasta_padrao()
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.horas, self.max_mb, self.largura = horas, max_mb, largura
        self.trava = threading.Lock()

    @staticmethod
    def _hora(p: Path) -> float:
        return datetime.strptime(p.stem[:15], "%Y%m%d-%H%M%S").timestamp()

    def salvar(self, cid: str, frame: np.ndarray, ts: float | None = None, revisado: bool = False) -> Path | None:
        ts = ts or time.time()
        h, w = frame.shape[:2]
        if w > self.largura:
            frame = cv2.resize(frame, (self.largura, int(h * self.largura / w)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if not ok:
            return None
        d = self.pasta / cid
        d.mkdir(exist_ok=True)
        p = d / f"{datetime.fromtimestamp(ts):%Y%m%d-%H%M%S}{'r' if revisado else ''}.jpg"
        p.write_bytes(buf.tobytes())
        return p

    def pendentes(self, limite: int) -> list[tuple[str, Path, float]]:
        """As imagens ainda não lidas, da mais antiga para a mais nova (todas as câmeras juntas)."""
        achadas = []
        for d in self.pasta.iterdir():
            if not d.is_dir():
                continue
            nomes = sorted(f for f in os.listdir(d) if f.endswith(".jpg") and not f.endswith("r.jpg"))[:limite]
            for n in nomes:
                try:
                    achadas.append((d.name, d / n, self._hora(d / n)))
                except ValueError:
                    pass
        return sorted(achadas, key=lambda t: t[2])[:limite]

    def marcar(self, caminho: Path):
        try:
            os.replace(caminho, caminho.with_name(caminho.stem + "r.jpg"))
        except OSError:
            pass

    def limpar(self) -> int:
        """Apaga o que passou do prazo e, se a pasta passar do limite, as mais antigas."""
        corte = time.time() - self.horas * 3600
        todas = []
        for d in self.pasta.iterdir():
            if d.is_dir():
                for f in d.iterdir():
                    try:
                        todas.append((self._hora(f), f, f.stat().st_size))
                    except (ValueError, OSError):
                        pass
        apagadas = 0
        total = sum(t[2] for t in todas)
        for ts, f, tam in sorted(todas):
            if ts < corte or total > self.max_mb * 1024 * 1024:
                try:
                    f.unlink()
                    total -= tam
                    apagadas += 1
                except OSError:
                    pass
        return apagadas


class CapturaRapida(threading.Thread):
    """Tira uma imagem a cada `intervalo` s das câmeras que vigiam eventos (banheiro, bebedouro, comedouro), sem esperar a varredura."""

    def __init__(self, v, intervalo: float = 30):
        super().__init__(name="captura-rapida", daemon=True)
        self.v, self.intervalo = v, intervalo

    def run(self):
        falhas: dict[str, tuple[int, float]] = {}
        while True:
            ini = time.time()
            for cfg_cam, reg in list(self.v.cameras):
                cid = reg["id"]
                n, ate = falhas.get(cid, (0, 0.0))
                if reg.get("ativo") is False or time.time() < ate:
                    continue
                try:
                    if not self.v.camera_rapida(cid, reg["nome"]):
                        continue
                    self.v.buffer.salvar(cid, capture.capturar(cfg_cam))
                    falhas.pop(cid, None)
                except Exception:
                    falhas[cid] = (n + 1, time.time() + min(300, 20 * 2**n))
            time.sleep(max(1.0, self.intervalo - (time.time() - ini)))
