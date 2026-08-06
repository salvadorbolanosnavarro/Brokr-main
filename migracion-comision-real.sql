-- Migración: comisión real cobrada al cerrar una operación
-- Ejecutar manualmente en Supabase SQL Editor ANTES de subir los HTML.

ALTER TABLE propiedades ADD COLUMN IF NOT EXISTS comision_real numeric;
