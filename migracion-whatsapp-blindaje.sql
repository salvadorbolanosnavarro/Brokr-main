-- =============================================================================
-- Broquer · WhatsApp — migración de blindaje
-- Segura de correr en producción: solo AGREGA cosas, no borra ni cambia nada
-- de lo que ya existe. Se puede correr aunque el código viejo siga arriba.
-- =============================================================================

-- 1) Base de conocimiento del negocio.
--    Todo lo que la IA no puede sacar del catálogo: comisiones, si aceptan
--    Infonavit o FOVISSSTE, requisitos para rentar, dónde está la oficina,
--    horarios, política de apartado. Sin esto, ante cualquier pregunta que no
--    sea "muéstrame casas" la IA se queda muda o inventa.
alter table wa2_entrenamiento
  add column if not exists conocimiento text;

-- 2) Acuse de entrega fallida.
--    Cuando Meta rechaza un mensaje (número dado de baja, plantilla no
--    aprobada, límite de la cuenta) el agente creía que sí había salido.
--    Aquí queda registrado el motivo real.
alter table wa2_mensajes
  add column if not exists entrega_error text;

-- 3) Un mensaje de WhatsApp NUNCA puede guardarse dos veces.
--    Meta reenvía el mismo webhook cuando no recibe respuesta a tiempo. El
--    código revisa si ya existe, pero entre revisar e insertar caben dos
--    entregas simultáneas: el resultado son mensajes duplicados en la bandeja
--    y respuestas dobles de la IA. Esto lo hace imposible a nivel de base.
--    Primero se limpian los duplicados que ya existan (se conserva el más
--    viejo de cada uno), porque si no el índice único no se puede crear.
delete from wa2_mensajes a
 using wa2_mensajes b
 where a.wa_message_id is not null
   and a.wa_message_id = b.wa_message_id
   and a.created_at > b.created_at;

create unique index if not exists wa2_mensajes_wa_message_id_uniq
  on wa2_mensajes (wa_message_id)
  where wa_message_id is not null;

-- 4) Índices de lectura. La bandeja y las estadísticas leen wa2_mensajes
--    constantemente; sin estos, cada apertura de un chat hace un recorrido
--    completo de la tabla y la instancia Micro de Supabase se satura.
create index if not exists wa2_mensajes_conv_fecha_idx
  on wa2_mensajes (conversacion_id, created_at desc);

create index if not exists wa2_conversaciones_user_fecha_idx
  on wa2_conversaciones (user_id, last_message_at desc);

-- 5) Ruta interna del archivo en el almacenamiento.
--    Sin esto, al borrar un mensaje la foto seguiría viva en una liga
--    pública aunque el mensaje ya no apareciera — lo contrario de una
--    supresión real conforme a la LFPDPPP.
alter table wa2_mensajes
  add column if not exists media_path text;
