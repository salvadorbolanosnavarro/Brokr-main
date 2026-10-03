-- ═══════════════════════════════════════════════════════════════════════════
-- Broquer — Fase 2: multimedia de inmuebles (paridad EasyBroker)
--
-- QUÉ AGREGA (sólo columnas nuevas con default; no borra ni cambia nada)
--   propiedades.videos      text[] — ligas de YouTube (varias)
--   propiedades.tours       text[] — ligas de tour virtual (Matterport, Kuula…)
--   propiedades.documentos  jsonb  — documentos PÚBLICOS (planos, volantes,
--                                    lista de precios):
--                                    [{"nombre":"Plano.pdf","url":"…",
--                                      "tipo":"application/pdf","tamano":123}]
--                                    Son distintos de los adjuntos privados de
--                                    la bitácora (actividades.adjuntos).
--   Bucket de Storage 'documentos-publicos' (lectura pública, como las fotos).
--   La vista propiedades_publicas_extra suma videos, tours y documentos para
--   el micrositio.
--
-- Requiere: migracion-fase1-inventario.sql. Idempotente.
-- Correr en Supabase → SQL Editor → Run.
-- ═══════════════════════════════════════════════════════════════════════════

begin;

alter table public.propiedades
  add column if not exists videos text[] not null default '{}'::text[],
  add column if not exists tours text[] not null default '{}'::text[],
  add column if not exists documentos jsonb not null default '[]'::jsonb;

alter table public.propiedades drop constraint if exists propiedades_documentos_es_arreglo;
alter table public.propiedades
  add constraint propiedades_documentos_es_arreglo check (jsonb_typeof(documentos) = 'array');

-- ── Bucket público de documentos de inmuebles ──
-- Las rutas son <org_id o user_id>/<archivo>; subir requiere sesión.
insert into storage.buckets (id, name, public)
select 'documentos-publicos', 'documentos-publicos', true
where not exists (select 1 from storage.buckets where id = 'documentos-publicos');

drop policy if exists "lectura publica de documentos de inmuebles" on storage.objects;
create policy "lectura publica de documentos de inmuebles"
  on storage.objects for select
  using (bucket_id = 'documentos-publicos');

drop policy if exists "usuarios autenticados suben documentos de inmuebles" on storage.objects;
create policy "usuarios autenticados suben documentos de inmuebles"
  on storage.objects for insert
  with check (bucket_id = 'documentos-publicos' and auth.role() = 'authenticated');

drop policy if exists "dueno borra sus documentos de inmuebles" on storage.objects;
create policy "dueno borra sus documentos de inmuebles"
  on storage.objects for delete
  using (bucket_id = 'documentos-publicos' and owner = auth.uid());

-- ── Vista pública: suma multimedia ──
-- (se recrea con las mismas columnas de la fase 1 + las nuevas al final)
create or replace view public.propiedades_publicas_extra as
select p.id, p.subtipo,
       case when coalesce(p.mostrar_precio, true) then p.operaciones
            else coalesce((select jsonb_agg(o - 'precio') from jsonb_array_elements(p.operaciones) o), '[]'::jsonb)
       end as operaciones,
       coalesce(p.mostrar_precio, true) as mostrar_precio,
       p.precio_unidad, p.mantenimiento_incluido,
       p.antiguedad, p.condicion, p.disposicion, p.orientacion,
       p.pisos_edificio, p.caracteristicas, p.otras_caracteristicas,
       case when p.mostrar_ubicacion_exacta then p.lat end as lat,
       case when p.mostrar_ubicacion_exacta then p.lng end as lng,
       p.videos, p.tours, p.documentos
  from public.propiedades p
 where p.id in (select id from public.propiedades_publicas);

grant select on public.propiedades_publicas_extra to anon, authenticated;

commit;
