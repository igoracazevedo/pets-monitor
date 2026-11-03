from dataclasses import dataclass

import numpy as np

# Classes do COCO que interessam: cachorro e gato valem direto; "urso de pelúcia/urso/ovelha" é como o modelo costuma rotular
# cachorros pequenos e peludos (spitz), então só valem se a cor bater com um pet conhecido.
FORTES = {15: "gato", 16: "cachorro"}
PESSOA = {0: "pessoa"}  # só quando `detectar_pessoas` está ligado
FRACAS = {77: "cachorro", 21: "cachorro", 18: "cachorro"}


@dataclass
class Deteccao:
    especie: str            # o que o modelo achou (cães pequenos às vezes viram "gato")
    confianca: float
    caixa: tuple[int, int, int, int]  # x1, y1, x2, y2 em pixels
    fraca: bool = False     # classe duvidosa (ex.: "urso de pelúcia"): só vale com confirmação pela cor


def _iou(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    uni = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / uni if uni > 0 else 0.0


def sem_repetidas(dets: list["Deteccao"]) -> list["Deteccao"]:
    """O mesmo animal às vezes sai com dois rótulos (cachorro e "urso de pelúcia", ou cachorro e gato): fica o mais confiável.
    Dois animais juntos NÃO são juntados: só some a caixa que quase coincide com outra (sobreposição > 70%)."""
    ordem = sorted(dets, key=lambda d: (d.fraca, -d.confianca))  # fortes primeiro
    ficam: list[Deteccao] = []
    for d in ordem:
        if all(_iou(d.caixa, f.caixa) < 0.7 for f in ficam):
            ficam.append(d)
    return sorted(ficam, key=lambda d: -d.confianca)


class Detector:
    def __init__(self, modelo: str, confianca: float, tamanho: int, confianca_fraca: float = 0.3, pessoas: bool = False):
        from ultralytics import YOLO  # importa aqui: demora e só é preciso ao detectar

        self.modelo = YOLO(modelo)
        self.confianca = confianca
        self.confianca_fraca = max(confianca, confianca_fraca)
        self.tamanho = tamanho
        self.pessoas = pessoas

    def detectar(self, frame: np.ndarray, com_fracas: bool = True) -> list[Deteccao]:
        classes = list(FORTES) + (list(FRACAS) if com_fracas else []) + (list(PESSOA) if self.pessoas else [])
        res = self.modelo.predict(frame, imgsz=self.tamanho, conf=self.confianca, classes=classes, iou=0.85, verbose=False)[0]  # iou alto: dois animais encostados não viram uma caixa só
        out = []
        for b in res.boxes:
            cls, conf = int(b.cls[0]), float(b.conf[0])
            fraca = cls in FRACAS
            if fraca and conf < self.confianca_fraca:
                continue
            x1, y1, x2, y2 = (int(v) for v in b.xyxy[0].tolist())
            out.append(Deteccao((FORTES | FRACAS | PESSOA)[cls], conf, (x1, y1, x2, y2), fraca))
        return sem_repetidas(out)
