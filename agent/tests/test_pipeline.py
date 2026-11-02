"""Teste sem câmera e sem internet: detector e banco falsos, imagens sintéticas (um pet marrom e outro claro)."""
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pets_agent.detect import Deteccao
from pets_agent.identify import Identificador, caracteristica, criar_perfil
from pets_agent.varredura import Varredura


def cena(cor_bgr, caixa):
    img = np.full((480, 640, 3), (90, 110, 120), np.uint8)  # chão cinza
    x1, y1, x2, y2 = caixa
    rng = np.random.default_rng(1)
    pelo = np.clip(np.array(cor_bgr) + rng.integers(-12, 12, (y2 - y1, x2 - x1, 3)), 0, 255).astype(np.uint8)
    img[y1:y2, x1:x2] = pelo
    return img


MARROM, CLARO = (40, 70, 110), (215, 225, 235)
CAIXA = (200, 150, 420, 400)

pets = []
for pid, nome, cor in [("p1", "Marrom", MARROM), ("p2", "Claro", CLARO)]:
    feats = [caracteristica(cena(cor, CAIXA), CAIXA) for _ in range(3)]
    pets.append({"id": pid, "nome": nome, "perfil": criar_perfil(feats)})

ident = Identificador(pets, 0.55, 0.05)
assert ident.palpite(caracteristica(cena(MARROM, CAIXA), CAIXA)).nome == "Marrom"
assert ident.palpite(caracteristica(cena(CLARO, CAIXA), CAIXA)).nome == "Claro"
um = Identificador(pets[:1], 0.55, 0.05)
assert um.palpite(caracteristica(cena(CLARO, CAIXA), CAIXA)).como == "unico"
print("identificação por cor: ok")


class DetectorFalso:
    def detectar(self, frame):
        return [Deteccao("cachorro", 0.9, CAIXA)]


class BancoFalso:
    def __init__(self):
        self.avist, self.pos, self.fotos, self.status = [], [], [], []

    def pets(self):
        return pets

    def garantir_camera(self, nome, ambiente, ordem):
        return {"id": f"cam-{nome}"}

    def status_camera(self, cid, ok, erro=None, quadro_path=None):
        self.status.append((cid, ok, erro))

    def enviar_foto(self, caminho, jpeg):
        assert jpeg[:2] == b"\xff\xd8"
        self.fotos.append(caminho)

    def avistamento(self, l):
        self.avist.append(l)

    def ultima_posicao(self, l):
        self.pos.append(l)


tmp = Path(tempfile.mkdtemp())
cv2.imwrite(str(tmp / "sala.jpg"), cena(MARROM, CAIXA))
cfg = {
    "historico_a_cada_s": 300, "quadro_da_camera_a_cada_s": 60, "largura_foto": 640,
    "identificacao": {"pontuacao_minima": 0.55, "margem_minima": 0.05},
    "cameras": [
        {"nome": "Sala", "fonte": "arquivo", "caminho": str(tmp / "sala.jpg")},
        {"nome": "Quebrada", "fonte": "arquivo", "caminho": str(tmp / "nao-existe.jpg")},
    ],
}
db = BancoFalso()
v = Varredura(cfg, db, DetectorFalso())
r1 = v.todas()
assert "Sala: Marrom" in r1[0], r1
assert "ERRO" in r1[1], r1                      # câmera quebrada não derruba a varredura
assert len(db.avist) == 1 and len(db.pos) == 1
v.todas()                                       # mesma câmera, parado: não repete o histórico
assert len(db.avist) == 1 and len(db.pos) == 2, (len(db.avist), len(db.pos))
assert db.pos[-1]["pet_id"] == "p1" and db.pos[-1]["snapshot_path"].startswith("avistamentos/")
print("varredura: ok", r1)
