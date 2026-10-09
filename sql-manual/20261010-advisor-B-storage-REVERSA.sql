-- REVERSA de 20261010-advisor-B-storage.sql
-- Quita las 4 reglas nuevas y vuelve a crear las 4 reglas de "ver" originales
-- exactamente como estaban (desde la foto en respaldo_advisor_20261010).
begin;

do $$
declare p record;
begin
  if to_regclass('respaldo_advisor_20261010.storage_politicas') is null then
    raise exception 'No existe la foto de reglas de storage: la parte B no se aplicó o ya se revirtió.';
  end if;

  drop policy if exists "fotos_propiedades_ve_sus_archivos"   on storage.objects;
  drop policy if exists "documentos_publicos_ve_sus_archivos" on storage.objects;
  drop policy if exists "adjuntos_historial_ve_sus_archivos"  on storage.objects;
  drop policy if exists "avatares_ve_sus_archivos"            on storage.objects;

  for p in select * from respaldo_advisor_20261010.storage_politicas loop
    if not exists (select 1 from pg_policies
                    where schemaname = 'storage' and tablename = 'objects' and policyname = p.nombre) then
      execute format('create policy %I on storage.objects as %s for %s to %s%s%s',
        p.nombre, p.permissive, p.cmd,
        (select string_agg(case when x = 'public' then 'public' else quote_ident(x) end, ', ')
           from unnest(p.roles) x),
        case when p.qual       is not null then ' using (' || p.qual || ')' else '' end,
        case when p.with_check is not null then ' with check (' || p.with_check || ')' else '' end);
    end if;
  end loop;
  drop table respaldo_advisor_20261010.storage_politicas;
end $$;

commit;
