-- Broquer · Tareas — archivos adjuntos
-- Pégalo en Supabase > SQL Editor y dale Run. Es seguro correrlo más de una
-- vez y no toca las tareas existentes (llegan con '[]').
--
-- Mismo formato que actividades.adjuntos (migracion-actividades-adjuntos.sql)
-- y mismo bucket 'adjuntos-historial', así que no hace falta nada de Storage:
--   { "url": "...", "nombre": "contrato.pdf", "tipo": "application/pdf",
--     "tamano": 123456, "categoria": "imagen" | "video" | "archivo" }

alter table public.tareas
  add column if not exists adjuntos jsonb not null default '[]'::jsonb;

alter table public.tareas
  drop constraint if exists tareas_adjuntos_es_arreglo;
alter table public.tareas
  add constraint tareas_adjuntos_es_arreglo check (jsonb_typeof(adjuntos) = 'array');
