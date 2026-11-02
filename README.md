# Pets Monitor

Varre as câmeras de casa e guarda sempre a **última posição** dos pets.

- `web/` — site (React/Vite) hospedado na **Vercel**. Só lê o Supabase.
- `agent/` — programa Python que roda **em casa** (PC, Raspberry, NAS): lê as câmeras RTSP, detecta cães/gatos (YOLO), identifica cada pet pela cor e grava no Supabase.
- `supabase/schema.sql` — tabelas `pm_*`, regras de acesso e bucket `pm-snapshots`.

> A Vercel não alcança câmeras da rede local nem roda processo contínuo, por isso o leitor fica em casa e a Vercel só mostra os dados.

## 1. Supabase
Rode `supabase/schema.sql` no SQL Editor. Seu e-mail já entra como admin; outros são liberados em **Ajustes**.

## 2. Site (Vercel)
Importe o repositório com **Root Directory = `web`**. Variáveis (opcionais, já há padrões):
`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`. Login Google usa o provedor já ativo no Supabase; adicione a URL do site em *Authentication → URL Configuration*.

## 3. Programa de casa
```bash
cd agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # SUPABASE_URL, SUPABASE_SERVICE_KEY, URLs RTSP
cp config.example.yaml config.yaml
python -m pets_agent testar <camera>      # confere uma câmera
python -m pets_agent ensinar --pasta fotos  # fotos/<NomePet>/*.jpg
python -m pets_agent varrer               # varredura contínua (--uma-vez p/ teste)
```
Também há `Dockerfile` para deixar rodando 24h.

Dica RTSP: `rtsp://usuario:senha@IP:554/stream1` (varia por marca). Use fotos de cada pet em ângulos e luz diferentes para ensinar.
