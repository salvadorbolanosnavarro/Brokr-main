-- Trial de Broquer Max SIN tarjeta (7 días) + registro de demos agendadas.
-- Correr en el SQL Editor de Supabase. Todo es aditivo.

-- 1) Fecha de vencimiento del trial sin tarjeta. Cuando pasa, el backend
--    reporta la suscripción como inactiva y la marca "expired" — el candado
--    de Broquer Max se cierra solo, sin cron ni intervención.
ALTER TABLE public.suscripciones
  ADD COLUMN IF NOT EXISTS trial_hasta timestamptz;

COMMENT ON COLUMN public.suscripciones.trial_hasta IS
  'Vencimiento del trial sin tarjeta de Broquer Max. NULL en suscripciones de pago.';

-- 2) Solicitudes de demo desde landing e index. Solo el backend (service key)
--    escribe y lee; nadie desde el navegador.
CREATE TABLE IF NOT EXISTS public.demos_agendadas (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre     text NOT NULL,
  contacto   text NOT NULL,           -- teléfono o correo
  fecha      date NOT NULL,
  hora       text NOT NULL,           -- "HH:MM"
  mensaje    text DEFAULT '',
  origen     text DEFAULT '',         -- landing | index
  user_id    uuid,                    -- si venía con sesión
  created_at timestamptz DEFAULT now()
);

ALTER TABLE public.demos_agendadas ENABLE ROW LEVEL SECURITY;
-- Sin políticas: RLS activo y cero policies = solo la service key entra.
