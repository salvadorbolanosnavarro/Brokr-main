-- ══════════════════════════════════════════════════════════════════════════
-- REVERSA de borrar-respaldo-wa2-numeros.sql
-- ══════════════════════════════════════════════════════════════════════════
-- 1. Vuelve a crear la tabla vacía, con la misma estructura, y sin acceso
--    para anon ni authenticated (igual que quedó tras la migración de
--    seguridad del 9 de octubre).
-- 2. Después cargas los datos desde el CSV que exportaste:
--    Supabase → Table Editor → wa2_numeros_backup_20260720 → "Insert"
--    → "Import data from CSV" → eliges el archivo → "Import data".
-- ══════════════════════════════════════════════════════════════════════════

begin;

do $$
declare ddl text;
begin
  if to_regclass('public.wa2_numeros_backup_20260720') is not null then
    raise exception 'La tabla wa2_numeros_backup_20260720 ya existe; no hay nada que revertir.';
  end if;
  select crear_sql into ddl
    from respaldo_ddl_20261009.tablas
   where tabla = 'public.wa2_numeros_backup_20260720';
  if ddl is null then
    raise exception 'No encontré la estructura guardada en respaldo_ddl_20261009.tablas.';
  end if;
  execute ddl;
  execute 'revoke all on public.wa2_numeros_backup_20260720 from public, anon, authenticated';
end $$;

commit;

-- Comprobación: debe decir "wa2_numeros_backup_20260720".
select to_regclass('public.wa2_numeros_backup_20260720') as tabla_respaldo;
