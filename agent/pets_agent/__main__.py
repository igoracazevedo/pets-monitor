import argparse
import time
from pathlib import Path

import cv2

from . import capture, config
from .identify import caracteristica, criar_perfil
from .store import Supabase


def _detector(cfg):
    from .detect import Detector

    d = cfg["deteccao"]
    return Detector(d["modelo"], d["confianca_minima"], d["tamanho"])


def cmd_testar(args):
    cfg = config.carregar(args.config)
    cam = next((c for c in cfg["cameras"] if c["nome"].lower() == args.camera.lower()), None)
    if not cam:
        raise SystemExit("Câmera não encontrada no config.yaml. Disponíveis: " + ", ".join(c["nome"] for c in cfg["cameras"]))
    frame = capture.capturar(cam)
    saida = Path(f"teste-{cam['nome']}.jpg")
    cv2.imwrite(str(saida), frame)
    print(f"Quadro salvo em {saida} ({frame.shape[1]}x{frame.shape[0]})")
    dets = _detector(cfg).detectar(frame)
    for d in dets:
        print(f"  {d.especie} {d.confianca:.0%} caixa={d.caixa}")
    if not dets:
        print("  nenhum cachorro/gato neste quadro")


def cmd_ensinar(args):
    """Lê fotos em fotos/<nome do pet>/*.jpg, calcula a cor de cada um e guarda o perfil no Supabase."""
    cfg = config.carregar(args.config)
    db = Supabase()
    detector = _detector(cfg)
    existentes = {p["nome"].lower(): p for p in db.pets()}
    raiz = Path(args.pasta)
    pastas = [p for p in sorted(raiz.iterdir()) if p.is_dir()] if raiz.exists() else []
    if not pastas:
        raise SystemExit(f"Crie a pasta {raiz}/<nome do pet>/ e coloque 5 a 15 fotos de cada um (de preferência sozinho na foto).")
    for pasta in pastas:
        feats = []
        for foto in sorted(list(pasta.glob("*.jpg")) + list(pasta.glob("*.jpeg")) + list(pasta.glob("*.png"))):
            img = cv2.imread(str(foto))
            if img is None:
                continue
            dets = detector.detectar(img)
            if dets:
                feats.append(caracteristica(img, dets[0].caixa))
            else:
                h, w = img.shape[:2]
                feats.append(caracteristica(img, (0, 0, w, h)))  # foto de perto sem detecção: usa a foto toda
        if not feats:
            print(f"{pasta.name}: nenhuma foto utilizável")
            continue
        pet = existentes.get(pasta.name.lower()) or db.criar_pet(pasta.name)
        db.salvar_perfil(pet["id"], criar_perfil(feats))
        print(f"{pasta.name}: perfil salvo com {len(feats)} foto(s)")


def _caixa_do_pet(dets, porte):
    """Foto com os dois cães: o grande é o de maior caixa, o pequeno o de menor."""
    if len(dets) == 1 or porte not in ("grande", "pequeno"):
        return dets[0].caixa
    area = lambda d: d.caixa[2] * d.caixa[3]
    return (max(dets, key=area) if porte == "grande" else min(dets, key=area)).caixa


def aprender_do_site(db, detector) -> int:
    """Refaz o perfil dos pets cujas fotos foram alteradas no site. Retorna quantos pets foram atualizados."""
    import numpy as np

    feitos = 0
    for pet in db.pets_para_reaprender():
        feats = []
        for f in db.fotos_do_pet(pet["id"]):
            try:
                img = cv2.imdecode(np.frombuffer(db.baixar_foto_pet(f["path"]), np.uint8), cv2.IMREAD_COLOR)
            except Exception as e:
                print(f"  {pet['nome']}: foto ignorada ({e})")
                continue
            if img is None:
                continue
            dets = detector.detectar(img)
            if dets:
                feats.append(caracteristica(img, _caixa_do_pet(dets, pet.get("porte"))))
            else:
                h, w = img.shape[:2]
                feats.append(caracteristica(img, (0, 0, w, h)))
        db.salvar_perfil(pet["id"], criar_perfil(feats) if feats else None)
        print(f"{pet['nome']}: perfil atualizado com {len(feats)} foto(s) do site")
        feitos += 1
    return feitos


def cmd_sincronizar(args):
    cfg = config.carregar(args.config)
    n = aprender_do_site(Supabase(), _detector(cfg))
    print("Nada novo no site." if n == 0 else f"{n} pet(s) atualizado(s).")


def cmd_varrer(args):
    from .varredura import Varredura

    cfg = config.carregar(args.config)
    db = Supabase()
    v = Varredura(cfg, db, _detector(cfg))
    if not v.pets:
        print("Aviso: nenhum pet cadastrado. Rode primeiro: python -m pets_agent ensinar")
    if args.uma_vez:
        for linha in v.todas():
            print(linha)
        return
    print(f"Varrendo {len(v.cameras)} câmera(s) a cada {cfg['intervalo_s']} s. Ctrl+C para parar.")
    ultimo_sync = 0.0
    while True:
        ini = time.time()
        try:
            if ini - ultimo_sync > 120:  # fotos novas enviadas pelo site entram sozinhas
                ultimo_sync = ini
                if aprender_do_site(db, v.detector):
                    v.recarregar_pets()
            for linha in v.todas():
                print(time.strftime("%H:%M:%S"), linha, flush=True)
        except Exception as e:  # nunca morre por um erro isolado
            print("Erro na varredura:", e, flush=True)
        time.sleep(max(1.0, cfg["intervalo_s"] - (time.time() - ini)))


def main():
    p = argparse.ArgumentParser(prog="pets_agent", description="Monitor de pets pelas câmeras de casa")
    p.add_argument("--config", help="caminho do config.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("testar", help="tira um quadro de uma câmera e mostra o que o detector achou")
    t.add_argument("camera")
    t.set_defaults(fn=cmd_testar)
    e = sub.add_parser("ensinar", help="gera o perfil de cor de cada pet a partir de fotos")
    e.add_argument("--pasta", default="fotos")
    e.set_defaults(fn=cmd_ensinar)
    sy = sub.add_parser("sincronizar", help="aprende com as fotos enviadas pelo site")
    sy.set_defaults(fn=cmd_sincronizar)
    r = sub.add_parser("varrer", help="varre as câmeras (contínuo, ou --uma-vez)")
    r.add_argument("--uma-vez", action="store_true")
    r.set_defaults(fn=cmd_varrer)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
