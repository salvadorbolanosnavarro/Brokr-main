-- REVERSA de 20261010-contactos-reglas-rapidas.sql
-- Vuelve a poner las reglas de contactos exactamente como estaban (desde la
-- foto en respaldo_contactos_20261010) y quita las dos funciones nuevas.
begin;

do $$
declare p record;
begin
  if to_regclass('respaldo_contactos_20261010.politicas') is null then
    raise exception 'No existe la foto de reglas de contactos: el script no se aplicó o ya se revirtió.';
  end if;
  for p in select policyname from pg_policies where schemaname = 'public' and tablename = 'contactos' loop
    execute format('drop policy %I on public.contactos', p.policyname);
  end loop;
  for p in select * from respaldo_contactos_20261010.politicas loop
    execute format('create policy %I on public.contactos as %s for %s to %s%s%s',
      p.nombre, p.permissive, p.cmd,
      (select string_agg(case when x = 'public' then 'public' else quote_ident(x) end, ', ') from unnest(p.roles) x),
      case when p.qual       is not null then ' using (' || p.qual || ')' else '' end,
      case when p.with_check is not null then ' with check (' || p.with_check || ')' else '' end);
  end loop;
end $$;

drop function if exists public.contactos_de_mis_tareas();
drop function if exists public.companeros_activos_de_mi_org();
drop schema respaldo_contactos_20261010 cascade;

commit;
