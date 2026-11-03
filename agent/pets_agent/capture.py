import os
import threading
import time
from urllib.parse import quote

import cv2
import numpy as np
import requests

# RTSP por TCP é mais estável em Wi-Fi; tempo limite de 5 s para não travar a varredura
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|timeout;5000000|stimeout;5000000")


# câmera fora do ar não pode segurar a varredura por 30 s: 5 s para conectar e 8 s para ler
_LIMITES = [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 8000]
# câmera que mantém a conexão aberta (Mercusys etc.) demora mais para entregar o primeiro quadro
_LIMITES_LONGOS = [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 20000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 20000]


def _rtsp(url: str, descartar: int = 5) -> np.ndarray:
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG, _LIMITES)
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
    r = requests.get(url, auth=auth, timeout=(4, 8))
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


def _snapshot_intelbras(cam: dict) -> np.ndarray:
    """Foto por HTTP (padrão Dahua/Intelbras), com login Digest e, se a câmera preferir, Basic."""
    from requests.auth import HTTPBasicAuth, HTTPDigestAuth

    url = f"http://{cam['host']}/cgi-bin/snapshot.cgi"
    ultimo = None
    for auth in (HTTPDigestAuth(cam["usuario"], cam["senha"]), HTTPBasicAuth(cam["usuario"], cam["senha"])):
        try:
            r = requests.get(url, auth=auth, timeout=(4, 8))
            if r.ok and r.content[:2] == b"\xff\xd8":
                img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
                if img is not None:
                    return img
            ultimo = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            ultimo = str(e)[:300]
    raise RuntimeError(ultimo or "sem resposta")


def _intelbras(cam: dict) -> np.ndarray:
    try:
        return _snapshot_intelbras(cam)
    except Exception as e_http:
        url = f"rtsp://{quote(cam['usuario'], safe='')}:{quote(cam['senha'], safe='')}@{cam['host']}:554/cam/realmonitor?channel=1&subtype=1"
        try:
            return _rtsp(url)
        except Exception as e_rtsp:
            raise RuntimeError(f"foto HTTP falhou ({e_http}); RTSP falhou ({e_rtsp})")


class _Fluxo(threading.Thread):
    """Mantém uma câmera RTSP conectada o tempo todo e guarda só o quadro mais recente."""

    def __init__(self, url: str):
        super().__init__(daemon=True)
        self.url, self.quadro, self.ts, self.erro = url, None, 0.0, "conectando"
        self.start()

    def run(self):
        while True:
            cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG, _LIMITES_LONGOS)
            if not cap.isOpened():
                self.erro = "não conectou (confira IP, porta, usuário/senha da 'Conta da câmera' e o caminho RTSP)"
                time.sleep(5)
                continue
            falhas = 0
            while falhas < 30:
                ok, frame = cap.read()
                if ok and frame is not None:
                    self.quadro, self.ts, self.erro, falhas = frame, time.time(), None, 0
                else:
                    falhas += 1
                    time.sleep(0.2)
            cap.release()
            self.erro = "conexão perdida; reconectando"


_fluxos: dict[str, _Fluxo] = {}


def _continuo(url: str) -> np.ndarray:
    f = _fluxos.get(url) or _fluxos.setdefault(url, _Fluxo(url))
    for _ in range(125):  # até ~25 s para o primeiro quadro (a conexão fica aberta; as próximas voltas são instantâneas)
        if f.quadro is not None:
            break
        time.sleep(0.2)
    if f.quadro is None or time.time() - f.ts > 20:
        raise RuntimeError(f.erro or "sem imagem recente")
    return f.quadro.copy()


def capturar(cam: dict) -> np.ndarray:
    """Um quadro da câmera (BGR). `fonte`: rtsp | http | arquivo."""
    fonte = cam.get("fonte", "rtsp")
    if fonte == "rtsp":
        return _rtsp(cam["url"])
    if fonte == "intelbras":
        return _intelbras(cam)
    if fonte == "rtsp_continuo":
        return _continuo(cam["url"])
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
