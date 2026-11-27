-- Migración: Seguimiento automático (piloto privado).
-- Correr manualmente en el SQL Editor de Supabase. Es 100% aditiva e
-- idempotente: no borra ni modifica datos existentes y se puede correr dos veces.
--
-- Qué guarda:
--   seg_secuencias      Secuencias de toques (plantillas aprobadas + días de espera).
--   seg_inscripciones   Qué contacto de WhatsApp va en qué secuencia y en qué toque.
--   seg_envios          Bitácora de cada mensaje automático (enviado o fallido).
--   seg_eventos         Avisos por evento: bajada de precio y coincidencias nuevas.
--   seg_precios         Último precio visto de cada inmueble (para detectar bajadas).
--   seg_ajustes         Ajustes por cuenta: horario, tope diario y avisos.
-- El backend escribe con la llave de servicio; RLS deja a cada quien ver lo suyo.

CREATE TABLE IF NOT EXISTS seg_secuencias (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  numero_id uuid NOT NULL,
  nombre text NOT NULL,
  activa boolean NOT NULL DEFAULT true,
  auto_leads_nuevos boolean NOT NULL DEFAULT false,
  pasos jsonb NOT NULL DEFAULT '[]'::jsonb,
  hora_envio integer NOT NULL DEFAULT 10,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS seg_secuencias_user ON seg_secuencias (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS seg_inscripciones (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  secuencia_id uuid NOT NULL REFERENCES seg_secuencias(id) ON DELETE CASCADE,
  numero_id uuid NOT NULL,
  contacto_id uuid NOT NULL,
  conversacion_id uuid,
  estado text NOT NULL DEFAULT 'activa',
  paso integer NOT NULL DEFAULT 0,
  intentos integer NOT NULL DEFAULT 0,
  origen text NOT NULL DEFAULT 'manual',
  motivo text,
  proximo_en timestamptz,
  ultimo_envio_en timestamptz,
  respondio_en timestamptz,
  inscrito_en timestamptz NOT NULL DEFAULT now(),
  UNIQUE (secuencia_id, contacto_id)
);
CREATE INDEX IF NOT EXISTS seg_inscripciones_cola ON seg_inscripciones (user_id, estado, proximo_en);
CREATE INDEX IF NOT EXISTS seg_inscripciones_contacto ON seg_inscripciones (contacto_id);

CREATE TABLE IF NOT EXISTS seg_envios (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  contacto_id uuid NOT NULL,
  inscripcion_id uuid,
  evento_id uuid,
  tipo text NOT NULL DEFAULT 'toque',
  paso integer,
  plantilla text,
  estado text NOT NULL DEFAULT 'enviado',
  error text,
  wamid text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS seg_envios_user ON seg_envios (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS seg_envios_contacto ON seg_envios (contacto_id, created_at DESC);

CREATE TABLE IF NOT EXISTS seg_eventos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  contacto_id uuid NOT NULL,
  numero_id uuid NOT NULL,
  tipo text NOT NULL,
  propiedad_id uuid NOT NULL,
  clave text NOT NULL,
  detalle jsonb NOT NULL DEFAULT '{}'::jsonb,
  estado text NOT NULL DEFAULT 'pendiente',
  motivo text,
  created_at timestamptz NOT NULL DEFAULT now(),
  enviado_en timestamptz,
  UNIQUE (contacto_id, tipo, propiedad_id, clave)
);
CREATE INDEX IF NOT EXISTS seg_eventos_user ON seg_eventos (user_id, estado, created_at DESC);

CREATE TABLE IF NOT EXISTS seg_precios (
  propiedad_id uuid PRIMARY KEY,
  user_id uuid NOT NULL,
  precio numeric NOT NULL,
  moneda text,
  visto_en timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS seg_ajustes (
  user_id uuid PRIMARY KEY,
  numero_id uuid,
  eventos_activos boolean NOT NULL DEFAULT false,
  plantilla_precio text,
  plantilla_coincidencia text,
  idioma text NOT NULL DEFAULT 'es_MX',
  tope_diario integer NOT NULL DEFAULT 60,
  hora_inicio integer NOT NULL DEFAULT 9,
  hora_fin integer NOT NULL DEFAULT 20,
  resumen_diario boolean NOT NULL DEFAULT true,
  ultimo_resumen date,
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE seg_secuencias ENABLE ROW LEVEL SECURITY;
ALTER TABLE seg_inscripciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE seg_envios ENABLE ROW LEVEL SECURITY;
ALTER TABLE seg_eventos ENABLE ROW LEVEL SECURITY;
ALTER TABLE seg_precios ENABLE ROW LEVEL SECURITY;
ALTER TABLE seg_ajustes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS seg_secuencias_owner ON seg_secuencias;
CREATE POLICY seg_secuencias_owner ON seg_secuencias
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
DROP POLICY IF EXISTS seg_inscripciones_owner ON seg_inscripciones;
CREATE POLICY seg_inscripciones_owner ON seg_inscripciones
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
DROP POLICY IF EXISTS seg_envios_owner ON seg_envios;
CREATE POLICY seg_envios_owner ON seg_envios
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
DROP POLICY IF EXISTS seg_eventos_owner ON seg_eventos;
CREATE POLICY seg_eventos_owner ON seg_eventos
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
DROP POLICY IF EXISTS seg_precios_owner ON seg_precios;
CREATE POLICY seg_precios_owner ON seg_precios
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
DROP POLICY IF EXISTS seg_ajustes_owner ON seg_ajustes;
CREATE POLICY seg_ajustes_owner ON seg_ajustes
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
