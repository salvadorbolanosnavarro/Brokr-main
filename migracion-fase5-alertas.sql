-- ═══════════════════════════════════════════════════════════════════════════
-- Broquer — Fase 5: alertas de búsqueda y coincidencias (paridad EasyBroker)
--
-- QUÉ AGREGA (sólo columnas/tablas nuevas; no borra nada)
--   requerimientos_busqueda
--     + org_id, operaciones[], tipos[], zonas[] (varias colonias o ciudades),
--       moneda, banos_min, estacionamientos_min, m² de construcción y de
--       terreno (mín/máx), caracteristicas[] (casillas de la Fase 1, incluye
--       financiamiento), solo_comision_compartida, ultima_alerta_en.
--     · contacto_id pasa de uuid a text: los contactos de Broquer usan ids de
--       texto ("c_…"), así que guardar un requerimiento fallaba para ellos.
--       El cambio de tipo conserva todos los valores (uuid → texto).
--   alertas_enviadas  qué inmueble coincidió con qué requerimiento, de dónde
--                     salió (propio, equipo, bolsa) y si ya se le mandó al
--                     cliente (por WhatsApp o correo, cuándo y quién).
--
-- Requiere: migracion-fase1-inventario.sql. Idempotente.
-- Correr en Supabase → SQL Editor → Run.
-- ═══════════════════════════════════════════════════════════════════════════

begin;

-- contacto_id a texto (sólo si hoy es uuid).
do $$
begin
  if exists (select 1 from information_schema.columns
              where table_schema = 'public' and table_name = 'requerimientos_busqueda'
                and column_name = 'contacto_id' and data_type = 'uuid') then
    alter table public.requerimientos_busqueda alter column contacto_id type text using contacto_id::text;
  end if;
  if exists (select 1 from information_schema.columns
              where table_schema = 'public' and table_name = 'busqueda_resultados'
                and column_name = 'contacto_id' and data_type = 'uuid') then
    alter table public.busqueda_resultados alter column contacto_id type text using contacto_id::text;
  end if;
end $$;

alter table public.requerimientos_busqueda
  add column if not exists org_id uuid,
  add column if not exists operaciones text[] not null default '{}'::text[],
  add column if not exists tipos text[] not null default '{}'::text[],
  add column if not exists zonas text[] not null default '{}'::text[],
  add column if not exists moneda text not null default 'MXN',
  add column if not exists banos_min numeric,
  add column if not exists estacionamientos_min integer,
  add column if not exists m2_construccion_min numeric,
  add column if not exists m2_construccion_max numeric,
  add column if not exists m2_terreno_min numeric,
  add column if not exists m2_terreno_max numeric,
  add column if not exists caracteristicas text[] not null default '{}'::text[],
  add column if not exists solo_comision_compartida boolean not null default false,
  add column if not exists ultima_alerta_en timestamptz;

-- Rellena lo nuevo desde los campos de siempre.
update public.requerimientos_busqueda r
   set org_id = om.org_id
  from public.organizacion_miembros om
 where r.org_id is null and om.user_id = r.user_id and om.activo = true;
update public.requerimientos_busqueda
   set operaciones = array[operacion]
 where coalesce(array_length(operaciones, 1), 0) = 0 and operacion is not null;
update public.requerimientos_busqueda
   set tipos = array[tipo_inmueble]
 where coalesce(array_length(tipos, 1), 0) = 0 and tipo_inmueble is not null;
update public.requerimientos_busqueda
   set zonas = array_remove(array[nullif(btrim(colonia), ''), nullif(btrim(ciudad), '')], null)
 where coalesce(array_length(zonas, 1), 0) = 0 and (colonia is not null or ciudad is not null);

create index if not exists idx_req_org on public.requerimientos_busqueda (org_id, activo);

create table if not exists public.alertas_enviadas (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  requerimiento_id uuid not null,
  contacto_id text not null,
  propiedad_id uuid not null,
  origen text not null default 'propio',       -- propio | equipo | bolsa
  estado text not null default 'pendiente',    -- pendiente | enviada | descartada
  canal text,                                  -- whatsapp | correo
  detectada_en timestamptz not null default now(),
  enviada_en timestamptz,
  enviada_por uuid
);
create unique index if not exists alertas_req_prop_uniq on public.alertas_enviadas (requerimiento_id, propiedad_id);
create index if not exists idx_alertas_org on public.alertas_enviadas (org_id, estado);
alter table public.alertas_enviadas enable row level security;
drop policy if exists "equipo ve alertas de su organizacion" on public.alertas_enviadas;
create policy "equipo ve alertas de su organizacion"
  on public.alertas_enviadas for select
  using (org_id in (select public.mis_org_ids()));

commit;
