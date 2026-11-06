-- REVERSA de 20261106-archivos-seguros.sql (Parte A)
-- Regresa los tipos/tamaños de los 3 buckets a como estaban, quita las dos
-- reglas restrictivas y la función, y vuelve a crear la vista
-- propiedades_publicas_extra con su definición original (desde el respaldo).
-- No toca archivos.
begin;

do $$
declare
  b record;
  v record;
begin
  if to_regclass('respaldo_archivos_20261106.buckets') is null then
    raise exception 'No existe el respaldo de la Parte A: no se aplicó o ya se revirtió.';
  end if;

  for b in select * from respaldo_archivos_20261106.buckets loop
    update storage.buckets
       set allowed_mime_types = b.allowed_mime_types,
           file_size_limit = b.file_size_limit
     where id = b.id;
  end loop;

  drop policy if exists "archivos_seguros_subir" on storage.objects;
  drop policy if exists "archivos_seguros_actualizar" on storage.objects;
  drop function if exists public.archivo_nombre_seguro(text, text);

  select * into v from respaldo_archivos_20261106.vista where nombre = 'propiedades_publicas_extra';
  if found then
    execute 'create or replace view public.propiedades_publicas_extra as ' || rtrim(v.definicion, ';');
    if v.opciones is not null then
      execute format('alter view public.propiedades_publicas_extra set (%s)', array_to_string(v.opciones, ', '));
    end if;
  end if;

  drop table respaldo_archivos_20261106.buckets;
  drop table respaldo_archivos_20261106.vista;
end $$;

grant select on public.propiedades_publicas_extra to anon, authenticated;

commit;
