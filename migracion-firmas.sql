-- =============================================================================
-- Broquer · Firma electrónica — migración
-- Segura de correr en producción: solo AGREGA cosas. No borra ni cambia nada
-- de lo que ya existe. Se puede correr aunque el código viejo siga arriba.
--
-- CÓMO CORRERLA
--   Supabase > SQL Editor > pega todo > Run. Railway y GitHub NUNCA ejecutan
--   archivos .sql: esto se corre a mano, una sola vez.
--
-- LA IDEA DE FONDO
--   Un documento firmado no vale por la imagen del garabato. Vale por la
--   evidencia que lo rodea: quién abrió la liga, desde qué IP, a qué hora,
--   con qué código de verificación, qué texto aceptó y qué archivo exacto
--   tenía enfrente cuando lo aceptó. Por eso el peso de este esquema no
--   está en el trazo, está en la bitácora y en los hashes.
--
--   El PDF original NUNCA se modifica. Se conserva byte por byte y su
--   SHA-256 queda grabado antes de mandarlo a firmar. El documento final
--   es ese mismo archivo, intacto, con la constancia anexada al final.
--   Así "lo que firmaron" y "lo que se guardó" son demostrablemente iguales.
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 1) DOCUMENTOS
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists firma_documentos (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null,
  propiedad_id        uuid,
  titulo              text not null,

  -- promesa | arrendamiento | exclusiva | carta_intencion | convenio | otro
  tipo                text not null default 'otro',

  -- 'simple'    → trazo + código de verificación + bitácora.
  -- 'reforzado' → lo mismo, más constancia de conservación NOM-151 emitida
  --               por un PSC. Las columnas nom151_* de abajo existen desde
  --               hoy para no tener que migrar cuando se contrate el PSC.
  nivel               text not null default 'simple',

  -- borrador | enviado | parcial | completo | cancelado | vencido
  estado              text not null default 'borrador',

  -- Folio legible, el que se cita por teléfono o en un juicio. Ej: BRQ-7K2M4XQP
  folio               text unique,

  -- El PDF tal como lo subió el agente. Este archivo no se toca jamás.
  archivo_ruta        text,
  archivo_nombre      text,
  archivo_bytes       bigint,
  paginas             integer,
  hash_original       text,          -- SHA-256 hex del PDF original

  -- El entregable: original intacto + constancia anexada.
  firmado_ruta        text,
  hash_firmado        text,

  -- Si está en true, ningún firmante puede firmar sin subir su identificación.
  exige_ine           boolean not null default false,

  mensaje             text,          -- nota del agente para los firmantes
  vence_at            timestamptz,
  completado_at       timestamptz,
  cancelado_at        timestamptz,
  motivo_cancelacion  text,

  -- Reservado para el PSC. Null mientras no se contrate uno.
  nom151_ruta         text,
  nom151_folio        text,
  nom151_at           timestamptz,

  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

alter table firma_documentos add column if not exists propiedad_id       uuid;
alter table firma_documentos add column if not exists exige_ine          boolean not null default false;
alter table firma_documentos add column if not exists nom151_ruta        text;
alter table firma_documentos add column if not exists nom151_folio       text;
alter table firma_documentos add column if not exists nom151_at          timestamptz;

create index if not exists firma_documentos_user_idx
  on firma_documentos (user_id, created_at desc);
create index if not exists firma_documentos_estado_idx
  on firma_documentos (user_id, estado);
create index if not exists firma_documentos_propiedad_idx
  on firma_documentos (propiedad_id) where propiedad_id is not null;


-- ─────────────────────────────────────────────────────────────────────────────
-- 2) FIRMANTES
--    Ojo con quién es quién: el agente NO es firmante de una promesa ni de un
--    arrendamiento. Ahí las partes son el cliente y su contraparte. El agente
--    solo aparece como parte en su propio contrato de exclusiva o en un
--    convenio entre asesores. Por eso no hay ninguna columna "agente": un
--    firmante es un contacto del CRM, punto.
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists firma_firmantes (
  id                  uuid primary key default gen_random_uuid(),

  -- Desnormalizado a propósito: permite políticas RLS de una sola línea sin
  -- subconsulta contra firma_documentos en cada lectura.
  user_id             uuid not null,
  documento_id        uuid not null references firma_documentos(id) on delete cascade,

  -- Vínculos opcionales al resto de la plataforma.
  contacto_id         uuid,          -- contactos.id
  expediente_id       uuid,          -- pld_expedientes.id (si ya está identificado)

  nombre              text not null,
  email               text,
  telefono            text,          -- E.164, ej +524431234567

  -- promitente_vendedor | promitente_comprador | arrendador | arrendatario |
  -- fiador | obligado_solidario | copropietario | conyuge | propietario |
  -- agente_mediador | otro
  rol                 text not null default 'otro',

  -- null = firma en paralelo (todos a la vez).
  -- 1,2,3… = firma en cascada; a cada quien le llega su turno cuando el
  -- anterior terminó. Sirve para el fiador, que solo debe firmar si los
  -- principales ya firmaron.
  orden               integer,
  obligatorio         boolean not null default true,

  token               text unique,   -- la liga privada de esta persona
  -- pendiente | abierto | firmado | rechazado
  estado              text not null default 'pendiente',

  -- Código de verificación. NUNCA se guarda en claro: solo su hash.
  otp_hash            text,
  otp_expira_at       timestamptz,
  otp_intentos        integer not null default 0,
  otp_canal           text,          -- whatsapp | email
  otp_enviado_at      timestamptz,
  verificado_at       timestamptz,

  firmado_at          timestamptz,
  rechazado_at        timestamptz,
  motivo_rechazo      text,

  trazo_ruta          text,          -- PNG del trazo
  ine_frente_ruta     text,
  ine_reverso_ruta    text,

  -- Evidencia del acto. Se llena en el momento de firmar, no antes.
  ip                  text,
  user_agent          text,
  geo_lat             double precision,
  geo_lng             double precision,
  geo_precision       double precision,

  -- El texto EXACTO que la persona aceptó, copiado literal. Si mañana se
  -- cambia la redacción del consentimiento, lo que se firmó ayer sigue
  -- guardado tal cual se leyó ayer. Sin esto la evidencia no sirve.
  consentimiento_at   timestamptz,
  consentimiento_texto text,

  created_at          timestamptz not null default now()
);

alter table firma_firmantes add column if not exists expediente_id    uuid;
alter table firma_firmantes add column if not exists ine_frente_ruta  text;
alter table firma_firmantes add column if not exists ine_reverso_ruta text;
alter table firma_firmantes add column if not exists geo_precision    double precision;

create index if not exists firma_firmantes_doc_idx
  on firma_firmantes (documento_id, orden nulls first, created_at);
create index if not exists firma_firmantes_user_idx
  on firma_firmantes (user_id);
create index if not exists firma_firmantes_contacto_idx
  on firma_firmantes (contacto_id) where contacto_id is not null;

-- La liga es la credencial. Búsqueda por token en cada carga de la página
-- pública: sin índice único esto es un recorrido completo de tabla y además
-- deja la puerta abierta a dos firmantes con el mismo token.
create unique index if not exists firma_firmantes_token_uniq
  on firma_firmantes (token) where token is not null;


-- ─────────────────────────────────────────────────────────────────────────────
-- 3) BITÁCORA
--    Se escribe, nunca se corrige. Es lo único que contesta la pregunta
--    "¿cómo sabes que fue él?" el día que alguien lo niegue.
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists firma_eventos (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null,
  documento_id  uuid references firma_documentos(id) on delete cascade,
  firmante_id   uuid references firma_firmantes(id) on delete set null,

  -- documento_creado | archivo_subido | enviado | liga_abierta | documento_visto |
  -- otp_enviado | otp_fallido | otp_verificado | consentimiento | ine_subida |
  -- firmado | rechazado | sellado | cancelado | descargado | recordatorio
  tipo          text not null,
  detalle       text,
  actor         text,          -- agente | firmante | sistema
  ip            text,
  user_agent    text,
  payload       jsonb,
  created_at    timestamptz not null default now()
);

create index if not exists firma_eventos_doc_idx
  on firma_eventos (documento_id, created_at);
create index if not exists firma_eventos_user_idx
  on firma_eventos (user_id, created_at desc);


-- ─────────────────────────────────────────────────────────────────────────────
-- 4) SEGURIDAD (RLS)
--    El backend usa la service_role key y se brinca estas reglas: así debe ser,
--    porque es él quien valida el JWT y quien atiende al firmante, que no tiene
--    sesión. Estas políticas protegen el acceso DIRECTO desde el navegador del
--    agente, para que nadie lea documentos de otra cuenta cambiando un id.
--
--    La bitácora es deliberadamente de solo lectura para el dueño: puede
--    consultarla, no puede editarla ni borrarla. Una bitácora que el propio
--    interesado puede corregir no prueba nada.
-- ─────────────────────────────────────────────────────────────────────────────
alter table firma_documentos enable row level security;
alter table firma_firmantes  enable row level security;
alter table firma_eventos    enable row level security;

drop policy if exists "dueño gestiona sus documentos" on firma_documentos;
create policy "dueño gestiona sus documentos"
  on firma_documentos for all
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

drop policy if exists "dueño gestiona sus firmantes" on firma_firmantes;
create policy "dueño gestiona sus firmantes"
  on firma_firmantes for all
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

drop policy if exists "dueño solo lee su bitacora" on firma_eventos;
create policy "dueño solo lee su bitacora"
  on firma_eventos for select
  using (user_id = auth.uid());


-- ─────────────────────────────────────────────────────────────────────────────
-- 5) ALMACENAMIENTO
--    Bucket PRIVADO. A diferencia de las fotos de propiedades, aquí viven
--    contratos con nombres, domicilios e identificaciones. Nada de lectura
--    pública: todo se sirve con ligas firmadas que caducan.
-- ─────────────────────────────────────────────────────────────────────────────
insert into storage.buckets (id, name, public)
select 'firmas', 'firmas', false
where not exists (select 1 from storage.buckets where id = 'firmas');

drop policy if exists "dueño lee sus archivos de firma" on storage.objects;
create policy "dueño lee sus archivos de firma"
  on storage.objects for select
  using (bucket_id = 'firmas' and (storage.foldername(name))[1] = auth.uid()::text);

drop policy if exists "dueño escribe sus archivos de firma" on storage.objects;
create policy "dueño escribe sus archivos de firma"
  on storage.objects for insert
  with check (bucket_id = 'firmas' and (storage.foldername(name))[1] = auth.uid()::text);

drop policy if exists "dueño borra sus archivos de firma" on storage.objects;
create policy "dueño borra sus archivos de firma"
  on storage.objects for delete
  using (bucket_id = 'firmas' and (storage.foldername(name))[1] = auth.uid()::text);
