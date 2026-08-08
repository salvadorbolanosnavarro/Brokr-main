-- Migración: WhatsApp 2.0 — borrar un número borra TODO lo suyo.
-- Correr manualmente en el SQL Editor de Supabase.
--
-- Problema que arregla: al eliminar un número de WhatsApp solo se borraba la
-- fila de wa2_numeros. Sus conversaciones, mensajes, contactos, agenda,
-- entrenamiento, campañas y automatizaciones quedaban huérfanos — por eso los
-- chats seguían apareciendo en la bandeja aunque el número ya no existiera.
--
-- Este archivo hace dos cosas:
--   1) Borra los huérfanos que ya existen hoy.
--   2) Agrega llaves foráneas con ON DELETE CASCADE para que la base misma
--      garantice que esto no vuelva a pasar, aunque el backend falle a medias.

-- ── 1) Limpieza de huérfanos existentes ─────────────────────────────────────

-- Mensajes de conversaciones cuyo número ya no existe
DELETE FROM wa2_mensajes m
 USING wa2_conversaciones c
 WHERE m.conversacion_id = c.id
   AND c.numero_id NOT IN (SELECT id FROM wa2_numeros);

-- Mensajes cuya conversación ya no existe (huérfanos de segundo grado)
DELETE FROM wa2_mensajes
 WHERE conversacion_id NOT IN (SELECT id FROM wa2_conversaciones);

DELETE FROM wa2_conversaciones
 WHERE numero_id NOT IN (SELECT id FROM wa2_numeros);

DELETE FROM wa2_contactos
 WHERE numero_id NOT IN (SELECT id FROM wa2_numeros);

DELETE FROM wa2_agenda
 WHERE numero_id NOT IN (SELECT id FROM wa2_numeros);

DELETE FROM wa2_entrenamiento
 WHERE numero_id IS NOT NULL
   AND numero_id NOT IN (SELECT id FROM wa2_numeros);

DELETE FROM wa2_campanas
 WHERE numero_id NOT IN (SELECT id FROM wa2_numeros);

DELETE FROM wa2_automatizaciones
 WHERE numero_id IS NOT NULL
   AND numero_id NOT IN (SELECT id FROM wa2_numeros);

-- ── 2) Llaves foráneas con cascada ──────────────────────────────────────────
-- numero_id NULL (entrenamiento default, automatización para todos los
-- números) es válido: una FK ignora los NULL, así que esas filas no se tocan.

ALTER TABLE wa2_conversaciones
  DROP CONSTRAINT IF EXISTS wa2_conversaciones_numero_fk;
ALTER TABLE wa2_conversaciones
  ADD CONSTRAINT wa2_conversaciones_numero_fk
  FOREIGN KEY (numero_id) REFERENCES wa2_numeros(id) ON DELETE CASCADE;

ALTER TABLE wa2_mensajes
  DROP CONSTRAINT IF EXISTS wa2_mensajes_conversacion_fk;
ALTER TABLE wa2_mensajes
  ADD CONSTRAINT wa2_mensajes_conversacion_fk
  FOREIGN KEY (conversacion_id) REFERENCES wa2_conversaciones(id) ON DELETE CASCADE;

ALTER TABLE wa2_contactos
  DROP CONSTRAINT IF EXISTS wa2_contactos_numero_fk;
ALTER TABLE wa2_contactos
  ADD CONSTRAINT wa2_contactos_numero_fk
  FOREIGN KEY (numero_id) REFERENCES wa2_numeros(id) ON DELETE CASCADE;

ALTER TABLE wa2_agenda
  DROP CONSTRAINT IF EXISTS wa2_agenda_numero_fk;
ALTER TABLE wa2_agenda
  ADD CONSTRAINT wa2_agenda_numero_fk
  FOREIGN KEY (numero_id) REFERENCES wa2_numeros(id) ON DELETE CASCADE;

ALTER TABLE wa2_entrenamiento
  DROP CONSTRAINT IF EXISTS wa2_entrenamiento_numero_fk;
ALTER TABLE wa2_entrenamiento
  ADD CONSTRAINT wa2_entrenamiento_numero_fk
  FOREIGN KEY (numero_id) REFERENCES wa2_numeros(id) ON DELETE CASCADE;

ALTER TABLE wa2_campanas
  DROP CONSTRAINT IF EXISTS wa2_campanas_numero_fk;
ALTER TABLE wa2_campanas
  ADD CONSTRAINT wa2_campanas_numero_fk
  FOREIGN KEY (numero_id) REFERENCES wa2_numeros(id) ON DELETE CASCADE;

ALTER TABLE wa2_automatizaciones
  DROP CONSTRAINT IF EXISTS wa2_automatizaciones_numero_fk;
ALTER TABLE wa2_automatizaciones
  ADD CONSTRAINT wa2_automatizaciones_numero_fk
  FOREIGN KEY (numero_id) REFERENCES wa2_numeros(id) ON DELETE CASCADE;
