import os

import cv2
import numpy as np
import requests

# RTSP por TCP é mais estável em Wi-Fi; tempo limite de 5 s para não travar a varredura
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;5000000")


def _rtsp(url: str, descartar: int = 5) -> np.ndarray:
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    try:
        if not cap.isOpened():
            raise RuntimeError("não conectou (confira IP, usuário/senha e se o RTSP está ativado na câmera)")
        for _ in range(descartar):  # descarta quadros velhos do buffer
            cap.grab()
        ok, frame = cap.read()
        if not ok or frame is None:
            raise RuntimeError("conectou, mas não veio imagem")
        return frame
    finally:
        cap.release()


def _http(url: str, usuario: str | None, senha: str | None) -> np.ndarray:
    auth = (usuario, senha) if usuario else None
    r = requests.get(url, auth=auth, timeout=8)
    r.raise_for_status()
    img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError("a resposta HTTP não é uma imagem")
    return img


def capturar(cam: dict) -> np.ndarray:
    """Um quadro da câmera (BGR). `fonte`: rtsp | http | arquivo."""
    fonte = cam.get("fonte", "rtsp")
    if fonte == "rtsp":
        return _rtsp(cam["url"])
    if fonte == "http":
        return _http(cam["url"], cam.get("usuario"), cam.get("senha"))
    if fonte == "arquivo":
        img = cv2.imread(cam["caminho"])
        if img is None:
            raise RuntimeError(f"não abri {cam['caminho']}")
        return img
    raise RuntimeError(f"fonte desconhecida: {fonte}")
