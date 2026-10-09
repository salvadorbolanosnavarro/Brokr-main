-- ═══════════════════════════════════════════════════════════════════════════
-- Broquer — Fase 3: contactos y pipeline (paridad EasyBroker)
--
-- QUÉ AGREGA (sólo tablas/columnas nuevas con default; no borra nada)
--   pipeline_etapas   + org_id, clave (estable: es lo que se guarda en
--                       contactos.estatus; renombrar sólo cambia el nombre),
--                       es_sistema. Se siembran las etapas default por
--                       organización, incluida la nueva "Basura/Spam".
--   contacto_tipos    catálogo de tipos de contacto por organización
--                       (los de siempre + Valuador, Jurídico, Agente externo).
--   fuentes_captacion catálogo controlado de fuentes por organización. Se
--                       llena con las fuentes de texto libre que ya existen,
--                       sin duplicados por mayúsculas, acentos o espacios.
--   contactos         + fuente_id, telefonos (jsonb), correos (jsonb),
--                       puesto, redes (jsonb), etapa_cambiada_en.
--   Funciones de servicio (sólo backend) para renombrar/fusionar/eliminar
--   etiquetas de contactos e inmuebles en toda una organización.
--
-- TOLERA TABLAS VIEJAS: en producción pipeline_etapas y fuentes_captacion ya
-- existían con otra forma (user_id NOT NULL, sin org_id/nombre_norm). Aquí se
-- agregan las columnas que falten y se quita el NOT NULL de columnas viejas
-- que Broquer ya no llena. No se borra ninguna fila ni columna.
--
-- Requiere: migracion-fase1-inventario.sql (usa bk_normaliza) y
-- migracion-aislamiento-organizacion.sql (usa mis_org_ids). Idempotente.
-- Correr en Supabase → SQL Editor → Run.
-- ═══════════════════════════════════════════════════════════════════════════

begin;

-- ── Columnas viejas NOT NULL que Broquer ya no llena ────────────────────────
-- Va primero: si alguna de estas tablas ya existía con columnas obligatorias que no son
-- de este esquema (y sin valor por defecto), los guardados nuevos fallarían.
-- Se les quita el NOT NULL (no se borran ni se cambian los datos).
do $$
declare r record;
begin
  for r in
    select c.relname as tabla, a.attname as columna
      from pg_attribute a
      join pg_class c on c.oid = a.attrelid
      join pg_namespace n on n.oid = c.relnamespace
      join (values
        ('pipeline_etapas',   array['id', 'nombre']),
        ('contacto_tipos',    array['id', 'org_id', 'clave', 'nombre']),
        ('fuentes_captacion', array['id', 'org_id', 'nombre', 'nombre_norm'])
      ) as t(tabla, nuestras) on t.tabla = c.relname
     where n.nspname = 'public' and a.attnum > 0 and not a.attisdropped
       and a.attnotnull and not a.atthasdef
       and a.attname <> all (t.nuestras)
       and not exists (select 1 from pg_index i
                        where i.indrelid = c.oid and i.indisprimary and a.attnum = any (i.indkey))
  loop
    execute format('alter table public.%I alter column %I drop not null', r.tabla, r.columna);
    raise notice '%.%: se quitó NOT NULL (columna vieja que Broquer ya no llena)', r.tabla, r.columna;
  end loop;
end $$;

-- ── Etapas del pipeline ─────────────────────────────────────────────────────
create table if not exists public.pipeline_etapas (
  id uuid primary key default gen_random_uuid(),
  user_id uuid,
  nombre text not null,
  orden integer default 0,
  color text,
  created_at timestamptz default now()
);
alter table public.pipeline_etapas
  add column if not exists user_id uuid,
  add column if not exists nombre text,
  add column if not exists orden integer default 0,
  add column if not exists color text,
  add column if not exists created_at timestamptz default now(),
  add column if not exists org_id uuid,
  add column if not exists clave text,
  add column if not exists es_sistema boolean not null default false;
-- Tabla vieja: user_id venía NOT NULL; las etapas nuevas son de la
-- organización y no llevan user_id.
alter table public.pipeline_etapas alter column user_id drop not null;

-- La clave de las etapas que ya existían es el nombre en minúsculas: es
-- exactamente lo que las pantallas guardaban en contactos.estatus.
update public.pipeline_etapas set clave = lower(btrim(nombre)) where clave is null;
update public.pipeline_etapas e
   set org_id = om.org_id
  from public.organizacion_miembros om
 where e.org_id is null and e.user_id is not null
   and om.user_id = e.user_id and om.activo = true;

-- Etapas default para cada organización que todavía no tiene ninguna.
insert into public.pipeline_etapas (org_id, clave, nombre, orden, color, es_sistema)
select o.id, d.clave, d.nombre, d.orden, d.color, true
  from public.organizaciones o
  cross join (values
    ('futuro',     'Futuro',      10, 'var(--etapa-futuro)'),
    ('nuevo',      'Nuevo',       20, 'var(--etapa-nuevo)'),
    ('activo',     'Activo',      30, 'var(--etapa-activo)'),
    ('contactado', 'Contactado',  40, 'var(--etapa-contactado)'),
    ('cerrado',    'Cerrado',     50, 'var(--etapa-cerrado)'),
    ('descartado', 'Descartado',  60, 'var(--etapa-descartado)')
  ) as d(clave, nombre, orden, color)
 where not exists (select 1 from public.pipeline_etapas e where e.org_id = o.id);

-- "Basura/Spam" para todas las organizaciones (al final del tablero).
insert into public.pipeline_etapas (org_id, clave, nombre, orden, color, es_sistema)
select o.id, 'spam', 'Basura/Spam',
       coalesce((select max(orden) from public.pipeline_etapas e where e.org_id = o.id), 0) + 10,
       'var(--mute-2)', true
  from public.organizaciones o
 where not exists (select 1 from public.pipeline_etapas e where e.org_id = o.id and e.clave = 'spam');

create index if not exists idx_pipeline_etapas_org on public.pipeline_etapas (org_id, orden);

alter table public.pipeline_etapas enable row level security;
drop policy if exists "equipo ve etapas de su organizacion" on public.pipeline_etapas;
create policy "equipo ve etapas de su organizacion"
  on public.pipeline_etapas for select
  using (org_id in (select public.mis_org_ids()) or user_id = auth.uid());
-- Escrituras sólo por el backend (Ajustes de CRM valida que seas admin).

-- ── Tipos de contacto ───────────────────────────────────────────────────────
create table if not exists public.contacto_tipos (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  clave text not null,
  nombre text not null,
  orden integer not null default 0,
  es_sistema boolean not null default false,
  created_at timestamptz not null default now()
);
create unique index if not exists contacto_tipos_org_clave on public.contacto_tipos (org_id, clave);

insert into public.contacto_tipos (org_id, clave, nombre, orden, es_sistema)
select o.id, d.clave, d.nombre, d.orden, true
  from public.organizaciones o
  cross join (values
    ('arrendador',         'Propietario / Arrendador',  10),
    ('arrendatario',       'Inquilino / Arrendatario',  20),
    ('comprador',          'Comprador',                 30),
    ('vendedor',           'Vendedor',                  40),
    ('obligado_solidario', 'Obligado solidario',        50),
    ('colega',             'Colega / Agente',           60),
    ('notario',            'Notario',                   70),
    ('valuador',           'Valuador',                  80),
    ('juridico',           'Jurídico',                  90),
    ('agente_externo',     'Agente externo',           100),
    ('otro',               'Otro',                     110)
  ) as d(clave, nombre, orden)
on conflict (org_id, clave) do nothing;

alter table public.contacto_tipos enable row level security;
drop policy if exists "equipo ve tipos de su organizacion" on public.contacto_tipos;
create policy "equipo ve tipos de su organizacion"
  on public.contacto_tipos for select
  using (org_id in (select public.mis_org_ids()));

-- ── Fuentes de captación (catálogo controlado) ──────────────────────────────
create table if not exists public.fuentes_captacion (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  nombre text not null,
  nombre_norm text not null,
  created_at timestamptz not null default now()
);
-- Tabla vieja (id, user_id NOT NULL, nombre, created_at): se completa.
alter table public.fuentes_captacion
  add column if not exists org_id uuid,
  add column if not exists nombre text,
  add column if not exists nombre_norm text,
  add column if not exists created_at timestamptz not null default now();
do $$
begin
  if exists (select 1 from information_schema.columns
              where table_schema = 'public' and table_name = 'fuentes_captacion' and column_name = 'user_id') then
    alter table public.fuentes_captacion alter column user_id drop not null;
    update public.fuentes_captacion f
       set org_id = om.org_id
      from public.organizacion_miembros om
     where f.org_id is null and om.user_id = f.user_id and om.activo = true;
  end if;
end $$;
update public.fuentes_captacion set nombre_norm = public.bk_normaliza(nombre)
 where nombre_norm is null and nombre is not null;
create unique index if not exists fuentes_captacion_org_norm on public.fuentes_captacion (org_id, nombre_norm);

alter table public.contactos
  add column if not exists fuente_id uuid,
  add column if not exists telefonos jsonb not null default '[]'::jsonb,
  add column if not exists correos jsonb not null default '[]'::jsonb,
  add column if not exists puesto text,
  add column if not exists redes jsonb not null default '{}'::jsonb,
  add column if not exists etapa_cambiada_en timestamptz;

-- Fuentes que ya existen como texto libre: una por variante normalizada; el
-- nombre que queda es la forma más usada.
insert into public.fuentes_captacion (org_id, nombre, nombre_norm)
select org_id, nombre, norm
  from (
    select c.org_id, btrim(c.fuente) as nombre, public.bk_normaliza(c.fuente) as norm,
           row_number() over (partition by c.org_id, public.bk_normaliza(c.fuente)
                              order by count(*) desc, btrim(c.fuente)) as rn
      from public.contactos c
     where c.org_id is not null and coalesce(btrim(c.fuente), '') <> ''
     group by c.org_id, btrim(c.fuente), public.bk_normaliza(c.fuente)
  ) v
 where rn = 1 and norm <> ''
on conflict (org_id, nombre_norm) do nothing;

-- Fuentes default para todas las organizaciones.
insert into public.fuentes_captacion (org_id, nombre, nombre_norm)
select o.id, d.nombre, public.bk_normaliza(d.nombre)
  from public.organizaciones o
  cross join (values ('Facebook'), ('Instagram'), ('WhatsApp'), ('Referido'),
                     ('Portal inmobiliario'), ('Sitio web'), ('Llamada directa'),
                     ('Bolsa Broquer'), ('EasyBroker')) as d(nombre)
on conflict (org_id, nombre_norm) do nothing;

-- Cada contacto apunta a su fuente del catálogo y su texto queda con el
-- nombre canónico (así "facebook", "Facebook " y "FACEBOOK" son una sola).
update public.contactos c
   set fuente_id = f.id,
       fuente = f.nombre
  from public.fuentes_captacion f
 where c.fuente_id is null
   and c.org_id = f.org_id
   and coalesce(btrim(c.fuente), '') <> ''
   and public.bk_normaliza(c.fuente) = f.nombre_norm;

alter table public.fuentes_captacion enable row level security;
drop policy if exists "equipo ve fuentes de su organizacion" on public.fuentes_captacion;
create policy "equipo ve fuentes de su organizacion"
  on public.fuentes_captacion for select
  using (org_id in (select public.mis_org_ids()));

-- Fecha del último cambio de etapa (filtro "cambió de etapa entre…").
create or replace function public.bk_contacto_etapa_cambiada()
returns trigger language plpgsql as $$
begin
  if tg_op = 'INSERT' or new.estatus is distinct from old.estatus then
    new.etapa_cambiada_en := now();
  end if;
  return new;
end $$;
drop trigger if exists trg_contacto_etapa_cambiada on public.contactos;
create trigger trg_contacto_etapa_cambiada
  before insert or update of estatus on public.contactos
  for each row execute function public.bk_contacto_etapa_cambiada();

-- ── Etiquetas: renombrar / fusionar / eliminar en toda la organización ──────
-- Sólo las llama el backend con la service key (Ajustes de CRM valida admin).
create or replace function public.bk_filas_de_org(p_tabla text, p_org uuid)
returns text language sql immutable as $$
  select format(
    '(org_id = %L or (org_id is null and user_id in (select user_id from public.organizacion_miembros where org_id = %L and activo)))',
    p_org, p_org)
$$;

create or replace function public.bk_etiquetas_conteo(p_tabla text, p_org uuid)
returns table(etiqueta text, n bigint)
language plpgsql stable security definer set search_path = public as $$
begin
  if p_tabla not in ('contactos', 'propiedades') then raise exception 'tabla inválida'; end if;
  return query execute format(
    'select t, count(*) from public.%I, unnest(coalesce(etiquetas, ''{}''::text[])) as t where %s group by t order by t',
    p_tabla, public.bk_filas_de_org(p_tabla, p_org));
end $$;

create or replace function public.bk_etiqueta_renombrar(p_tabla text, p_org uuid, p_de text, p_a text)
returns integer
language plpgsql security definer set search_path = public as $$
declare n integer;
begin
  if p_tabla not in ('contactos', 'propiedades') then raise exception 'tabla inválida'; end if;
  if coalesce(btrim(p_a), '') = '' then raise exception 'nombre vacío'; end if;
  -- Reemplaza y quita duplicados (si la destino ya estaba, es una fusión).
  execute format(
    'update public.%I set etiquetas = (select array_agg(distinct x order by x) from unnest(array_replace(etiquetas, %L, %L)) as x)
      where %L = any(etiquetas) and %s',
    p_tabla, p_de, btrim(p_a), p_de, public.bk_filas_de_org(p_tabla, p_org));
  get diagnostics n = row_count;
  return n;
end $$;

create or replace function public.bk_etiqueta_eliminar(p_tabla text, p_org uuid, p_etiqueta text)
returns integer
language plpgsql security definer set search_path = public as $$
declare n integer;
begin
  if p_tabla not in ('contactos', 'propiedades') then raise exception 'tabla inválida'; end if;
  execute format(
    'update public.%I set etiquetas = array_remove(etiquetas, %L) where %L = any(etiquetas) and %s',
    p_tabla, p_etiqueta, p_etiqueta, public.bk_filas_de_org(p_tabla, p_org));
  get diagnostics n = row_count;
  return n;
end $$;

revoke all on function public.bk_etiquetas_conteo(text, uuid) from public, anon, authenticated;
revoke all on function public.bk_etiqueta_renombrar(text, uuid, text, text) from public, anon, authenticated;
revoke all on function public.bk_etiqueta_eliminar(text, uuid, text) from public, anon, authenticated;


commit;

select (select count(*) from public.pipeline_etapas) as etapas,
       (select count(*) from public.contacto_tipos) as tipos,
       (select count(*) from public.fuentes_captacion) as fuentes,
       (select count(*) from public.contactos where fuente_id is not null) as contactos_con_fuente;
