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


def filtrar_protecao(caixas: list[tuple[tuple[int, int, int, int], float]], shape) -> list[tuple[int, int, int, int]]:
    """Fica a caixa com certeza >= 0.45, ou a duvidosa (>= 0.25) que ocupe até 12% da imagem."""
    h, w = shape[:2]
    out = []
    for (x1, y1, x2, y2), conf in caixas:
        area = (x2 - x1) * (y2 - y1) / float(w * h)
        if conf >= 0.45 or (conf >= 0.25 and area <= 0.12):
            out.append((x1, y1, x2, y2))
    return out


def _iou(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    uni = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / uni if uni > 0 else 0.0


def _dentro(a, b) -> float:
    """Fração da caixa `a` que está dentro da caixa `b`."""
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area = (a[2] - a[0]) * (a[3] - a[1])
    return (ix * iy) / area if area > 0 else 0.0


def sem_repetidas(dets: list["Deteccao"]) -> list["Deteccao"]:
    """O mesmo animal às vezes sai com dois rótulos (cachorro e "urso de pelúcia", ou cachorro e gato): fica o mais confiável.
    Dois animais juntos NÃO são juntados: só some a caixa que quase coincide com outra (sobreposição > 70%)."""
    ordem = sorted(dets, key=lambda d: (d.fraca, -d.confianca))  # fortes primeiro
    ficam: list[Deteccao] = []
    for d in ordem:
        if any(_iou(d.caixa, f.caixa) >= 0.7 for f in ficam):
            continue
        # caixa duvidosa que engloba um animal já achado é a cama/almofada em volta dele, não um segundo animal
        if d.fraca and any(not f.fraca and f.especie != "pessoa" and _dentro(f.caixa, d.caixa) > 0.6 for f in ficam):
            continue
        ficam.append(d)
    return sorted(ficam, key=lambda d: -d.confianca)


class Detector:
    def __init__(self, modelo: str, confianca: float, tamanho: int, confianca_fraca: float = 0.3, pessoas: bool = False, confianca_pessoa: float = 0.55):
        from ultralytics import YOLO  # importa aqui: demora e só é preciso ao detectar

        self.modelo = YOLO(modelo)
        self.confianca = confianca
        self.confianca_fraca = max(confianca, confianca_fraca)
        self.tamanho = tamanho
        self.pessoas = pessoas
        self.confianca_pessoa = max(confianca, confianca_pessoa)  # travesseiro, roupa na cama e sombra parecem gente com 40-50%

    def detectar(self, frame: np.ndarray, com_fracas: bool = True) -> list[Deteccao]:
        classes = list(FORTES) + (list(FRACAS) if com_fracas else []) + (list(PESSOA) if self.pessoas else [])
        res = self.modelo.predict(frame, imgsz=self.tamanho, conf=self.confianca, classes=classes, iou=0.85, verbose=False)[0]  # iou alto: dois animais encostados não viram uma caixa só
        out = []
        for b in res.boxes:
            cls, conf = int(b.cls[0]), float(b.conf[0])
            fraca = cls in FRACAS
            if (fraca and conf < self.confianca_fraca) or (cls in PESSOA and conf < self.confianca_pessoa):
                continue
            x1, y1, x2, y2 = (int(v) for v in b.xyxy[0].tolist())
            out.append(Deteccao((FORTES | FRACAS | PESSOA)[cls], conf, (x1, y1, x2, y2), fraca))
        out = sem_repetidas(out)
        refinadas: list[Deteccao] = []
        for d in out:
            refinadas.extend(self._separar(frame, d) if d.especie != "pessoa" else [d])
        return sem_repetidas(refinadas)

    def pessoas_na_imagem(self, frame: np.ndarray, conf: float = 0.25) -> list[tuple[int, int, int, int]]:
        """Caixas das pessoas a esconder. Pouca certeza só vale para caixa pequena (gente parcial); caixa grande e duvidosa
        costuma ser cama, cobertor ou bicho de pelúcia, e esconderia a foto toda à toa."""
        res = self.modelo.predict(frame, imgsz=self.tamanho, conf=conf, classes=list(PESSOA), iou=0.85, verbose=False)[0]
        return filtrar_protecao([(tuple(int(v) for v in b.xyxy[0].tolist()), float(b.conf[0])) for b in res.boxes], frame.shape)

    def _separar(self, frame: np.ndarray, d: Deteccao) -> list[Deteccao]:
        """Animais deitados juntos saem numa caixa só. Amplia a região e procura de novo: se achar 2 ou mais, troca a caixa por elas."""
        x1, y1, x2, y2 = d.caixa
        h, w = frame.shape[:2]
        bw, bh = x2 - x1, y2 - y1
        if bw < 24 or bh < 24 or bw * bh > 0.25 * w * h:
            return [d]
        px, py = int(bw * 0.3), int(bh * 0.3)
        ox1, oy1, ox2, oy2 = max(0, x1 - px), max(0, y1 - py), min(w, x2 + px), min(h, y2 + py)
        recorte = frame[oy1:oy2, ox1:ox2]
        escala = 640 / max(recorte.shape[:2])
        if escala < 1.5:
            return [d]
        import cv2

        grande = cv2.resize(recorte, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)
        res = self.modelo.predict(grande, imgsz=640, conf=max(0.15, self.confianca * 0.7), classes=list(FORTES) + list(FRACAS), iou=0.85, verbose=False)[0]
        subs = []
        for b in res.boxes:
            cls, conf = int(b.cls[0]), float(b.conf[0])
            fraca = cls in FRACAS
            if fraca and conf < self.confianca_fraca:
                continue
            a1, b1, a2, b2 = (v / escala for v in b.xyxy[0].tolist())
            subs.append(Deteccao((FORTES | FRACAS)[cls], conf, (int(ox1 + a1), int(oy1 + b1), int(ox1 + a2), int(oy1 + b2)), fraca))
        subs = sem_repetidas(subs)
        return subs if len(subs) >= 2 else [d]
