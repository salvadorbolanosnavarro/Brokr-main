-- ══════════════════════════════════════════════════════════════════════════
-- Archivos seguros · Parte A — cerrar la subida directa desde el navegador
-- ══════════════════════════════════════════════════════════════════════════
-- Contexto: en otra plataforma alguien subió como "adjunto" una copia de
-- WhatsApp Web (.html). Quedó en una liga pública que se abría como página.
--
-- El navegador sube directo a Supabase en 3 buckets: fotos-propiedades,
-- documentos-publicos y adjuntos-historial. La validación del navegador
-- (archivos-seguros.js) se puede saltar, así que aquí se pone la barrera que
-- NO se puede saltar, en Supabase mismo:
--   1. Cada bucket acepta solo ciertos tipos (Content-Type) y un tamaño máximo.
--      text/html, image/svg+xml, XML, JS, etc. quedan fuera.
--   2. Una regla RESTRICTIVA rechaza nombres con extensión riesgosa en
--      cualquier parte (foto.jpg.html, x.html.jpg, .svg, .js, .mhtml…) y exige
--      una extensión de la lista blanca del bucket.
--   3. La vista pública propiedades_publicas_extra deja de mostrar documentos
--      marcados como privados ("publico": false). Los documentos que ya
--      existían no tienen esa marca y siguen públicos: ninguna ficha cambia.
--
-- NO borra, mueve ni cambia archivos existentes. NO cambia ningún bucket a
-- privado (eso es la Parte B). El backend (service_role) no usa reglas RLS,
-- pero sí respeta los tipos/tamaños del bucket; los tipos elegidos cubren
-- todo lo que el backend sube a estos buckets.
--
-- Reversa: 20261106-archivos-seguros-REVERSA.sql
-- Verificación (solo lectura): 20261106-archivos-seguros-verificar.sql
-- ══════════════════════════════════════════════════════════════════════════

begin;

create schema if not exists respaldo_archivos_20261106;
revoke all on schema respaldo_archivos_20261106 from public, anon, authenticated;

-- ── Foto de cómo estaba todo, para la reversa ────────────────────────────
do $$
begin
  if to_regclass('respaldo_archivos_20261106.buckets') is not null then
    raise exception 'La Parte A ya se aplicó (existe respaldo_archivos_20261106.buckets). Corre la REVERSA antes de repetirla.';
  end if;
  create table respaldo_archivos_20261106.buckets as
    select id, public, allowed_mime_types, file_size_limit
      from storage.buckets
     where id in ('fotos-propiedades', 'documentos-publicos', 'adjuntos-historial');
  create table respaldo_archivos_20261106.vista (
    nombre text primary key, definicion text not null, opciones text[]);
  insert into respaldo_archivos_20261106.vista
    select 'propiedades_publicas_extra',
           pg_get_viewdef('public.propiedades_publicas_extra'::regclass, false),
           c.reloptions
      from pg_class c
     where c.oid = 'public.propiedades_publicas_extra'::regclass;
  revoke all on all tables in schema respaldo_archivos_20261106 from public, anon, authenticated;
end $$;

-- ── 1) Tipos y tamaño máximo por bucket ──────────────────────────────────
update storage.buckets
   set allowed_mime_types = array['image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif',
                                  'image/heic', 'image/heif'],
       file_size_limit = 26214400            -- 25 MB
 where id = 'fotos-propiedades';

update storage.buckets
   set allowed_mime_types = array['application/pdf', 'image/jpeg', 'image/jpg', 'image/png', 'image/webp'],
       file_size_limit = 15728640            -- 15 MB
 where id = 'documentos-publicos';

update storage.buckets
   set allowed_mime_types = array[
         'image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif', 'image/heic', 'image/heif',
         'application/pdf',
         'video/mp4', 'video/quicktime', 'video/3gpp', 'video/webm',
         'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
         'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
         'application/vnd.openxmlformats-officedocument.presentationml.presentation',
         'application/msword', 'application/vnd.ms-excel', 'application/vnd.ms-powerpoint',
         'application/zip', 'application/x-zip-compressed',
         'text/plain', 'text/csv'],
       file_size_limit = 26214400            -- 25 MB
 where id = 'adjuntos-historial';

-- ── 2) Nombres: lista blanca de extensiones y nada riesgoso en el nombre ──
-- RESTRICTIVA: se suma (AND) a las reglas que ya existen; no abre nada nuevo.
create or replace function public.archivo_nombre_seguro(p_bucket text, p_nombre text)
returns boolean
language sql
immutable
set search_path = ''
as $$
  select case
    when p_bucket not in ('fotos-propiedades', 'documentos-publicos', 'adjuntos-historial') then true
    -- Ningún segmento del nombre puede ser una extensión riesgosa (foto.jpg.html, x.html.jpg).
    when lower(p_nombre) ~ '\.(html?|xhtml?|shtml|mhtml?|webarchive|eml|svgz?|xml|xslt?|rss|atom|m?js|cjs|jsx|tsx?|vbs|vbe|wsf|wsh|hta|exe|msi|bat|cmd|com|scr|pif|cpl|dll|sys|lnk|reg|sh|bash|zsh|ps1|psm1|jar|apk|app|dmg|pkg|deb|rpm|php[345]?|phtml|phar|aspx?|jsp|cgi|pl|py|rb|swf|url|iso|svc|htaccess)(\.|$)'
      then false
    when p_bucket = 'fotos-propiedades' then
      lower(p_nombre) ~ '\.(jpe?g|jfif|jpe|png|webp|gif|heic|heif)$'
    when p_bucket = 'documentos-publicos' then
      lower(p_nombre) ~ '\.(pdf|jpe?g|png|webp)$'
    else -- adjuntos-historial
      lower(p_nombre) ~ '\.(jpe?g|jfif|jpe|png|webp|gif|heic|heif|pdf|mp4|m4v|mov|qt|3gpp?|webm|docx|dotx|xlsx|pptx|doc|xls|ppt|zip|txt|csv)$'
  end
$$;
revoke all on function public.archivo_nombre_seguro(text, text) from public;
grant execute on function public.archivo_nombre_seguro(text, text) to anon, authenticated, service_role;

drop policy if exists "archivos_seguros_subir" on storage.objects;
create policy "archivos_seguros_subir" on storage.objects
  as restrictive for insert to public
  with check (public.archivo_nombre_seguro(bucket_id, name));

drop policy if exists "archivos_seguros_actualizar" on storage.objects;
create policy "archivos_seguros_actualizar" on storage.objects
  as restrictive for update to public
  using (true)
  with check (public.archivo_nombre_seguro(bucket_id, name));

-- ── 3) Vista pública: solo documentos públicos ──────────────────────────
-- Se toma la definición VIGENTE de la vista (no una copia vieja del repo) y
-- se envuelve: mismas columnas, mismo orden y tipo; solo la columna
-- documentos pasa por el filtro.
do $$
declare
  v_def  text := rtrim(btrim(pg_get_viewdef('public.propiedades_publicas_extra'::regclass, false)), ';');
  v_ops  text[] := (select opciones from respaldo_archivos_20261106.vista where nombre = 'propiedades_publicas_extra');
  v_cols text;
begin
  if not exists (select 1 from pg_attribute
                  where attrelid = 'public.propiedades_publicas_extra'::regclass
                    and attname = 'documentos' and not attisdropped
                    and atttypid = 'jsonb'::regtype) then
    raise exception 'La vista propiedades_publicas_extra no tiene la columna documentos (jsonb); no se toca.';
  end if;
  select string_agg(
           case when attname = 'documentos' then
             $q$COALESCE(( SELECT jsonb_agg(d.value) FROM jsonb_array_elements(v.documentos) d(value)
                          WHERE COALESCE(d.value ->> 'publico', 'true') <> 'false'), '[]'::jsonb) AS documentos$q$
           else 'v.' || quote_ident(attname) end, ', ' order by attnum)
    into v_cols
    from pg_attribute
   where attrelid = 'public.propiedades_publicas_extra'::regclass and attnum > 0 and not attisdropped;
  execute 'create or replace view public.propiedades_publicas_extra as select ' || v_cols
       || ' from (' || v_def || ') v';
  if v_ops is not null then
    execute format('alter view public.propiedades_publicas_extra set (%s)', array_to_string(v_ops, ', '));
  end if;
end $$;

grant select on public.propiedades_publicas_extra to anon, authenticated;

commit;
