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

notify pgrst, 'reload schema';
