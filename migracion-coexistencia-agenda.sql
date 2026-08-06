-- Migración: coexistencia WhatsApp 2.0 — agenda del celular, nombres de leads
-- y contactos conocidos. Correr manualmente en el SQL Editor de Supabase.
-- Es 100% aditiva: no borra ni modifica datos existentes.

-- Nombres del lead con su prioridad:
--   nombre_chat   = cómo se presentó él mismo en el chat (lo llena la IA)  [1]
--   nombre_agenda = cómo lo tiene el asesor en la agenda de su celular     [2]
--   nombre_wa     = el nombre que el lead se puso en WhatsApp              [3, último recurso]
--   nombre        = el que se muestra (resuelto con esa prioridad)
ALTER TABLE wa2_contactos ADD COLUMN IF NOT EXISTS nombre_chat text;
ALTER TABLE wa2_contactos ADD COLUMN IF NOT EXISTS nombre_agenda text;
ALTER TABLE wa2_contactos ADD COLUMN IF NOT EXISTS nombre_wa text;
ALTER TABLE wa2_contactos ADD COLUMN IF NOT EXISTS conocido boolean DEFAULT false;

-- Agenda sincronizada del celular del asesor (smb_app_state_sync) + marca de
-- personas con las que ya había chat antes de conectar el número (history).
CREATE TABLE IF NOT EXISTS wa2_agenda (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  numero_id uuid,
  telefono text NOT NULL,
  nombre text,
  conocido boolean DEFAULT false,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS wa2_agenda_numero_tel
  ON wa2_agenda (numero_id, telefono);

ALTER TABLE wa2_agenda ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS wa2_agenda_owner ON wa2_agenda;
CREATE POLICY wa2_agenda_owner ON wa2_agenda
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Número PERSONAL del asesor: desde ahí le escribe a su número de Broquer y
-- lo atiende Broq en modo asesor (en coexistencia no es posible mandarse
-- mensajes a uno mismo, así que este es el disparador real del modo asesor).
ALTER TABLE wa2_numeros ADD COLUMN IF NOT EXISTS numero_personal text;
