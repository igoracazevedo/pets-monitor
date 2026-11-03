"""Quem é quem pela cor do pelo: histograma HSV do recorte comparado com o perfil de cada pet."""
from dataclasses import dataclass

import cv2
import numpy as np

BINS = (12, 4, 4)  # matiz, saturação, brilho


def caracteristica(frame: np.ndarray, caixa: tuple[int, int, int, int]) -> np.ndarray:
    """Histograma normalizado do miolo da caixa (a borda pega muito chão e parede)."""
    x1, y1, x2, y2 = caixa
    w, h = x2 - x1, y2 - y1
    mx, my = int(w * 0.15), int(h * 0.15)
    crop = frame[max(0, y1 + my) : max(1, y2 - my), max(0, x1 + mx) : max(1, x2 - mx)]
    if crop.size == 0:
        crop = frame[max(0, y1) : max(1, y2), max(0, x1) : max(1, x2)]
    crop = cv2.resize(crop, (64, 64))
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1, 2], None, list(BINS), [0, 180, 0, 256, 0, 256]).flatten()
    hist = hist / (hist.sum() + 1e-9)
    return hist.astype(np.float32)


def pontuacao(a: np.ndarray, b: np.ndarray) -> float:
    """1 = idêntico, 0 = totalmente diferente (coeficiente de Bhattacharyya)."""
    return float(np.sum(np.sqrt(a * b)))


def criar_perfil(caracteristicas: list[np.ndarray], de_camera: list[np.ndarray] | None = None) -> dict:
    """`hist` é a média (compatível com versões antigas); `hists` guarda cada amostra, marcada com a origem (foto do celular ou quadro da câmera)."""
    de_camera = (de_camera or [])[-80:]
    todas = list(caracteristicas) + de_camera
    media = np.mean(todas, axis=0)
    amostras = [{"o": "foto", "h": [round(float(v), 5) for v in f]} for f in caracteristicas] + [{"o": "camera", "h": [round(float(v), 5) for v in f]} for f in de_camera]
    return {"hist": [round(float(v), 6) for v in media], "hists": amostras, "amostras": len(todas), "bins": list(BINS), "versao": 2}


def amostras_de_camera(perfil: dict | None) -> list[np.ndarray]:
    return [np.array(a["h"], dtype=np.float32) for a in (perfil or {}).get("hists", []) if a.get("o") == "camera"]


@dataclass
class Palpite:
    pet_id: str | None
    nome: str | None
    pontuacao: float
    como: str  # cor | unico | incerto | tamanho | pessoa | rosto
    pessoa_id: str | None = None


class Identificador:
    def __init__(self, pets: list[dict], pontuacao_minima: float, margem_minima: float):
        self.pets = []
        for p in pets:
            perfil = p.get("perfil")
            if not (perfil and perfil.get("hist")):
                continue
            fotos = [np.array(a["h"], dtype=np.float32) for a in perfil.get("hists", []) if a.get("o") != "camera"]
            cam = amostras_de_camera(perfil)
            # com 2+ amostras tiradas pela própria câmera, só elas valem (a foto do celular tem outra luz e outra cor)
            usar = cam if len(cam) >= 2 else (fotos or [np.array(perfil["hist"], dtype=np.float32)])
            self.pets.append({"id": p["id"], "nome": p["nome"], "hist": np.array(perfil["hist"], dtype=np.float32), "amostras": usar})
        self.total_pets = len(pets)
        self.minimo = pontuacao_minima
        self.margem = margem_minima

    def pontuacoes(self, feat: np.ndarray) -> list[tuple[float, dict]]:
        return sorted(((max(pontuacao(feat, h) for h in p["amostras"]), p) for p in self.pets), key=lambda t: -t[0])

    def palpite(self, feat: np.ndarray, excluir: set[str] | None = None) -> Palpite:
        excluir = excluir or set()
        if self.total_pets == 1 and len(self.pets) == 1:
            p = self.pets[0]
            return Palpite(p["id"], p["nome"], max(pontuacao(feat, h) for h in p["amostras"]), "unico")
        cand = [(s, p) for s, p in self.pontuacoes(feat) if p["id"] not in excluir]
        if not cand:
            return Palpite(None, None, 0.0, "incerto")
        melhor = cand[0]
        segundo = cand[1][0] if len(cand) > 1 else 0.0
        if melhor[0] >= self.minimo and melhor[0] - segundo >= self.margem:
            return Palpite(melhor[1]["id"], melhor[1]["nome"], melhor[0], "cor")
        return Palpite(None, None, melhor[0], "incerto")
