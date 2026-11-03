"""Privacidade: nas imagens GUARDADAS (site, histórico, fotos sob demanda) o corpo das pessoas é pixelado e só a cabeça fica nítida.
O reconhecimento e a detecção usam a imagem original; a protegida é só a que sai do computador de casa."""
import cv2
import numpy as np


def _pixelar(img: np.ndarray) -> np.ndarray:
    """Mosaico grosso (blocos bem visíveis): não dá para recuperar o corpo."""
    h, w = img.shape[:2]
    bloco = max(10, int(min(h, w) / 14))
    pequena = cv2.resize(img, (max(2, w // bloco), max(2, h // bloco)), interpolation=cv2.INTER_AREA)
    return cv2.resize(pequena, (w, h), interpolation=cv2.INTER_NEAREST)


def _cabeca(rosto: tuple[int, int, int, int], w: int, h: int) -> tuple[int, int, int, int]:
    """Do quadrado do rosto para a cabeça inteira (cabelo, orelhas e queixo)."""
    fx, fy, fw, fh = rosto
    x1, x2 = fx - int(fw * 0.35), fx + fw + int(fw * 0.35)
    y1, y2 = fy - int(fh * 0.55), fy + fh + int(fh * 0.25)
    return max(0, x1), max(0, y1), min(w, x2), min(h, y2)


def desfocar_pessoas(frame: np.ndarray, caixas: list[tuple[int, int, int, int]], rostos=None) -> np.ndarray:
    """Pixela cada pessoa (caixa x1,y1,x2,y2) e devolve a cabeça nítida por cima. Sem rosto visível, a pessoa inteira fica pixelada."""
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
            bh, bw = original.shape[:2]
            for rosto in faces:
                a, b, c, d = _cabeca(rosto, bw, bh)
                if c - a < 4 or d - b < 4:
                    continue
                mascara = np.zeros((d - b, c - a), np.uint8)
                cv2.ellipse(mascara, ((c - a) // 2, (d - b) // 2), ((c - a) // 2, (d - b) // 2), 0, 0, 360, 255, -1)
                regiao = bloco[b:d, a:c]
                regiao[mascara > 0] = original[b:d, a:c][mascara > 0]
        saida[y1:y2, x1:x2] = bloco
    return saida
