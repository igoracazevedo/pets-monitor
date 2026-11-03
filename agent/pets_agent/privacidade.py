"""Privacidade: nas imagens GUARDADAS (site, histórico, fotos sob demanda) o corpo das pessoas é desfocado e só o rosto fica nítido.
O reconhecimento e a detecção usam a imagem original; a protegida é só a que sai do computador de casa."""
import cv2
import numpy as np


def _pixelar(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    pequena = cv2.resize(img, (max(3, w // 10), max(3, h // 10)), interpolation=cv2.INTER_AREA)
    pix = cv2.resize(pequena, (w, h), interpolation=cv2.INTER_NEAREST)
    return cv2.GaussianBlur(pix, (0, 0), max(2.0, min(w, h) / 25))


def desfocar_pessoas(frame: np.ndarray, caixas: list[tuple[int, int, int, int]], rostos=None) -> np.ndarray:
    """Pixela cada pessoa (caixa x1,y1,x2,y2) e devolve o rosto nítido por cima. Sem rosto visível, a pessoa inteira fica pixelada."""
    if not caixas:
        return frame
    saida = frame.copy()
    h, w = frame.shape[:2]
    for x1, y1, x2, y2 in caixas:
        mx, my = int((x2 - x1) * 0.08), int((y2 - y1) * 0.06)
        x1, y1, x2, y2 = max(0, x1 - mx), max(0, y1 - my), min(w, x2 + mx), min(h, y2 + my)
        if x2 - x1 < 4 or y2 - y1 < 4:
            continue
        original = frame[y1:y2, x1:x2]
        bloco = _pixelar(original)
        if rostos is not None:
            try:
                faces = rostos.caixas(original)
            except Exception:
                faces = []
            for fx, fy, fw, fh in faces:
                px, py = int(fw * 0.12), int(fh * 0.12)  # um respiro em volta do rosto
                a, b = max(0, fy - py), max(0, fx - px)
                bloco[a : fy + fh + py, b : fx + fw + px] = original[a : fy + fh + py, b : fx + fw + px]
        saida[y1:y2, x1:x2] = bloco
    return saida
