import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv

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
    cfg.setdefault("intervalo_s", 15)
    cfg.setdefault("historico_a_cada_s", 300)
    cfg.setdefault("quadro_da_camera_a_cada_s", 60)
    cfg.setdefault("largura_foto", 960)
    cfg.setdefault("deteccao", {})
    cfg["deteccao"].setdefault("modelo", "yolov8n.pt")
    cfg["deteccao"].setdefault("confianca_minima", 0.35)
    cfg["deteccao"].setdefault("tamanho", 640)
    cfg.setdefault("identificacao", {})
    cfg["identificacao"].setdefault("pontuacao_minima", 0.55)
    cfg["identificacao"].setdefault("margem_minima", 0.05)
    return cfg
