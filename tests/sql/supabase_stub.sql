-- Esqueleto mínimo tipo Supabase para probar migraciones en un Postgres local.
-- NO es el esquema real: sólo las tablas/columnas que las migraciones tocan.
create role anon nologin;
create role authenticated nologin;
create role service_role nologin bypassrls;
create schema auth;
create table auth.users (id uuid primary key, email text);
create function auth.uid() returns uuid language sql stable as
  $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
grant usage on schema auth to anon, authenticated;
grant usage on schema public to anon, authenticated;

create table public.organizaciones (id uuid primary key default gen_random_uuid(), nombre text);
create table public.organizacion_miembros (
  id uuid primary key default gen_random_uuid(),
  org_id uuid, user_id uuid, rol_org text default 'agente',
  activo boolean default true, permisos jsonb default '{}'::jsonb);

create table public.propiedades (
  id uuid primary key default gen_random_uuid(),
  user_id uuid, org_id uuid, asignado_a uuid,
  titulo text, tipo text, operacion text, estatus text default 'activa',
  precio numeric, moneda text default 'MXN', colonia text, ciudad text, estado text,
  amenidades text[], etiquetas text[], fotos text[], archivada boolean default false,
  mostrar_ubicacion_exacta boolean default false, mostrar_precio boolean default true, eb_public_id text,
  created_at timestamptz default now(), updated_at timestamptz default now());

create table public.contactos (
  id uuid primary key default gen_random_uuid(),
  user_id uuid, org_id uuid, asignado_a uuid, nombre text, telefono text, email text,
  tipo text, fuente text, etapa text, etiquetas text[],
  created_at timestamptz default now(), updated_at timestamptz default now());

create table public.tareas (
  id uuid primary key default gen_random_uuid(),
  user_id uuid, org_id uuid, asignado_a uuid, titulo text,
  fecha timestamptz, completada boolean default false);

-- Política "vieja" demasiado abierta, a propósito, para probar el candado.
alter table public.propiedades enable row level security;
create policy "vieja abierta" on public.propiedades for select using (true);
alter table public.contactos enable row level security;
create policy "vieja abierta" on public.contactos for select using (true);
alter table public.tareas enable row level security;
create policy "vieja abierta" on public.tareas for select using (true);

create view public.propiedades_publicas as
  select id, user_id, titulo, precio from public.propiedades where estatus = 'activa';

grant select, insert, update, delete on all tables in schema public to authenticated;
grant select on public.propiedades_publicas to anon;
