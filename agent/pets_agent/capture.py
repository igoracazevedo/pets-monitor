import os
from urllib.parse import quote

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


def url_nvr(cam: dict) -> str:
    """NVR Intelbras/Dahua: um IP, vários canais. Usuário e senha entram no .env e são codificados aqui (senha com @, # etc. funciona)."""
    usuario, senha, ip = (os.environ.get(k, "") for k in ("NVR_USUARIO", "NVR_SENHA", "NVR_IP"))
    if not (usuario and senha and ip):
        raise RuntimeError("defina NVR_IP, NVR_USUARIO e NVR_SENHA no .env")
    porta = os.environ.get("NVR_PORTA", "554")
    return f"rtsp://{quote(usuario, safe='')}:{quote(senha, safe='')}@{ip}:{porta}/cam/realmonitor?channel={int(cam['canal'])}&subtype={int(cam.get('subtipo', 1))}"


def capturar(cam: dict) -> np.ndarray:
    """Um quadro da câmera (BGR). `fonte`: rtsp | http | arquivo."""
    fonte = cam.get("fonte", "rtsp")
    if fonte == "rtsp":
        return _rtsp(cam["url"])
    if fonte == "nvr":
        return _rtsp(url_nvr(cam))
    if fonte == "http":
        return _http(cam["url"], cam.get("usuario"), cam.get("senha"))
    if fonte == "arquivo":
        img = cv2.imread(cam["caminho"])
        if img is None:
            raise RuntimeError(f"não abri {cam['caminho']}")
        return img
    raise RuntimeError(f"fonte desconhecida: {fonte}")
