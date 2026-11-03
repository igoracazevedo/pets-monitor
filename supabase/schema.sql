-- =====================================================================
-- pets-monitor — esquema do Supabase (prefixo pm_)
-- Rode uma vez no SQL Editor. O banco é compartilhado com os outros apps: tudo aqui começa com pm_.
-- =====================================================================

-- Quem pode ver e gerenciar (login Google pelo e-mail)
create table if not exists public.pm_membros (
  email text primary key check (email = lower(email)),
  admin boolean not null default false,
  created_at timestamptz not null default now()
);
insert into public.pm_membros (email, admin) values ('igoracazevedo@gmail.com', true) on conflict (email) do nothing;

create or replace function public.pm_is_membro() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.pm_membros where email = lower(coalesce(auth.jwt() ->> 'email', '')));
$$;
create or replace function public.pm_is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.pm_membros where admin and email = lower(coalesce(auth.jwt() ->> 'email', '')));
$$;
grant execute on function public.pm_is_membro(), public.pm_is_admin() to authenticated;

-- Pets: o perfil (cores) é gerado pelo agente a partir das fotos de cada um
create table if not exists public.pm_pets (
  id uuid primary key default gen_random_uuid(),
  nome text not null unique,
  especie text not null default 'cachorro' check (especie in ('cachorro', 'gato')),
  descricao text,
  perfil jsonb,
  ativo boolean not null default true,
  created_at timestamptz not null default now()
);

-- Câmeras (a URL RTSP fica só no computador de casa, nunca no banco)
create table if not exists public.pm_cameras (
  id uuid primary key default gen_random_uuid(),
  nome text not null unique,
  ambiente text,
  ordem int not null default 0,
  ativo boolean not null default true,
  ultima_leitura timestamptz,
  ultimo_status text,            -- ok | erro
  ultimo_erro text,
  ultimo_quadro_path text,
  created_at timestamptz not null default now()
);

-- Cada vez que um pet é visto (guardamos quando muda de câmera ou de tempos em tempos)
create table if not exists public.pm_avistamentos (
  id bigint generated always as identity primary key,
  pet_id uuid references public.pm_pets(id) on delete cascade,
  especie text not null default 'cachorro',
  camera_id uuid not null references public.pm_cameras(id) on delete cascade,
  visto_em timestamptz not null default now(),
  confianca numeric(4, 3),
  identificacao text,            -- cor | unico | incerto
  x numeric(5, 4), y numeric(5, 4), w numeric(5, 4), h numeric(5, 4),   -- caixa no quadro (0 a 1)
  snapshot_path text
);
create index if not exists pm_avistamentos_visto_idx on public.pm_avistamentos (visto_em desc);
create index if not exists pm_avistamentos_pet_idx on public.pm_avistamentos (pet_id, visto_em desc);

-- Última posição de cada pet (uma linha por pet)
create table if not exists public.pm_ultima_posicao (
  pet_id uuid primary key references public.pm_pets(id) on delete cascade,
  camera_id uuid references public.pm_cameras(id) on delete set null,
  visto_em timestamptz not null,
  confianca numeric(4, 3),
  x numeric(5, 4), y numeric(5, 4), w numeric(5, 4), h numeric(5, 4),
  snapshot_path text
);

-- Segurança: membros leem; só admin altera pets/câmeras/membros. O agente grava com a chave de serviço (ignora RLS).
alter table public.pm_membros enable row level security;
alter table public.pm_pets enable row level security;
alter table public.pm_cameras enable row level security;
alter table public.pm_avistamentos enable row level security;
alter table public.pm_ultima_posicao enable row level security;

drop policy if exists pm_membros_ler on public.pm_membros;
create policy pm_membros_ler on public.pm_membros for select to authenticated using (public.pm_is_membro());
drop policy if exists pm_membros_admin on public.pm_membros;
create policy pm_membros_admin on public.pm_membros for all to authenticated using (public.pm_is_admin()) with check (public.pm_is_admin());

do $$
declare t text;
begin
  foreach t in array array['pm_pets', 'pm_cameras', 'pm_avistamentos', 'pm_ultima_posicao'] loop
    execute format('drop policy if exists %I on public.%I', t || '_ler', t);
    execute format('create policy %I on public.%I for select to authenticated using (public.pm_is_membro())', t || '_ler', t);
    execute format('drop policy if exists %I on public.%I', t || '_admin', t);
    execute format('create policy %I on public.%I for all to authenticated using (public.pm_is_admin()) with check (public.pm_is_admin())', t || '_admin', t);
  end loop;
end $$;

-- Fotos dos quadros (bucket privado; o site usa links assinados)
insert into storage.buckets (id, name, public) values ('pm-snapshots', 'pm-snapshots', false) on conflict (id) do nothing;
drop policy if exists pm_snapshots_ler on storage.objects;
create policy pm_snapshots_ler on storage.objects for select to authenticated using (bucket_id = 'pm-snapshots' and public.pm_is_membro());

-- Cadastro de pets pelo site: porte (ajuda a separar à noite), fotos para ensinar e aviso para o agente reaprender
alter table public.pm_pets add column if not exists porte text check (porte in ('pequeno', 'medio', 'grande'));
alter table public.pm_pets add column if not exists precisa_reaprender boolean not null default false;

create table if not exists public.pm_pet_fotos (
  id uuid primary key default gen_random_uuid(),
  pet_id uuid not null references public.pm_pets(id) on delete cascade,
  path text not null,
  created_at timestamptz not null default now()
);
alter table public.pm_pet_fotos enable row level security;
drop policy if exists pm_pet_fotos_ler on public.pm_pet_fotos;
create policy pm_pet_fotos_ler on public.pm_pet_fotos for select to authenticated using (public.pm_is_membro());
drop policy if exists pm_pet_fotos_admin on public.pm_pet_fotos;
create policy pm_pet_fotos_admin on public.pm_pet_fotos for all to authenticated using (public.pm_is_admin()) with check (public.pm_is_admin());

insert into storage.buckets (id, name, public) values ('pm-fotos-pets', 'pm-fotos-pets', false) on conflict (id) do nothing;
drop policy if exists pm_fotos_pets_ler on storage.objects;
create policy pm_fotos_pets_ler on storage.objects for select to authenticated using (bucket_id = 'pm-fotos-pets' and public.pm_is_membro());
drop policy if exists pm_fotos_pets_enviar on storage.objects;
create policy pm_fotos_pets_enviar on storage.objects for insert to authenticated with check (bucket_id = 'pm-fotos-pets' and public.pm_is_admin());
drop policy if exists pm_fotos_pets_apagar on storage.objects;
create policy pm_fotos_pets_apagar on storage.objects for delete to authenticated using (bucket_id = 'pm-fotos-pets' and public.pm_is_admin());

-- Pedido "onde estão agora?" e modo ao vivo (o agente de casa consulta a cada poucos segundos)
create table if not exists public.pm_pedidos (
  id uuid primary key default gen_random_uuid(),
  tipo text not null default 'localizar' check (tipo in ('localizar')),
  created_at timestamptz not null default now(),
  atendido_em timestamptz
);
create table if not exists public.pm_ao_vivo (
  id int primary key default 1 check (id = 1),
  ate timestamptz not null default now()
);
insert into public.pm_ao_vivo (id) values (1) on conflict do nothing;
alter table public.pm_pedidos enable row level security;
alter table public.pm_ao_vivo enable row level security;
drop policy if exists pm_pedidos_membros on public.pm_pedidos;
create policy pm_pedidos_membros on public.pm_pedidos for all to authenticated using (public.pm_is_membro()) with check (public.pm_is_membro());
drop policy if exists pm_ao_vivo_membros on public.pm_ao_vivo;
create policy pm_ao_vivo_membros on public.pm_ao_vivo for all to authenticated using (public.pm_is_membro()) with check (public.pm_is_membro());

-- Foto de perfil do pet (arquivo no bucket pm-fotos-pets, fora das fotos de aprendizado)
alter table public.pm_pets add column if not exists foto_perfil_path text;

-- Câmeras achadas na rede: identificadas pelo número de série (o IP muda); o nome é o apelido que você dá no app
alter table public.pm_cameras add column if not exists identificador text unique;
alter table public.pm_cameras add column if not exists ip_atual text;

-- "Ver ao vivo": uma foto nova de cada câmera sob demanda, com a hora da captura
alter table public.pm_cameras add column if not exists foto_em timestamptz;
alter table public.pm_pedidos drop constraint if exists pm_pedidos_tipo_check;
alter table public.pm_pedidos add constraint pm_pedidos_tipo_check check (tipo in ('localizar', 'fotos'));

-- Última posição: quando a foto foi tirada (a foto só muda quando o pet muda de lugar)
alter table public.pm_ultima_posicao add column if not exists foto_em timestamptz;

-- "Não é pet": lugares da câmera (ex.: urso de pelúcia grande) que o detector deve ignorar
create table if not exists public.pm_ignorar (
  id uuid primary key default gen_random_uuid(),
  camera_id uuid not null references public.pm_cameras(id) on delete cascade,
  x numeric(5, 4) not null, y numeric(5, 4) not null, w numeric(5, 4) not null, h numeric(5, 4) not null,
  created_at timestamptz not null default now()
);
alter table public.pm_ignorar enable row level security;
drop policy if exists pm_ignorar_ler on public.pm_ignorar;
create policy pm_ignorar_ler on public.pm_ignorar for select to authenticated using (public.pm_is_membro());
drop policy if exists pm_ignorar_admin on public.pm_ignorar;
create policy pm_ignorar_admin on public.pm_ignorar for all to authenticated using (public.pm_is_admin()) with check (public.pm_is_admin());

-- Pessoas: quantas há agora em cada câmera (o agente atualiza a cada volta em que muda)
create table if not exists public.pm_presenca (
  camera_id uuid primary key references public.pm_cameras(id) on delete cascade,
  pessoas int not null default 0,
  ultima_vez timestamptz,
  snapshot_path text,
  foto_em timestamptz
);
alter table public.pm_presenca enable row level security;
drop policy if exists pm_presenca_ler on public.pm_presenca;
create policy pm_presenca_ler on public.pm_presenca for select to authenticated using (public.pm_is_membro());
drop policy if exists pm_presenca_admin on public.pm_presenca;
create policy pm_presenca_admin on public.pm_presenca for all to authenticated using (public.pm_is_admin()) with check (public.pm_is_admin());

notify pgrst, 'reload schema';
