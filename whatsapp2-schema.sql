-- =============================================================================
-- Broquer · WhatsApp 2.0 — Esquema de base de datos (Supabase / Postgres)
-- Módulo nuevo, tablas nuevas (prefijo wa2_). No toca wa_numbers / wa_contacts /
-- wa_conversations / wa_messages / wa_training del módulo WhatsApp original.
-- Pégalo en Supabase > SQL Editor y dale Run. Es seguro correrlo aunque ya
-- exista (todo "if not exists").
-- =============================================================================

-- Cada número de WhatsApp conectado. A diferencia del módulo viejo, un mismo
-- usuario puede tener VARIAS filas aquí (varios números a la vez).
create table if not exists wa2_numeros (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null,
  phone_number_id  text not null unique,       -- Phone Number ID de Meta
  waba_id          text,
  waba_name        text,
  display_number   text,                       -- número bonito, ej 4431234567
  alias            text,                       -- nombre interno, ej "Línea ventas"
  access_token     text,                       -- business system user token
  token_expires_at timestamptz,
  ia_enabled       boolean default true,       -- switch por número
  webhook_verificado boolean default false,    -- true = Meta confirmó que manda los mensajes aquí
  created_at       timestamptz default now(),
  updated_at       timestamptz default now()
);

-- Prospectos. Uno por (número, wa_id) — el mismo prospecto puede escribirle
-- a dos números distintos del mismo agente y son leads independientes.
create table if not exists wa2_contactos (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null,
  numero_id    uuid not null references wa2_numeros(id) on delete cascade,
  wa_id        text not null,
  nombre       text,
  presupuesto  text,
  forma_pago   text,
  busca        text,
  temperatura  text default 'Nuevo',            -- Caliente | Tibio | Frío | Nuevo
  score        int  default 0,                  -- 0-100
  etapa        text default 'Nuevo',            -- Nuevo | Contactado | Cita | Negociación | Cierre | Perdido
  resumen      text,
  notas        jsonb default '[]'::jsonb,        -- [{texto, autor:'ia'|'agente', fecha}]
  created_at   timestamptz default now(),
  updated_at   timestamptz default now(),
  unique (numero_id, wa_id)
);

-- Una conversación por contacto. ai_enabled = false significa que el agente
-- tomó el control ("pasarlo al usuario", como en Manychat).
create table if not exists wa2_conversaciones (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null,
  contacto_id      uuid not null references wa2_contactos(id) on delete cascade,
  numero_id        uuid not null references wa2_numeros(id) on delete cascade,
  ai_enabled       boolean default true,
  property_ctx     text,
  unread_count     int default 0,
  last_message_at  timestamptz default now(),
  created_at       timestamptz default now(),
  unique (contacto_id)
);

-- Todos los mensajes. wa_message_id único evita duplicados si Meta reintenta.
create table if not exists wa2_mensajes (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null,
  contacto_id      uuid not null references wa2_contactos(id) on delete cascade,
  conversacion_id  uuid not null references wa2_conversaciones(id) on delete cascade,
  wa_message_id    text unique,
  direction        text not null,               -- 'in' | 'out'
  sender           text not null,                -- 'lead' | 'ia' | 'agente'
  body             text,
  media_url        text,
  status           text,
  created_at       timestamptz default now()
);

-- Entrenamiento (identidad de la IA). numero_id NULL = plantilla por default
-- que aplica a cualquier número nuevo que el usuario conecte.
create table if not exists wa2_entrenamiento (
  id                 uuid primary key default gen_random_uuid(),
  user_id            uuid not null,
  numero_id          uuid references wa2_numeros(id) on delete cascade,
  nombre_ia          text,                        -- con qué nombre se presenta
  tono               text,
  identidad          text,                        -- "quién eres" en primera persona
  puede              text,
  debe               text,
  no_debe            text,
  especialidad       text,
  objetivo           text,
  datos_calificar    jsonb default '[]'::jsonb,
  preguntas_extra    jsonb default '[]'::jsonb,
  escalar_palabras    jsonb default '[]'::jsonb,   -- palabras que pasan al humano
  horario_activo     boolean default false,
  hora_inicio        text default '08:00',
  hora_fin           text default '21:00',
  fuera_horario_msg  text,
  max_mensajes_ia    int default 0,
  activo             boolean default true,
  created_at         timestamptz default now(),
  updated_at         timestamptz default now(),
  unique (user_id, numero_id)
);

-- Citas agendadas por la IA (o a mano) — la agenda del usuario dentro de Broquer.
create table if not exists wa2_citas (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null,
  contacto_id  uuid references wa2_contactos(id) on delete set null,
  numero_id    uuid references wa2_numeros(id) on delete set null,
  inmueble_id  uuid references propiedades(id) on delete set null,
  titulo       text,
  fecha        date not null,
  hora         text not null,                     -- HH:MM
  notas        text,
  estado       text default 'pendiente',           -- pendiente | confirmada | cancelada
  created_at   timestamptz default now()
);

create index if not exists idx_wa2_contactos_owner  on wa2_contactos (user_id, updated_at desc);
create index if not exists idx_wa2_conv_owner       on wa2_conversaciones (user_id, last_message_at desc);
create index if not exists idx_wa2_conv_numero      on wa2_conversaciones (numero_id, last_message_at desc);
create index if not exists idx_wa2_msg_conv         on wa2_mensajes (conversacion_id, created_at);
create index if not exists idx_wa2_citas_owner      on wa2_citas (user_id, fecha, hora);

-- Si ya habías corrido una versión anterior de este archivo (sin la columna
-- webhook_verificado), esta línea la agrega sin tronar ni duplicar nada.
alter table wa2_numeros add column if not exists webhook_verificado boolean default false;

-- =============================================================================
-- SEGURIDAD (RLS) — el backend usa la service_role key y se brinca esto.
-- Protege el acceso directo desde el frontend con el token del agente.
-- =============================================================================
alter table wa2_numeros        enable row level security;
alter table wa2_contactos      enable row level security;
alter table wa2_conversaciones enable row level security;
alter table wa2_mensajes       enable row level security;
alter table wa2_entrenamiento  enable row level security;
alter table wa2_citas          enable row level security;

drop policy if exists "dueño ve sus numeros 2"        on wa2_numeros;
drop policy if exists "dueño ve sus contactos 2"      on wa2_contactos;
drop policy if exists "dueño ve sus conversaciones 2" on wa2_conversaciones;
drop policy if exists "dueño ve sus mensajes 2"       on wa2_mensajes;
drop policy if exists "dueño ve su entrenamiento 2"   on wa2_entrenamiento;
drop policy if exists "dueño ve sus citas 2"          on wa2_citas;

create policy "dueño ve sus numeros 2"        on wa2_numeros        for all using (user_id = auth.uid());
create policy "dueño ve sus contactos 2"      on wa2_contactos      for all using (user_id = auth.uid());
create policy "dueño ve sus conversaciones 2" on wa2_conversaciones for all using (user_id = auth.uid());
create policy "dueño ve sus mensajes 2"       on wa2_mensajes       for all using (user_id = auth.uid());
create policy "dueño ve su entrenamiento 2"   on wa2_entrenamiento  for all using (user_id = auth.uid());
create policy "dueño ve sus citas 2"          on wa2_citas          for all using (user_id = auth.uid());
