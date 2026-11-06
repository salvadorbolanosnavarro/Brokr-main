-- Esqueleto tipo Supabase Storage para probar sql-manual/20261106-archivos-*.sql
-- en un Postgres local. NO es el esquema real: solo lo que esas migraciones tocan.
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then create role service_role nologin bypassrls; end if;
end $$;
create schema auth;
create function auth.uid() returns uuid language sql stable as
  $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
grant usage on schema auth to anon, authenticated;
grant usage on schema public to anon, authenticated;

create schema storage;
grant usage on schema storage to anon, authenticated;
create table storage.buckets (id text primary key, name text, public boolean,
  allowed_mime_types text[], file_size_limit bigint);
create table storage.objects (id uuid primary key default gen_random_uuid(), bucket_id text, name text,
  owner uuid default auth.uid());
alter table storage.objects enable row level security;
grant select, insert, update on storage.objects to anon, authenticated;
insert into storage.buckets (id, name, public) values
  ('fotos-propiedades', 'fotos-propiedades', true), ('documentos-publicos', 'documentos-publicos', true),
  ('adjuntos-historial', 'adjuntos-historial', true), ('wa-media', 'wa-media', true),
  ('firmas', 'firmas', false);
-- Reglas permisivas como las de producción: con sesión se puede subir.
create policy "sube con sesion" on storage.objects for insert to authenticated with check (true);
create policy "ve lo suyo" on storage.objects for select to authenticated using (owner = auth.uid());
create policy "actualiza lo suyo" on storage.objects for update to authenticated using (owner = auth.uid());
create policy "lectura publica de adjuntos de historial" on storage.objects for select using (bucket_id = 'adjuntos-historial');

create table public.propiedades (id uuid primary key default gen_random_uuid(), subtipo text,
  documentos jsonb not null default '[]'::jsonb, videos text[] default '{}', tours text[] default '{}');
create view public.propiedades_publicas as select id from public.propiedades;
create view public.propiedades_publicas_extra with (security_barrier = true) as
select p.id, p.subtipo, p.videos, p.tours, p.documentos
  from public.propiedades p
 where p.id in (select id from public.propiedades_publicas);
grant select on public.propiedades_publicas_extra to anon, authenticated;

insert into public.propiedades (id, documentos) values
  ('00000000-0000-0000-0000-000000000001',
   '[{"nombre":"viejo.pdf","url":"https://x/viejo.pdf"},
     {"nombre":"privado.pdf","url":"https://x/privado.pdf","publico":false},
     {"nombre":"publicado.pdf","url":"https://x/publicado.pdf","publico":true}]');
