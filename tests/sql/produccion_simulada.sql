-- Producción simulada (octubre 2026) para probar puesta-al-dia-produccion.sql.
-- Sólo las tablas que existen hoy en public (lista que mandó Chava), con las
-- formas viejas conocidas: pipeline_etapas.user_id NOT NULL, fuentes_captacion
-- y respuestas_guardadas viejas, sin finanzas/firmas/buscador/etc.
-- Las columnas son las mínimas plausibles; NO es el esquema real.
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then create role service_role nologin bypassrls; end if;
end $$;
create schema auth;
create table auth.users (id uuid primary key, email text);
create function auth.uid() returns uuid language sql stable as
  $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
create function auth.role() returns text language sql stable as
  $$ select coalesce(current_setting('request.jwt.claim.role', true), 'anon') $$;
grant usage on schema auth to anon, authenticated;
grant usage on schema public to anon, authenticated;

create schema storage;
create table storage.buckets (id text primary key, name text, public boolean);
create table storage.objects (id uuid primary key default gen_random_uuid(), bucket_id text, name text, owner uuid);
alter table storage.objects enable row level security;
create function storage.foldername(name text) returns text[] language sql immutable as
  $$ select string_to_array(name, '/') $$;
insert into storage.buckets values ('fotos-propiedades', 'fotos-propiedades', true), ('wa-media', 'wa-media', true);

-- ── Cuentas ──
create table public.usuarios (id uuid primary key, email text, nombre text, telefono text, rol text, activo boolean default true,
  slug text, sitio_activo boolean, nombre_publico text, foto_url text, whatsapp_publico text, created_at timestamptz default now());
create table public.admin_usuarios (id uuid primary key default gen_random_uuid(), email text);
create table public.organizaciones (id uuid primary key default gen_random_uuid(), nombre text, owner_id uuid, tipo text,
  activo boolean default true, asientos_max integer default 1);
create table public.organizacion_miembros (id uuid primary key default gen_random_uuid(), org_id uuid, user_id uuid,
  rol_org text default 'agente', activo boolean default true, permisos jsonb default '{}'::jsonb);
create table public.organizacion_invitaciones (id uuid primary key default gen_random_uuid(), org_id uuid, email text);
create table public.suscripciones (id uuid primary key default gen_random_uuid(), user_id uuid, org_id uuid, plan_id text,
  plan_nombre text, status text, stripe_subscription_id text, updated_at timestamptz default now());
create table public.usage_logs (id uuid primary key default gen_random_uuid(), user_id uuid, created_at timestamptz default now());
create table public.module_sessions (id uuid primary key default gen_random_uuid(), user_id uuid);
create table public.user_integrations (id uuid primary key default gen_random_uuid(), user_id uuid, proveedor text);

-- ── Inmuebles ──
create table public.propiedades (
  id uuid primary key default gen_random_uuid(), user_id uuid, org_id uuid,
  titulo text, tipo text, operacion text, estatus text default 'activa', precio numeric, moneda text default 'MXN',
  calle text, colonia text, ciudad text, cp text, m2_construccion numeric, m2_terreno numeric, recamaras int, banos numeric,
  estacionamientos int, anio_construccion int, descripcion text, notas text, clave_interna text, codigo_llave text,
  etiquetas text[] default '{}', fotos text[] default '{}', archivada boolean default false,
  mostrar_ubicacion_exacta boolean default false, mostrar_precio boolean default true, eb_public_id text,
  created_at timestamptz default now(), updated_at timestamptz default now());
create unique index propiedades_user_eb_unique on public.propiedades (user_id, eb_public_id) where eb_public_id is not null;
create view public.propiedades_publicas as
  select id, user_id, titulo, precio from public.propiedades where estatus = 'activa' and not archivada;
create table public.propiedades_avm (id uuid primary key default gen_random_uuid(), lat double precision, lng double precision);
create table public.avaluos_historial (id uuid primary key default gen_random_uuid(), user_id uuid);
create table public.catalogo_inmuebles (id uuid primary key default gen_random_uuid(), nombre text);
create table public.listas_propiedades (id uuid primary key default gen_random_uuid(), user_id uuid);
create table public.listas_items (id uuid primary key default gen_random_uuid(), lista_id uuid);
create table public.testimonios (id uuid primary key default gen_random_uuid(), user_id uuid, texto text);
create view public.testimonios_publicos as select id, texto from public.testimonios;
create view public.usuarios_publicos as select id, nombre_publico from public.usuarios;
create table public.machotes_contrato (id uuid primary key default gen_random_uuid(), user_id uuid);

-- ── Contactos, tareas, bitácora ──
create table public.contactos (
  id text primary key default ('c_' || floor(random() * 1e12)::text),
  user_id uuid, org_id uuid, nombre text, telefono text, wa text, email text, tipo text, fuente text,
  estatus text, es_potencial boolean default false, probabilidad text, etiquetas text[] default '{}',
  created_at timestamptz default now(), updated_at timestamptz default now());
create table public.contactos_propiedades (id uuid primary key default gen_random_uuid(), user_id uuid, contacto_id text,
  propiedad_id uuid, relacion text, created_at timestamptz default now());
create table public.leads (id uuid primary key default gen_random_uuid(), user_id uuid, nombre text);
create table public.etiquetas (id uuid primary key default gen_random_uuid(), user_id uuid, nombre text);
create table public.tareas (id uuid primary key default gen_random_uuid(), user_id uuid, titulo text,
  fecha_entrega timestamptz, completada boolean default false, contacto_id text, propiedad_id uuid, created_at timestamptz default now());
create table public.tareas_contactos (id uuid primary key default gen_random_uuid(), user_id uuid not null,
  tarea_id uuid not null references public.tareas(id) on delete cascade, contacto_id text not null references public.contactos(id) on delete cascade,
  created_at timestamptz default now(), unique (tarea_id, contacto_id));
create table public.tareas_propiedades (id uuid primary key default gen_random_uuid(), user_id uuid not null,
  tarea_id uuid not null references public.tareas(id) on delete cascade, propiedad_id uuid not null references public.propiedades(id) on delete cascade,
  created_at timestamptz default now(), unique (tarea_id, propiedad_id));
create table public.actividades (id uuid primary key default gen_random_uuid(), user_id uuid, contacto_id text, propiedad_id uuid,
  tipo text, texto text, created_at timestamptz default now());
create table public.correos (id uuid primary key default gen_random_uuid(), direccion text, asunto text, created_at timestamptz default now());
create table public.facturas_cfdi (stripe_invoice_id text primary key, monto numeric);

-- Formas viejas que encontró Chava
create table public.pipeline_etapas (id uuid primary key default gen_random_uuid(), user_id uuid not null, nombre text not null,
  orden int default 0, color text, created_at timestamptz default now());
create table public.fuentes_captacion (id uuid primary key default gen_random_uuid(), user_id uuid not null, nombre text,
  created_at timestamptz default now());
create table public.respuestas_guardadas (id uuid primary key default gen_random_uuid(), user_id uuid not null, titulo text,
  contenido text not null, created_at timestamptz default now(), updated_at timestamptz default now());

-- ── PLD ──
create table public.pld_config (id uuid primary key default gen_random_uuid(), user_id uuid);
create table public.pld_expedientes (id uuid primary key default gen_random_uuid(), user_id uuid, contacto_id text, token_publico text);
create table public.pld_operaciones (id uuid primary key default gen_random_uuid(), user_id uuid);
create table public.pld_avisos (id uuid primary key default gen_random_uuid(), user_id uuid, estatus text default 'borrador', tipo text,
  constraint pld_avisos_estatus_check check (estatus in ('borrador', 'presentado')));
create table public.pld_documentos (id uuid primary key default gen_random_uuid(), user_id uuid);
create table public.pld_bitacora (id uuid primary key default gen_random_uuid(), user_id uuid);

-- ── WhatsApp ──
create table public.wa_numbers (id uuid primary key default gen_random_uuid(), user_id uuid not null, phone_number_id text unique);
create table public.wa_contacts (id uuid primary key default gen_random_uuid(), user_id uuid not null, wa_id text);
create table public.wa_conversations (id uuid primary key default gen_random_uuid(), user_id uuid not null, contact_id uuid);
create table public.wa_messages (id uuid primary key default gen_random_uuid(), user_id uuid not null, conversation_id uuid);
create table public.wa_citas (id uuid primary key default gen_random_uuid(), user_id uuid);
create table public.wa_training (id uuid primary key default gen_random_uuid(), user_id uuid);
create table public.wac_numbers (id uuid primary key default gen_random_uuid(), user_id uuid not null, waba_id text, phone_number_id text);
create table public.wa2_numeros (id uuid primary key default gen_random_uuid(), user_id uuid);
create table public.wa2_numeros_backup_20260720 (id uuid, user_id uuid);
create table public.wa2_contactos (id uuid primary key default gen_random_uuid(), user_id uuid, numero_id uuid, wa_id text, nombre text);
create table public.wa2_conversaciones (id uuid primary key default gen_random_uuid(), user_id uuid, numero_id uuid, contacto_id uuid,
  ai_enabled boolean default true, last_message_at timestamptz default now());
create table public.wa2_mensajes (id uuid primary key default gen_random_uuid(), user_id uuid, conversacion_id uuid, wa_message_id text,
  cuerpo text, created_at timestamptz default now());
create table public.wa2_entrenamiento (id uuid primary key default gen_random_uuid(), user_id uuid, numero_id uuid);
create table public.wa2_citas (id uuid primary key default gen_random_uuid(), user_id uuid);

grant select, insert, update, delete on all tables in schema public to authenticated;

-- ── Datos para comprobar que no se borra nada y que los rellenos funcionan ──
insert into auth.users values ('10000000-0000-0000-0000-000000000001', 'chava@x.mx'), ('10000000-0000-0000-0000-000000000002', 'ana@x.mx');
insert into public.usuarios (id, email, nombre) values ('10000000-0000-0000-0000-000000000001', 'chava@x.mx', 'Chava'),
  ('10000000-0000-0000-0000-000000000002', 'ana@x.mx', 'Ana');
insert into public.organizaciones (id, nombre, owner_id) values ('00000000-0000-0000-0000-0000000000a1', 'Grupo Navarro', '10000000-0000-0000-0000-000000000001');
insert into public.organizacion_miembros (org_id, user_id, rol_org) values
  ('00000000-0000-0000-0000-0000000000a1', '10000000-0000-0000-0000-000000000001', 'owner'),
  ('00000000-0000-0000-0000-0000000000a1', '10000000-0000-0000-0000-000000000002', 'agente');
insert into public.propiedades (user_id, titulo, eb_public_id) values
  ('10000000-0000-0000-0000-000000000001', 'Casa sin empresa', 'EB-1'),
  ('10000000-0000-0000-0000-000000000002', 'Depa sin empresa', 'EB-2');
insert into public.contactos (id, user_id, nombre, fuente, estatus) values
  ('c_1', '10000000-0000-0000-0000-000000000001', 'ANA PEREZ', 'facebook ', 'nuevo'),
  ('c_2', '10000000-0000-0000-0000-000000000002', 'LUIS', 'Facebook', 'activo');
insert into public.actividades (user_id, contacto_id, tipo, texto) values ('10000000-0000-0000-0000-000000000001', 'c_1', 'nota', 'Llamar');
insert into public.tareas (user_id, titulo, contacto_id) values ('10000000-0000-0000-0000-000000000002', 'Visita', 'c_2');
insert into public.pipeline_etapas (user_id, nombre, orden) values ('10000000-0000-0000-0000-000000000001', 'Nuevo', 10);
insert into public.wa2_numeros (id, user_id) values ('20000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001');
insert into public.wa2_conversaciones (id, user_id, numero_id) values
  ('30000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001'),
  ('30000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-0000000000ff');  -- huérfana
insert into public.wa2_mensajes (user_id, conversacion_id, wa_message_id, cuerpo) values
  ('10000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000001', 'wamid.A', 'hola'),
  ('10000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000001', 'wamid.A', 'hola (repetido)'),
  ('10000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000099', 'wamid.B', 'huérfano');
