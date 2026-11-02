from dataclasses import dataclass

import numpy as np

# Classes do COCO que interessam
CLASSES = {15: "gato", 16: "cachorro"}


@dataclass
class Deteccao:
    especie: str            # o que o modelo achou (cães pequenos às vezes viram "gato")
    confianca: float
    caixa: tuple[int, int, int, int]  # x1, y1, x2, y2 em pixels


class Detector:
    def __init__(self, modelo: str, confianca: float, tamanho: int):
        from ultralytics import YOLO  # importa aqui: demora e só é preciso ao detectar

        self.modelo = YOLO(modelo)
        self.confianca = confianca
        self.tamanho = tamanho

    def detectar(self, frame: np.ndarray) -> list[Deteccao]:
        res = self.modelo.predict(frame, imgsz=self.tamanho, conf=self.confianca, classes=list(CLASSES), verbose=False)[0]
        out = []
        for b in res.boxes:
            x1, y1, x2, y2 = (int(v) for v in b.xyxy[0].tolist())
            out.append(Deteccao(CLASSES[int(b.cls[0])], float(b.conf[0]), (x1, y1, x2, y2)))
        return sorted(out, key=lambda d: -d.confianca)
