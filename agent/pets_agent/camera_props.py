"""Lê o camera.properties (mesmo arquivo do outro app) e converte nas câmeras do agente."""
import re
from pathlib import Path
from urllib.parse import quote


def _ler(arquivo: Path) -> dict[int, dict[str, str]]:
    cams: dict[int, dict[str, str]] = {}
    for linha in arquivo.read_text(encoding="utf-8-sig").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        m = re.fullmatch(r"camera\.(\d+)\.(\w+)", chave.strip())
        if m:
            cams.setdefault(int(m.group(1)), {})[m.group(2)] = valor.strip()
    return cams


def carregar_cameras(arquivo: str | Path) -> list[dict]:
    """Câmera sem senha (intelbras) ou sem endereço (rtsp) fica de fora, como no outro app. A ordem do arquivo é mantida."""
    arquivo = Path(arquivo)
    if not arquivo.exists():
        raise SystemExit(f"Não achei {arquivo}. Copie o camera.properties do outro app para a pasta do agente.")
    out = []
    for n, c in sorted(_ler(arquivo).items()):
        nome = c.get("nome") or f"Câmera {n}"
        tipo = (c.get("tipo") or "intelbras").lower()
        usuario, senha = c.get("usuario", ""), c.get("senha", "")
        if tipo == "intelbras":
            if not c.get("host") or not senha:
                continue
            out.append({"nome": nome, "ambiente": nome, "fonte": "intelbras", "host": c["host"], "usuario": usuario or "admin", "senha": senha})
        elif tipo == "foto":  # câmera que entrega foto JPEG por HTTP (endereço que o `sondar --onvif` mostra)
            if not c.get("foto"):
                continue
            out.append({"nome": nome, "ambiente": nome, "fonte": "http", "url": c["foto"], "usuario": usuario, "senha": senha})
        elif tipo == "rtsp":
            url = c.get("rtsp", "")
            if not url:
                continue
            if usuario and "@" not in url:  # coloca o login na URL (codificado)
                url = url.replace("rtsp://", f"rtsp://{quote(usuario, safe='')}:{quote(senha, safe='')}@", 1)
            # câmera que "trava se reconectar a cada foto": mantém a conexão aberta
            # continuo=nao: conecta só na hora da foto (NVR aguenta; poupa o processador do PC)
            fonte = "rtsp" if (c.get("continuo", "sim").strip().lower() in ("nao", "não", "n", "0", "false")) else "rtsp_continuo"
            out.append({"nome": nome, "ambiente": nome, "fonte": fonte, "url": url})
    return out
