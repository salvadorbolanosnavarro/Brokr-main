-- ════════════════════════════════════════════════════════════════
-- Broquer · Consola — módulos por cuenta y acceso completo con vencimiento
-- Correr UNA vez en Supabase → SQL Editor. Es aditiva y reversible.
--
-- Qué agrega a "usuarios":
--   · modulos_desactivados   → módulos que el admin apagó para esa cuenta,
--                              sin tocar su rol ni su suscripción.
--   · acceso_completo_hasta  → fecha de término de un acceso completo dado
--                              a mano por un admin, independiente del rol
--                              "equipo" y de cualquier suscripción de Stripe.
--                              NULL = no tiene un acceso completo así.
-- ════════════════════════════════════════════════════════════════

ALTER TABLE public.usuarios
  ADD COLUMN IF NOT EXISTS modulos_desactivados text[] NOT NULL DEFAULT '{}'::text[];

ALTER TABLE public.usuarios
  ADD COLUMN IF NOT EXISTS acceso_completo_hasta timestamptz;

COMMENT ON COLUMN public.usuarios.modulos_desactivados IS
  'Claves de módulos que un admin desactivó para esta cuenta desde la Consola. Vacío = todos los módulos de su plan disponibles.';

COMMENT ON COLUMN public.usuarios.acceso_completo_hasta IS
  'Vencimiento de un acceso completo otorgado a mano por un admin (independiente del rol "equipo" y de Stripe). NULL = sin ese acceso.';
