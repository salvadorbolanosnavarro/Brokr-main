-- =============================================================================
-- AVM Broquer v2: tablas de datos del modelo de valor
-- Copiar TODO, pegar en Supabase > SQL Editor, botón Run.
--
-- QUÉ CREA
--   avm_listings        anuncios únicos (uno por URL), con ubicación y H3
--   avm_price_history   cada cambio de precio de un anuncio
--   avm_closings        cierres reales capturados por el equipo
--   avm_context_ageb    Censo 2020 por AGEB + NSE + rezago CONEVAL
--   avm_poi_counts      conteos DENUE por hexágono H3-9 y distancias OSM
--   avm_index           índice de precios por zona y trimestre (SHF, etc.)
--   avm_predictions     bitácora de cada estimado, para auditar contra cierres
--   avm_text_cache      caché de lo que el LLM extrajo de cada descripción
--   bucket avm-modelos  (privado) para guardar las versiones del modelo
--
-- NO ROMPE NADA. Solo crea tablas nuevas (if not exists). Se puede correr dos
-- veces. Todas con RLS activo y sin políticas: solo el backend (service key)
-- las lee y escribe, igual que avm_scrape_cache.
-- =============================================================================

begin;

create extension if not exists postgis;

-- ── avm_listings ─────────────────────────────────────────────────────────────
create table if not exists avm_listings (
  id                  bigint generated always as identity primary key,
  fuente              text not null,                 -- inmuebles24, vivanuncios, ...
  url                 text not null unique,
  fecha_alta          date not null default current_date,
  fecha_baja          date,                          -- 14 días sin aparecer
  ultimo_visto        timestamptz not null default now(),
  tipo                text not null check (tipo in ('casa','depto','terreno','local')),
  operacion           text not null check (operacion in ('venta','renta')),
  precio              numeric(16,2) not null check (precio > 0),
  moneda              text not null default 'MXN',
  m2_construidos      numeric(10,2),
  m2_terreno          numeric(10,2),
  recamaras           smallint,
  banos               smallint,
  medios_banos        smallint,
  estacionamientos    smallint,
  edad_anios          smallint,
  nivel               smallint,                      -- nivel/piso (deptos)
  amenidades          jsonb not null default '{}'::jsonb,
  descripcion         text,
  fotos               jsonb not null default '[]'::jsonb,
  lat                 double precision,
  lon                 double precision,
  geom                geography(Point, 4326)
                      generated always as (
                        case when lat is not null and lon is not null
                             then st_setsrid(st_makepoint(lon, lat), 4326)::geography end
                      ) stored,
  precision_ubicacion text check (precision_ubicacion in ('exacta','aproximada')),
  estado              text,
  municipio           text,
  colonia             text,
  h3_7                text,
  h3_8                text,
  h3_9                text,
  ageb_cvegeo         text,
  cluster_id          bigint,                        -- duplicados comparten cluster
  es_principal        boolean not null default true,
  calidad             text not null default 'pendiente'
                      check (calidad in ('pendiente','ok','descartado')),
  motivo_descarte     text,
  extra               jsonb not null default '{}'::jsonb,  -- variables extraídas del texto
  creado_en           timestamptz not null default now(),
  actualizado_en      timestamptz not null default now()
);

create index if not exists avm_listings_geom_idx    on avm_listings using gist (geom);
create index if not exists avm_listings_h3_8_idx    on avm_listings (h3_8);
create index if not exists avm_listings_h3_7_idx    on avm_listings (h3_7);
create index if not exists avm_listings_mun_idx     on avm_listings (municipio, tipo, operacion);
create index if not exists avm_listings_cluster_idx on avm_listings (cluster_id);
create index if not exists avm_listings_vivo_idx    on avm_listings (fecha_baja) where fecha_baja is null;

-- ── avm_price_history ────────────────────────────────────────────────────────
create table if not exists avm_price_history (
  id          bigint generated always as identity primary key,
  listing_id  bigint not null references avm_listings(id) on delete cascade,
  fecha       timestamptz not null default now(),
  precio      numeric(16,2) not null check (precio > 0)
);
create index if not exists avm_price_history_listing_idx on avm_price_history (listing_id, fecha);

-- ── avm_closings ─────────────────────────────────────────────────────────────
create table if not exists avm_closings (
  id                      bigint generated always as identity primary key,
  listing_id              bigint references avm_listings(id) on delete set null,
  capturado_por           uuid,                       -- auth.users.id
  tipo                    text not null check (tipo in ('casa','depto','terreno','local')),
  precio_oferta_inicial   numeric(16,2) check (precio_oferta_inicial > 0),
  precio_cierre           numeric(16,2) not null check (precio_cierre > 0),
  fecha_cierre            date not null,
  dias_en_mercado         integer check (dias_en_mercado >= 0),
  fuente                  text not null check (fuente in ('navarro','cierres','avaluo')),
  m2_construidos          numeric(10,2),
  m2_terreno              numeric(10,2),
  recamaras               smallint,
  banos                   smallint,
  edad_anios              smallint,
  conservacion            smallint check (conservacion between 1 and 5),
  lat                     double precision,
  lon                     double precision,
  estado                  text,
  municipio               text,
  colonia                 text,
  notas                   text,
  creado_en               timestamptz not null default now()
);
create index if not exists avm_closings_mun_idx on avm_closings (municipio, fecha_cierre);

-- ── avm_context_ageb ─────────────────────────────────────────────────────────
create table if not exists avm_context_ageb (
  cvegeo             text primary key,               -- ent+mun+loc+ageb (13)
  estado             text,
  municipio          text,
  poblacion          integer,
  viviendas          integer,
  densidad_hab_km2   numeric(12,2),
  escolaridad_prom   numeric(5,2),
  pct_auto           numeric(5,2),
  pct_internet       numeric(5,2),
  pct_computadora    numeric(5,2),
  nse_amai           text,                           -- A/B, C+, C, C-, D+, D, E
  nse_score          numeric(5,2),                   -- ordinal numérico del NSE
  rezago_coneval     text,                           -- Muy bajo ... Muy alto
  lat                double precision,
  lon                double precision,
  fuente             text not null default 'INEGI Censo 2020',
  actualizado_en     timestamptz not null default now()
);

-- ── avm_poi_counts ───────────────────────────────────────────────────────────
create table if not exists avm_poi_counts (
  h3_9                 text primary key,
  escuelas             integer not null default 0,
  hospitales           integer not null default 0,
  supermercados        integer not null default 0,
  bancos               integer not null default 0,
  restaurantes         integer not null default 0,
  dist_avenida_m       numeric(10,1),
  dist_parque_m        numeric(10,1),
  dist_centro_m        numeric(10,1),
  fuente               text not null default 'DENUE + OSM',
  actualizado_en       timestamptz not null default now()
);

-- ── avm_index ────────────────────────────────────────────────────────────────
create table if not exists avm_index (
  id          bigint generated always as identity primary key,
  zona        text not null,                         -- municipio o zona metropolitana
  nivel       text not null default 'municipio' check (nivel in ('municipio','zm','estado','nacional')),
  trimestre   text not null,                         -- '2026T3'
  valor       numeric(12,4) not null check (valor > 0),
  fuente      text not null default 'SHF',
  unique (zona, nivel, trimestre, fuente)
);

-- ── avm_predictions ──────────────────────────────────────────────────────────
create table if not exists avm_predictions (
  id               bigint generated always as identity primary key,
  usuario          uuid,
  creado_en        timestamptz not null default now(),
  version_modelo   text not null,
  entrada          jsonb not null,
  motores          jsonb not null,                   -- valor, sigma y estado por motor
  pesos            jsonb not null,
  valor            numeric(16,2),
  rango_bajo       numeric(16,2),
  rango_alto       numeric(16,2),
  confianza        text,
  delta            numeric(6,4),
  emitido          boolean not null default true,
  closing_id       bigint references avm_closings(id) on delete set null
);
create index if not exists avm_predictions_fecha_idx on avm_predictions (creado_en);

-- ── avm_text_cache ───────────────────────────────────────────────────────────
create table if not exists avm_text_cache (
  hash_descripcion text primary key,                 -- sha256 del texto
  extraido         jsonb not null,
  modelo           text,
  creado_en        timestamptz not null default now()
);

-- ── Bucket privado para los artefactos del modelo (joblib) ───────────────────
do $$
begin
  if to_regclass('storage.buckets') is not null then
    insert into storage.buckets (id, name, public)
    values ('avm-modelos', 'avm-modelos', false)
    on conflict (id) do nothing;
  end if;
end $$;

-- ── RLS: solo service key ────────────────────────────────────────────────────
alter table avm_listings       enable row level security;
alter table avm_price_history  enable row level security;
alter table avm_closings       enable row level security;
alter table avm_context_ageb   enable row level security;
alter table avm_poi_counts     enable row level security;
alter table avm_index          enable row level security;
alter table avm_predictions    enable row level security;
alter table avm_text_cache     enable row level security;

commit;
