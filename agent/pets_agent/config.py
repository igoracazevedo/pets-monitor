import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .camera_props import carregar_cameras

RAIZ = Path(__file__).resolve().parent.parent


def _expandir(valor):
    """Troca ${NOME} pelo valor da variável de ambiente (em qualquer nível do YAML)."""
    if isinstance(valor, str):
        def sub(m):
            v = os.environ.get(m.group(1))
            if v is None:
                raise SystemExit(f"Variável {m.group(1)} não está definida no .env")
            return v

        return re.sub(r"\$\{(\w+)\}", sub, valor)
    if isinstance(valor, list):
        return [_expandir(v) for v in valor]
    if isinstance(valor, dict):
        return {k: _expandir(v) for k, v in valor.items()}
    return valor


def carregar(caminho: str | None = None) -> dict:
    load_dotenv(RAIZ / ".env")
    arq = Path(caminho) if caminho else RAIZ / "config.yaml"
    if not arq.exists():
        raise SystemExit(f"Não achei {arq}. Copie config.example.yaml para config.yaml e ajuste.")
    cfg = _expandir(yaml.safe_load(arq.read_text(encoding="utf-8")))
    # câmeras podem vir do camera.properties (o mesmo arquivo do outro app) em vez de listadas no YAML
    arq_cam = cfg.get("cameras_arquivo") or ("camera.properties" if not cfg.get("cameras") and (RAIZ / "camera.properties").exists() else None)
    if arq_cam:
        p = Path(arq_cam)
        cfg["cameras"] = carregar_cameras(p if p.is_absolute() else (arq.parent / p if (arq.parent / p).exists() else RAIZ / p))
    cfg.setdefault("cameras", [])
    if cfg.get("descobrir_rede"):  # as Intelbras são achadas pela rede; do arquivo só sai o login delas
        intel = [c for c in cfg["cameras"] if c.get("fonte") == "intelbras"]
        if not intel:
            raise SystemExit("descobrir_rede: o camera.properties precisa ter ao menos uma câmera 'intelbras' com usuário e senha.")
        cfg["credencial_intelbras"] = {"usuario": intel[0]["usuario"], "senha": intel[0]["senha"]}
        cfg["cameras"] = [c for c in cfg["cameras"] if c.get("fonte") != "intelbras"]
    cfg.setdefault("intervalo_s", 15)
    cfg.setdefault("historico_a_cada_s", 300)
    cfg.setdefault("quadro_da_camera_a_cada_s", 60)
    cfg.setdefault("largura_foto", 960)
    cfg.setdefault("deteccao", {})
    cfg["deteccao"].setdefault("modelo", "yolov8s.pt")
    cfg["deteccao"].setdefault("confianca_minima", 0.25)
    cfg["deteccao"].setdefault("tamanho", 960)
    cfg.setdefault("identificacao", {})
    cfg["identificacao"].setdefault("pontuacao_minima", 0.55)
    cfg["identificacao"].setdefault("margem_minima", 0.05)
    return cfg
