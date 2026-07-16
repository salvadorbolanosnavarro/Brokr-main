-- =============================================================================
-- Broquer · Migración para CRM + Chats + Notificaciones en móvil / iOS
-- Pégalo completo en Supabase > SQL Editor y dale Run. Es seguro correrlo
-- varias veces: todo va con "if not exists".
-- =============================================================================

-- 1) Contador de mensajes sin leer por conversación.
--    Lo sube el webhook cuando escribe el prospecto; lo baja a 0 la bandeja
--    cuando abres el chat. Es el número del globito rojo.
alter table wa_conversations
  add column if not exists unread_count int not null default 0;

-- Los chats que ya existían arrancan en 0 (no en null).
update wa_conversations set unread_count = 0 where unread_count is null;

-- 2) Token del iPhone para las notificaciones (APNs).
--    Lo escribe la app de iOS sola, al abrirla, cuando aceptas el permiso.
alter table usuarios
  add column if not exists apns_token text;

-- Búsqueda rápida del token cuando Apple avisa que ya no sirve.
create index if not exists idx_usuarios_apns on usuarios (apns_token)
  where apns_token is not null;

-- 3) Índice para que el globito se calcule rápido.
create index if not exists idx_wa_conv_unread
  on wa_conversations (user_id) where unread_count > 0;
