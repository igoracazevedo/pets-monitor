"""Espelha o que aparece na janela do iniciar.bat para o Supabase (tabela pm_logs), para ler no app.

Nunca atrapalha a varredura: envia em segundo plano, em lotes, e se a internet cair guarda as linhas e tenta de novo.
"""
import sys
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

MAX_PENDENTES = 2000  # se ficar muito tempo sem enviar, descarta as mais antigas
DIAS_GUARDADOS = 3


class _Espelho:
    def __init__(self, destino, nivel: str, fila: deque):
        self.destino = destino
        self.nivel = nivel
        self.fila = fila
        self.parcial = ""

    def write(self, texto):
        n = self.destino.write(texto)
        self.parcial += texto
        *linhas, self.parcial = self.parcial.split("\n")
        for ln in linhas:
            ln = ln.rstrip("\r")
            if ln.strip():
                self.fila.append((datetime.now(timezone.utc).isoformat(), self._nivel(ln), ln[:500]))
        return n

    def _nivel(self, ln: str) -> str:
        baixo = ln.lower()
        if self.nivel == "erro" or "erro" in baixo or "traceback" in baixo or "falhou" in baixo:
            return "erro"
        return "info"

    def flush(self):
        self.destino.flush()

    def __getattr__(self, nome):  # encoding, isatty etc.
        return getattr(self.destino, nome)


def instalar(db) -> None:
    """Passa a copiar tudo que o programa escreve (print e erros) para o Supabase."""
    fila: deque = deque(maxlen=MAX_PENDENTES)
    sys.stdout = _Espelho(sys.stdout, "info", fila)
    sys.stderr = _Espelho(sys.stderr, "erro", fila)

    def enviar():
        ultima_limpeza = 0.0
        while True:
            time.sleep(3)
            try:
                lote = [fila.popleft() for _ in range(min(len(fila), 200))]
                if lote:
                    try:
                        db._rest("POST", "pm_logs", json=[{"created_at": t, "nivel": n, "linha": ln} for t, n, ln in lote])
                    except Exception:
                        fila.extendleft(reversed(lote))  # tenta de novo no próximo ciclo
                        raise
                if time.time() - ultima_limpeza > 3600:
                    ultima_limpeza = time.time()
                    corte = (datetime.now(timezone.utc) - timedelta(days=DIAS_GUARDADOS)).isoformat()
                    db._rest("DELETE", "pm_logs", {"created_at": f"lt.{corte}"})
            except Exception:
                time.sleep(10)  # sem internet ou tabela ainda não criada: não polui a janela

    threading.Thread(target=enviar, name="registro", daemon=True).start()
