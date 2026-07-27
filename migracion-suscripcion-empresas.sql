-- ════════════════════════════════════════════════════════════════
-- Broquer · Suscripción para Empresas (Stripe)
-- Correr UNA vez en Supabase → SQL Editor. Es aditiva y reversible.
--
-- Qué agrega:
--   · suscripciones.periodo  → 'mensual' | 'anual' (para prorratear lugares)
--   · suscripciones.asientos → lugares contratados en el momento del pago
--   · índice por org_id para las consultas del plan de empresa
-- ════════════════════════════════════════════════════════════════

ALTER TABLE public.suscripciones
  ADD COLUMN IF NOT EXISTS periodo  text,
  ADD COLUMN IF NOT EXISTS asientos integer;

COMMENT ON COLUMN public.suscripciones.periodo  IS 'mensual | anual — ciclo de cobro del plan de empresas';
COMMENT ON COLUMN public.suscripciones.asientos IS 'Lugares contratados en el plan de empresas';

CREATE INDEX IF NOT EXISTS idx_suscripciones_org_plan
  ON public.suscripciones (org_id, plan_id);

CREATE INDEX IF NOT EXISTS idx_suscripciones_stripe_sub
  ON public.suscripciones (stripe_subscription_id);

-- Las organizaciones ya tienen tipo/plan/asientos_max/activo/vence_el desde
-- migracion-empresas.sql. Esto solo asegura el default de lugares.
ALTER TABLE public.organizaciones
  ALTER COLUMN asientos_max SET DEFAULT 5;
