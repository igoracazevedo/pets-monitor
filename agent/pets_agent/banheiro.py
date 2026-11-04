"""Banheiro dos cachorros: reconhece xixi e coco no tapete comparando a imagem de agora com uma foto do tapete LIMPO.
Aprende com os exemplos que você manda pelo app ("limpo no Banheiro", "xixi no Banheiro", "coco no Banheiro"): cada exemplo é uma foto guardada."""
import cv2
import numpy as np

ROTULOS = ("limpo", "xixi", "coco")
MAX_POR_ROTULO = 12
DIST_MAX = 0.9  # mais longe que isso de qualquer exemplo = "não sei" (luz mudou, câmera mexeu...)


def cortar(img: np.ndarray, recorte) -> np.ndarray:
    """Só a região marcada como banheiro (x, y, largura, altura de 0 a 1); sem região, a imagem inteira."""
    if not recorte:
        return img
    h, w = img.shape[:2]
    x, y, rw, rh = recorte
    x1, y1, x2, y2 = max(0, int(x * w)), max(0, int(y * h)), min(w, int((x + rw) * w)), min(h, int((y + rh) * h))
    return img[y1:y2, x1:x2] if x2 - x1 > 8 and y2 - y1 > 8 else img


def _pequena(img: np.ndarray, largura: int = 320) -> np.ndarray:
    h, w = img.shape[:2]
    img = cv2.resize(img, (largura, max(8, int(h * largura / w))), interpolation=cv2.INTER_AREA)
    return cv2.GaussianBlur(img, (5, 5), 0)


def caracteristicas(base: np.ndarray, atual: np.ndarray) -> np.ndarray:
    """O que mudou em relação ao tapete limpo: quanto, quantas manchas e de que cor (claro/escuro, amarelado, avermelhado)."""
    a = _pequena(base)
    b = _pequena(atual)
    if b.shape != a.shape:
        b = cv2.resize(b, (a.shape[1], a.shape[0]))
    la = cv2.cvtColor(a, cv2.COLOR_BGR2LAB).astype(np.float32)
    lb = cv2.cvtColor(b, cv2.COLOR_BGR2LAB).astype(np.float32)
    d = lb - la
    d -= np.median(d.reshape(-1, 3), axis=0)  # tira a mudança geral de luz
    mag = np.sqrt((d**2).sum(axis=2))
    mascara = (mag > 14).astype(np.uint8)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    total = mascara.size
    n, _, stats, _ = cv2.connectedComponentsWithStats(mascara)
    areas = [stats[i, cv2.CC_STAT_AREA] for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= 0.002 * total]
    if not areas:
        return np.zeros(7, np.float32)
    ocupado = mascara > 0
    dl, da, db = (float(d[..., k][ocupado].mean()) for k in range(3))
    return np.array([
        min(1.0, sum(areas) / total * 10), min(len(areas), 6) / 6, min(1.0, max(areas) / total * 10),
        dl / 40, da / 40, db / 40, float(lb[..., 0][ocupado].mean()) / 255,
    ], np.float32)


class Banheiro:
    """Guarda os exemplos de cada câmera-banheiro e diz o estado do tapete: limpo, xixi ou coco."""

    def __init__(self, db):
        self.db = db
        self.cache: dict[str, dict] = {}

    def _imagem(self, caminho: str) -> np.ndarray | None:
        return cv2.imdecode(np.frombuffer(self.db.baixar_snapshot(caminho), np.uint8), cv2.IMREAD_COLOR)

    def carregar(self, cid: str, recorte=None):
        linhas = sorted(self.db.banheiro_amostras(cid), key=lambda r: r["created_at"])
        por_rotulo: dict[str, list] = {r: [] for r in ROTULOS}
        for l in linhas:
            if l["rotulo"] in por_rotulo:
                por_rotulo[l["rotulo"]].append(l)
        imagens = {}
        for r, ls in por_rotulo.items():
            for l in ls[-MAX_POR_ROTULO:]:
                try:
                    img = self._imagem(l["snapshot_path"])
                    if img is not None:
                        imagens.setdefault(r, []).append(img)
                except Exception:
                    pass
        self.cache[cid] = {**self._montar(imagens, recorte), "recorte": recorte}

    @staticmethod
    def _montar(imagens: dict[str, list], recorte=None) -> dict:
        limpas = imagens.get("limpo") or []
        base = cortar(limpas[-1], recorte) if limpas else None  # o "limpo" mais recente é a referência
        exemplos = []
        if base is not None:
            for r, imgs in imagens.items():
                for img in imgs:
                    exemplos.append((r, caracteristicas(base, cortar(img, recorte))))
        return {"base": base, "exemplos": exemplos}

    def pronto(self, cid: str) -> bool:
        c = self.cache.get(cid)
        return bool(c and c["base"] is not None and any(r in ("xixi", "coco") for r, _ in c["exemplos"]))

    def classificar(self, cid: str, frame: np.ndarray, recorte=None):
        """-> (rotulo, distância) ou None quando ainda não há exemplos suficientes. 'desconhecido' = nada parecido com o que já vi."""
        if cid not in self.cache or self.cache[cid].get("recorte") != recorte:
            self.carregar(cid, recorte)
        if not self.pronto(cid):
            return None
        c = self.cache[cid]
        v = caracteristicas(c["base"], cortar(frame, recorte))
        if v[0] < 0.03:  # quase nada mudou
            return "limpo", 0.0
        dist, rot = min((float(np.linalg.norm(v - e)), r) for r, e in c["exemplos"])
        return (rot, dist) if dist <= DIST_MAX else ("desconhecido", dist)

    def ensinar(self, cid: str, rotulo: str, frame: np.ndarray, jpeg_fn) -> str:
        """Guarda o exemplo no banco (foto + rótulo) e recarrega."""
        from datetime import datetime

        caminho = f"banheiro/{cid[:8]}-{rotulo}-{datetime.now():%Y%m%d%H%M%S}.jpg"
        self.db.enviar_foto(caminho, jpeg_fn(frame))
        self.db.nova_amostra_banheiro({"camera_id": cid, "rotulo": rotulo, "snapshot_path": caminho})
        self.cache.pop(cid, None)  # recarrega na próxima leitura
        return caminho
