-- Migración: WhatsApp 2.0 — Campañas (broadcasts), etiquetas de contactos y
-- bajas (opt-out). Correr manualmente en el SQL Editor de Supabase.
-- Es 100% aditiva: no borra ni modifica datos existentes.

-- Etiquetas del contacto de WhatsApp (segmentación para campañas) y marca de
-- baja: si el prospecto escribe "baja" / "stop", jamás vuelve a recibir una
-- campaña, aunque siga pudiendo chatear normal.
ALTER TABLE wa2_contactos ADD COLUMN IF NOT EXISTS etiquetas jsonb DEFAULT '[]'::jsonb;
ALTER TABLE wa2_contactos ADD COLUMN IF NOT EXISTS opt_out boolean DEFAULT false;

-- Una campaña = una plantilla aprobada enviada a una audiencia (todos los
-- contactos de un número, o solo los que tengan cierta etiqueta).
CREATE TABLE IF NOT EXISTS wa2_campanas (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  numero_id uuid NOT NULL,
  nombre text NOT NULL,
  plantilla text NOT NULL,
  idioma text DEFAULT 'es_MX',
  variables jsonb DEFAULT '[]'::jsonb,
  etiqueta text,
  estado text DEFAULT 'enviando',
  total integer DEFAULT 0,
  enviados integer DEFAULT 0,
  fallidos integer DEFAULT 0,
  created_at timestamptz DEFAULT now(),
  terminado_at timestamptz
);

CREATE INDEX IF NOT EXISTS wa2_campanas_user
  ON wa2_campanas (user_id, created_at DESC);

ALTER TABLE wa2_campanas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS wa2_campanas_owner ON wa2_campanas;
CREATE POLICY wa2_campanas_owner ON wa2_campanas
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Registro individual de cada envío de la campaña (para saber exactamente a
-- quién sí le llegó y a quién no, y por qué falló).
CREATE TABLE IF NOT EXISTS wa2_campana_envios (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campana_id uuid NOT NULL,
  user_id uuid NOT NULL,
  contacto_id uuid,
  wa_id text,
  nombre text,
  estado text DEFAULT 'pendiente',
  error text,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS wa2_campana_envios_campana
  ON wa2_campana_envios (campana_id);

ALTER TABLE wa2_campana_envios ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS wa2_campana_envios_owner ON wa2_campana_envios;
CREATE POLICY wa2_campana_envios_owner ON wa2_campana_envios
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
