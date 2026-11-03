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

    def pets_para_reaprender(self) -> list[dict]:
        return self._rest("GET", "pm_pets", {"select": "*", "precisa_reaprender": "eq.true", "ativo": "eq.true"})

    def fotos_do_pet(self, pet_id: str) -> list[dict]:
        return self._rest("GET", "pm_pet_fotos", {"select": "*", "pet_id": f"eq.{pet_id}", "order": "created_at"})

    def baixar_foto_pet(self, caminho: str) -> bytes:
        r = requests.get(f"{self.url}/storage/v1/object/pm-fotos-pets/{caminho}", headers=self.h, timeout=30)
        if not r.ok:
            raise RuntimeError(f"foto {caminho}: HTTP {r.status_code}")
        return r.content

    def cameras(self) -> list[dict]:
        return self._rest("GET", "pm_cameras", {"select": "*", "order": "ordem,nome"})

    # --- escrita ---
    def garantir_camera(self, nome: str, ambiente: str | None, ordem: int) -> dict:
        achadas = self._rest("GET", "pm_cameras", {"select": "*", "nome": f"eq.{nome}"})
        if achadas:
            return achadas[0]
        novas = self._rest("POST", "pm_cameras", json={"nome": nome, "ambiente": ambiente, "ordem": ordem}, extra={"Prefer": "return=representation"})
        return novas[0]

    def status_camera(self, camera_id: str, ok: bool, erro: str | None = None, quadro_path: str | None = None):
        corpo = {"ultima_leitura": agora(), "ultimo_status": "ok" if ok else "erro", "ultimo_erro": None if ok else (erro or "")[:300]}
        if quadro_path:
            corpo["ultimo_quadro_path"] = quadro_path
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
