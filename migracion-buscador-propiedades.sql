-- Buscador de propiedades: cada cliente puede tener un "requerimiento" de
-- búsqueda (rango de precio, colonia, tipo de propiedad...) y un ciclo de
-- fondo lo revisa una vez al día, deja listos los enlaces de anuncios que
-- se le parecen y los vuelve a leer si el requerimiento cambió.
--
-- Un requerimiento por cliente (unique en contacto_id): si el usuario
-- vuelve a guardar la ficha de "Requerimiento" de un cliente, se actualiza
-- el mismo registro en vez de acumular duplicados.

create table if not exists requerimientos_busqueda (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null,
  contacto_id         uuid not null,
  activo              boolean not null default true,
  operacion           text not null default 'venta',
  tipo_inmueble       text not null default 'casa',
  colonia             text,
  ciudad              text,
  estado              text,
  precio_min          numeric,
  precio_max          numeric,
  recamaras_min       integer,
  notas               text,
  creado_en           timestamptz not null default now(),
  actualizado_en      timestamptz not null default now(),
  ultima_busqueda_en  timestamptz,
  unique (contacto_id)
);

create index if not exists requerimientos_busqueda_user_idx
  on requerimientos_busqueda (user_id);

create index if not exists requerimientos_busqueda_pendientes_idx
  on requerimientos_busqueda (activo, ultima_busqueda_en);

-- Resultados de la última corrida del ciclo diario. Se reemplazan por
-- completo en cada corrida de un requerimiento (delete + insert) en vez de
-- ir acumulando historial: lo que le sirve al usuario es la foto de hoy,
-- no un archivo de enlaces viejos que ya pudieron venderse o rentarse.
create table if not exists busqueda_resultados (
  id                  uuid primary key default gen_random_uuid(),
  requerimiento_id    uuid not null,
  user_id             uuid not null,
  contacto_id         uuid not null,
  titulo              text,
  url                 text not null,
  portal              text,
  precio              numeric,
  precio_confirmado   boolean not null default false,
  snippet             text,
  encontrado_en       timestamptz not null default now()
);

create index if not exists busqueda_resultados_requerimiento_idx
  on busqueda_resultados (requerimiento_id);

create index if not exists busqueda_resultados_contacto_idx
  on busqueda_resultados (contacto_id);

-- Sin RLS: se lee/escribe exclusivamente con el service key desde el
-- backend (igual que avm_scrape_cache y bolsa.py) — el endpoint filtra por
-- user_id de la sesión, nunca se expone una tabla completa por PostgREST
-- con la llave pública.
alter table requerimientos_busqueda enable row level security;
alter table busqueda_resultados enable row level security;
