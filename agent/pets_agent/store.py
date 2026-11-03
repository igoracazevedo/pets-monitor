"""Acesso ao Supabase pela API REST (chave de serviço, só neste computador)."""
import os
from datetime import datetime, timezone

import requests


class Supabase:
    def __init__(self):
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        chave = os.environ.get("SUPABASE_SERVICE_KEY", "")
        if not url or not chave:
            raise SystemExit("Defina SUPABASE_URL e SUPABASE_SERVICE_KEY no .env")
        self.url = url
        self.h = {"apikey": chave, "Authorization": f"Bearer {chave}"}

    def _rest(self, metodo: str, tabela: str, params=None, json=None, extra=None):
        h = {**self.h, "Content-Type": "application/json", **(extra or {})}
        r = requests.request(metodo, f"{self.url}/rest/v1/{tabela}", params=params, json=json, headers=h, timeout=20)
        if not r.ok:
            raise RuntimeError(f"{tabela}: HTTP {r.status_code} {r.text[:200]}")
        return r.json() if r.text else None

    # --- leitura ---
    def pets(self) -> list[dict]:
        return self._rest("GET", "pm_pets", {"select": "*", "ativo": "eq.true", "order": "nome"})

    def pet_por_id(self, pet_id: str) -> dict | None:
        r = self._rest("GET", "pm_pets", {"select": "*", "id": f"eq.{pet_id}"})
        return r[0] if r else None

    def correcoes_pendentes(self) -> list[dict]:
        return self._rest("GET", "pm_correcoes", {"select": "*", "aplicada": "is.false", "order": "created_at"})

    def correcao_aplicada(self, correcao_id: str):
        self._rest("PATCH", "pm_correcoes", {"id": f"eq.{correcao_id}"}, json={"aplicada": True})

    def baixar_snapshot(self, caminho: str) -> bytes:
        r = requests.get(f"{self.url}/storage/v1/object/pm-snapshots/{caminho}", headers=self.h, timeout=30)
        if not r.ok:
            raise RuntimeError(f"snapshot {caminho}: HTTP {r.status_code}")
        return r.content

    def pet_por_nome(self, nome: str) -> dict | None:
        r = self._rest("GET", "pm_pets", {"select": "*", "nome": f"ilike.{nome}"})
        return r[0] if r else None

    def pets_para_reaprender(self) -> list[dict]:
        return self._rest("GET", "pm_pets", {"select": "*", "precisa_reaprender": "eq.true", "ativo": "eq.true"})

    def fotos_do_pet(self, pet_id: str) -> list[dict]:
        return self._rest("GET", "pm_pet_fotos", {"select": "*", "pet_id": f"eq.{pet_id}", "order": "created_at"})

    def baixar_foto_pet(self, caminho: str) -> bytes:
        r = requests.get(f"{self.url}/storage/v1/object/pm-fotos-pets/{caminho}", headers=self.h, timeout=30)
        if not r.ok:
            raise RuntimeError(f"foto {caminho}: HTTP {r.status_code}")
        return r.content

    def pedidos_pendentes(self) -> list[dict]:
        return self._rest("GET", "pm_pedidos", {"select": "id,tipo", "atendido_em": "is.null"})

    def atender_pedidos(self, ids: list[str]):
        for i in ids:
            self._rest("PATCH", "pm_pedidos", {"id": f"eq.{i}"}, json={"atendido_em": agora()})

    def ao_vivo_ativo(self) -> bool:
        linhas = self._rest("GET", "pm_ao_vivo", {"select": "ate", "id": "eq.1"})
        if not linhas:
            return False
        return datetime.fromisoformat(linhas[0]["ate"].replace("Z", "+00:00")) > datetime.now(timezone.utc)

    # --- pessoas cadastradas (rosto) ---
    def pessoas(self) -> list[dict]:
        return self._rest("GET", "pm_pessoas", {"select": "*", "ativo": "eq.true", "order": "nome"})

    def pessoas_para_reaprender(self) -> list[dict]:
        return self._rest("GET", "pm_pessoas", {"select": "*", "precisa_reaprender": "eq.true", "ativo": "eq.true"})

    def fotos_da_pessoa(self, pessoa_id: str) -> list[dict]:
        return self._rest("GET", "pm_pessoa_fotos", {"select": "*", "pessoa_id": f"eq.{pessoa_id}", "order": "created_at"})

    def rostos_das_pessoas(self) -> dict[str, list]:
        linhas = self._rest("GET", "pm_pessoa_rostos", {"select": "*"})
        return {l["pessoa_id"]: (l.get("perfil") or {}).get("embs", []) for l in linhas}

    def salvar_rostos(self, pessoa_id: str, embs: list):
        self._rest("POST", "pm_pessoa_rostos", {"on_conflict": "pessoa_id"}, json={"pessoa_id": pessoa_id, "perfil": {"embs": embs}}, extra={"Prefer": "resolution=merge-duplicates"})
        self._rest("PATCH", "pm_pessoas", {"id": f"eq.{pessoa_id}"}, json={"precisa_reaprender": False})

    # --- avisos no celular ---
    def assinaturas_push(self) -> list[dict]:
        return self._rest("GET", "pm_push", {"select": "endpoint,assinatura"})

    def remover_assinatura(self, endpoint: str):
        self._rest("DELETE", "pm_push", {"endpoint": f"eq.{endpoint}"})

    def url_assinada(self, caminho: str, bucket: str = "pm-snapshots", segundos: int = 86400) -> str | None:
        r = requests.post(f"{self.url}/storage/v1/object/sign/{bucket}/{caminho}", json={"expiresIn": segundos}, headers=self.h, timeout=15)
        return f"{self.url}/storage/v1{r.json()['signedURL']}" if r.ok else None

    def presenca(self, linha: dict):
        self._rest("POST", "pm_presenca", {"on_conflict": "camera_id"}, json=linha, extra={"Prefer": "resolution=merge-duplicates"})

    def ignorar(self) -> list[dict]:
        return self._rest("GET", "pm_ignorar", {"select": "*"})

    def cameras(self) -> list[dict]:
        return self._rest("GET", "pm_cameras", {"select": "*", "order": "ordem,nome"})

    # --- escrita ---
    def garantir_camera(self, nome: str, ambiente: str | None, ordem: int, identificador: str | None = None, ip: str | None = None) -> dict:
        """Câmeras descobertas na rede são achadas pelo identificador (número de série); as fixas, pelo nome."""
        if identificador:
            achadas = self._rest("GET", "pm_cameras", {"select": "*", "identificador": f"eq.{identificador}"})
            if achadas:
                if ip and achadas[0].get("ip_atual") != ip:
                    self._rest("PATCH", "pm_cameras", {"id": f"eq.{achadas[0]['id']}"}, json={"ip_atual": ip})
                    achadas[0]["ip_atual"] = ip
                return achadas[0]
            existentes = {c["nome"] for c in self._rest("GET", "pm_cameras", {"select": "nome"})}
            novo = nome
            while novo in existentes:
                novo += "*"
            return self._rest("POST", "pm_cameras", json={"nome": novo, "ambiente": ambiente, "ordem": ordem, "identificador": identificador, "ip_atual": ip}, extra={"Prefer": "return=representation"})[0]
        achadas = self._rest("GET", "pm_cameras", {"select": "*", "nome": f"eq.{nome}"})
        if achadas:
            if ip and achadas[0].get("ip_atual") != ip:
                self._rest("PATCH", "pm_cameras", {"id": f"eq.{achadas[0]['id']}"}, json={"ip_atual": ip})
                achadas[0]["ip_atual"] = ip
            return achadas[0]
        novas = self._rest("POST", "pm_cameras", json={"nome": nome, "ambiente": ambiente, "ordem": ordem, "ip_atual": ip}, extra={"Prefer": "return=representation"})
        return novas[0]

    def status_camera(self, camera_id: str, ok: bool, erro: str | None = None, quadro_path: str | None = None):
        corpo = {"ultima_leitura": agora(), "ultimo_status": "ok" if ok else "erro", "ultimo_erro": None if ok else (erro or "")[:300]}
        if quadro_path:
            corpo["ultimo_quadro_path"] = quadro_path
            corpo["foto_em"] = agora()  # hora da última imagem guardada desta câmera
        self._rest("PATCH", "pm_cameras", {"id": f"eq.{camera_id}"}, json=corpo)

    def salvar_perfil(self, pet_id: str, perfil: dict | None):
        self._rest("PATCH", "pm_pets", {"id": f"eq.{pet_id}"}, json={"perfil": perfil, "precisa_reaprender": False})

    def criar_pet(self, nome: str, especie: str = "cachorro") -> dict:
        return self._rest("POST", "pm_pets", json={"nome": nome, "especie": especie}, extra={"Prefer": "return=representation"})[0]

    def enviar_foto(self, caminho: str, jpeg: bytes):
        r = requests.post(
            f"{self.url}/storage/v1/object/pm-snapshots/{caminho}",
            data=jpeg,
            headers={**self.h, "Content-Type": "image/jpeg", "x-upsert": "true"},
            timeout=30,
        )
        if not r.ok:
            raise RuntimeError(f"foto: HTTP {r.status_code} {r.text[:200]}")

    def avistamento(self, linha: dict):
        self._rest("POST", "pm_avistamentos", json=linha)

    def ultima_posicao(self, linha: dict):
        self._rest("POST", "pm_ultima_posicao", {"on_conflict": "pet_id"}, json=linha, extra={"Prefer": "resolution=merge-duplicates"})


def agora() -> str:
    return datetime.now(timezone.utc).isoformat()
