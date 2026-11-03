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

    def garantir_camera(self, nome, ambiente, ordem, identificador=None, ip=None):
        return {"id": f"cam-{identificador or nome}", "nome": nome, "ativo": True}

    def cameras(self):
        return [{"id": "cam-sn:AAA", "nome": "Sala de jantar", "ativo": True}]

    def ignorar(self):
        return []

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


# ---- noite: tamanho no lugar de cor ----
from pets_agent.noturno import MemoriaTamanhos, eh_noturno, por_tamanho

cinza = np.full((480, 640, 3), 120, np.uint8)
assert eh_noturno(cinza) and not eh_noturno(cena(MARROM, CAIXA))
duas = [(100, 100, 220, 200), (300, 120, 520, 400)]  # pequena e grande
pets_p = [
    {"id": "g", "nome": "Mavi", "porte": "grande"},
    {"id": "p", "nome": "Bebela", "porte": "pequeno"},
]
mem = MemoriaTamanhos()
r = por_tamanho(duas, cinza.shape, "Quarto", pets_p, mem)
assert [x.nome for x in r] == ["Bebela", "Mavi"], r
assert [x.nome for x in por_tamanho(duas[::-1], cinza.shape, "Quarto", pets_p, mem)] == ["Mavi", "Bebela"]
um = por_tamanho([duas[1]], cinza.shape, "Quarto", pets_p, mem)
assert um[0].como == "incerto"  # um só, sem histórico: não chuta
mem.atualizar("Quarto", "g", 0.30)
mem.atualizar("Quarto", "p", 0.05)
assert por_tamanho([duas[1]], cinza.shape, "Quarto", pets_p, mem)[0].nome == "Mavi"
assert por_tamanho([duas[0]], cinza.shape, "Quarto", pets_p, mem)[0].nome == "Bebela"
print("identificação à noite por tamanho: ok")


# ---- descoberta pela rede: o apelido vem do banco, o IP pode mudar ----
from pets_agent import descoberta

achadas_falsas = [{"ip": "10.0.0.21", "identificador": "sn:AAA", "modelo": "IPC"}]
descoberta.ip_local = lambda: "10.0.0.5"
descoberta.descobrir = lambda base, u, s, excluir=None, ignorados=None, relatorio=None: achadas_falsas
cfg2 = {**cfg, "cameras": [], "credencial_intelbras": {"usuario": "admin", "senha": "x"}}
db2 = BancoFalso()
v2 = Varredura(cfg2, db2, DetectorFalso())
assert v2.precisa_redescobrir()
assert v2.redescobrir() == 1
assert v2.cameras[0][0]["host"] == "10.0.0.21" and v2.cameras[0][1]["nome"].startswith("Câmera")
v2.ultimo_nomes = 0
v2.atualizar_nomes()
assert v2.cameras[0][1]["nome"] == "Sala de jantar"  # apelido veio do banco
achadas_falsas[0]["ip"] = "10.0.0.99"  # a câmera mudou de IP
v2.ultima_descoberta = 0
v2.redescobrir()
assert v2.cameras[0][0]["host"] == "10.0.0.99" and len(v2.cameras) == 1  # mesma câmera, IP novo
assert not v2.precisa_redescobrir()
print("descoberta pela rede: ok")


# ---- perfil com amostras da câmera: com 2+ delas, só elas valem ----
fotos_cel = [caracteristica(cena(CLARO, CAIXA), CAIXA)]
cam_amostras = [caracteristica(cena(MARROM, CAIXA), CAIXA), caracteristica(cena(MARROM, CAIXA), CAIXA)]
pets_v2 = [
    {"id": "m", "nome": "Mavi", "perfil": criar_perfil(fotos_cel, cam_amostras)},   # foto do celular clara, mas na câmera ela é "marrom"
    {"id": "b", "nome": "Bebela", "perfil": criar_perfil([caracteristica(cena((20, 30, 40), CAIXA), CAIXA)])},
]
ident2 = Identificador(pets_v2, 0.55, 0.05)
assert ident2.palpite(caracteristica(cena(MARROM, CAIXA), CAIXA)).nome == "Mavi"
print("perfil com amostras da câmera: ok")


# ---- histórico: só registra quando a posição muda; "Onde estão agora?" força ----
db3 = BancoFalso()
cfg3 = {**cfg, "cameras": [{"nome": "Sala", "fonte": "arquivo", "caminho": str(tmp / "sala.jpg")}], "historico_a_cada_s": 0}
v3 = Varredura(cfg3, db3, DetectorFalso())
v3.todas(); v3.todas(); v3.todas()
assert len(db3.avist) == 1, len(db3.avist)          # parado: um registro só
assert all("identificacao" not in p for p in db3.pos)  # coluna que não existe em pm_ultima_posicao
assert len(db3.pos) == 3                                # mas a última posição é atualizada a cada volta
v3.todas(forcar=True)
assert len(db3.avist) == 2                              # pedido do usuário força um registro novo
class DetectorAndou(DetectorFalso):
    n = 0
    def detectar(self, frame):
        DetectorAndou.n += 1
        return [Deteccao("cachorro", 0.9, (20, 20, 120, 120) if DetectorAndou.n % 2 else (500, 300, 600, 400))]
v4 = Varredura(cfg3, BancoFalso(), DetectorAndou())
v4.todas(); v4.todas()
assert len(v4.db.avist) == 2                            # andou de verdade: registra de novo
print("histórico só com mudança relevante: ok")
