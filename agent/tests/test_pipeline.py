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

    def presenca(self, linha):
        self.pres = getattr(self, "pres", []) + [linha]

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


# ---- pessoas ----
class DetectorGente(DetectorFalso):
    def detectar(self, frame):
        return [Deteccao("pessoa", 0.9, (50, 50, 200, 400)), Deteccao("pessoa", 0.8, (300, 60, 420, 380))]
db5 = BancoFalso()
v5 = Varredura(cfg3, db5, DetectorGente())
saida = v5.todas()
assert "2 pessoa(s)" in saida[0], saida
assert len(db5.avist) == 1 and db5.avist[0]["especie"] == "pessoa" and db5.avist[0]["pet_id"] is None  # um registro por câmera
assert db5.pres[-1]["pessoas"] == 2
v5.todas()
assert len(db5.avist) == 1  # parada/ainda lá: não enche o histórico
print("pessoas: ok")


# ---- reconhecimento de rosto (com vetores de mentira: o modelo real só roda no PC) ----
from pets_agent.rostos import Rostos, cosseno

class RostosFalso(Rostos):
    def __init__(self, vetor):
        super().__init__()
        self.vetor = vetor
    def rostos(self, img):
        return [((0, 0, 50, 50), self.vetor)] if self.vetor is not None else []

rng = np.random.default_rng(7)
igor, rafa = rng.normal(size=128).astype(np.float32), rng.normal(size=128).astype(np.float32)
conhecidos = [{"id": "p1", "nome": "Igor", "embs": [igor]}, {"id": "p2", "nome": "Rafaelly", "embs": [rafa]}]
perto = igor + rng.normal(scale=0.2, size=128).astype(np.float32)
r = RostosFalso(perto).identificar(np.zeros((10, 10, 3), np.uint8), conhecidos)
assert r and r[0]["nome"] == "Igor", r
estranho = rng.normal(size=128).astype(np.float32)
assert RostosFalso(estranho).identificar(np.zeros((10, 10, 3), np.uint8), conhecidos) is None  # desconhecido não vira ninguém
assert RostosFalso(None).identificar(np.zeros((10, 10, 3), np.uint8), conhecidos) is None

db6 = BancoFalso()
v6 = Varredura(cfg3, db6, DetectorGente())
v6.rostos = RostosFalso(perto)
v6.conhecidos = conhecidos
saida = v6.todas()
assert "Igor" in saida[0], saida
assert any(a.get("pessoa_id") == "p1" for a in db6.avist), db6.avist
assert "Igor" in (db6.pres[-1].get("quem") or ""), db6.pres[-1]
print("reconhecimento de pessoas: ok")


# ---- avisos no celular: só pet marcado, e só em lugar novo ----
class NotifFalso:
    ativo = True
    def __init__(self): self.msgs = []
    def enviar(self, titulo, corpo, imagem=None, tag=None):
        self.msgs.append((titulo, corpo)); return 1

class BancoComAviso(BancoFalso):
    def pets(self):
        return [{**p, "notificar": p["nome"] == "Marrom"} for p in pets]
    def url_assinada(self, caminho, *a, **k):
        return "https://exemplo/foto.jpg"

dbn = BancoComAviso()
vn = Varredura(cfg3, dbn, DetectorFalso())
vn.notificador = NotifFalso()
vn.todas(); vn.todas()
assert len(vn.notificador.msgs) == 1 and "Marrom" in vn.notificador.msgs[0][0], vn.notificador.msgs  # parado: avisa uma vez
vn.todas(forcar=True)
assert len(vn.notificador.msgs) == 2  # "Onde estão agora?" avisa de novo
vn2 = Varredura(cfg3, BancoComAviso(), DetectorFalso())
vn2.notificador = NotifFalso()
vn2.pets = [{**p, "notificar": False} for p in pets]
vn2.todas()
assert vn2.notificador.msgs == []  # pet sem "Avisar" não notifica
print("avisos no celular: ok")


# ---- correção no Histórico vira amostra de aprendizado ----
import importlib
principal = importlib.import_module("pets_agent.__main__")
ok_jpg, buf = cv2.imencode(".jpg", cena(MARROM, CAIXA))

class BancoCorrecao:
    def __init__(self):
        self.salvos, self.feitas = [], []
        self.pet = {"id": "p1", "nome": "Marrom", "perfil": criar_perfil([caracteristica(cena(CLARO, CAIXA), CAIXA)])}
    def correcoes_pendentes(self):
        return [{"id": "c1", "snapshot_path": "x.jpg", "x": 200 / 640, "y": 150 / 480, "w": 220 / 640, "h": 250 / 480, "pet_id": "p1", "pessoa_id": None}]
    def baixar_snapshot(self, caminho): return buf.tobytes()
    def pet_por_id(self, i): return self.pet
    def salvar_perfil(self, i, perfil): self.salvos.append(perfil)
    def correcao_aplicada(self, i): self.feitas.append(i)

dbc = BancoCorrecao()
assert principal.aprender_correcoes(dbc) == 1 and dbc.feitas == ["c1"]
perfil_novo = dbc.salvos[0]
assert sum(1 for a in perfil_novo["hists"] if a["o"] == "camera") == 1 and sum(1 for a in perfil_novo["hists"] if a["o"] == "foto") == 1
print("correção do histórico aprendida: ok")


# ---- "bater foto" de uma câmera só ----
dbf = BancoFalso()
vf = Varredura({**cfg3, "cameras": [{"nome": "A", "fonte": "arquivo", "caminho": str(tmp / "sala.jpg")}, {"nome": "B", "fonte": "arquivo", "caminho": str(tmp / "sala.jpg")}]}, dbf, DetectorFalso())
assert vf.fotos_agora({"cam-B"}) == 1 and vf.fotos_agora() == 2 and dbf.fotos.count("ao-vivo/cam-B.jpg") == 2 and dbf.fotos.count("ao-vivo/cam-A.jpg") == 1
print("bater foto: ok")
