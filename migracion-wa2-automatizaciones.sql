-- Migración: WhatsApp 2.0 — Automatizaciones tipo receta (fase 2 del plan
-- de campañas y automatización). Correr manualmente en el SQL Editor de
-- Supabase. Es 100% aditiva: no borra ni modifica datos existentes.

-- Una automatización = un disparador + una lista ordenada de pasos.
--   disparador: 'palabra' (el mensaje contiene alguna de las palabras)
--               o 'nuevo' (primer mensaje de un contacto nuevo)
--   acciones:   lista de pasos {tipo, valor} donde tipo es
--               'mensaje' (responder con un texto),
--               'etiqueta' (ponerle una etiqueta al contacto) o
--               'humano' (apagar la IA y avisarle al agente).
CREATE TABLE IF NOT EXISTS wa2_automatizaciones (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  numero_id uuid,
  nombre text NOT NULL,
  activa boolean DEFAULT true,
  disparador text DEFAULT 'palabra',
  palabras jsonb DEFAULT '[]'::jsonb,
  acciones jsonb DEFAULT '[]'::jsonb,
  veces_usada integer DEFAULT 0,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS wa2_automatizaciones_user
  ON wa2_automatizaciones (user_id, created_at DESC);

ALTER TABLE wa2_automatizaciones ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS wa2_automatizaciones_owner ON wa2_automatizaciones;
CREATE POLICY wa2_automatizaciones_owner ON wa2_automatizaciones
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
