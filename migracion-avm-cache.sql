-- Caché durable de páginas raspadas por el AVM (Firecrawl y fetch directo).
-- Dos valuaciones cercanas en tiempo suelen tocar exactamente las mismas
-- URLs de portal (misma colonia, mismo tipo de inmueble): sin esto se le
-- vuelve a cobrar crédito a Firecrawl por la misma página cada vez. La
-- caché en memoria de core/cache.py no sirve para esto: es por proceso y
-- Railway puede reciclar el dyno entre una valuación y la siguiente.
--
-- Efecto secundario buscado, no solo ahorro: esta tabla es el histórico de
-- precios por colonia que hoy no existe en ningún lado — cada fila es un
-- precio/m² fechado y ubicado que se puede consultar más adelante para
-- tendencias de zona, no solo para servir de caché de un solo uso.

create table if not exists avm_scrape_cache (
  url text primary key,
  host text not null,
  colonia text,
  ciudad text,
  fetch_status text not null,
  page_text text not null,
  creado_en timestamptz not null default now()
);

create index if not exists avm_scrape_cache_creado_idx
  on avm_scrape_cache (creado_en);

create index if not exists avm_scrape_cache_colonia_idx
  on avm_scrape_cache (colonia, ciudad);

-- Sin RLS de por medio: esta tabla no tiene datos de usuario ni de cuenta,
-- solo texto de páginas públicas de portales inmobiliarios. Se lee/escribe
-- exclusivamente con el service key desde el backend (igual que bolsa.py).
alter table avm_scrape_cache enable row level security;
