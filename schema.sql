-- =============================================================================
-- Broquer · WhatsApp — Esquema de base de datos (Supabase / Postgres)
-- Pégalo en Supabase > SQL Editor y dale Run.
-- =============================================================================

-- Mapea cada número de WhatsApp (phone_number_id de Meta) a su agente dueño.
-- En multiagente, aquí vive quién es dueño de cada número.
create table if not exists wa_numbers (
  id               uuid primary key default gen_random_uuid(),
  user_id         uuid not null,                 -- agente dueño (auth.users.id)
  phone_number_id  text not null unique,          -- el Phone Number ID de Meta
  display_number   text,                          -- el número bonito, ej +52 443...
  created_at       timestamptz default now()
);

-- Contactos (prospectos que escriben por WhatsApp). Uno por número de cliente.
create table if not exists wa_contacts (
  id           uuid primary key default gen_random_uuid(),
  user_id     uuid not null,
  wa_id        text not null,                     -- número del cliente (lo manda Meta)
  nombre       text,
  presupuesto  text,
  forma_pago   text,
  busca        text,
  temperatura  text default 'Nuevo',              -- Caliente | Tibio | Frío | Nuevo
  score        int  default 0,                    -- 0-100
  etapa        text default 'Nuevo',              -- Nuevo | Contactado | Cita | Negociación | Cierre
  resumen      text,
  created_at   timestamptz default now(),
  updated_at   timestamptz default now(),
  unique (user_id, wa_id)
);

-- Una conversación por contacto. Aquí está el switch ai_enabled (apagar la IA
-- = el agente toma el control) y el contexto de la propiedad del anuncio.
create table if not exists wa_conversations (
  id               uuid primary key default gen_random_uuid(),
  user_id         uuid not null,
  contact_id       uuid not null references wa_contacts(id) on delete cascade,
  phone_number_id  text,
  ai_enabled       boolean default true,          -- false = contesta el humano
  property_ctx     text,                          -- de qué propiedad/anuncio venía
  last_message_at  timestamptz default now(),
  created_at       timestamptz default now(),
  unique (contact_id)
);

-- Todos los mensajes (entrantes y salientes). wa_message_id es único para evitar
-- duplicados cuando Meta reintenta el webhook.
create table if not exists wa_messages (
  id               uuid primary key default gen_random_uuid(),
  user_id         uuid not null,
  contact_id       uuid not null references wa_contacts(id) on delete cascade,
  conversation_id  uuid not null references wa_conversations(id) on delete cascade,
  wa_message_id    text unique,                   -- id de Meta (dedupe)
  direction        text not null,                 -- 'in' | 'out'
  sender           text not null,                 -- 'lead' | 'ai' | 'agent'
  body             text,
  status           text,                          -- sent | delivered | read (opcional)
  created_at       timestamptz default now()
);

-- Índices para que la bandeja cargue rápido
create index if not exists idx_wa_contacts_owner   on wa_contacts (user_id, updated_at desc);
create index if not exists idx_wa_conv_owner        on wa_conversations (user_id, last_message_at desc);
create index if not exists idx_wa_msg_conv          on wa_messages (conversation_id, created_at);

-- =============================================================================
-- SEGURIDAD (RLS)
-- El backend usa la service_role key y se BRINCA estas reglas (así debe ser).
-- Estas políticas protegen el acceso desde el frontend (la bandeja), para que
-- cada agente solo vea SUS propios datos.
-- =============================================================================
alter table wa_numbers       enable row level security;
alter table wa_contacts      enable row level security;
alter table wa_conversations enable row level security;
alter table wa_messages      enable row level security;

create policy "dueño ve sus numeros"        on wa_numbers       for all using (user_id = auth.uid());
create policy "dueño ve sus contactos"      on wa_contacts      for all using (user_id = auth.uid());
create policy "dueño ve sus conversaciones" on wa_conversations for all using (user_id = auth.uid());
create policy "dueño ve sus mensajes"       on wa_messages      for all using (user_id = auth.uid());
