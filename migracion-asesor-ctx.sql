-- Migración: memoria corta del modo asesor de Broq por WhatsApp.
-- Guarda en la conversación el id/nombre de lo último creado o tocado, para
-- que "esa misma tarea" o "ese contacto" resuelvan bien en el siguiente
-- mensaje. Correr una vez en el SQL Editor de Supabase. 100% aditiva.
ALTER TABLE wa2_conversaciones ADD COLUMN IF NOT EXISTS asesor_ctx jsonb;
