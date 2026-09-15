-- Adjuntos (fotos, videos, archivos) en el historial de Contactos/Directorio,
-- Clientes e Inmuebles. Los tres módulos reutilizan la misma tabla
-- "actividades" (una fila por nota, filtrada por contacto_id o
-- propiedad_id) y el mismo feed de historial, así que un solo cambio de
-- esquema + un solo bucket cubre los tres.
--
-- Cambio aditivo y seguro: no rompe filas existentes (adjuntos llega con
-- default '[]'::jsonb).
--
-- Cada elemento del arreglo "adjuntos" tiene esta forma:
--   { "url": "...", "nombre": "foto.jpg", "tipo": "image/jpeg",
--     "tamano": 123456, "categoria": "imagen" | "video" | "archivo" }

alter table actividades
  add column if not exists adjuntos jsonb not null default '[]'::jsonb;

alter table actividades
  drop constraint if exists actividades_adjuntos_es_arreglo;
alter table actividades
  add constraint actividades_adjuntos_es_arreglo check (jsonb_typeof(adjuntos) = 'array');

-- ── Bucket de adjuntos (público, mismo patrón que 'fotos-propiedades') ──────
-- Contactos, Clientes e Inmuebles son recursos compartidos por todo el
-- equipo de la organización (no hay una sola cuenta dueña de cada fila), así
-- que el bucket va público para lectura —igual que las fotos de inmuebles—
-- en vez del patrón "dueño-only" de 'firmas'/'fin-comprobantes', que sí
-- protege documentos personales de una sola cuenta.
insert into storage.buckets (id, name, public)
select 'adjuntos-historial', 'adjuntos-historial', true
where not exists (select 1 from storage.buckets where id = 'adjuntos-historial');

drop policy if exists "lectura publica de adjuntos de historial" on storage.objects;
create policy "lectura publica de adjuntos de historial"
  on storage.objects for select
  using (bucket_id = 'adjuntos-historial');

drop policy if exists "usuarios autenticados suben adjuntos de historial" on storage.objects;
create policy "usuarios autenticados suben adjuntos de historial"
  on storage.objects for insert
  with check (bucket_id = 'adjuntos-historial' and auth.role() = 'authenticated');
