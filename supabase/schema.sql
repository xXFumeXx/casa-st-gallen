-- Casa St. Gallen – schema del database (Supabase / Postgres)
-- Da eseguire una volta in Supabase: SQL Editor → New query → incolla → Run.

-- Chi può usare l'app: 'owner' modifica, 'viewer' guarda soltanto.
create table if not exists public.membri (
  email text primary key,
  ruolo text not null check (ruolo in ('owner','viewer')),
  creato timestamptz not null default now()
);

-- Annunci: un documento JSON per annuncio, id = "<fonte>:<id sul sito>".
create table if not exists public.annunci (
  id text primary key,
  d jsonb not null,
  notificato boolean not null default false,
  creato timestamptz not null default now(),
  aggiornato timestamptz not null default now()
);
create index if not exists annunci_notificato_idx on public.annunci (notificato) where not notificato;

-- Registro dei controlli automatici ("ultimo" + uno per giro).
create table if not exists public.controlli (
  id text primary key,
  d jsonb not null,
  creato timestamptz not null default now()
);

-- Impostazioni condivise (pesi del punteggio).
create table if not exists public.impostazioni (
  id text primary key,
  d jsonb not null
);

-- Iscrizioni alle notifiche push dei dispositivi.
create table if not exists public.push_sub (
  endpoint text primary key,
  sub jsonb not null,
  email text not null,
  ua text,
  creato timestamptz not null default now()
);

-- Funzioni di controllo dei permessi.
create or replace function public.is_member() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from membri where email = lower(auth.jwt() ->> 'email'));
$$;
create or replace function public.is_owner() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from membri where email = lower(auth.jwt() ->> 'email') and ruolo = 'owner');
$$;

-- Modifica parziale di un annuncio (stato, note…) dall'app: solo il proprietario.
create or replace function public.patch_annuncio(p_id text, p_patch jsonb) returns void
language plpgsql security invoker set search_path = public as $$
begin
  update annunci set d = d || p_patch, aggiornato = now() where id = p_id;
  if not found then raise exception 'annuncio non trovato o permesso negato'; end if;
end $$;

-- Regole di accesso (Row Level Security).
alter table public.membri       enable row level security;
alter table public.annunci      enable row level security;
alter table public.controlli    enable row level security;
alter table public.impostazioni enable row level security;
alter table public.push_sub     enable row level security;

drop policy if exists "membri: leggo me stesso" on public.membri;
create policy "membri: leggo me stesso" on public.membri for select to authenticated
  using (email = lower(auth.jwt() ->> 'email'));

drop policy if exists "annunci: membri leggono" on public.annunci;
create policy "annunci: membri leggono" on public.annunci for select to authenticated using (public.is_member());
drop policy if exists "annunci: owner modifica" on public.annunci;
create policy "annunci: owner modifica" on public.annunci for update to authenticated using (public.is_owner()) with check (public.is_owner());

drop policy if exists "controlli: membri leggono" on public.controlli;
create policy "controlli: membri leggono" on public.controlli for select to authenticated using (public.is_member());

drop policy if exists "impostazioni: membri leggono" on public.impostazioni;
create policy "impostazioni: membri leggono" on public.impostazioni for select to authenticated using (public.is_member());
drop policy if exists "impostazioni: owner scrive" on public.impostazioni;
create policy "impostazioni: owner scrive" on public.impostazioni for all to authenticated using (public.is_owner()) with check (public.is_owner());

drop policy if exists "push: membri gestiscono le proprie" on public.push_sub;
create policy "push: membri gestiscono le proprie" on public.push_sub for all to authenticated
  using (public.is_member() and email = lower(auth.jwt() ->> 'email'))
  with check (public.is_member() and email = lower(auth.jwt() ->> 'email'));

revoke execute on function public.patch_annuncio(text, jsonb) from public, anon;
grant execute on function public.patch_annuncio(text, jsonb) to authenticated, service_role;

-- Accesso alle tabelle tramite l'API (le regole sopra decidono le righe visibili).
grant usage on schema public to anon, authenticated, service_role;
grant select on public.membri to authenticated;
grant select, update on public.annunci to authenticated;
grant select on public.controlli to authenticated;
grant select, insert, update, delete on public.impostazioni to authenticated;
grant select, insert, update, delete on public.push_sub to authenticated;
grant all on public.membri, public.annunci, public.controlli, public.impostazioni, public.push_sub to service_role;
grant execute on function public.is_member() to authenticated;
grant execute on function public.is_owner() to authenticated;

-- Aggiornamenti in tempo reale nell'app.
do $$ begin
  begin alter publication supabase_realtime add table public.annunci; exception when duplicate_object then null; end;
  begin alter publication supabase_realtime add table public.controlli; exception when duplicate_object then null; end;
end $$;

-- Pesi iniziali del punteggio.
insert into public.impostazioni (id, d) values
  ('punteggio', '{"pesi":{"prezzo":35,"distanza":25,"date":20,"contratto":10,"spese":10},"penalitaMese":5}')
on conflict (id) do nothing;

-- Proprietario: sostituisci con la tua email prima di eseguire.
-- insert into public.membri (email, ruolo) values ('TUA_EMAIL', 'owner') on conflict (email) do update set ruolo = excluded.ruolo;
-- Antonio (sola lettura):
-- insert into public.membri (email, ruolo) values ('EMAIL_ANTONIO', 'viewer') on conflict (email) do nothing;
