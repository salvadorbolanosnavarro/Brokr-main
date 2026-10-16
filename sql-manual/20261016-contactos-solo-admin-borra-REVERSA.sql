-- REVERSA de 20261016-contactos-solo-admin-borra.sql
-- Vuelve a poner las dos reglas de borrado de contactos exactamente como
-- estaban (desde la foto en respaldo_contactos_borrar_20261016) y quita la
-- función nueva.
begin;

do $$
declare p record;
begin
  if to_regclass('respaldo_contactos_borrar_20261016.politicas') is null then
    raise exception 'No existe la foto de reglas de borrado: el script no se aplicó o ya se revirtió.';
  end if;
  for p in select * from respaldo_contactos_borrar_20261016.politicas loop
    execute format('drop policy if exists %I on public.contactos', p.nombre);
    execute format('create policy %I on public.contactos as %s for %s to %s%s%s',
      p.nombre, p.permissive, p.cmd,
      (select string_agg(case when x = 'public' then 'public' else quote_ident(x) end, ', ') from unnest(p.roles) x),
      case when p.qual       is not null then ' using (' || p.qual || ')' else '' end,
      case when p.with_check is not null then ' with check (' || p.with_check || ')' else '' end);
  end loop;
end $$;

drop function if exists public.soy_agente_de_empresa();
drop schema respaldo_contactos_borrar_20261016 cascade;

commit;
