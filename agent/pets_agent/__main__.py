import argparse
import time
from pathlib import Path

import cv2
import numpy as np

from . import capture, config
from .identify import amostras_de_camera, caracteristica, criar_perfil
from .noturno import eh_noturno
from .store import Supabase


def _detector(cfg):
    from .detect import Detector

    d = cfg["deteccao"]
    return Detector(d["modelo"], d["confianca_minima"], d["tamanho"], d.get("confianca_fraca", 0.3), cfg.get("detectar_pessoas", True), d.get("confianca_pessoa", 0.55))


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


def cmd_ensinar_camera(args):
    """Ensina a aparência de um pet olhando pela câmera onde ele está agora (a cor na câmera difere da do celular)."""
    from .varredura import Varredura, _anotar

    cfg = config.carregar(args.config)
    db = Supabase()
    v = Varredura(cfg, db, _detector(cfg))
    pet_nome = args.pet or input("Nome do pet (ex.: Mavi): ").strip()
    cam_nome = args.camera or input("Nome da câmera onde ele está agora (como aparece na aba Câmeras): ").strip()
    pet = db.pet_por_nome(pet_nome)
    if not pet:
        raise SystemExit(f"Não achei o pet '{pet_nome}'. Cadastre na aba Pets do site.")
    if v.cred:
        v.redescobrir()
    v.atualizar_nomes()
    alvo = next(((c, r) for c, r in v.cameras if r["nome"].lower() == cam_nome.lower()), None)
    if not alvo:
        raise SystemExit("Câmera não encontrada. Disponíveis: " + ", ".join(r["nome"] for _, r in v.cameras))
    c, reg = alvo
    novas = []
    pasta = Path("ensinadas")
    pasta.mkdir(exist_ok=True)
    for i in range(args.quantas):
        try:
            frame = capture.capturar(c)
        except Exception as e:
            print(f"  quadro {i + 1}: sem imagem ({str(e)[:80]})")
            continue
        dets = v.detector.detectar(frame)
        if not dets:
            print(f"  quadro {i + 1}: nenhum cachorro achado")
        else:
            caixa = _caixa_do_pet(dets, pet.get("porte"))
            if len(dets) > 1:
                print(f"  quadro {i + 1}: {len(dets)} animais; usei o de porte '{pet.get('porte') or 'não informado'}'")
            novas.append(caracteristica(frame, caixa))
            cv2.imwrite(str(pasta / f"{pet_nome}-{reg['id'][:6]}-{i + 1}.jpg"), _anotar(frame, [(caixa, pet_nome)]))
            print(f"  quadro {i + 1}: ok")
        time.sleep(1.5)
    if not novas:
        raise SystemExit("Nenhuma amostra tirada. Confirme que o pet está visível nessa câmera e tente de novo.")
    atual = db.pet_por_nome(pet_nome)
    # sem cuidar do que já havia de foto: criar_perfil junta as fotos antigas (hists com origem foto) com as amostras novas
    antigas_foto = [np.array(a["h"], dtype=np.float32) for a in (atual.get("perfil") or {}).get("hists", []) if a.get("o") != "camera"]
    db.salvar_perfil(pet["id"], criar_perfil(antigas_foto, amostras_de_camera(atual.get("perfil")) + novas))
    print(f"{pet_nome}: {len(novas)} amostra(s) nova(s) da câmera '{reg['nome']}'. As imagens usadas estão em {pasta}\\ — confira se a caixa está no pet certo.")


def cmd_verificar(args):
    """Tira uma foto de cada câmera agora, acha os cães e diz quem é quem. Salva as imagens marcadas em verificacao/ (não mexe no histórico do site)."""
    from .varredura import Varredura, _anotar

    cfg = config.carregar(args.config)
    db = Supabase()
    v = Varredura(cfg, db, _detector(cfg))
    if aprender_do_site(db, v.detector):  # fotos enviadas pelo site desde a última vez
        v.recarregar_pets()
    try:
        if aprender_pessoas(db):
            v.carregar_pessoas()
    except Exception as e:
        print("Pessoas (rosto):", e)
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
        cv2.imwrite(str(arq), _anotar(v.proteger(frame), marcas))
        if dets:
            quem = ", ".join(f"{p.nome or 'não identificado'} ({p.como}, {d.confianca:.0%})" for d, p in zip(dets, palpites))
        else:
            quem = "nenhum cachorro/gato"
        print(f"- {rotulo}: {quem}  -> {arq}")


def cmd_ensinar(args):
    """Pasta fotos/<nome do pet>/: cria o pet se não existe e refaz o perfil juntando essas fotos com as enviadas pelo site."""
    cfg = config.carregar(args.config)
    db = Supabase()
    raiz = Path(args.pasta)
    pastas = [p for p in sorted(raiz.iterdir()) if p.is_dir()] if raiz.exists() else []
    if not pastas:
        raise SystemExit(f"Crie a pasta {raiz}/<nome do pet>/ e coloque 5 a 15 fotos de cada um (de preferência sozinho na foto).")
    existentes = {p["nome"].lower() for p in db.pets()}
    for pasta in pastas:
        if pasta.name.lower() not in existentes:
            db.criar_pet(pasta.name)
            print(f"{pasta.name}: pet criado")
    if not aprender_do_site(db, _detector(cfg), str(raiz), todos=True):
        print("Nenhum pet para atualizar.")


def _caixa_do_pet(dets, porte):
    """Foto com os dois cães: o grande é o de maior caixa, o pequeno o de menor."""
    if len(dets) == 1 or porte not in ("grande", "pequeno"):
        return dets[0].caixa
    area = lambda d: d.caixa[2] * d.caixa[3]
    return (max(dets, key=area) if porte == "grande" else min(dets, key=area)).caixa


def aprender_do_site(db, detector, pasta_local: str = "fotos", todos: bool = False) -> int:
    """Refaz o perfil dos pets cujas fotos mudaram no site (ou todos, com todos=True).
    Junta as fotos do site com as da pasta local fotos/<nome do pet>/, para uma fonte não apagar a outra."""
    import numpy as np

    pets = db.pets() if todos else db.pets_para_reaprender()
    feitos = 0
    for pet in pets:
        imagens = []
        for f in db.fotos_do_pet(pet["id"]):
            try:
                imagens.append(cv2.imdecode(np.frombuffer(db.baixar_foto_pet(f["path"]), np.uint8), cv2.IMREAD_COLOR))
            except Exception as e:
                print(f"  {pet['nome']}: foto do site ignorada ({e})")
        pasta = next((p for p in Path(pasta_local).glob("*") if p.is_dir() and p.name.lower() == pet["nome"].lower()), None) if Path(pasta_local).exists() else None
        if pasta:
            for foto in sorted([*pasta.glob("*.jpg"), *pasta.glob("*.jpeg"), *pasta.glob("*.png")]):
                imagens.append(cv2.imread(str(foto)))
        feats, sem_cao, infra = [], 0, 0
        for img in imagens:
            if img is None:
                continue
            if eh_noturno(img):  # infravermelho não tem cor: não serve para o perfil de cor
                infra += 1
                continue
            dets = detector.detectar(img)
            if not dets:  # sem cachorro achado: usar a foto toda sujaria o perfil com o fundo
                sem_cao += 1
                continue
            feats.append(caracteristica(img, _caixa_do_pet(dets, pet.get("porte"))))
        db.salvar_perfil(pet["id"], criar_perfil(feats, amostras_de_camera(pet.get("perfil"))) if (feats or amostras_de_camera(pet.get("perfil"))) else None)
        if sem_cao or infra:
            print(f"  {pet['nome']}: {sem_cao} foto(s) sem cachorro detectado e {infra} de infravermelho foram ignoradas")
        print(f"{pet['nome']}: perfil atualizado: {len(feats)} foto(s) + {len(amostras_de_camera(pet.get('perfil')))} amostra(s) de câmera")
        feitos += 1
    return feitos


def aprender_pessoas(db) -> int:
    """Refaz o 'rosto' das pessoas cadastradas no site cujas fotos mudaram. Usa o maior rosto de cada foto; foto sem rosto é ignorada."""
    import numpy as np

    pendentes = db.pessoas_para_reaprender()
    if not pendentes:
        return 0
    from .rostos import Rostos

    rostos = Rostos()
    for pessoa in pendentes:
        embs, sem_rosto = [], 0
        for f in db.fotos_da_pessoa(pessoa["id"]):
            try:
                img = cv2.imdecode(np.frombuffer(db.baixar_foto_pet(f["path"]), np.uint8), cv2.IMREAD_COLOR)
                e = rostos.maior(img) if img is not None else None
            except Exception as ex:
                print(f"  {pessoa['nome']}: foto ignorada ({ex})")
                e = None
            if e is None:
                sem_rosto += 1
            else:
                embs.append([round(float(v), 5) for v in e])
        db.salvar_rostos(pessoa["id"], embs)
        print(f"{pessoa['nome']}: {len(embs)} rosto(s) aprendido(s)" + (f"; {sem_rosto} foto(s) sem rosto visível foram ignoradas" if sem_rosto else ""))
    return len(pendentes)


def aprender_correcoes(db, rostos=None) -> int:
    """Correções feitas no Histórico ("quem foi encontrado"): a imagem do avistamento vira mais uma amostra do pet/pessoa certo."""
    import numpy as np

    feitas = 0
    for c in db.correcoes_pendentes():
        try:
            img = cv2.imdecode(np.frombuffer(db.baixar_snapshot(c["snapshot_path"]), np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                raise RuntimeError("imagem ilegível")
            h, w = img.shape[:2]
            x1, y1 = int(float(c["x"]) * w), int(float(c["y"]) * h)
            caixa = (x1, y1, x1 + int(float(c["w"]) * w), y1 + int(float(c["h"]) * h))
            if c.get("pet_id"):
                pet = db.pet_por_id(c["pet_id"])
                perfil = (pet or {}).get("perfil") or {}
                antigas_foto = [np.array(a["h"], dtype=np.float32) for a in perfil.get("hists", []) if a.get("o") != "camera"]
                if not antigas_foto and perfil.get("hist"):
                    antigas_foto = [np.array(perfil["hist"], dtype=np.float32)]
                db.salvar_perfil(c["pet_id"], criar_perfil(antigas_foto, amostras_de_camera(perfil) + [caracteristica(img, caixa)]))
                print(f"Correção aprendida: {pet['nome'] if pet else c['pet_id']}", flush=True)
            elif c.get("pessoa_id") and rostos is not None:
                x1, y1, x2, y2 = caixa
                emb = rostos.maior(img[max(0, y1) : y2, max(0, x1) : x2])
                if emb is not None:
                    atuais = db.rostos_das_pessoas().get(c["pessoa_id"], [])
                    db.salvar_rostos(c["pessoa_id"], (atuais + [[round(float(v), 5) for v in emb]])[-40:])
                    print("Correção aprendida: rosto de pessoa", flush=True)
        except Exception as e:
            print(f"  correção ignorada: {e}", flush=True)
        db.correcao_aplicada(c["id"])  # mesmo se falhar, não fica tentando para sempre
        feitas += 1
    return feitas


def cmd_sincronizar(args):
    cfg = config.carregar(args.config)
    db = Supabase()
    n = aprender_do_site(db, _detector(cfg), todos=getattr(args, "todos", False))
    try:
        n += aprender_pessoas(db)
    except Exception as e:
        print("Pessoas (rosto):", e)
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
                try:
                    if aprender_pessoas(db):
                        v.carregar_pessoas()
                    if aprender_correcoes(db, v.rostos):
                        v.recarregar_pets()
                        v.carregar_pessoas()
                except Exception as e:
                    print("Pessoas (rosto) / correções:", e, flush=True)
            if v.precisa_redescobrir():
                print(f"{time.strftime('%H:%M:%S')} procurando câmeras na rede... {v.redescobrir()} Intelbras achada(s)", flush=True)
            pedidos = db.pedidos_pendentes()
            if pedidos:  # "Onde estão agora?" (varredura completa), "Ver ao vivo" (só uma foto de cada câmera) ou teste de aviso
                tipos = {p.get("tipo", "localizar") for p in pedidos}
                if "teste" in tipos and v.notificador:
                    n = v.notificador.enviar("Pets Monitor", "Teste de aviso: está funcionando!", None, "teste")
                    print(time.strftime("%H:%M:%S"), f"[teste] aviso enviado para {n} aparelho(s)", flush=True)
                if "localizar" in tipos:
                    for linha in v.todas(forcar=True):
                        print(time.strftime("%H:%M:%S"), "[pedido]", linha, flush=True)
                    ultima_varredura = time.time()
                elif "fotos" in tipos:
                    ids = {p.get("camera_id") for p in pedidos if p.get("tipo") == "fotos"}
                    print(time.strftime("%H:%M:%S"), f"[fotos] {v.fotos_agora(None if None in ids else ids)} câmera(s)", flush=True)
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
    ec = sub.add_parser("ensinar-camera", help="ensina um pet pela câmera onde ele está agora")
    ec.add_argument("pet", nargs="?", default="")
    ec.add_argument("camera", nargs="?", default="")
    ec.add_argument("--quantas", type=int, default=6)
    ec.set_defaults(fn=cmd_ensinar_camera)
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
    sy.add_argument("--todos", action="store_true", help="refaz o perfil de todos os pets, mesmo sem fotos novas")
    sy.set_defaults(fn=cmd_sincronizar)
    r = sub.add_parser("varrer", help="varre as câmeras (contínuo, ou --uma-vez)")
    r.add_argument("--uma-vez", action="store_true")
    r.set_defaults(fn=cmd_varrer)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
