-- La ventana de 24h de WhatsApp se cuenta desde el ÚLTIMO MENSAJE DEL
-- PROSPECTO, no desde cualquier actividad de la conversación. La columna
-- que ya existía (last_message_at) se actualiza con CUALQUIER mensaje
-- (también los que manda el agente o la IA), así que no sirve para saber
-- si la ventana sigue abierta. Esta columna nueva sí es exclusiva del
-- prospecto.
--
-- Cambio aditivo y seguro: no rompe filas existentes. Se rellena con el
-- mejor dato disponible (last_message_at) para las conversaciones que ya
-- existían, así no se ven todas como "ventana cerrada" desde el día uno.

alter table wa2_conversaciones
  add column if not exists last_inbound_at timestamptz;

update wa2_conversaciones
  set last_inbound_at = last_message_at
  where last_inbound_at is null;
