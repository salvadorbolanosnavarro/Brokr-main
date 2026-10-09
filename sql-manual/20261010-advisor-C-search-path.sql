-- ══════════════════════════════════════════════════════════════════════════
-- Security Advisor · C) Fijar search_path en 8 funciones
-- ══════════════════════════════════════════════════════════════════════════
-- buscar_cercanos (AVM) usa PostGIS, que vive en el esquema public, y lee
-- public.propiedades_avm: las dos cosas siguen al alcance con este search_path.
-- Las otras 7 son triggers de fechas/estatus y dos funciones de texto.
-- La foto del search_path anterior queda en respaldo_advisor_20261010 para
-- 20261010-advisor-C-search-path-REVERSA.sql.
-- ══════════════════════════════════════════════════════════════════════════

begin;

create schema if not exists respaldo_advisor_20261010;
revoke all on schema respaldo_advisor_20261010 from public, anon, authenticated;

do $$
begin
  if to_regclass('respaldo_advisor_20261010.funciones_config') is not null then
    raise notice 'La foto de search_path ya existe; no se vuelve a tomar.';
    return;
  end if;
  create table respaldo_advisor_20261010.funciones_config (
    firma     text primary key,
    proconfig text[]
  );
  revoke all on respaldo_advisor_20261010.funciones_config from public, anon, authenticated;
  insert into respaldo_advisor_20261010.funciones_config
  select p.oid::regprocedure::text, p.proconfig
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public'
     and p.proname in ('buscar_cercanos', 'bk_set_updated_at', 'tocar_updated_at', 'fb_touch_updated_at',
                       'bk_normaliza', 'bk_contacto_etapa_cambiada', 'bk_filas_de_org', 'bk_propiedad_publicada');
end $$;

do $$
declare f regprocedure;
begin
  for f in
    select p.oid::regprocedure
      from pg_proc p
      join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'public'
       and p.proname in ('buscar_cercanos', 'bk_set_updated_at', 'tocar_updated_at', 'fb_touch_updated_at',
                         'bk_normaliza', 'bk_contacto_etapa_cambiada', 'bk_filas_de_org', 'bk_propiedad_publicada')
  loop
    execute format('alter function %s set search_path = public, extensions, pg_temp', f);
  end loop;
end $$;

commit;
