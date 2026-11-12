"""Intermediário RTSP local que entra na câmera com login Basic.

Algumas Mercusys oferecem Basic e Digest, mas recusam toda resposta Digest, mesmo com a senha certa, e o ffmpeg
(OpenCV) sempre responde o Digest. Com camera.N.auth=basic o OpenCV fala com este intermediário em 127.0.0.1: ele
repassa a conexão para a câmera sem mudar nada, só troca o endereço na linha de cada pedido RTSP e acrescenta
"Authorization: Basic", então a câmera nem pede login. Os quadros intercalados ($, RTP/RTCP por TCP) e as respostas
da câmera passam como estão. É a mesma técnica do launcher da TV (RtspBasicProxy.java).
"""
import base64
import logging
import socket
import threading
from urllib.parse import urlsplit

log = logging.getLogger(__name__)
_rodando: dict[tuple, "_Intermediario"] = {}
_trava = threading.Lock()


def url_para(url: str, usuario: str, senha: str) -> str:
    """Endereço que o OpenCV deve abrir: o do intermediário (iniciado no primeiro uso) com o mesmo caminho."""
    with _trava:
        chave = (url, usuario, senha)
        p = _rodando.get(chave)
        if p is None:
            p = _rodando[chave] = _Intermediario(url, usuario, senha)
    return p.local + url[len(p.real):]


class _Intermediario:
    def __init__(self, url: str, usuario: str, senha: str):
        u = urlsplit(url)
        self.host, self.porta = u.hostname, u.port or 554
        self.real = f"rtsp://{u.netloc}"
        token = base64.b64encode(f"{usuario}:{senha}".encode()).decode()
        self.auth = f"Authorization: Basic {token}\r\n".encode()
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(4)
        self.local = f"rtsp://127.0.0.1:{self.srv.getsockname()[1]}"
        threading.Thread(target=self._aceitar, daemon=True).start()

    def _aceitar(self):
        while True:
            cli, _ = self.srv.accept()
            threading.Thread(target=self._repassar, args=(cli,), daemon=True).start()

    def _repassar(self, cli: socket.socket):
        try:
            cam = socket.create_connection((self.host, self.porta), 8)
            cam.settimeout(None)
        except OSError as e:
            log.warning("rtsp_basic: não conectou em %s:%s (%s)", self.host, self.porta, e)
            cli.close()
            return

        def volta():
            try:
                while dados := cam.recv(65536):
                    cli.sendall(dados)
            except OSError:
                pass
            finally:
                cli.close()
                cam.close()

        threading.Thread(target=volta, daemon=True).start()
        try:
            self._pedidos(cli.makefile("rb"), cam)
        except (OSError, ValueError):
            pass
        finally:
            cli.close()
            cam.close()

    def _pedidos(self, entrada, cam: socket.socket):
        """Do OpenCV para a câmera: pedidos RTSP reescritos, quadros $ copiados como estão."""
        local, real = self.local.encode(), self.real.encode()
        while True:
            primeiro = entrada.read(1)
            if not primeiro:
                return
            if primeiro == b"$":
                cab = entrada.read(3)
                corpo = entrada.read(int.from_bytes(cab[1:3], "big"))
                cam.sendall(b"$" + cab + corpo)
                continue
            linhas = [primeiro + entrada.readline()]
            while True:
                linha = entrada.readline()
                if not linha:
                    return
                if linha in (b"\r\n", b"\n"):
                    break
                linhas.append(linha)
            linhas[0] = linhas[0].replace(local, real, 1)
            tamanho = 0
            saida = [linhas[0]]
            for linha in linhas[1:]:
                minus = linha.lower()
                if minus.startswith(b"authorization:"):
                    continue
                if minus.startswith(b"content-length:"):
                    tamanho = int(linha.split(b":", 1)[1].strip() or 0)
                saida.append(linha)
            msg = b"".join(saida) + self.auth + b"\r\n"
            if tamanho:
                msg += entrada.read(tamanho)
            cam.sendall(msg)
