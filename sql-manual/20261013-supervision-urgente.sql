-- ══════════════════════════════════════════════════════════════════════════
-- Comentarios urgentes de supervisión
-- ══════════════════════════════════════════════════════════════════════════
-- En cuentas de empresa, el dueño o un admin puede dejar en la bitácora de un
-- cliente una nota marcada como URGENTE para el agente asignado. Al agente le
-- llega un aviso, la ve en el apartado "Urgente de supervisión" de Clientes y
-- la marca como atendida cuando ya la resolvió; el supervisor ve si ya lo hizo.
--
-- Qué hace:
--   1) Cuatro columnas nuevas en actividades (todas opcionales, las notas de
--      siempre quedan igual: urgente = false):
--        urgente       la nota es un comentario urgente de supervisión
--        para_usuario  el agente que tiene que atenderlo
--        atendido_en   cuándo lo marcó como atendido (null = pendiente)
--        atendido_por  quién lo marcó
--   2) Un candado (trigger): desde el navegador nadie puede poner, quitar ni
--      cambiar esas cuatro columnas. Solo el backend (routers/supervision.py,
--      con service key) las escribe, después de revisar que quien crea el
--      comentario es owner/admin y que quien lo da por atendido es el agente
--      destinatario o un admin. Así un agente no puede fabricar "urgentes"
--      ni borrar la marca desde la consola.
--   3) Un índice para contar rápido los pendientes de cada agente.
--
-- No toca reglas de RLS ni datos existentes. Idempotente.
-- Para quitarlo: 20261013-supervision-urgente-REVERSA.sql
-- ══════════════════════════════════════════════════════════════════════════

begin;

alter table public.actividades add column if not exists urgente boolean not null default false;
alter table public.actividades add column if not exists para_usuario uuid;
alter table public.actividades add column if not exists atendido_en timestamptz;
alter table public.actividades add column if not exists atendido_por uuid;

create index if not exists idx_actividades_urgentes_pendientes
  on public.actividades (para_usuario, created_at desc)
  where urgente and atendido_en is null;

create or replace function public.actividades_candado_supervision()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  -- El backend (service key) y el SQL Editor sí pueden.
  if current_user in ('service_role', 'postgres', 'supabase_admin') then
    return new;
  end if;
  if tg_op = 'INSERT' then
    if new.urgente or new.para_usuario is not null
       or new.atendido_en is not null or new.atendido_por is not null then
      raise exception 'Los comentarios urgentes de supervisión se crean desde Broquer, no directo.'
        using errcode = '42501';
    end if;
  elsif new.urgente is distinct from old.urgente
     or new.para_usuario is distinct from old.para_usuario
     or new.atendido_en is distinct from old.atendido_en
     or new.atendido_por is distinct from old.atendido_por then
    raise exception 'Los comentarios urgentes de supervisión se cambian desde Broquer, no directo.'
      using errcode = '42501';
  end if;
  return new;
end;
$$;

revoke all on function public.actividades_candado_supervision() from public, anon, authenticated;

drop trigger if exists actividades_candado_supervision on public.actividades;
create trigger actividades_candado_supervision
  before insert or update on public.actividades
  for each row execute function public.actividades_candado_supervision();

commit;

-- ── Verificación ─────────────────────────────────────────────────────────
select count(*) filter (where urgente) as urgentes,
       count(*) filter (where urgente and atendido_en is null) as pendientes,
       count(*) as total
  from public.actividades;
