"""Acha as câmeras Intelbras na rede pelo número de série: o IP pode mudar à vontade, o apelido fica no app."""
import platform
import re
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor

import requests
from requests.auth import HTTPDigestAuth


def ip_local() -> str:
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        u.connect(("8.8.8.8", 80))
        return u.getsockname()[0]
    finally:
        u.close()


def porta_aberta(ip: str, porta: int, limite: float = 1.2) -> bool:
    s = socket.socket()
    s.settimeout(limite)
    try:
        s.connect((ip, porta))
        return True
    except Exception:
        return False
    finally:
        s.close()


def candidatos(base: str, excluir: set[str] | None = None) -> list[str]:
    """Aparelhos da rede com a porta 37777 (protocolo Dahua/Intelbras) ou 554 (RTSP) aberta."""
    excluir = excluir or set()
    ips = [f"{base}.{i}" for i in range(1, 255) if f"{base}.{i}" not in excluir]

    def sonda(ip):
        return ip if (porta_aberta(ip, 37777) or porta_aberta(ip, 554)) else None

    with ThreadPoolExecutor(64) as ex:
        return [ip for ip in ex.map(sonda, ips) if ip]


def mac_do_ip(ip: str) -> str | None:
    try:
        cmd = ["arp", "-a", ip] if platform.system() == "Windows" else ["ip", "neigh", "show", ip]
        saida = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
        m = re.search(r"([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}", saida)
        return m.group(0).lower().replace("-", ":") if m else None
    except Exception:
        return None


def _valor(texto: str, chave: str) -> str | None:
    m = re.search(rf"{chave}=([^\r\n]+)", texto)
    return m.group(1).strip() if m else None


def identificar(ip: str, usuario: str, senha: str) -> dict | None:
    """Intelbras responde ao número de série pelo CGI padrão. Retorna None se não for câmera (ou a senha não servir)."""
    base = f"http://{ip}/cgi-bin/magicBox.cgi?action="
    auth = HTTPDigestAuth(usuario, senha)
    try:
        r = requests.get(base + "getSerialNo", auth=auth, timeout=(3, 5))
    except requests.RequestException:
        return None
    if r.status_code == 401:
        return {"ip": ip, "erro_login": True}
    sn = _valor(r.text, "sn") if r.ok else None
    if not sn:
        return None
    tipo = ""
    try:
        tipo = _valor(requests.get(base + "getDeviceType", auth=auth, timeout=(3, 5)).text, "type") or ""
    except requests.RequestException:
        pass
    if re.search(r"NVR|DVR|XVR|HCVR", tipo, re.I):  # gravador não é câmera
        return None
    return {"ip": ip, "identificador": f"sn:{sn}", "modelo": tipo}


def descobrir(base: str, usuario: str, senha: str, excluir: set[str] | None = None, ignorados: set[str] | None = None, relatorio: list[str] | None = None) -> list[dict]:
    """Câmeras Intelbras achadas agora. `ignorados` (preenchido aqui) guarda IPs que recusaram o login: não insiste, para não bloquear."""
    ignorados = ignorados if ignorados is not None else set()
    alvo = [ip for ip in candidatos(base, (excluir or set()) | ignorados)]
    with ThreadPoolExecutor(12) as ex:
        res = list(ex.map(lambda ip: identificar(ip, usuario, senha), alvo))
    achadas = []
    for ip, r in zip(alvo, res):
        if not r:
            if relatorio is not None:
                relatorio.append(f"{ip}: porta de câmera aberta, mas não respondeu como câmera Intelbras (outro aparelho, ou firmware diferente)")
            continue
        if r.get("erro_login"):
            ignorados.add(r["ip"])
            if relatorio is not None:
                relatorio.append(f"{ip}: RECUSOU o login (senha diferente das outras?). Não insisto, para não bloquear a câmera")
            continue
        achadas.append(r)
    return achadas
