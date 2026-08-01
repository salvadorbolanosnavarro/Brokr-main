-- ════════════════════════════════════════════════════════════════
-- BROQUER — Migración: Bolsa inmobiliaria
-- Correr manualmente en Supabase SQL Editor. Aditiva y segura:
-- no borra ni modifica nada existente.
--
-- Qué agrega a la tabla propiedades:
--   en_bolsa        → si la propiedad está publicada en la bolsa compartida
--   bolsa_comision  → porcentaje de comisión que el captador comparte (0-100)
--   bolsa_notas     → condiciones o notas del captador para otros agentes
--   bolsa_fecha     → cuándo se publicó en la bolsa (para ordenar por reciente)
--
-- La visibilidad entre cuentas NO se abre por RLS: las propiedades en
-- bolsa se sirven desde el backend con service key (routers/bolsa.py),
-- que expone solo los campos públicos. Las políticas RLS existentes de
-- propiedades quedan intactas.
-- ════════════════════════════════════════════════════════════════

ALTER TABLE propiedades ADD COLUMN IF NOT EXISTS en_bolsa boolean NOT NULL DEFAULT false;
ALTER TABLE propiedades ADD COLUMN IF NOT EXISTS bolsa_comision numeric;
ALTER TABLE propiedades ADD COLUMN IF NOT EXISTS bolsa_notas text;
ALTER TABLE propiedades ADD COLUMN IF NOT EXISTS bolsa_fecha timestamptz;

-- Índice parcial: solo indexa las filas que sí están en bolsa,
-- así el listado nacional es rápido sin engordar la tabla.
CREATE INDEX IF NOT EXISTS idx_propiedades_en_bolsa
  ON propiedades (bolsa_fecha DESC)
  WHERE en_bolsa = true;
