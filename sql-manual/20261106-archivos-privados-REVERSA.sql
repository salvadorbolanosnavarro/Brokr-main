-- REVERSA de 20261106-archivos-privados.sql (Parte B)
-- Regresa adjuntos-historial y wa-media a como estaban (públicos) y vuelve a
-- crear las reglas de lectura que se hubieran quitado. No toca archivos.
begin;

do $$
declare
  b record;
  p record;
begin
  if to_regclass('respaldo_archivos_20261106.buckets_privados') is null then
    raise exception 'No existe el respaldo de la Parte B: no se aplicó o ya se revirtió.';
  end if;
  for b in select * from respaldo_archivos_20261106.buckets_privados loop
    update storage.buckets set public = b.public where id = b.id;
  end loop;

  if to_regclass('respaldo_archivos_20261106.politicas_lectura') is not null then
    for p in select * from respaldo_archivos_20261106.politicas_lectura loop
      if not exists (select 1 from pg_policies
                      where schemaname = 'storage' and tablename = 'objects' and policyname = p.policyname) then
        execute format('create policy %I on storage.objects as %s for %s to %s%s%s',
          p.policyname, p.permissive, p.cmd,
          (select string_agg(case when x = 'public' then 'public' else quote_ident(x) end, ', ')
             from unnest(p.roles) x),
          case when p.qual       is not null then ' using (' || p.qual || ')' else '' end,
          case when p.with_check is not null then ' with check (' || p.with_check || ')' else '' end);
      end if;
    end loop;
    drop table respaldo_archivos_20261106.politicas_lectura;
  end if;

  drop table respaldo_archivos_20261106.buckets_privados;
end $$;

commit;
