"""Avisos no celular (Web Push, o mesmo mecanismo do myBill): o PC de casa envia direto para os aparelhos cadastrados no site."""
import json
import os
import time

NAO_CONFIGURADO = "Notificações desligadas: faltam VAPID_PRIVATE_KEY no .env (o instalador já coloca) ou a biblioteca pywebpush."


class Notificador:
    def __init__(self, db):
        self.db = db
        self.chave = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
        self.assunto = os.environ.get("VAPID_SUBJECT", "mailto:pets-monitor@example.com")
        self._assinaturas: list[dict] = []
        self._lidas = 0.0
        self.avisou_falta = False

    @property
    def ativo(self) -> bool:
        return bool(self.chave)

    def _assinaturas_atuais(self) -> list[dict]:
        if time.time() - self._lidas > 60:
            try:
                self._assinaturas = self.db.assinaturas_push()
            except Exception:
                self._assinaturas = []
            self._lidas = time.time()
        return self._assinaturas

    def enviar(self, titulo: str, corpo: str, imagem: str | None = None, tag: str | None = None) -> int:
        """Devolve para quantos aparelhos foi enviado. Aparelho que desinstalou o app (404/410) é removido."""
        if not self.ativo:
            if not self.avisou_falta:
                print(NAO_CONFIGURADO, flush=True)
                self.avisou_falta = True
            return 0
        try:
            from pywebpush import WebPushException, webpush
        except ImportError:
            print(NAO_CONFIGURADO, flush=True)
            return 0
        enviados = 0
        carga = json.dumps({"title": titulo, "body": corpo, "image": imagem, "tag": tag, "url": "/"})
        for a in self._assinaturas_atuais():
            try:
                webpush(subscription_info=a["assinatura"], data=carga, vapid_private_key=self.chave, vapid_claims={"sub": self.assunto}, ttl=3600)
                enviados += 1
            except WebPushException as e:
                if getattr(e.response, "status_code", None) in (404, 410):
                    try:
                        self.db.remover_assinatura(a["endpoint"])
                    except Exception:
                        pass
                else:
                    print(f"  aviso não enviado: {str(e)[:120]}", flush=True)
            except Exception as e:
                print(f"  aviso não enviado: {str(e)[:120]}", flush=True)
        return enviados
