# Pets Monitor

Varre as câmeras de casa e guarda sempre a **última posição** dos pets.

- `web/` — site (React/Vite) hospedado na **Vercel**. Só lê o Supabase.
- `agent/` — programa Python que roda **em casa** (PC, Raspberry, NAS): lê as câmeras RTSP, detecta cães/gatos (YOLO), identifica cada pet pela cor e grava no Supabase.
- `supabase/schema.sql` — tabelas `pm_*`, regras de acesso e bucket `pm-snapshots`.

> A Vercel não alcança câmeras da rede local nem roda processo contínuo, por isso o leitor fica em casa e a Vercel só mostra os dados.

## 1. Supabase
Rode `supabase/schema.sql` no SQL Editor (pode rodar de novo a cada atualização). Seu e-mail já entra como admin; outros são liberados em **Ajustes**.

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

## Uso no site
- **Início → Onde estão agora?** pede uma varredura na hora e mostra a foto e a câmera de cada cachorra.
- **Câmeras → Ver ao vivo** atualiza as imagens a cada ~2 s enquanto a tela estiver aberta (o programa de casa só captura nesse modo quando alguém está olhando).
- **Pets** cadastra pets novos e envia fotos; o programa de casa aprende sozinho em até 2 min.

> "Ao vivo" aqui são quadros atualizados a cada poucos segundos, sem expor as câmeras na internet. Vídeo contínuo exigiria um servidor de vídeo em casa (go2rtc) com túnel seguro; dá para adicionar depois.
