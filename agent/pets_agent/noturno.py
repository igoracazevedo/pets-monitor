"""À noite (infravermelho) todo pelo vira cinza: a cor não separa os pets, então decide pelo tamanho."""
import json
import math
from pathlib import Path

import cv2
import numpy as np

from .identify import Palpite

ORDEM_PORTE = {"pequeno": 0, "medio": 1, "grande": 2}


def eh_noturno(frame: np.ndarray, limite: float = 1.0) -> bool:
    """Infravermelho é cinza puro (B = G = R em todo pixel). Diferença média entre canais: noite ~0, dia (mesmo com parede branca) >= 2,8 nos prints das câmeras."""
    p = cv2.resize(frame, (96, 54)).astype(np.int16)
    spread = (np.abs(p[..., 0] - p[..., 1]) + np.abs(p[..., 1] - p[..., 2])) / 2
    return float(spread.mean()) < limite


class MemoriaTamanhos:
    """Quanto cada pet ocupa do quadro em cada câmera (aprendido de dia, quando a cor identifica com segurança)."""

    def __init__(self, arquivo: str | Path | None = None):
        self.arquivo = Path(arquivo) if arquivo else None
        self.dados: dict[str, dict[str, float]] = {}
        if self.arquivo and self.arquivo.exists():
            try:
                self.dados = json.loads(self.arquivo.read_text())
            except Exception:
                self.dados = {}

    def atualizar(self, camera: str, pet_id: str, area: float):
        c = self.dados.setdefault(camera, {})
        c[pet_id] = area if pet_id not in c else 0.9 * c[pet_id] + 0.1 * area  # média móvel
        if self.arquivo:
            try:
                self.arquivo.write_text(json.dumps(self.dados))
            except OSError:
                pass

    def da_camera(self, camera: str) -> dict[str, float]:
        return self.dados.get(camera, {})


def area_relativa(caixa: tuple[int, int, int, int], forma: tuple[int, ...]) -> float:
    x1, y1, x2, y2 = caixa
    h, w = forma[:2]
    return max(1, (x2 - x1) * (y2 - y1)) / float(w * h)


def por_tamanho(caixas: list[tuple[int, int, int, int]], forma, camera: str, pets: list[dict], memoria: MemoriaTamanhos, razao_minima: float = 1.3) -> list[Palpite]:
    """Um palpite por caixa, na mesma ordem. Sem certeza, devolve 'incerto' em vez de chutar."""
    incerto = lambda: Palpite(None, None, 0.0, "incerto")
    saida = [incerto() for _ in caixas]
    if not caixas or len(pets) < 2:
        if len(pets) == 1 and caixas:  # um único pet cadastrado
            return [Palpite(pets[0]["id"], pets[0]["nome"], 1.0, "unico") for _ in caixas]
        return saida
    areas = [area_relativa(c, forma) for c in caixas]

    # 1) dois ou mais animais no quadro: o maior é o pet de maior porte, o menor é o de menor porte
    com_porte = sorted((p for p in pets if p.get("porte") in ORDEM_PORTE), key=lambda p: ORDEM_PORTE[p["porte"]])
    if len(caixas) >= 2 and len(com_porte) >= 2 and ORDEM_PORTE[com_porte[0]["porte"]] != ORDEM_PORTE[com_porte[-1]["porte"]]:
        ordem = sorted(range(len(caixas)), key=lambda i: areas[i])
        menor, maior = ordem[0], ordem[-1]
        if areas[maior] / areas[menor] >= razao_minima:
            g, m = com_porte[-1], com_porte[0]
            saida[maior] = Palpite(g["id"], g["nome"], 0.6, "tamanho")
            saida[menor] = Palpite(m["id"], m["nome"], 0.6, "tamanho")
        return saida

    # 2) um animal só: compara com o tamanho que cada pet costuma ter nesta câmera
    mem = memoria.da_camera(camera)
    conhecidos = [(p, mem[p["id"]]) for p in pets if p["id"] in mem]
    if len(caixas) == 1 and len(conhecidos) >= 2:
        conhecidos.sort(key=lambda t: t[1])
        pequeno, grande = conhecidos[0], conhecidos[-1]
        if grande[1] / pequeno[1] >= 1.5:
            dist = lambda ref: abs(math.log(areas[0] / ref))
            dp, dg = dist(pequeno[1]), dist(grande[1])
            melhor, outro = ((pequeno, dp), dg) if dp < dg else ((grande, dg), dp)
            if melhor[1] < 0.6 * outro:
                saida[0] = Palpite(melhor[0][0]["id"], melhor[0][0]["nome"], 0.5, "tamanho")
    return saida
