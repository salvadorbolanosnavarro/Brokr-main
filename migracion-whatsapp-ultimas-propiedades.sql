-- Guarda qué propiedades le mandó la IA al prospecto en cada conversación
-- (id + título). Sirve para, cuando después agenda una visita, saber a cuál
-- de esas propiedades se refiere y adjuntarla sola a la tarea de la cita
-- (además del contacto, que ya se adjuntaba).
-- Cambio aditivo y seguro: no rompe filas existentes.

alter table wa2_conversaciones
  add column if not exists ultimas_propiedades jsonb not null default '[]'::jsonb;
