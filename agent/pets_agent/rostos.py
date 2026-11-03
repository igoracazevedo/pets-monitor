"""Reconhecimento de rosto no próprio PC (modelos YuNet + SFace do OpenCV, ~39 MB, baixados na primeira vez).
Nada sai do computador: o site só recebe o nome de quem foi reconhecido."""
from pathlib import Path

import cv2
import numpy as np
import requests

BASE = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models"
MODELOS = {
    "face_detection_yunet_2023mar.onnx": f"{BASE}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx": f"{BASE}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
}
LIMITE = 0.40   # similaridade mínima (cosseno) para aceitar quem é; o valor sugerido pelo OpenCV é 0.363, aqui um pouco mais rígido
MARGEM = 0.04   # e precisa ficar à frente da segunda pessoa mais parecida


def cosseno(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


class Rostos:
    def __init__(self, pasta: str | Path = "modelos"):
        self.pasta = Path(pasta)
        self._det = None
        self._rec = None

    def _baixar(self, nome: str):
        self.pasta.mkdir(exist_ok=True)
        arq = self.pasta / nome
        if not arq.exists() or arq.stat().st_size < 100_000 and "yunet" not in nome:
            print(f"Baixando modelo de rosto {nome} (só na primeira vez)...", flush=True)
            r = requests.get(MODELOS[nome], timeout=120)
            r.raise_for_status()
            arq.write_bytes(r.content)

    def _carregar_detector(self):
        if self._det is None:
            self._baixar("face_detection_yunet_2023mar.onnx")
            self._det = cv2.FaceDetectorYN_create(str(self.pasta / "face_detection_yunet_2023mar.onnx"), "", (320, 320), 0.7, 0.3, 5000)

    def _carregar(self):
        self._carregar_detector()
        if self._rec is None:
            self._baixar("face_recognition_sface_2021dec.onnx")
            self._rec = cv2.FaceRecognizerSF_create(str(self.pasta / "face_recognition_sface_2021dec.onnx"), "")

    def caixas(self, img: np.ndarray) -> list[tuple[int, int, int, int]]:
        """Só onde há rostos (x, y, largura, altura), sem reconhecer ninguém. Rosto pequeno é ampliado antes de procurar."""
        self._carregar_detector()
        h, w = img.shape[:2]
        k = 1.0 if max(h, w) >= 320 else 320 / max(h, w)
        grande = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC) if k > 1 else img
        self._det.setInputSize((grande.shape[1], grande.shape[0]))
        _, faces = self._det.detect(grande)
        return [(int(f[0] / k), int(f[1] / k), int(f[2] / k), int(f[3] / k)) for f in (faces if faces is not None else [])]

    def rostos(self, img: np.ndarray) -> list[tuple[tuple[int, int, int, int], np.ndarray]]:
        """Cada rosto achado: (caixa x, y, w, h, vetor de 128 números). Ordem: do maior para o menor."""
        self._carregar()
        h, w = img.shape[:2]
        self._det.setInputSize((w, h))
        _, faces = self._det.detect(img)
        out = []
        for f in (faces if faces is not None else []):
            alinhado = self._rec.alignCrop(img, f)
            emb = self._rec.feature(alinhado).flatten().astype(np.float32)
            out.append(((int(f[0]), int(f[1]), int(f[2]), int(f[3])), emb))
        return sorted(out, key=lambda t: -(t[0][2] * t[0][3]))

    def maior(self, img: np.ndarray) -> np.ndarray | None:
        r = self.rostos(img)
        return r[0][1] if r else None

    def identificar(self, img: np.ndarray, conhecidos: list[dict]) -> tuple[dict, float] | None:
        """`conhecidos`: [{"id", "nome", "embs": [vetores]}]. Devolve (pessoa, similaridade) ou None se não houver certeza."""
        if not conhecidos:
            return None
        melhor = None
        for _, emb in self.rostos(img):
            ranking = sorted(((max(cosseno(emb, e) for e in p["embs"]), p) for p in conhecidos if p["embs"]), key=lambda t: -t[0])
            if not ranking:
                continue
            segundo = ranking[1][0] if len(ranking) > 1 else 0.0
            if ranking[0][0] >= LIMITE and ranking[0][0] - segundo >= MARGEM and (melhor is None or ranking[0][0] > melhor[1]):
                melhor = (ranking[0][1], ranking[0][0])
        return melhor
