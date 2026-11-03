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


def cmd_diagnosticar(args):
    """Para cada câmera: o PC alcança? quais portas abrem? o que a foto HTTP responde? (sem usar o detector)"""
    import socket

    import requests
    from requests.auth import HTTPBasicAuth, HTTPDigestAuth

    cfg = config.carregar(args.config)
    cams = [c for c in cfg["cameras"] if not args.camera or c["nome"].lower() == args.camera.lower()]
    for c in cams:
        host = c.get("host") or (c.get("url", "").split("@")[-1].split("/")[0].split(":")[0])
        print(f"\n== {c['nome']} ({host})")
        for porta in (80, 554, 8080, 8000, 443, 37777):
            s = socket.socket()
            s.settimeout(3)
            try:
                s.connect((host, porta))
                print(f"  porta {porta}: ABERTA")
            except Exception as e:
                print(f"  porta {porta}: {type(e).__name__} {str(e)[:60]}")
            finally:
                s.close()
        if c.get("fonte") == "intelbras":
            for nome, auth in (("Digest", HTTPDigestAuth(c["usuario"], c["senha"])), ("Basic", HTTPBasicAuth(c["usuario"], c["senha"]))):
                try:
                    r = requests.get(f"http://{host}/cgi-bin/snapshot.cgi", auth=auth, timeout=(5, 10))
                    print(f"  foto HTTP ({nome}): status {r.status_code}, {len(r.content)} bytes, tipo {r.headers.get('Content-Type')}")
                    if r.ok:
                        break
                except Exception as e:
                    print(f"  foto HTTP ({nome}): {type(e).__name__}: {str(e)[:250]}")


def cmd_descobrir(args):
    """Varre a rede /24 do PC atrás de câmeras Intelbras (porta 37777) e RTSP (554); salva uma foto de cada achada para você ver onde fica."""
    import socket
    from concurrent.futures import ThreadPoolExecutor

    import requests
    from requests.auth import HTTPDigestAuth

    cfg = config.carregar(args.config)
    cams = cfg["cameras"]
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        u.connect(("8.8.8.8", 80))
        meu = u.getsockname()[0]
    finally:
        u.close()
    base = ".".join(meu.split(".")[:3])
    print(f"PC em {meu}; varrendo {base}.1 a {base}.254 (uns 10 s)...")

    def aberta(ip, porta):
        s = socket.socket()
        s.settimeout(1.2)
        try:
            s.connect((ip, porta))
            return True
        except Exception:
            return False
        finally:
            s.close()

    def sonda(i):
        ip = f"{base}.{i}"
        return ip, aberta(ip, 37777), aberta(ip, 554), aberta(ip, 80)

    with ThreadPoolExecutor(64) as ex:
        achados = [r for r in ex.map(sonda, range(1, 255)) if r[1] or r[2]]

    conhecidos = {c.get("host") or c.get("url", "").split("@")[-1].split(":")[0]: c["nome"] for c in cams}
    cred = next((c for c in cams if c.get("fonte") == "intelbras"), None)
    pasta = Path("descobertas")
    pasta.mkdir(exist_ok=True)
    print("\nAparelhos com porta de câmera aberta:")
    for ip, p37777, p554, p80 in achados:
        tipo = "Intelbras" if p37777 else "RTSP"
        nome = conhecidos.get(ip)
        linha = f"  {ip:15} {tipo:9} " + (f"= {nome}" if nome else "NOVO (não está no camera.properties)")
        if cred and p80 and (p37777 or nome is None):
            try:
                r = requests.get(f"http://{ip}/cgi-bin/snapshot.cgi", auth=HTTPDigestAuth(cred["usuario"], cred["senha"]), timeout=(4, 8))
                if r.ok and r.content[:2] == b"\xff\xd8":
                    (pasta / f"{ip}.jpg").write_bytes(r.content)
                    linha += f"  -> foto em descobertas\\{ip}.jpg"
            except Exception:
                pass
        print(linha)
    achados_ip = {a[0] for a in achados}
    sumidas = [(ip, n) for ip, n in conhecidos.items() if ip not in achados_ip]
    if sumidas:
        print("\nCâmeras do arquivo que NÃO apareceram na rede:")
        for ip, n in sumidas:
            print(f"  {n} (antes em {ip})")
    print("\nSe há câmeras NOVAS com foto, abra as fotos para ver qual é cada uma e troque o IP no camera.properties.")


CAMINHOS_RTSP = [
    "/", "/stream1", "/stream2", "/live", "/live/ch0", "/live/ch00_0", "/11", "/12", "/h264", "/h264Preview_01_main", "/h264Preview_01_sub",
    "/Streaming/Channels/101", "/Streaming/Channels/102", "/cam/realmonitor?channel=1&subtype=0", "/cam/realmonitor?channel=1&subtype=1",
    "/onvif1", "/onvif2", "/profile1", "/ch0_0.h264", "/user=admin_password=_channel=1_stream=0.sdp?real_stream", "/av0_0", "/videoMain", "/mpeg4", "/1", "/cam1/h264",
]


def cmd_sondar(args):
    """Câmera genérica: testa os caminhos RTSP mais comuns e diz qual devolve imagem."""
    from urllib.parse import quote

    if not args.ip:
        args.ip = input("IP da câmera (ex.: 192.168.18.10): ").strip()
        args.usuario = input("Usuário da câmera (Enter se não tem): ").strip()
        args.senha = input("Senha da câmera (Enter se não tem): ").strip()
    cred = f"{quote(args.usuario, safe='')}:{quote(args.senha, safe='')}@" if args.usuario else ""
    print(f"Testando {len(CAMINHOS_RTSP)} caminhos em {args.ip}:{args.porta} (uns 5 s cada se não existir)...")
    achou = False
    for c in CAMINHOS_RTSP:
        url = f"rtsp://{cred}{args.ip}:{args.porta}{c}"
        try:
            capture._rtsp(url, descartar=2)
            print(f"  FUNCIONA: {c}")
            print(f"  -> no camera.properties:  camera.N.rtsp=rtsp://{args.ip}:{args.porta}{c}")
            achou = True
            break
        except Exception as e:
            print(f"  {c}: {str(e)[:50]}")
    if not achou:
        print("Nenhum caminho comum funcionou. Veja no manual/app da câmera o endereço RTSP e o usuário/senha da câmera (nem sempre é o mesmo do app).")


def cmd_verificar(args):
    """Tira uma foto de cada câmera agora, acha os cães e diz quem é quem. Salva as imagens marcadas em verificacao/ (não mexe no histórico do site)."""
    from .varredura import Varredura, _anotar

    cfg = config.carregar(args.config)
    db = Supabase()
    v = Varredura(cfg, db, _detector(cfg))
    if aprender_do_site(db, v.detector):  # fotos enviadas pelo site desde a última vez
        v.recarregar_pets()
    if v.cred:
        print(f"{v.redescobrir()} câmera(s) Intelbras achada(s) na rede.")
    if not v.pets or not any(p.get("perfil") for p in v.pets):
        print("Aviso: nenhum pet com fotos ensinadas ainda; a identificação vai sair como '?'. Envie as fotos na aba Pets do site.")
    pasta = Path("verificacao")
    pasta.mkdir(exist_ok=True)
    for c, reg in v.cameras:
        nome = reg["nome"]
        rotulo = f"{nome} ({c.get('host', '')})".replace(" ()", "")
        try:
            frame = capture.capturar(c)
        except Exception as e:
            print(f"- {rotulo}: SEM IMAGEM ({str(e)[:90]})")
            continue
        dets, palpites = v.analisar(frame, reg["id"], aprender=False)
        marcas = [(d.caixa, f"{p.nome or '?'}") for d, p in zip(dets, palpites)]
        arq = pasta / f"{(c.get('host') or nome).replace('.', '-')}.jpg"
        cv2.imwrite(str(arq), _anotar(frame, marcas))
        if dets:
            quem = ", ".join(f"{p.nome or 'não identificado'} ({p.como}, {d.confianca:.0%})" for d, p in zip(dets, palpites))
        else:
            quem = "nenhum cachorro/gato"
        print(f"- {rotulo}: {quem}  -> {arq}")


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
        if v.cred:
            v.redescobrir()
        for linha in v.todas():
            print(linha)
        return
    if v.cred:
        print(f"Procurando câmeras na rede... {v.redescobrir()} Intelbras achada(s). Dê apelido a cada uma na aba Câmeras do site.")
    print(f"Varrendo {len(v.cameras)} câmera(s) a cada {cfg['intervalo_s']} s. Ctrl+C para parar.")
    ultimo_sync = 0.0
    ultima_varredura = 0.0
    while True:
        ini = time.time()
        try:
            if ini - ultimo_sync > 120:  # fotos novas enviadas pelo site entram sozinhas
                ultimo_sync = ini
                if aprender_do_site(db, v.detector):
                    v.recarregar_pets()
            if v.precisa_redescobrir():
                print(f"{time.strftime('%H:%M:%S')} procurando câmeras na rede... {v.redescobrir()} Intelbras achada(s)", flush=True)
            pedidos = db.pedidos_pendentes()
            if pedidos:  # "Onde estão agora?" (varredura completa) ou "Ver ao vivo" (só uma foto de cada câmera)
                if any(p.get("tipo", "localizar") == "localizar" for p in pedidos):
                    for linha in v.todas(forcar=True):
                        print(time.strftime("%H:%M:%S"), "[pedido]", linha, flush=True)
                    ultima_varredura = time.time()
                else:
                    print(time.strftime("%H:%M:%S"), f"[fotos] {v.fotos_agora()} câmera(s)", flush=True)
                db.atender_pedidos([p["id"] for p in pedidos])
            elif ini - ultima_varredura >= cfg["intervalo_s"]:
                ultima_varredura = ini
                for linha in v.todas():
                    print(time.strftime("%H:%M:%S"), linha, flush=True)
        except Exception as e:  # nunca morre por um erro isolado
            print("Erro na varredura:", e, flush=True)
        time.sleep(2)


def main():
    p = argparse.ArgumentParser(prog="pets_agent", description="Monitor de pets pelas câmeras de casa")
    p.add_argument("--config", help="caminho do config.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("testar", help="tira um quadro de uma câmera e mostra o que o detector achou")
    t.add_argument("camera")
    t.set_defaults(fn=cmd_testar)
    so = sub.add_parser("sondar", help="câmera genérica: descobre o caminho RTSP que funciona")
    so.add_argument("ip", nargs="?", default="")
    so.add_argument("usuario", nargs="?", default="")
    so.add_argument("senha", nargs="?", default="")
    so.add_argument("--porta", type=int, default=554)
    so.set_defaults(fn=cmd_sondar)
    vf = sub.add_parser("verificar", help="uma foto de cada câmera: quem está onde (salva imagens marcadas)")
    vf.set_defaults(fn=cmd_verificar)
    ds = sub.add_parser("descobrir", help="procura as câmeras na rede (quando o IP mudou)")
    ds.set_defaults(fn=cmd_descobrir)
    dg = sub.add_parser("diagnosticar", help="testa a rede de cada câmera (portas e foto HTTP)")
    dg.add_argument("camera", nargs="?")
    dg.set_defaults(fn=cmd_diagnosticar)
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
