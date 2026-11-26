-- ═══════════════════════════════════════════════════════════════════════════
-- Broquer — Análisis comparativo de mercado (ACM)
--
-- QUÉ AGREGA (sólo tablas nuevas; no toca ni borra nada existente)
--
--   mercado_comparables        Base propia de anuncios del mercado. Cada fila
--                              es UN inmueble (deduplicado entre portales por
--                              "huella"), con la fecha en que se vio por
--                              primera y última vez. Un anuncio que deja de
--                              aparecer pasa a estatus 'retirado': es lo más
--                              cercano a "se vendió" que hay con datos
--                              públicos. Sólo datos públicos de anuncios: sin
--                              teléfonos, nombres ni datos personales.
--   mercado_precios_historial  Cada cambio de precio de un anuncio (para
--                              detectar bajas de precio).
--   mercado_colonias_geo       Caché de coordenadas por colonia: los anuncios
--                              casi nunca traen coordenadas, así que se ubican
--                              en el centro de su colonia (precisión
--                              'colonia', no 'exacta').
--   mercado_zonas              Zonas que la recolección nocturna revisa. Se
--                              alimenta sola con las zonas donde los asesores
--                              hacen ACM.
--   acm_analisis               Los ACM que arma cada asesor: propiedad
--                              analizada, comparables elegidos con sus
--                              ajustes, estrategia de precio, nota para el
--                              propietario y liga pública para compartir.
--
-- Seguridad: RLS encendido y SIN políticas en todas las tablas. Se leen y
-- escriben exclusivamente desde el backend con el service key
-- (routers/acm.py y routers/acm_datos.py), que filtra cada consulta por la
-- cuenta (org_id) o el usuario de la sesión. Nada queda expuesto por la llave
-- pública de PostgREST.
--
-- Idempotente. Correr en Supabase → SQL Editor → Run.
-- ═══════════════════════════════════════════════════════════════════════════

begin;

create table if not exists public.mercado_comparables (
  id                   uuid primary key default gen_random_uuid(),
  huella               text not null unique,          -- llave de deduplicación (core/acm_calculo.huella_comparable)
  fuente               text not null default 'portal', -- portal | easybroker
  portal               text,
  url                  text,
  titulo               text,
  tipo                 text not null,                  -- casa | departamento | terreno | local | oficina | bodega | otro
  operacion            text not null,                  -- venta | renta
  precio               numeric not null,
  moneda               text not null default 'MXN',
  precio_inicial       numeric,                        -- primer precio visto (para medir bajas)
  m2_construccion      numeric,
  m2_terreno           numeric,
  recamaras            integer,
  banos                numeric,
  estacionamientos     integer,
  antiguedad           integer,
  colonia              text,
  colonia_norm         text,
  ciudad               text,
  ciudad_norm          text,
  estado               text,
  pais                 text not null default 'MX',
  lat                  double precision,
  lng                  double precision,
  precision_ubicacion  text not null default 'colonia', -- exacta | colonia | ciudad
  foto_url             text,
  primera_vez          timestamptz not null default now(),
  ultima_vez           timestamptz not null default now(),
  veces_visto          integer not null default 1,
  estatus              text not null default 'activo',  -- activo | retirado
  retirado_en          timestamptz,
  bajas_precio         integer not null default 0,
  creado_en            timestamptz not null default now(),
  actualizado_en       timestamptz not null default now()
);

create index if not exists idx_mercado_comp_geo
  on public.mercado_comparables (pais, operacion, tipo, lat, lng);
create index if not exists idx_mercado_comp_zona
  on public.mercado_comparables (pais, ciudad_norm, colonia_norm, operacion, tipo);
create index if not exists idx_mercado_comp_vigencia
  on public.mercado_comparables (estatus, ultima_vez);

create table if not exists public.mercado_precios_historial (
  id             bigserial primary key,
  comparable_id  uuid not null references public.mercado_comparables (id) on delete cascade,
  precio         numeric not null,
  moneda         text not null default 'MXN',
  visto_en       timestamptz not null default now()
);
create index if not exists idx_mercado_hist_comp
  on public.mercado_precios_historial (comparable_id, visto_en);

create table if not exists public.mercado_colonias_geo (
  clave      text primary key,                         -- pais|ciudad_norm|colonia_norm
  colonia    text,
  ciudad     text,
  estado     text,
  pais       text not null default 'MX',
  lat        double precision,
  lng        double precision,
  creado_en  timestamptz not null default now()
);

create table if not exists public.mercado_zonas (
  clave                text primary key,               -- pais|ciudad_norm|colonia_norm|tipo|operacion
  pais                 text not null default 'MX',
  colonia              text,
  ciudad               text,
  estado               text,
  tipo                 text not null,
  operacion            text not null,
  lat                  double precision,
  lng                  double precision,
  solicitada_en        timestamptz not null default now(), -- último ACM que pidió esta zona
  ultima_recoleccion   timestamptz,
  corridas             integer not null default 0,
  ultimo_resultado     integer not null default 0,
  creado_en            timestamptz not null default now()
);
create index if not exists idx_mercado_zonas_pend
  on public.mercado_zonas (solicitada_en desc, ultima_recoleccion);

create table if not exists public.acm_analisis (
  id                uuid primary key default gen_random_uuid(),
  org_id            uuid,
  user_id           uuid not null,
  contacto_id       text,
  propiedad_id      uuid,
  origen_id         uuid,                               -- ACM del que se actualizó
  titulo            text,
  estatus           text not null default 'borrador',   -- borrador | presentado
  sujeto            jsonb not null default '{}'::jsonb,
  comparables       jsonb not null default '[]'::jsonb,
  estrategia        jsonb not null default '{}'::jsonb,
  resultado         jsonb not null default '{}'::jsonb,
  nota_propietario  text,
  notas_internas    text,
  liga_token        text unique,
  liga_activa       boolean not null default false,
  vistas            integer not null default 0,
  ultima_vista      timestamptz,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
create index if not exists idx_acm_org on public.acm_analisis (org_id, updated_at desc);
create index if not exists idx_acm_user on public.acm_analisis (user_id, updated_at desc);
create index if not exists idx_acm_propiedad on public.acm_analisis (propiedad_id);

alter table public.mercado_comparables enable row level security;
alter table public.mercado_precios_historial enable row level security;
alter table public.mercado_colonias_geo enable row level security;
alter table public.mercado_zonas enable row level security;
alter table public.acm_analisis enable row level security;

commit;
