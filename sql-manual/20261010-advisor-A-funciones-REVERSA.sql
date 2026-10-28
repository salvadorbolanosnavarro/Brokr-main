-- REVERSA de 20261010-advisor-A-funciones.sql
-- Deja los permisos de ejecución de las 13 funciones exactamente como estaban,
-- usando la foto guardada en respaldo_advisor_20261010.funciones_permisos.
begin;

do $$
declare
  f   record;
  a   record;
  rol text;
begin
  if to_regclass('respaldo_advisor_20261010.funciones_permisos') is null then
    raise exception 'No existe la foto de permisos de funciones: la parte A no se aplicó o ya se revirtió.';
  end if;
  for f in select * from respaldo_advisor_20261010.funciones_permisos loop
    continue when to_regprocedure(f.firma) is null;
    -- Quitar los permisos actuales que no son del dueño…
    for a in
      select distinct x.grantee
        from pg_proc p, aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) x
       where p.oid = f.firma::regprocedure and x.grantee <> p.proowner
    loop
      rol := case when a.grantee = 0 then 'public' else quote_ident(a.grantee::regrole::text) end;
      execute format('revoke all on function %s from %s', f.firma, rol);
    end loop;
    -- …y volver a dar exactamente los que había.
    for a in
      select x.grantee, x.privilege_type, x.is_grantable
        from pg_proc p, aclexplode(coalesce(f.proacl, acldefault('f', p.proowner))) x
       where p.oid = f.firma::regprocedure and x.grantee <> p.proowner
    loop
      rol := case when a.grantee = 0 then 'public' else quote_ident(a.grantee::regrole::text) end;
      execute format('grant %s on function %s to %s%s', a.privilege_type, f.firma, rol,
                     case when a.is_grantable then ' with grant option' else '' end);
    end loop;
  end loop;
  drop table respaldo_advisor_20261010.funciones_permisos;
end $$;

commit;
