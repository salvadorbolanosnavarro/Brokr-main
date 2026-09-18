-- ═══════════════════════════════════════════════════════════════════════════
-- Broquer — Un contacto asignado sigue visible aunque le apaguen "ver
-- contactos del equipo" (Broquer para Empresas)
--
-- QUÉ ARREGLA
--   Cuando el dueño/admin apaga "ver contactos del equipo" para un agente,
--   ese agente deja de ver los contactos que no capturó él mismo — INCLUSO
--   los que el propio dueño le asignó con "Asignar a" (columna asignado_a,
--   ver migracion-asignacion-agente.sql). Asignarle un contacto a alguien
--   para que lo trabaje y que acto seguido no pueda verlo es una
--   contradicción: la responsabilidad no le sirve de nada si no puede ni
--   abrir la ficha.
--
--   La política de RLS existente de "contactos" en Supabase ya decide, por
--   fila, si un agente sin "ver_contactos_equipo" ve un contacto ajeno
--   (normalmente: solo si user_id = auth.uid(), es decir, si él lo capturó).
--   Este script NO toca esa política — no sabemos su nombre exacto y
--   tocarla a ciegas es peligroso. En vez de eso, agrega una política
--   PERMISSIVE adicional para SELECT: Postgres combina políticas
--   permissive del mismo comando con OR, así que esta solo AMPLÍA quién
--   puede ver una fila (nunca resta lo que la política vieja ya permitía).
--
-- QUÉ NO HACE
--   No cambia quién puede asignar (sigue siendo solo owner/admin, ver
--   POST /org/asignar en routers/organizaciones.py). No cambia INSERT,
--   UPDATE ni DELETE: un agente con un contacto asignado puede VERLO, no
--   necesariamente editarlo o borrarlo (eso lo sigue decidiendo la política
--   de escritura existente).
--
-- Idempotente: se puede correr las veces que sea.
-- Correr manualmente en el SQL Editor de Supabase.
-- ═══════════════════════════════════════════════════════════════════════════

alter table public.contactos enable row level security;

drop policy if exists "agente ve sus contactos asignados" on public.contactos;

create policy "agente ve sus contactos asignados"
  on public.contactos
  for select
  using (asignado_a = auth.uid());

-- ── Resultado ──
select polname, polcmd
  from pg_policy
 where polrelid = 'public.contactos'::regclass
 order by polname;
