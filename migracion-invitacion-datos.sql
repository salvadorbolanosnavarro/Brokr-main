-- =============================================================================
-- Broquer — Invitaciones con opción de traer datos
-- Copiar TODO, pegar en Supabase > SQL Editor, botón Run.
--
-- QUÉ AGREGA
--   La columna traer_datos en organizacion_invitaciones. Cuando el dueño de
--   una empresa invita a alguien que ya tiene cuenta en Broquer, puede decidir
--   si esa persona entra al equipo CON su inventario y contactos (se mueven a
--   la empresa) o entra limpia (sus datos se quedan guardados en su cuenta
--   individual, en pausa, por si algún día sale del equipo).
--
-- Es seguro correrlo más de una vez.
-- =============================================================================

ALTER TABLE public.organizacion_invitaciones
  ADD COLUMN IF NOT EXISTS traer_datos boolean NOT NULL DEFAULT false;
