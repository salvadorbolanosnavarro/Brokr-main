-- ══════════════════════════════════════════════════════════════════════════
-- Borrar la tabla de respaldo wa2_numeros_backup_20260720
-- ══════════════════════════════════════════════════════════════════════════
-- Tiene tokens de WhatsApp en texto plano y nadie la usa (revisado en el repo).
--
-- ANTES de correr esto, exporta la tabla a CSV por si acaso:
--   Supabase → Table Editor → esquema "public" → wa2_numeros_backup_20260720
--   → botón "Export" (arriba a la derecha) → "Export as CSV".
--   OJO: ese CSV tiene tokens en texto plano. Guárdalo en un lugar seguro
--   (no por correo ni WhatsApp) y bórralo cuando ya no lo necesites.
--
-- Qué hace:
--   1. Guarda SOLO la estructura de la tabla (nombres y tipos de columnas,
--      sin datos y sin tokens) en respaldo_ddl_20261009, para que la reversa
--      pueda volver a crearla.
--   2. Borra la tabla. Si algo dependiera de ella, se detiene y no borra nada.
-- Todo en una sola transacción.
-- ══════════════════════════════════════════════════════════════════════════

begin;

create schema if not exists respaldo_ddl_20261009;
revoke all on schema respaldo_ddl_20261009 from public, anon, authenticated;

create table if not exists respaldo_ddl_20261009.tablas (
  tabla      text primary key,
  crear_sql  text not null,
  guardado   timestamptz not null default now()
);
revoke all on respaldo_ddl_20261009.tablas from public, anon, authenticated;

do $$
begin
  if to_regclass('public.wa2_numeros_backup_20260720') is null then
    raise notice 'La tabla wa2_numeros_backup_20260720 ya no existe; no hay nada que borrar.';
    return;
  end if;

  insert into respaldo_ddl_20261009.tablas (tabla, crear_sql)
  select 'public.wa2_numeros_backup_20260720',
         'create table public.wa2_numeros_backup_20260720 (' ||
         string_agg(format('%I %s%s%s', a.attname, format_type(a.atttypid, a.atttypmod),
                           case when d.adbin is not null then ' default ' || pg_get_expr(d.adbin, d.adrelid) else '' end,
                           case when a.attnotnull then ' not null' else '' end),
                    ', ' order by a.attnum) || ')'
    from pg_attribute a
    left join pg_attrdef d on d.adrelid = a.attrelid and d.adnum = a.attnum
   where a.attrelid = 'public.wa2_numeros_backup_20260720'::regclass
     and a.attnum > 0 and not a.attisdropped
  on conflict (tabla) do nothing;

  drop table public.wa2_numeros_backup_20260720;
end $$;

commit;

-- Comprobación: debe decir "null" (la tabla ya no existe).
select to_regclass('public.wa2_numeros_backup_20260720') as tabla_respaldo;
