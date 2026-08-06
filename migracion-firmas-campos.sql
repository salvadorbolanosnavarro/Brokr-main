-- =============================================================================
-- Broquer · Firma electrónica — campos colocados sobre el documento
-- Segura de correr en producción: solo AGREGA. No borra ni cambia nada.
-- Corre DESPUÉS de migracion-firmas.sql.
--
-- QUÉ RESUELVE
--   Los contratos dicen "lo firman al margen de cada página y al calce de
--   esta". Si las firmas solo viven en la constancia anexa, el documento se
--   contradice a sí mismo y un abogado contrario tiene de dónde agarrarse.
--   Además, impreso sin la constancia parece un contrato sin firmar.
--
--   Con esto el agente marca dónde va cada firma y la plataforma la coloca
--   ahí. Sirve igual para los contratos que genera Broquer y para el machote
--   que el agente sube con su propia redacción, que es el caso que no se
--   puede controlar de ninguna otra forma.
--
-- CÓMO NO SE ROMPE LA INTEGRIDAD
--   El PDF original se conserva intacto y su huella no cambia. La firma se
--   agrega como una CAPA encima, sin reescribir el texto. Al final existen
--   dos archivos y dos huellas: el que se leyó y el que se firmó. La
--   constancia asienta ambas y en qué página y posición quedó cada firma.
--   El argumento pasa de "es idéntico" a "esto leyó, esto se le agregó, y
--   aquí está el registro de quién y cuándo" — que es más fuerte, no menos.
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 1) LOS CAMPOS
--    Las coordenadas van NORMALIZADAS de 0 a 1 sobre el tamaño de la página,
--    con el origen arriba a la izquierda (como se ve en pantalla).
--
--    Se guardan así y no en centímetros a propósito: una misma plantilla
--    sirve para páginas Carta y A4 sin recalcular nada, y la vista previa
--    del navegador coincide con el PDF final sin importar a qué resolución
--    se haya pintado la hoja.
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists firma_campos (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null,
  documento_id  uuid not null references firma_documentos(id) on delete cascade,
  firmante_id   uuid not null references firma_firmantes(id) on delete cascade,

  pagina        integer not null,          -- 1 = primera hoja

  -- firma   → el trazo grande, normalmente al calce
  -- rubrica → el trazo chico al margen de cada hoja
  -- nombre  → el nombre impreso debajo del trazo
  -- fecha   → la fecha en que firmó
  tipo          text not null default 'firma',

  x             double precision not null,
  y             double precision not null,
  ancho         double precision not null,
  alto          double precision not null,

  created_at    timestamptz not null default now(),

  constraint firma_campos_pagina_ok  check (pagina >= 1),
  constraint firma_campos_x_ok       check (x >= 0 and x <= 1),
  constraint firma_campos_y_ok       check (y >= 0 and y <= 1),
  constraint firma_campos_ancho_ok   check (ancho > 0 and ancho <= 1),
  constraint firma_campos_alto_ok    check (alto  > 0 and alto  <= 1)
);

create index if not exists firma_campos_doc_idx
  on firma_campos (documento_id, pagina);
create index if not exists firma_campos_firmante_idx
  on firma_campos (firmante_id);
create index if not exists firma_campos_user_idx
  on firma_campos (user_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- 2) LAS HOJAS EN IMAGEN
--    Para poder arrastrar un recuadro sobre el contrato hay que verlo. Cada
--    hoja se convierte una sola vez a imagen y se guarda; a partir de ahí la
--    pantalla de colocación abre al instante.
--
--    Se guarda la RUTA, no la imagen: el bucket 'firmas' es privado y todo
--    se sirve con ligas firmadas que caducan.
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists firma_paginas (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null,
  documento_id  uuid not null references firma_documentos(id) on delete cascade,
  pagina        integer not null,
  ruta          text not null,
  ancho_pt      double precision,          -- tamaño real de la hoja en puntos
  alto_pt       double precision,
  created_at    timestamptz not null default now()
);

create unique index if not exists firma_paginas_uniq
  on firma_paginas (documento_id, pagina);


-- ─────────────────────────────────────────────────────────────────────────────
-- 3) DÓNDE QUEDÓ CADA FIRMA
--    Se asienta en el propio documento para que la constancia lo pueda
--    reportar sin recalcular nada, aunque después se borren los campos.
-- ─────────────────────────────────────────────────────────────────────────────
alter table firma_documentos
  add column if not exists campos_colocados boolean not null default false;

alter table firma_documentos
  add column if not exists rubrica_todas boolean not null default false;


-- ─────────────────────────────────────────────────────────────────────────────
-- 4) SEGURIDAD (RLS)
--    Igual que el resto del módulo: el backend usa la service_role key y se
--    brinca estas reglas; estas protegen el acceso directo desde el navegador.
-- ─────────────────────────────────────────────────────────────────────────────
alter table firma_campos  enable row level security;
alter table firma_paginas enable row level security;

drop policy if exists "dueño gestiona sus campos" on firma_campos;
create policy "dueño gestiona sus campos"
  on firma_campos for all
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

drop policy if exists "dueño ve sus paginas" on firma_paginas;
create policy "dueño ve sus paginas"
  on firma_paginas for all
  using (user_id = auth.uid())
  with check (user_id = auth.uid());
