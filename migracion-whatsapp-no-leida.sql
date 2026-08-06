-- =============================================================================
-- WhatsApp 2.0 — control de lectura manual
--
-- Antes la conversación se daba por leída sola: la IA mandaba la palomita azul
-- en cuanto entraba el mensaje y el navegador ponía el contador en cero cada
-- vez que refrescaba el hilo. Resultado: nunca se sabía cuáles chats faltaba
-- atender.
--
-- Ahora leer es un acto explícito del agente:
--   · no_leida            → el agente la marcó como pendiente a mano.
--   · last_inbound_wamid  → id de Meta del último mensaje del prospecto; es lo
--                           que se necesita para mandar la palomita azul hasta
--                           que el agente abre la conversación en Broquer.
--
-- Correr en el SQL Editor de Supabase. Es aditiva y se puede repetir.
-- =============================================================================

ALTER TABLE wa2_conversaciones
  ADD COLUMN IF NOT EXISTS no_leida boolean NOT NULL DEFAULT false;

ALTER TABLE wa2_conversaciones
  ADD COLUMN IF NOT EXISTS last_inbound_wamid text;

CREATE INDEX IF NOT EXISTS idx_wa2_conv_pendientes
  ON wa2_conversaciones (user_id, no_leida);
