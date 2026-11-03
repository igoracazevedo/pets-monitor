"""Manutenção das fotos já guardadas no Supabase: desfoca o corpo das pessoas (rosto nítido) e compacta (menor e mais leve).
Guarda no PC (manutencao.json) o que já foi feito, então cada foto é tratada uma vez só."""
import json
import time
from pathlib import Path

import cv2
import numpy as np
import requests

ARQ = Path(__file__).resolve().parent.parent / "manutencao.json"
PASTAS = ("avistamentos", "ao-vivo", "cameras")


def _feitas() -> dict:
    try:
        return json.loads(ARQ.read_text(encoding="utf-8"))
    except Exception:
        return {}


def listar(db, prefixo: str = "") -> list[str]:
    """Todos os arquivos do bucket (desce nas pastas)."""
    achados: list[str] = []
    pilha = [prefixo]
    while pilha:
        pre = pilha.pop()
        off = 0
        while True:
            r = requests.post(
                f"{db.url}/storage/v1/object/list/pm-snapshots",
                json={"prefix": pre, "limit": 1000, "offset": off, "sortBy": {"column": "name", "order": "asc"}},
                headers=db.h,
                timeout=30,
            )
            r.raise_for_status()
            itens = r.json()
            for it in itens:
                caminho = f"{pre}/{it['name']}" if pre else it["name"]
                if it.get("id") is None:
                    pilha.append(caminho)
                elif caminho.lower().endswith((".jpg", ".jpeg")):
                    achados.append(caminho)
            if len(itens) < 1000:
                break
            off += 1000
    return achados


def pendentes(db) -> list[str]:
    feitas = _feitas()
    return [c for c in listar(db) if c not in feitas and c.split("/")[0] in PASTAS]


def tratar(v, caminho: str) -> str:
    """Baixa, protege, compacta e (se valer a pena) sobe de volta. Devolve o que foi feito."""
    bruto = v.db.baixar_snapshot(caminho)
    img = cv2.imdecode(np.frombuffer(bruto, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return "ilegível"
    from .varredura import _jpeg

    caixas = v.detector.pessoas_na_imagem(img) if v.cfg.get("proteger_pessoas", True) and hasattr(v.detector, "pessoas_na_imagem") else []
    if caixas:
        img = v.proteger(img)
    novo = _jpeg(img, min(v.cfg["largura_foto"], 960))
    if caixas or len(novo) < len(bruto) * 0.9:
        v.db.enviar_foto(caminho, novo)
        return f"{'pessoa protegida, ' if caixas else ''}{len(bruto) // 1024} KB → {len(novo) // 1024} KB"
    return "já estava leve"


def rodar(v, limite: int | None = None, lista: list[str] | None = None, mostrar=print) -> tuple[int, int]:
    """Trata até `limite` fotos pendentes. Devolve (tratadas, que ainda faltam)."""
    feitas = _feitas()
    fila = lista if lista is not None else pendentes(v.db)
    n = 0
    for c in list(fila):
        if limite is not None and n >= limite:
            break
        try:
            r = tratar(v, c)
            feitas[c] = int(time.time())
            mostrar(f"[manutenção] {c}: {r}")
        except Exception as e:
            mostrar(f"[manutenção] {c}: erro ({e}) — tento de novo depois")
            continue
        fila.remove(c)
        n += 1
        if n % 10 == 0:
            ARQ.write_text(json.dumps(feitas), encoding="utf-8")
    ARQ.write_text(json.dumps(feitas), encoding="utf-8")
    return n, len(fila)
