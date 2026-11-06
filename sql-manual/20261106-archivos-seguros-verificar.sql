-- Verificación de 20261106-archivos-seguros.sql (A) y 20261106-archivos-privados.sql (B).
-- SOLO LECTURA: no cambia nada. No muestra nombres de archivos ni datos de clientes.
select 'A · bucket ' || id as revision,
       case when allowed_mime_types is not null and not ('text/html' = any(allowed_mime_types))
                 and not ('image/svg+xml' = any(allowed_mime_types)) and file_size_limit is not null
            then 'OK' else 'PENDIENTE' end as estado,
       coalesce(array_length(allowed_mime_types, 1), 0) as tipos_permitidos,
       file_size_limit as tamano_maximo
  from storage.buckets
 where id in ('fotos-propiedades', 'documentos-publicos', 'adjuntos-historial')
union all
select 'A · regla ' || n,
       case when exists (select 1 from pg_policies where schemaname = 'storage' and tablename = 'objects'
                          and policyname = n and permissive = 'RESTRICTIVE') then 'OK' else 'PENDIENTE' end,
       null, null
  from unnest(array['archivos_seguros_subir', 'archivos_seguros_actualizar']) n
union all
select 'A · nombre WhatsApp.html rechazado',
       case when to_regprocedure('public.archivo_nombre_seguro(text,text)') is null then 'PENDIENTE'
            -- La prueba de la función se corre con query_to_xml para que este
            -- script funcione aunque la Parte A no esté aplicada.
            when (xpath('/row/ok/text()', query_to_xml(
                   $q$select not public.archivo_nombre_seguro('adjuntos-historial', 'WhatsApp.html')
                         and not public.archivo_nombre_seguro('fotos-propiedades', 'foto.jpg.html')
                         and public.archivo_nombre_seguro('fotos-propiedades', 'prop_abc.jpg') as ok$q$,
                   false, true, '')))[1]::text = 'true' then 'OK'
            else 'FALLA' end, null, null
union all
select 'A · vista solo documentos públicos',
       case when pg_get_viewdef('public.propiedades_publicas_extra'::regclass, false) like '%publico%'
            then 'OK' else 'PENDIENTE' end, null, null
union all
select 'B · bucket ' || id || ' privado',
       case when public then 'PENDIENTE (sigue público)' else 'OK' end, null, null
  from storage.buckets
 where id in ('adjuntos-historial', 'wa-media');
