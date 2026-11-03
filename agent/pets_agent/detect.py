from dataclasses import dataclass

import numpy as np

# Classes do COCO que interessam: cachorro e gato valem direto; "urso de pelúcia/urso/ovelha" é como o modelo costuma rotular
# cachorros pequenos e peludos (spitz), então só valem se a cor bater com um pet conhecido.
FORTES = {15: "gato", 16: "cachorro"}
FRACAS = {77: "cachorro", 21: "cachorro", 18: "cachorro"}


@dataclass
class Deteccao:
    especie: str            # o que o modelo achou (cães pequenos às vezes viram "gato")
    confianca: float
    caixa: tuple[int, int, int, int]  # x1, y1, x2, y2 em pixels
    fraca: bool = False     # classe duvidosa (ex.: "urso de pelúcia"): só vale com confirmação pela cor


class Detector:
    def __init__(self, modelo: str, confianca: float, tamanho: int, confianca_fraca: float = 0.3):
        from ultralytics import YOLO  # importa aqui: demora e só é preciso ao detectar

        self.modelo = YOLO(modelo)
        self.confianca = confianca
        self.confianca_fraca = max(confianca, confianca_fraca)
        self.tamanho = tamanho

    def detectar(self, frame: np.ndarray, com_fracas: bool = True) -> list[Deteccao]:
        classes = list(FORTES) + (list(FRACAS) if com_fracas else [])
        res = self.modelo.predict(frame, imgsz=self.tamanho, conf=self.confianca, classes=classes, verbose=False)[0]
        out = []
        for b in res.boxes:
            cls, conf = int(b.cls[0]), float(b.conf[0])
            fraca = cls in FRACAS
            if fraca and conf < self.confianca_fraca:
                continue
            x1, y1, x2, y2 = (int(v) for v in b.xyxy[0].tolist())
            out.append(Deteccao((FORTES | FRACAS)[cls], conf, (x1, y1, x2, y2), fraca))
        return sorted(out, key=lambda d: -d.confianca)
