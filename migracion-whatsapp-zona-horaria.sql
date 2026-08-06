-- Agrega la zona horaria del agente/número al entrenamiento de WhatsApp.
-- Antes el sistema asumía Ciudad de México (UTC-6) para TODOS los agentes,
-- lo cual está mal para Tijuana, Hermosillo, Cancún, etc. Con este campo,
-- las citas y el horario de atención se calculan en la zona real de cada
-- número. Es un cambio aditivo y seguro: no rompe filas existentes.

alter table wa2_entrenamiento
  add column if not exists zona_horaria text not null default 'America/Mexico_City';
