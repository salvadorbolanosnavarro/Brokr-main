-- Migración: WhatsApp 2.0 — Modos de encendido de la IA, pausa al responder
-- a mano, sesión de "cliente nuevo" y motor de flujos por pasos.
-- Correr manualmente en el SQL Editor de Supabase ANTES de subir el backend.
-- Es 100% aditiva e idempotente: se puede correr dos veces sin romper nada.

-- ─────────────────────────────────────────────────────────────────────────
-- 1) Conversaciones: estado de IA de tres valores por chat
--    'auto' = obedece el modo global del número (el default)
--    'on'   = la IA contesta SIEMPRE en este chat, aunque el modo global
--             esté apagado (el agente la encendió a propósito en este lead)
--    'off'  = la IA NUNCA contesta en este chat, aunque el global esté
--             encendido
--    ia_pausada_hasta: pausa temporal (el agente respondió a mano y la
--    config dice "pausar 1 hora"); null = sin pausa.
--    ia_sesion_nueva: marca que esta conversación pertenece a un "cliente
--    nuevo" (nunca había escrito, o llevaba más de N meses sin escribir).
--    Es lo que consulta el modo global "solo clientes nuevos".
-- ─────────────────────────────────────────────────────────────────────────
ALTER TABLE wa2_conversaciones ADD COLUMN IF NOT EXISTS ia_modo text;
ALTER TABLE wa2_conversaciones ADD COLUMN IF NOT EXISTS ia_pausada_hasta timestamptz;
ALTER TABLE wa2_conversaciones ADD COLUMN IF NOT EXISTS ia_sesion_nueva boolean DEFAULT false;

-- Backfill una sola vez: lo que estaba apagado a mano queda 'off', el resto
-- queda en 'auto'. Solo toca filas donde ia_modo sigue vacío, así que correr
-- esto de nuevo no pisa decisiones posteriores del usuario.
UPDATE wa2_conversaciones
   SET ia_modo = CASE WHEN ai_enabled = false THEN 'off' ELSE 'auto' END
 WHERE ia_modo IS NULL;

ALTER TABLE wa2_conversaciones ALTER COLUMN ia_modo SET DEFAULT 'auto';

-- ─────────────────────────────────────────────────────────────────────────
-- 2) Entrenamiento: configuración de encendido por número
--    modo_ia:
--      'siempre_encendida' — la IA contesta todos los chats (salvo los que
--                            el agente apague uno por uno)             [B]
--      'siempre_apagada'   — la IA no contesta nada (salvo los chats que
--                            el agente encienda uno por uno)           [A]
--      'solo_nuevos'       — la IA solo contesta a clientes nuevos:
--                            números que nunca han escrito o que llevan
--                            más de `nuevos_meses` sin escribir        [C]
--    pausa_al_responder: si el agente responde a mano (desde Broquer o
--    desde el WhatsApp de su celular), la IA se hace a un lado          [D]
--    pausa_duracion_min: por cuánto tiempo. 0 = para siempre (hasta que
--    el agente la vuelva a encender en ese chat).
-- ─────────────────────────────────────────────────────────────────────────
ALTER TABLE wa2_entrenamiento ADD COLUMN IF NOT EXISTS modo_ia text DEFAULT 'siempre_encendida';
ALTER TABLE wa2_entrenamiento ADD COLUMN IF NOT EXISTS pausa_al_responder boolean DEFAULT true;
ALTER TABLE wa2_entrenamiento ADD COLUMN IF NOT EXISTS pausa_duracion_min integer DEFAULT 0;
ALTER TABLE wa2_entrenamiento ADD COLUMN IF NOT EXISTS nuevos_meses integer DEFAULT 3;

-- ─────────────────────────────────────────────────────────────────────────
-- 3) Motor de flujos: estado por conversación
--    Cuando un flujo hace una pregunta o muestra un menú de opciones, aquí
--    queda anotado en qué paso va y qué respuestas lleva juntadas, para que
--    el siguiente mensaje del prospecto continúe el flujo (y NO lo agarre
--    la IA a medias). Una conversación solo puede tener un flujo activo.
-- ─────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS wa2_flujo_estados (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  conversacion_id uuid NOT NULL UNIQUE,
  automatizacion_id uuid NOT NULL,
  paso integer DEFAULT 0,
  datos jsonb DEFAULT '{}'::jsonb,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS wa2_flujo_estados_conv
  ON wa2_flujo_estados (conversacion_id);

ALTER TABLE wa2_flujo_estados ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS wa2_flujo_estados_owner ON wa2_flujo_estados;
CREATE POLICY wa2_flujo_estados_owner ON wa2_flujo_estados
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
