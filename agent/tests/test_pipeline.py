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


# ---- dois animais juntos continuam dois; o mesmo animal com dois rótulos vira um ----
from pets_agent.detect import sem_repetidas
juntos = sem_repetidas([Deteccao("cachorro", 0.9, (100, 100, 300, 300)), Deteccao("cachorro", 0.8, (240, 120, 420, 300))])  # encostados, IoU baixo
assert len(juntos) == 2
repetido = sem_repetidas([Deteccao("cachorro", 0.8, (100, 100, 300, 300)), Deteccao("cachorro", 0.5, (105, 102, 298, 302), True)])
assert len(repetido) == 1 and not repetido[0].fraca
print("vários animais na mesma foto: ok")


# ---- cama em volta do animal não é segundo animal; dois bichos juntos são separados na 2ª passada ----
cama = sem_repetidas([Deteccao("cachorro", 0.7, (355, 80, 445, 200)), Deteccao("cachorro", 0.33, (320, 0, 450, 230), True)])
assert len(cama) == 1 and not cama[0].fraca   # a caixa grande que engloba o cachorro some

import types
class CaixaFalsa:
    def __init__(self, cls, conf, xyxy): self.cls, self.conf, self.xyxy = [cls], [conf], [types.SimpleNamespace(tolist=lambda xyxy=xyxy: xyxy)]
class ModeloFalso:
    n = 0
    def predict(self, img, **k):
        ModeloFalso.n += 1
        if ModeloFalso.n == 1:   # 1ª passada: uma caixa só para os dois
            return [types.SimpleNamespace(boxes=[CaixaFalsa(16, 0.7, [100, 100, 220, 200])])]
        h, w = img.shape[:2]      # zoom: dois bichos separados na região ampliada
        return [types.SimpleNamespace(boxes=[CaixaFalsa(16, 0.8, [w * .3, h * .2, w * .6, h * .8]), CaixaFalsa(77, 0.5, [w * .1, h * .4, w * .3, h * .8])])]
from pets_agent.detect import Detector
det = Detector.__new__(Detector)
det.modelo, det.confianca, det.confianca_fraca, det.tamanho, det.pessoas = ModeloFalso(), 0.25, 0.3, 960, False
achados = det.detectar(np.full((480, 640, 3), 128, np.uint8))
assert len(achados) == 2, achados
print("separar animais juntos: ok")


# ---- pessoa com confiança baixa (travesseiro, roupa) não conta ----
class ModeloPessoa:
    def predict(self, img, **k):
        return [types.SimpleNamespace(boxes=[CaixaFalsa(0, 0.46, [10, 10, 100, 200]), CaixaFalsa(0, 0.78, [300, 10, 400, 200])])]
det2 = Detector.__new__(Detector)
det2.modelo, det2.confianca, det2.confianca_fraca, det2.confianca_pessoa, det2.tamanho, det2.pessoas = ModeloPessoa(), 0.25, 0.3, 0.55, 960, True
gente2 = det2.detectar(np.full((480, 640, 3), 128, np.uint8))
assert len(gente2) == 1 and gente2[0].confianca == 0.78
print("pessoa só com confiança alta: ok")


# ---- "urso de pelúcia" grande demais não vira pet, mesmo com cor parecida ----
class DetectorUrso(DetectorFalso):
    def detectar(self, frame):
        return [Deteccao("cachorro", 0.72, (60, 40, 560, 440), True)]  # ocupa 65% do quadro
dbu = BancoFalso()
vu = Varredura(cfg3, dbu, DetectorUrso())
assert "ninguém" in vu.todas()[0] and not dbu.avist
print("urso de pelúcia grande ignorado: ok")


def test_privacidade():
    import numpy as np
    from pets_agent.privacidade import desfocar_pessoas

    class R:
        def caixas(self, img):
            return [(40, 10, 20, 20)]

    rng = np.random.default_rng(1)
    f = rng.integers(0, 255, (200, 120, 3), dtype=np.uint8)
    out = desfocar_pessoas(f, [(20, 0, 100, 190)], R())
    corpo = (slice(100, 180), slice(30, 90))
    assert not np.array_equal(out[corpo], f[corpo]) and out[corpo].std() < f[corpo].std() and not np.array_equal(out[corpo], f[corpo])
    assert np.array_equal(out[16:24, 60:68], f[16:24, 60:68])  # rosto (40+20 offset) preservado
    assert np.array_equal(out[:, :10], f[:, :10])
    print("privacidade: corpo pixelado, cabeça nítida: ok")
test_privacidade()


def test_banheiro():
    import cv2
    import numpy as np
    from pets_agent.banheiro import Banheiro

    rng = np.random.default_rng(3)
    base = np.full((480, 640, 3), (200, 205, 208), np.uint8) + rng.integers(0, 6, (480, 640, 3), dtype=np.uint8)

    def com(mancha, cor, tam=(70, 40), pos=(300, 250)):
        im = base.copy()
        cv2.ellipse(im, pos, tam, 0, 0, 360, cor, -1)
        return im

    xixi1, xixi2 = com(1, (120, 200, 225), (90, 50)), com(1, (130, 205, 228), (70, 45), (250, 200))  # amarelado e grande
    coco1, coco2 = com(1, (40, 70, 90), (18, 12)), com(1, (35, 60, 85), (22, 14), (400, 300))      # escuro e pequeno
    luz = np.clip(base.astype(np.int16) + 6, 0, 255).astype(np.uint8)

    class DB:
        def __init__(s):
            s.imgs, s.l = {}, []
        def banheiro_amostras(s, cid):
            return [{"rotulo": r, "snapshot_path": p, "created_at": str(i)} for i, (r, p) in enumerate(s.l)]
        def baixar_snapshot(s, p):
            return cv2.imencode(".jpg", s.imgs[p])[1].tobytes()
        def enviar_foto(s, p, b):
            s.imgs[p] = cv2.imdecode(np.frombuffer(b, np.uint8), 1)
        def nova_amostra_banheiro(s, row):
            s.l.append((row["rotulo"], row["snapshot_path"]))

    db = DB()
    b = Banheiro(db)
    jp = lambda f: cv2.imencode(".jpg", f)[1].tobytes()
    assert b.classificar("c1", xixi1) is None  # ainda sem exemplos
    for rot, im in (("limpo", base), ("xixi", xixi1), ("coco", coco1), ("xixi", xixi2), ("coco", coco2)):
        b.ensinar("c1", rot, im, jp)
    assert b.classificar("c1", luz)[0] == "limpo"
    assert b.classificar("c1", com(1, (125, 200, 226), (80, 48), (330, 260)))[0] == "xixi"
    assert b.classificar("c1", com(1, (38, 66, 88), (20, 13), (200, 350)))[0] == "coco"
    print("banheiro: limpo, xixi e coco reconhecidos: ok")


test_banheiro()


def test_agua():
    import numpy as np
    from pets_agent.detect import Deteccao
    from pets_agent.varredura import Varredura

    class Pal:
        pet_id = "p1"

    class DB:
        l = []
        def enviar_foto(s, c, b): pass
        def evento_banheiro(s, r): s.l.append(r)
    v = Varredura.__new__(Varredura)
    v.cfg = {"largura_foto": 960, "proteger_pessoas": False}; v.db = DB(); v.notificador = None; v.ultima_agua = {}
    v.pets = [{"id": "p1", "nome": "Bebela"}]
    f = np.zeros((480, 640, 3), np.uint8)
    v.caixa_agua = {}
    v.vigiar_agua("c1234567", "Banheiro", f, [(Deteccao("dog", 0.8, (300, 300, 500, 400)), Pal())])
    assert not v.db.l  # longe da vasilha
    v.vigiar_agua("c1234567", "Banheiro", f, [(Deteccao("dog", 0.8, (90, 150, 155, 210)), Pal())])  # Mavi na vasilha rosa (foto real das 21:23)
    assert v.db.l and v.db.l[0]["tipo"] == "agua" and v.db.l[0]["pet_id"] == "p1"
    v.vigiar_agua("c1234567", "Banheiro", f, [(Deteccao("dog", 0.8, (90, 150, 155, 210)), Pal())])
    assert len(v.db.l) == 1  # não repete em 10 min
    print("água: Bebela bebeu água registrado uma vez: ok")


test_agua()


def test_protecao_filtro():
    from pets_agent.detect import filtrar_protecao

    cama = ((250, 330, 660, 640), 0.31)      # caixa enorme e duvidosa (cama): não esconde a foto toda
    cama2 = ((250, 200, 870, 640), 0.55)     # enorme e só 55%: também não
    pessoa = ((100, 50, 300, 600), 0.80)      # pessoa de verdade: esconde
    parcial = ((10, 10, 90, 120), 0.30)       # pedaço pequeno e duvidoso: esconde
    r = filtrar_protecao([cama, cama2, pessoa, parcial], (665, 876, 3))
    assert pessoa[0] in r and parcial[0] in r and cama[0] not in r and cama2[0] not in r
    print("proteção: cama não vira pessoa, gente de verdade continua escondida: ok")


test_protecao_filtro()


def test_agua_quarto():
    import numpy as np
    from pets_agent.detect import Deteccao
    from pets_agent.varredura import Varredura

    class Pal:
        pet_id = "p2"

    class DB:
        l = []
        def enviar_foto(s, c, b): pass
        def evento_banheiro(s, r): s.l.append(r)
    v = Varredura.__new__(Varredura)
    v.cfg = {"largura_foto": 960, "proteger_pessoas": False}; v.db = DB(); v.notificador = None; v.ultima_agua = {}; v.caixa_agua = {}
    v.pets = [{"id": "p2", "nome": "Bebela"}]
    f = np.zeros((480, 640, 3), np.uint8)
    # Quarto Varanda: Bebela no bebedouro lilás (x ~0.40, y ~0.49 da imagem)
    v.vigiar_agua("c1234567", "Quarto Varanda", f, [(Deteccao("dog", 0.8, (200, 200, 300, 270)), Pal())])
    assert len(v.db.l) == 1
    v.ultima_agua = {}  # passou o intervalo, mas ela continua exatamente parada no mesmo lugar
    v.vigiar_agua("c1234567", "Quarto Varanda", f, [(Deteccao("dog", 0.8, (200, 200, 300, 270)), Pal())])
    assert len(v.db.l) == 1
    print("água no quarto: Bebela no bebedouro lilás, e parada dormindo não conta: ok")


test_agua_quarto()


def test_cores_e_locais():
    import numpy as np
    from pets_agent import varredura as V
    from pets_agent.detect import Deteccao

    class DB:
        l = []
        def pessoas(s): return [{"nome": "Igor"}, {"nome": "Rafa", "cor": "#112233"}]
        def enviar_foto(s, c, b): pass
        def evento_banheiro(s, r): s.l.append(r)
    v = V.Varredura.__new__(V.Varredura)
    v.db = DB(); v.pets = [{"nome": "Bebela", "cor": "#ff0000"}, {"nome": "Mavi"}]
    v.atualizar_cores()
    assert V.CORES["Bebela"] == (0, 0, 255) and V.CORES["Mavi"] == V._bgr("#eb6834") and V.CORES["Igor"] == V._bgr("#e34948") and V.CORES["Rafa"] == (0x33, 0x22, 0x11)
    img = V._anotar(np.zeros((100, 100, 3), np.uint8), [((10, 10, 60, 60), "Bebela")])
    assert tuple(int(x) for x in img[10, 30]) == (0, 0, 255)  # a caixa usa a cor escolhida
    # bebedouro marcado no app vale mais que o padrão e vale em qualquer câmera
    class Pal: pet_id = "p1"
    v.cfg = {"largura_foto": 960, "proteger_pessoas": False}; v.notificador = None; v.ultima_agua = {}; v.caixa_agua = {}
    v.pets = [{"id": "p1", "nome": "Mavi"}]
    v.zonas = {"c1234567": [{"tipo": "bebedouro", "x": 0.7, "y": 0.1, "w": 0.1, "h": 0.1}]}
    f = np.zeros((100, 100, 3), np.uint8)
    v.vigiar_agua("c1234567", "Sala", f, [(Deteccao("dog", 0.9, (65, 5, 85, 25)), Pal())])
    assert len(v.db.l) == 1
    print("cores por pet/pessoa e bebedouro marcado no app: ok")


test_cores_e_locais()


def test_comida_e_banheiro_em_qualquer_camera():
    import cv2
    import numpy as np
    from pets_agent import varredura as V
    from pets_agent.banheiro import Banheiro, cortar
    from pets_agent.detect import Deteccao

    class Pal: pet_id = "p1"

    class DB:
        l = []
        def enviar_foto(s, c, b): pass
        def evento_banheiro(s, r): s.l.append(r)
    v = V.Varredura.__new__(V.Varredura)
    v.cfg = {"largura_foto": 960, "proteger_pessoas": False}; v.db = DB(); v.notificador = None; v.ultima_agua = {}; v.caixa_agua = {}
    v.pets = [{"id": "p1", "nome": "Mavi"}]
    v.zonas = {"cX": [{"tipo": "comedouro", "x": 0.1, "y": 0.6, "w": 0.2, "h": 0.2}]}
    f = np.zeros((200, 200, 3), np.uint8)
    v.vigiar_comida("cX", "Cozinha", f, [(Deteccao("dog", 0.9, (20, 120, 60, 160)), Pal())])
    assert [e["tipo"] for e in v.db.l] == ["comeu"] and v.db.l[0]["pet_id"] == "p1"
    # o mesmo bicho longe do comedouro não conta
    v.ultima_agua = {}; v.db.l.clear()
    v.vigiar_comida("cX", "Cozinha", f, [(Deteccao("dog", 0.9, (150, 10, 190, 40)), Pal())])
    assert not v.db.l
    # recorte: só a região do banheiro marcada entra na comparação
    img = np.arange(200 * 100 * 3, dtype=np.uint8).reshape(200, 100, 3)
    assert cortar(img, (0.5, 0.5, 0.5, 0.5)).shape[:2] == (100, 50)
    print("comeu em qualquer câmera e recorte do banheiro: ok")


test_comida_e_banheiro_em_qualquer_camera()


def test_mensagem_do_ensino():
    import cv2
    import numpy as np
    from pets_agent import varredura as V
    from pets_agent.banheiro import Banheiro

    class DB:
        def __init__(s): s.imgs, s.l, s.ev = {}, [], []
        def banheiro_amostras(s, cid): return [{"rotulo": r, "snapshot_path": p, "created_at": str(i)} for i, (r, p) in enumerate(s.l)]
        def baixar_snapshot(s, p): return cv2.imencode(".jpg", s.imgs[p])[1].tobytes()
        def enviar_foto(s, p, b): s.imgs[p] = cv2.imdecode(np.frombuffer(b, np.uint8), 1)
        def nova_amostra_banheiro(s, r): s.l.append((r["rotulo"], r["snapshot_path"]))
        def evento_banheiro(s, r): s.ev.append(r)
    v = V.Varredura.__new__(V.Varredura)
    v.db = DB(); v.banheiro = Banheiro(v.db); v.cfg = {"largura_foto": 640, "proteger_pessoas": False}; v.estado_banheiro = {}; v.zonas = {}
    v.cameras = [({"nome": "B"}, {"id": "cam12345", "nome": "Banheiro"})]
    V.capture.capturar = lambda c: np.full((120, 160, 3), 200, np.uint8)
    m1 = v.ensinar_banheiro("cam12345", "limpo")
    assert "1 limpo" in m1 and "Falta" not in m1, m1
    m2 = v.ensinar_banheiro("cam12345", "xixi")
    assert "1 limpo, 1 xixi" in m2, m2
    antes = len(v.db.ev)
    m3 = v.ensinar_banheiro("cam12345", "xixi_coco")
    assert "xixi e cocô" in m3 and "1 xixi e coco" in m3, m3
    assert [e["tipo"] for e in v.db.ev[antes:]] == ["xixi", "coco"], v.db.ev[antes:]  # os dois ao mesmo tempo = dois eventos
    assert v.db.l[-1][0] == "xixi_coco"
    assert "desconhecido" in v.ensinar_banheiro("cam12345", "lama")
    print("mensagem do ensino conta os exemplos guardados (inclusive xixi e cocô juntos): ok")


test_mensagem_do_ensino()


def _cenario(seed, itens=()):
    """Fundo com textura (fixo por câmera) e 'vasilhas' = retalhos coloridos com textura: (x, y, escala)."""
    rng = np.random.default_rng(seed)
    f = cv2.GaussianBlur(rng.integers(50, 170, (360, 640, 3)).astype(np.uint8), (0, 0), 2)
    padrao = np.clip(np.array((180, 110, 230)) + np.random.default_rng(99).integers(-60, 60, (43, 64, 3)), 0, 255).astype(np.uint8)
    for x, y, esc in itens:
        p = cv2.resize(padrao, (int(64 * esc), int(43 * esc)))
        f[y : y + p.shape[0], x : x + p.shape[1]] = p
    return f


def test_catalogo_acompanha_o_objeto():
    from pets_agent.catalogo import Catalogo

    class DB:
        def __init__(s): s.fotos, s.campos, s.baixar = [], [], {}
        def enviar_foto(s, c, b): s.fotos.append(c)
        def objeto(s, oid, campos): s.campos.append((oid, campos))
        def baixar_snapshot(s, c): return s.baixar[c]

    with tempfile.TemporaryDirectory() as d:
        db = DB()
        cat = Catalogo(db, Path(d), lambda pid: "Mavi", lambda cid: {"A": "Banheiro", "B": "Sala"}.get(cid, cid))
        linhas = [{"id": "z1", "tipo": "bebedouro", "pet_id": "p1", "camera_id": "A", "camera_origem": "A", "x": 0.2, "y": 0.5, "w": 0.1, "h": 0.12}]
        cat.sincronizar(linhas)
        assert cat.caixas("A", "bebedouro") == [(0.2, 0.5, 0.1, 0.12)]            # antes de aprender vale o lugar marcado
        cat.aprender("A", _cenario(1, [(128, 180, 1.0)]), [(0.2, 0.5, 0.1, 0.12)])  # bicho em cima: não aprende
        assert cat.objetos["z1"].dia is None
        cat.aprender("A", _cenario(1, [(128, 180, 1.0)]), [])
        assert cat.objetos["z1"].dia is not None and db.fotos == ["objetos/z1.jpg"] and db.campos[-1][0] == "z1" and db.campos[-1][1]["imagem_path"] == "objetos/z1.jpg"
        # mudou um pouco de lugar na mesma câmera: o catálogo acompanha
        cat.atualizar("A", _cenario(1, [(148, 190, 1.0)]), [], False, 1000)
        x, y, _, _ = cat.caixas("A", "bebedouro")[0]
        assert abs(x - 148 / 640) < 0.02 and abs(y - 190 / 360) < 0.03, (x, y)
        # bicho em cima da vasilha: não dá para conferir, continua onde estava
        antes = cat.caixas("A", "bebedouro")[0]
        cat.atualizar("A", _cenario(1), [(antes[0], antes[1], antes[2], antes[3])], True, 1100)
        assert cat.caixas("A", "bebedouro")[0] == antes and not cat.objetos["z1"].sumido
        # foi para outra câmera (e maior): só muda depois de 3 conferências seguidas
        for t in (2000, 2250, 2500):
            cat.atualizar("B", _cenario(7, [(400, 100, 1.4)]), [], True, t)
        assert cat.caixas("B", "bebedouro") and not cat.caixas("A", "bebedouro")
        bx = cat.caixas("B", "bebedouro")[0]
        assert abs(bx[0] - 400 / 640) < 0.03 and abs(bx[1] - 100 / 360) < 0.04, bx
        # reiniciando o programa o recorte continua guardado em disco
        cat2 = Catalogo(db, Path(d))
        cat2.sincronizar(linhas)
        assert cat2.objetos["z1"].dia is not None
        # outra câmera sem a vasilha não rouba o objeto
        cat3 = Catalogo(db, Path(d)); cat3.sincronizar(linhas)
        for t in (5000, 5250, 5500):
            cat3.atualizar("B", _cenario(7), [], True, t)
        assert cat3.caixas("A", "bebedouro") and not cat3.caixas("B", "bebedouro")
        # objeto criado no app: o recorte vem da foto marcada (960 px de largura), guardado no banco
        foto = cv2.resize(_cenario(1, [(128, 180, 1.0)]), (960, 540))
        recorte = foto[int(0.5 * 540) : int(0.62 * 540), int(0.2 * 960) : int(0.3 * 960)]
        db.baixar["objetos/n1.jpg"] = cv2.imencode(".jpg", recorte)[1].tobytes()
        with tempfile.TemporaryDirectory() as d2:
            cat4 = Catalogo(db, Path(d2))
            cat4.sincronizar([{**linhas[0], "id": "n1", "imagem_path": "objetos/n1.jpg", "largura_ref": 960}])
            assert cat4.objetos["n1"].dia is not None
            cat4.atualizar("A", _cenario(1, [(148, 190, 1.0)]), [], False, 1000)
            assert abs(cat4.caixas("A", "bebedouro")[0][0] - 148 / 640) < 0.03
            # o desenho na foto foi apagado (a linha continua existindo): o objeto segue no catálogo; some só quando a linha some
            cat4.sincronizar([{**linhas[0], "id": "n1", "imagem_path": "objetos/n1.jpg", "largura_ref": 960, "zona_id": None}])
            assert "n1" in cat4.objetos
            cat4.sincronizar([])
            assert "n1" not in cat4.objetos
    print("catálogo: acha o objeto onde ele estiver (outro lugar, outra câmera), sem trocar à toa, e persiste até apagar: ok")


test_catalogo_acompanha_o_objeto()


def test_buffer_e_segunda_leitura():
    import time as T
    from pets_agent import varredura as V
    from pets_agent.buffer import Buffer
    from pets_agent.detect import Deteccao

    with tempfile.TemporaryDirectory() as d:
        b = Buffer(Path(d), horas=12)
        f = np.zeros((90, 160, 3), np.uint8)
        agora = T.time()
        velho = b.salvar("c1", f, agora - 13 * 3600)
        novo = b.salvar("c1", f, agora - 600)
        lido = b.salvar("c1", f, agora - 300, revisado=True)
        assert [p.name for _, p, _ in b.pendentes(10)] == [velho.name, novo.name]   # os já lidos ficam de fora, do mais antigo ao mais novo
        b.marcar(novo)
        assert [p for _, p, _ in b.pendentes(10)] == [velho]
        assert b.limpar() == 1 and not velho.exists() and lido.exists()               # passou de 12 h: apaga

        class Pal: pet_id = "p1"; como = "cor"; nome = "Mavi"; pessoa_id = None

        class DB:
            def __init__(s): s.ev, s.fotos, s.antigos = [], [], []
            def enviar_foto(s, c, x): s.fotos.append(c)
            def evento_banheiro(s, r): s.ev.append(r)
            def eventos_desde(s, iso): return s.antigos
        v = V.Varredura.__new__(V.Varredura)
        v.cfg = {"largura_foto": 960, "proteger_pessoas": False}; v.db = DB(); v.notificador = None
        v.pets = [{"id": "p1", "nome": "Mavi"}]
        v.cameras = [({}, {"id": "cam1", "nome": "Banheiro", "ativo": True})]
        v.zonas = {"cam1": [{"tipo": "bebedouro", "x": 0.1, "y": 0.4, "w": 0.2, "h": 0.2}]}
        v.catalogo = None; v.buffer = Buffer(Path(d) / "b2")
        v.eventos_recentes = []; v.eventos_carga = 0.0
        v.rev_ultima, v.rev_caixa, v.rev_prev, v.rev_vistos, v.rev_banheiro = {}, {}, {}, {}, {}
        # imagem escura (< 128) = cachorra em cima da vasilha; clara = foi embora
        v.analisar = lambda frame, cid, aprender=False: (([Deteccao("dog", 0.9, (20, 40, 60, 80))], [Pal()]) if frame.mean() < 128 else ([], []))
        ts = agora - 7200  # 2 h atrás
        v.buffer.salvar("cam1", np.full((100, 100, 3), 10, np.uint8), ts)
        v.buffer.salvar("cam1", np.full((100, 100, 3), 20, np.uint8), ts + 30)        # ainda bebendo: a mesma visita
        v.buffer.salvar("cam1", np.full((100, 100, 3), 200, np.uint8), ts + 60)       # foi embora depois de pouco tempo: bebeu
        assert v.revisar(10) == 3 and not v.buffer.pendentes(10)
        assert [e["tipo"] for e in v.db.ev] == ["agua"] and v.db.ev[0]["pet_id"] == "p1"
        quando = datetime.fromisoformat(v.db.ev[0]["visto_em"]).timestamp()
        assert abs(quando - ts) < 2, "o evento leva a hora da imagem, não a hora da leitura"
        # já registrado (pela varredura ou por você) perto desse horário: não repete
        v.db.ev.clear(); v.rev_ultima.clear(); v.rev_caixa.clear()
        v.eventos_recentes = [("agua", "p1", ts + 3600 + 100)]
        v.buffer.salvar("cam1", np.full((100, 100, 3), 90, np.uint8), ts + 3600)
        v.buffer.salvar("cam1", np.full((100, 100, 3), 250, np.uint8), ts + 3700)
        v.eventos_carga = T.time()
        v.revisar(10)
        assert not v.db.ev
        # deitada ao lado da vasilha por 5 min: não é beber
        for i, cor in enumerate((30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 230)):
            v.buffer.salvar("cam1", np.full((100, 100, 3), cor, np.uint8), ts + 7200 + 30 * i)
        v.revisar(20)
        assert not v.db.ev, "ficou muito tempo na vasilha: deitada, não bebendo"
    print("imagens guardadas 12 h e segunda leitura: registra o que faltou, na hora certa, sem repetir: ok")


from datetime import datetime

test_buffer_e_segunda_leitura()


def test_banheiro_por_visita():
    """Xixi/cocô só depois de um bicho pisar no tapete: compara o tapete antes e depois da visita."""
    from pets_agent.visita_tapete import VigiaTapete, comparar

    rec = (0.5, 0.2, 0.4, 0.6)

    def cena(amarelo=False, coco=False, luz=1.0):
        img = np.full((240, 320, 3), (150, 160, 170), np.uint8)     # piso
        cv2.rectangle(img, (160, 48), (288, 192), (235, 238, 240), -1)  # tapete branco
        cv2.line(img, (224, 48), (224, 192), (210, 214, 216), 2)       # vinco do tapete (textura para o encaixe)
        if amarelo:
            cv2.circle(img, (200, 120), 22, (120, 200, 215), -1)       # mancha amarelada
        if coco:
            for x, y in ((250, 80), (258, 86), (247, 92)):
                cv2.circle(img, (x, y), 3, (20, 35, 60), -1)           # pedacinhos escuros
        return np.clip(img.astype(np.float32) * luz, 0, 255).astype(np.uint8)

    assert comparar(cena(), cena(amarelo=True), rec).tipos == ["xixi"]
    assert comparar(cena(), cena(coco=True), rec).tipos == ["coco"]
    assert comparar(cena(amarelo=True), cena(amarelo=True, luz=0.85), rec).tipos == [], "só a luz mudou"
    assert comparar(cena(amarelo=True), cena(), rec).tipos == [], "mancha que sumiu não é xixi"

    dog = ((0.6, 0.3, 0.8, 0.6), "p1")
    g = VigiaTapete()
    assert g.alimentar(cena(), 0, rec, [], []) == []                         # tapete livre: referência
    assert g.alimentar(cena(), 30, rec, [dog], []) == []                     # Mavi em cima
    assert g.alimentar(cena(amarelo=True), 60, rec, [], []) == []            # saiu (1ª imagem livre)
    ev = g.alimentar(cena(amarelo=True), 90, rec, [], [])                    # 2ª imagem livre: fecha a visita
    assert [(e["tipo"], e["pet_id"], e["ts"]) for e in ev] == [("xixi", "p1", 30)]
    # bicho só passou: nada novo
    g.alimentar(cena(amarelo=True), 120, rec, [dog], [])
    g.alimentar(cena(amarelo=True), 150, rec, [], [])
    assert g.alimentar(cena(amarelo=True), 180, rec, [], []) == []
    # a luz mudou com o tapete livre: sem visita, nunca vira evento
    assert g.alimentar(cena(amarelo=True, luz=0.8), 210, rec, [], []) == []
    # pessoa trocou o tapete: limpo
    g.alimentar(cena(amarelo=True), 240, rec, [], [(0.55, 0.1, 0.95, 0.9)])
    g.alimentar(cena(), 270, rec, [], [])
    assert [e["tipo"] for e in g.alimentar(cena(), 300, rec, [], [])] == ["limpo"]
    # cachorro longe do tapete não abre visita
    assert g.alimentar(cena(coco=True), 330, rec, [((0.0, 0.0, 0.2, 0.2), "p1")], []) == []
    print("banheiro por visita: xixi/cocô só depois de pisar no tapete, luz e manchas antigas não contam, pessoa limpa: ok")


test_banheiro_por_visita()


def test_contorno_livre():
    from pets_agent.catalogo import Catalogo, cobertura, mascara
    from pets_agent import varredura as V

    # triângulo no canto superior esquerdo do retângulo: o canto de baixo à direita está FORA do objeto
    tri = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
    zona = (0.2, 0.2, 0.2, 0.2, tri)
    assert cobertura(zona, (0.2, 0.2, 0.4, 0.4)) > 0.99                        # cobre tudo
    assert cobertura(zona, (0.33, 0.33, 0.4, 0.4)) < 0.05                      # só o canto de fora: não conta
    assert cobertura((0.2, 0.2, 0.2, 0.2), (0.33, 0.33, 0.4, 0.4)) > 0.1      # no retângulo, esse canto contaria
    m = mascara(tri, (40, 60))
    assert m[2, 2] == 255 and m[37, 55] == 0

    class Pal: pet_id = "p1"
    class DB:
        l = []
        def enviar_foto(s, c, b): pass
        def evento_banheiro(s, r): s.l.append(r)
    v = V.Varredura.__new__(V.Varredura)
    v.cfg = {"largura_foto": 960, "proteger_pessoas": False}; v.db = DB(); v.notificador = None; v.ultima_agua = {}; v.caixa_agua = {}
    v.pets = [{"id": "p1", "nome": "Mavi"}]
    # vasilha marcada com contorno livre: [x, y] absolutos (0 a 1); o bicho no canto vazio do retângulo não bebeu
    v.zonas = {"c": [{"tipo": "bebedouro", "x": 0.2, "y": 0.2, "w": 0.2, "h": 0.2, "poligono": [[0.2, 0.2], [0.4, 0.2], [0.2, 0.4]]}]}
    f = np.zeros((200, 200, 3), np.uint8)
    v.vigiar_agua("c", "Sala", f, [(Deteccao("dog", 0.9, (68, 68, 150, 150)), Pal())])  # só o canto de fora (0.34-0.75)
    assert not v.db.l
    v.vigiar_agua("c", "Sala", f, [(Deteccao("dog", 0.9, (40, 40, 90, 90)), Pal())])    # em cima da vasilha
    assert [e["tipo"] for e in v.db.l] == ["agua"]

    # reconhecimento pelo contorno: o fundo dentro do retângulo mas fora do contorno muda e a vasilha ainda é achada
    class DB2:
        def enviar_foto(s, c, b): pass
        def objeto(s, i, c): pass
        def baixar_snapshot(s, c): raise RuntimeError("sem banco")
    with tempfile.TemporaryDirectory() as d:
        cat = Catalogo(DB2(), Path(d))
        pol = [[0.2, 0.5], [0.3, 0.5], [0.2, 0.62]]  # triângulo na vasilha
        cat.sincronizar([{"id": "o1", "tipo": "bebedouro", "pet_id": "p1", "camera_id": "A", "x": 0.2, "y": 0.5, "w": 0.1, "h": 0.12, "poligono": pol}])
        cena1 = _cenario(1, [(128, 180, 1.0)])
        cat.aprender("A", cena1, [])
        assert cat.objetos["o1"].dia is not None and cat.objetos["o1"].dia.mask is not None
        cena2 = _cenario(1, [(148, 190, 1.0)])
        cena2[190 + 25 : 190 + 43, 148 + 40 : 148 + 64] = 255   # a ponta de fora do contorno mudou (outro objeto encostado)
        cat.atualizar("A", cena2, [], False, 1000)
        assert abs(cat.caixas("A", "bebedouro")[0][0] - 148 / 640) < 0.03
    print("contorno livre: só a área marcada conta (eventos e reconhecimento): ok")


test_contorno_livre()


def test_descrever_rtsp():
    import hashlib, re, socket, threading
    from pets_agent.__main__ import _descrever

    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(5)
    porta = srv.getsockname()[1]
    md5 = lambda t: hashlib.md5(t.encode()).hexdigest()

    def servir():
        for _ in range(5):
            c, _a = srv.accept()
            req = c.recv(4096).decode()
            url = re.search(r"DESCRIBE (\S+)", req).group(1)
            if "/stream2" in url:
                c.sendall(b"RTSP/1.0 404 Stream Not Found\r\nCSeq: 1\r\n\r\n")
            elif "Authorization" not in req:
                c.sendall(b'RTSP/1.0 401 Unauthorized\r\nCSeq: 1\r\nWWW-Authenticate: Digest realm="cam", nonce="abc123"\r\n\r\n')
            else:
                esperado = md5(f"{md5('igor:cam:segredo')}:abc123:{md5('DESCRIBE:' + url)}")
                if esperado in req:
                    corpo = "v=0\r\nm=video 0 RTP/AVP 96\r\na=rtpmap:96 H265/90000\r\n"
                    c.sendall(f"RTSP/1.0 200 OK\r\nCSeq: 2\r\nContent-Length: {len(corpo)}\r\n\r\n{corpo}".encode())
                else:
                    c.sendall(b"RTSP/1.0 401 Unauthorized\r\nCSeq: 2\r\n\r\n")
            c.close()

    threading.Thread(target=servir, daemon=True).start()
    r = _descrever("127.0.0.1", porta, "/stream1", "igor", "segredo")
    assert "200" in r["status"] and r["login"] == "Digest" and any("H265" in f for f in r["formatos"]), r
    assert "401" in _descrever("127.0.0.1", porta, "/stream1", "igor", "errada")["status"]
    assert "404" in _descrever("127.0.0.1", porta, "/stream2")["status"]
    assert "sem resposta" in _descrever("127.0.0.1", 9, "/stream1", timeout=1)["status"]
    print("sondar mostra o que a câmera responde (login, 404, formato do vídeo): ok")


test_descrever_rtsp()


def test_tocar_rtsp():
    import socket, threading
    from pets_agent.__main__ import _tocar

    def servidor(manda_video: bool):
        srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(5)

        def conexao(c):
            c.settimeout(5)
            try:
                while True:
                    req = c.recv(4096).decode()
                    if not req:
                        return
                    metodo = req.split(" ", 1)[0]
                    if "Authorization" not in req:
                        c.sendall(b'RTSP/1.0 401 Unauthorized\r\nCSeq: 1\r\nWWW-Authenticate: Digest realm="cam", nonce="n1"\r\n\r\n')
                    elif metodo == "DESCRIBE":
                        corpo = "v=0\r\nm=video 0 RTP/AVP 96\r\na=rtpmap:96 H264/90000\r\na=control:track1\r\n"
                        c.sendall(f"RTSP/1.0 200 OK\r\nCSeq: 2\r\nContent-Base: rtsp://x/stream1/\r\nContent-Length: {len(corpo)}\r\n\r\n{corpo}".encode())
                    elif metodo == "SETUP":
                        assert "track1" in req
                        c.sendall(b"RTSP/1.0 200 OK\r\nCSeq: 3\r\nSession: 99;timeout=60\r\nTransport: RTP/AVP/TCP;interleaved=0-1\r\n\r\n")
                    elif metodo == "PLAY":
                        c.sendall(b"RTSP/1.0 200 OK\r\nCSeq: 4\r\nSession: 99\r\n\r\n")
                        if manda_video:
                            for _ in range(20):
                                c.sendall(b"$\x00\x01\x00" + b"x" * 256)
            except Exception:
                pass
            finally:
                c.close()

        def laco():
            while True:
                c, _a = srv.accept()
                threading.Thread(target=conexao, args=(c,), daemon=True).start()

        threading.Thread(target=laco, daemon=True).start()
        return srv.getsockname()[1]

    assert "VÍDEO CHEGANDO" in _tocar("127.0.0.1", servidor(True), "/stream1", "igor", "segredo", segundos=1)
    assert "mandou só" in _tocar("127.0.0.1", servidor(False), "/stream1", "igor", "segredo", segundos=1)
    assert "não conectou" in _tocar("127.0.0.1", 9, "/stream1")
    print("sondar conta o vídeo que chega depois do PLAY: ok")


test_tocar_rtsp()


def test_onvif():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from pets_agent.__main__ import _onvif

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            corpo = self.rfile.read(int(self.headers["Content-Length"])).decode()
            if "GetCapabilities" in corpo:
                r = "<tt:XAddr>http://10.9.9.9:%d/onvif/media</tt:XAddr>" % self.server.server_port
            elif "GetProfiles" in corpo:
                r = '<trt:Profiles token="P1"><tt:Encoding>H265</tt:Encoding></trt:Profiles>'
            else:
                assert "Username" in corpo and "P1" in corpo
                r = "<tt:Uri>rtsp://192.168.18.10:8554/ch1</tt:Uri>"
            self.send_response(200); self.end_headers(); self.wfile.write(r.encode())

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    linhas = _onvif("127.0.0.1", srv.server_port, "igor", "segredo")
    assert any("rtsp://192.168.18.10:8554/ch1" in l and "H265" in l for l in linhas), linhas
    print("sondar pergunta o endereço RTSP por ONVIF: ok")


test_onvif()
