-- ════════════════════════════════════════════════════════════════
-- Brokr · Migración EasyBroker · 2026-05-12
-- Correr en Supabase Studio → SQL Editor
-- ════════════════════════════════════════════════════════════════

-- Paso 1: columnas nuevas (idempotente: si ya existen, no falla)
ALTER TABLE propiedades
  ADD COLUMN IF NOT EXISTS num_exterior  text,
  ADD COLUMN IF NOT EXISTS num_interior  text,
  ADD COLUMN IF NOT EXISTS estado        text,
  ADD COLUMN IF NOT EXISTS medio_bano    int,
  ADD COLUMN IF NOT EXISTS nivel         text,
  ADD COLUMN IF NOT EXISTS mantenimiento numeric,
  ADD COLUMN IF NOT EXISTS amenidades    text[];

-- Paso 2: índice único para que el UPSERT por eb_public_id funcione
-- (necesario para el on_conflict del nuevo /easybroker/import-all)
CREATE UNIQUE INDEX IF NOT EXISTS propiedades_user_eb_unique
  ON propiedades (user_id, eb_public_id)
  WHERE eb_public_id IS NOT NULL;

-- ════════════════════════════════════════════════════════════════
-- ⚠️  SOLO correr lo siguiente si el paso 2 falla con error de
--     "could not create unique index" por duplicados de la
--     importación previa que jaló las 500 (publicadas + no publicadas).
--     Esto borra duplicados conservando el de menor id.
-- ════════════════════════════════════════════════════════════════
-- DELETE FROM propiedades a USING propiedades b
-- WHERE a.id > b.id
--   AND a.user_id = b.user_id
--   AND a.eb_public_id = b.eb_public_id
--   AND a.eb_public_id IS NOT NULL;
--
-- Después de borrar duplicados, vuelve a correr el CREATE INDEX del Paso 2.
