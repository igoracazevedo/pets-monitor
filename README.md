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

## 3. Programa de casa (Windows)
Pré-requisito: Python 3.11 ou 3.12 (python.org, marcando "Add to PATH"). O PC precisa ficar ligado e na mesma rede do NVR.

1. Copie a pasta `agent` para o PC (ex.: `C:\PetsMonitor`) e dê dois cliques em `windows\instalar.bat`.
2. Edite o `.env`: `SUPABASE_URL` e `SUPABASE_SERVICE_KEY` (chave *service_role*, só neste PC).
3. Copie o seu **`camera.properties`** (hoje só o login das Intelbras e as câmeras `rtsp` dele são usados) (o mesmo do outro app) para a pasta `agent`. Ele é lido como está: câmeras `intelbras` (foto por HTTP, com RTSP de reserva) e `rtsp` (conexão mantida aberta). O arquivo nunca vai para o git. Alternativa com NVR: `config.nvr.example.yaml`.

**As câmeras Intelbras são achadas sozinhas pela rede**, pelo número de série, então o IP pode mudar. Na primeira volta elas aparecem no site (aba **Câmeras**) como "Câmera xxxx": olhe a imagem e toque no lápis para dar o nome do local. Câmera genérica (marca desconhecida): `windows\sondar.bat` descobre o caminho RTSP certo, e você a coloca no `camera.properties` como `tipo=rtsp`.
4. `windows\testar.bat` confere uma câmera (mostra se achou cachorro).
5. `windows\iniciar.bat` começa a varrer. Para subir sozinho ao entrar no Windows, rode `windows\iniciar-com-o-windows.bat`.

Fotos dos pets: envie pelo site (aba **Pets**). O programa aprende sozinho em até 2 min.

Em Linux/Raspberry: `pip install -r requirements.txt` e `python -m pets_agent varrer`.

### Como identifica cada pet
- **De dia:** pela cor do pelo (comparada com as fotos ensinadas).
- **À noite (infravermelho, imagem cinza):** pelo tamanho. Informe o *porte* de cada pet na aba Pets (maior/menor da casa). Com dois no quadro, o maior é o de maior porte. Com um só, usa o tamanho que ele costuma ter naquela câmera (aprendido de dia). Sem certeza, registra "incerto" em vez de chutar.

## Uso no site
- **Início → Onde estão agora?** pede uma varredura na hora e mostra a foto e a câmera de cada cachorra.
- **Câmeras → Ver ao vivo** atualiza as imagens a cada ~2 s enquanto a tela estiver aberta (o programa de casa só captura nesse modo quando alguém está olhando).
- **Pets** cadastra pets novos e envia fotos; o programa de casa aprende sozinho em até 2 min.

> "Ao vivo" aqui são quadros atualizados a cada poucos segundos, sem expor as câmeras na internet. Vídeo contínuo exigiria um servidor de vídeo em casa (go2rtc) com túnel seguro; dá para adicionar depois.

## Pessoas e avisos
- **Pessoas:** o agente acha pessoas nas câmeras (`detectar_pessoas`) e, se você cadastrar alguém na aba **Pessoas** com fotos do rosto, reconhece quem é (`reconhecer_pessoas`). O reconhecimento roda só no PC de casa (modelos YuNet + SFace do OpenCV, baixados na primeira vez); os vetores do rosto ficam numa tabela sem acesso pelo site. Cadastre só quem concordou. Câmeras no teto nem sempre pegam o rosto: nesses casos aparece só "Pessoa".
- **Avisos no celular:** em **Ajustes → Avisos neste aparelho**, ative e use **Enviar teste**. Marque **Avisar no celular quando encontrar** no pet ou na pessoa. O PC de casa envia o aviso (Web Push) quando o encontra num lugar novo, ou quando você toca em **Onde estão agora?**. A chave privada fica em `VAPID_PRIVATE_KEY` no `.env`; a pública já está no site.
- **Frequência:** a varredura roda a cada 5 minutos (`intervalo_s: 300`) ou na hora, em **Onde estão agora?**.
