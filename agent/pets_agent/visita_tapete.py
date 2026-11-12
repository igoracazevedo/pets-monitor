"""Banheiro por VISITA: só existe xixi/cocô quando um bicho pisou no tapete.

O jeito antigo (banheiro.py) olhava o tapete a cada imagem e dizia o "estado" (limpo/xixi/coco) pelo exemplo ensinado mais
parecido. Como o tapete fica com manchas antigas e a luz muda o dia todo, o estado pulava entre limpo, xixi e coco a cada
poucos minutos, e cada pulo virava um evento falso.

Aqui o evento nasce da visita:
1. enquanto o tapete está livre, a última imagem livre é a referência ("antes");
2. um cachorro/gato em cima do tapete abre a visita (anota quem é);
3. quando o tapete fica livre de novo (2 imagens seguidas), compara "antes" e "depois" só na área do tapete:
   - cocô = manchas NOVAS pequenas e bem escuras;
   - xixi = mancha NOVA amarelada e difusa;
   - nada novo = o bicho só passou (sem evento).
4. uma pessoa em cima do tapete que deixa menos sujeira do que antes = "limpo".
Antes e depois ficam a poucos minutos um do outro, então a luz quase não muda, e as manchas antigas se cancelam.
"""
from collections import Counter
from dataclasses import dataclass, field

import cv2
import numpy as np

LARGURA = 320            # o tapete é comparado nesta largura
MARGEM = 0.04            # folga em volta da área marcada (o tapete escorrega um pouco)
LIVRES_PARA_FECHAR = 2   # imagens seguidas sem ninguém no tapete para encerrar a visita
VISITA_MAX_S = 3 * 3600  # visita mais longa que isso (dormindo em cima) é encerrada sem comparar
REF_MAX_S = 40 * 60      # referência mais velha que isso: a luz pode ter mudado demais; compara mesmo assim, com mais rigor


@dataclass
class Resultado:
    xixi: bool = False
    coco: bool = False
    limpo: bool = False
    medidas: dict = field(default_factory=dict)

    @property
    def tipos(self) -> list[str]:
        return [t for t in ("coco", "xixi", "limpo") if getattr(self, t)]


def cortar(img: np.ndarray, recorte, margem: float = MARGEM) -> np.ndarray:
    h, w = img.shape[:2]
    if not recorte:
        return img
    x, y, rw, rh = recorte
    x1, y1 = max(0, int((x - margem) * w)), max(0, int((y - margem) * h))
    x2, y2 = min(w, int((x + rw + margem) * w)), min(h, int((y + rh + margem) * h))
    return img[y1:y2, x1:x2] if x2 - x1 > 16 and y2 - y1 > 16 else img


def _pequena(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    return cv2.resize(img, (LARGURA, max(16, int(h * LARGURA / w))), interpolation=cv2.INTER_AREA)


def _alinhar(antes: np.ndarray, depois: np.ndarray) -> tuple[np.ndarray, float]:
    """Encaixa o 'depois' no 'antes' (o tapete escorrega quando o bicho pisa). -> (depois alinhado, correlação 0..1)."""
    a = cv2.GaussianBlur(cv2.cvtColor(antes, cv2.COLOR_BGR2GRAY), (5, 5), 0).astype(np.float32)
    b = cv2.GaussianBlur(cv2.cvtColor(depois, cv2.COLOR_BGR2GRAY), (5, 5), 0).astype(np.float32)
    m = np.eye(2, 3, dtype=np.float32)
    try:
        cc, m = cv2.findTransformECC(a, b, m, cv2.MOTION_EUCLIDEAN, (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-4), None, 5)
    except cv2.error:
        return depois, 0.0
    if abs(m[0, 2]) > 0.2 * antes.shape[1] or abs(m[1, 2]) > 0.2 * antes.shape[0]:
        return depois, float(cc)  # "encaixe" absurdo: fica sem alinhar
    h, w = antes.shape[:2]
    return cv2.warpAffine(depois, m, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE), float(cc)


def _manchas(mascara: np.ndarray, min_frac: float, max_frac: float = 1.0) -> list[int]:
    n, _, stats, _ = cv2.connectedComponentsWithStats(mascara.astype(np.uint8))
    total = mascara.size
    return [int(stats[i, cv2.CC_STAT_AREA]) for i in range(1, n) if min_frac * total <= stats[i, cv2.CC_STAT_AREA] <= max_frac * total]


def sujeira(img_lab: np.ndarray) -> tuple[float, float]:
    """Quanto do tapete está amarelado (xixi) e quanto está escuro (cocô), em fração da área; serve para ver se limparam."""
    L, b = img_lab[..., 0], img_lab[..., 2]
    amarelo = (b - np.median(b)) > 9
    escuro = L < 0.45 * np.median(L)
    return float(amarelo.mean()), float(escuro.mean())


def comparar(antes_img: np.ndarray, depois_img: np.ndarray, recorte, rigor: float = 1.0) -> Resultado:
    """O que apareceu no tapete entre 'antes' e 'depois' (imagens inteiras da câmera; `recorte` = área do tapete 0..1)."""
    a = _pequena(cortar(antes_img, recorte))
    d = _pequena(cortar(depois_img, recorte))
    if d.shape != a.shape:
        d = cv2.resize(d, (a.shape[1], a.shape[0]))
    d, cc = _alinhar(a, d)
    la = cv2.cvtColor(cv2.GaussianBlur(a, (3, 3), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
    ld = cv2.cvtColor(cv2.GaussianBlur(d, (3, 3), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
    # tira a mudança geral de luz: brilho em proporção, cor em deslocamento
    ld[..., 0] *= np.median(la[..., 0]) / max(1.0, float(np.median(ld[..., 0])))
    for k in (1, 2):
        ld[..., k] += np.median(la[..., k]) - np.median(ld[..., k])
    dL, db = ld[..., 0] - la[..., 0], ld[..., 2] - la[..., 2]
    k3 = np.ones((3, 3), np.uint8)

    # cocô: ficou bem mais escuro E é escuro de verdade (não sombra leve), em manchinhas pequenas
    escuro = (dL < -35 * rigor) & (ld[..., 0] < 0.55 * np.median(ld[..., 0]))
    escuro = cv2.morphologyEx(escuro.astype(np.uint8), cv2.MORPH_OPEN, k3)
    pedacos = _manchas(escuro, 0.00015, 0.03)

    # xixi: ficou mais amarelado, sem escurecer muito; uma mancha razoável (difusa: fecha os buracos antes de medir)
    amarelo = (db > 7 * rigor) & (dL > -40)
    amarelo = cv2.morphologyEx(amarelo.astype(np.uint8), cv2.MORPH_OPEN, k3)
    amarelo = cv2.morphologyEx(amarelo, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    poças = _manchas(amarelo, 0.006 * rigor)

    sa, sd = sujeira(la), sujeira(ld)
    r = Resultado(
        # além da diferença, o tapete precisa ter MAIS escuro / MAIS amarelo do que antes (luz mudando não conta)
        coco=bool(pedacos) and sum(pedacos) / escuro.size < 0.05 and sd[1] > sa[1] + 0.0003,
        xixi=bool(poças) and sd[0] > sa[0] + 0.003,
        medidas={"alinhamento": round(cc, 3), "coco_area": round(sum(pedacos) / escuro.size, 4), "coco_n": len(pedacos),
                 "xixi_area": round(max(poças, default=0) / amarelo.size, 4), "amarelo_antes": round(sa[0], 4), "amarelo_depois": round(sd[0], 4),
                 "escuro_antes": round(sa[1], 4), "escuro_depois": round(sd[1], 4)},
    )
    if cc < 0.5:  # imagens que nem se encaixam (câmera mexeu, tapete trocado de lugar): não arrisca dizer xixi/cocô
        r.xixi = r.coco = False
    return r


def ficou_limpo(antes_img: np.ndarray, depois_img: np.ndarray, recorte) -> bool:
    """Depois de uma pessoa no tapete: a sujeira (amarelo + escuro) caiu bem? = trocaram/limparam o tapete."""
    sa = sujeira(cv2.cvtColor(_pequena(cortar(antes_img, recorte)), cv2.COLOR_BGR2LAB).astype(np.float32))
    sd = sujeira(cv2.cvtColor(_pequena(cortar(depois_img, recorte)), cv2.COLOR_BGR2LAB).astype(np.float32))
    antes, depois = sa[0] + 3 * sa[1], sd[0] + 3 * sd[1]
    return antes > 0.02 and depois < 0.35 * antes


def no_tapete(caixa_rel, recorte, minimo: float = 0.25) -> bool:
    """Caixa (x1, y1, x2, y2 de 0 a 1) com pelo menos `minimo` da área dentro do tapete (ou cobrindo boa parte dele)."""
    if not recorte:
        return False
    x, y, w, h = recorte
    x1, y1, x2, y2 = caixa_rel
    ix = max(0.0, min(x2, x + w) - max(x1, x))
    iy = max(0.0, min(y2, y + h) - max(y1, y))
    inter = ix * iy
    area = max(1e-6, (x2 - x1) * (y2 - y1))
    return inter / area >= minimo or inter / max(1e-6, w * h) >= 0.3


class VigiaTapete:
    """Estado de uma câmera de banheiro. Alimente com as imagens EM ORDEM de horário (segunda leitura)."""

    def __init__(self):
        self.ref = None          # última imagem com o tapete livre
        self.ref_ts = 0.0
        self.visita = None       # {"inicio", "quem": Counter, "pessoa": bool, "bicho": bool, "livres": int, "ultima_livre"}

    def alimentar(self, frame: np.ndarray, ts: float, recorte, bichos: list[tuple[tuple, str | None]], pessoas: list[tuple]) -> list[dict]:
        """bichos = [(caixa 0..1, pet_id ou None)], pessoas = [caixa 0..1]. -> eventos [{"tipo", "pet_id", "ts", "medidas"}]."""
        em_cima = [(c, p) for c, p in bichos if no_tapete(c, recorte)]
        gente = [c for c in pessoas if no_tapete(c, recorte, 0.15)]
        ocupado = bool(em_cima or gente)
        v = self.visita
        if ocupado:
            if v is None:
                if self.ref is None:
                    return []  # ainda sem referência do tapete livre: espera a próxima visita
                v = self.visita = {"inicio": ts, "quem": Counter(), "pessoa": False, "bicho": False, "livres": 0}
            v["livres"] = 0
            v["bicho"] = v["bicho"] or bool(em_cima)
            v["pessoa"] = v["pessoa"] or bool(gente)
            v["quem"].update(p for _, p in em_cima if p)
            if em_cima and v.get("frame") is None:
                v["frame"] = frame  # a imagem do bicho no tapete vai na foto do evento
            if ts - v["inicio"] > VISITA_MAX_S:  # dormiu no tapete: recomeça do zero
                self.visita, self.ref = None, None
            return []
        if v is None:
            self.ref, self.ref_ts = frame, ts  # tapete livre e nada acontecendo: referência sempre fresca
            return []
        v["livres"] += 1
        if v["livres"] < LIVRES_PARA_FECHAR:
            return []
        # visita terminou: compara antes x depois
        self.visita = None
        antes, antes_ts = self.ref, self.ref_ts
        self.ref, self.ref_ts = frame, ts
        eventos = []
        if v["pessoa"] and ficou_limpo(antes, frame, recorte):
            return [{"tipo": "limpo", "pet_id": None, "ts": ts, "medidas": {}}]
        if not v["bicho"]:
            return []
        rigor = 1.25 if ts - antes_ts > REF_MAX_S else 1.0
        r = comparar(antes, frame, recorte, rigor)
        quem = v["quem"].most_common(1)[0][0] if v["quem"] else None
        for tipo in ("coco", "xixi"):
            if getattr(r, tipo):
                eventos.append({"tipo": tipo, "pet_id": quem, "ts": v["inicio"], "medidas": r.medidas, "frame_visita": v.get("frame")})
        return eventos
