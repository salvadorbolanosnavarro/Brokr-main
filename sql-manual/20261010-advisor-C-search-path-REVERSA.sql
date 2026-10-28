-- REVERSA de 20261010-advisor-C-search-path.sql
-- Regresa el search_path de las 8 funciones a como estaba (hoy ninguna lo tenía).
begin;

do $$
declare
  f  record;
  sp text;
begin
  if to_regclass('respaldo_advisor_20261010.funciones_config') is null then
    raise exception 'No existe la foto de search_path: la parte C no se aplicó o ya se revirtió.';
  end if;
  for f in select * from respaldo_advisor_20261010.funciones_config loop
    continue when to_regprocedure(f.firma) is null;
    sp := null;
    select substr(c, length('search_path=') + 1) into sp
      from unnest(f.proconfig) c
     where c like 'search_path=%';
    if sp is null then
      execute format('alter function %s reset search_path', f.firma);
    else
      execute format('alter function %s set search_path to %s', f.firma, sp);
    end if;
  end loop;
  drop table respaldo_advisor_20261010.funciones_config;
end $$;

commit;
