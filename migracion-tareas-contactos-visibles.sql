-- ═══════════════════════════════════════════════════════════════════════════
-- Broquer — El cliente ligado a una tarea que te asignaron es visible para ti
-- (Broquer para Empresas)
--
-- QUÉ ARREGLA
--   Un miembro del equipo crea una tarea ligada a SU cliente y se la asigna
--   a otro miembro. Si a ese otro miembro le apagaron "ver contactos del
--   equipo", la política de RLS de `contactos` no le deja leer ese cliente:
--   en Tareas veía un genérico "Contacto" y no podía abrir la ficha, así que
--   nunca sabía de quién se trataba. Asignarle trabajo sobre un cliente y
--   esconderle quién es el cliente es una contradicción (mismo criterio que
--   migracion-contactos-asignados-visibles.sql).
--
--   Mientras esta migración no se corra, Tareas ya muestra nombre y teléfono
--   de esos clientes gracias a POST /org/tareas/contactos-vinculados
--   (routers/organizaciones.py). Esto agrega lo que falta: poder abrir la
--   ficha completa desde Contactos/Clientes.
--
-- QUÉ HACE
--   Agrega una política PERMISSIVE adicional de SELECT sobre `contactos`
--   (Postgres las combina con OR: solo AMPLÍA, nunca quita acceso). Un
--   contacto se vuelve visible para quien tenga ASIGNADA una tarea de la
--   misma empresa ligada a ese contacto (columna tareas.contacto_id o tabla
--   tareas_contactos).
--
-- QUÉ NO HACE
--   No toca las políticas existentes. No da permiso de editar ni borrar el
--   contacto. No abre los demás clientes del compañero: solo los ligados a
--   tareas que te asignaron. Si te quitan la tarea (o la reasignan), dejas
--   de ver el contacto.
--
-- Idempotente: se puede correr las veces que sea.
-- Correr manualmente en el SQL Editor de Supabase.
-- ═══════════════════════════════════════════════════════════════════════════

-- Todo se compara como texto: contactos.id es text y así no importa si
-- org_id/user_id de alguna tabla quedaron como text o como uuid.
--
-- SECURITY DEFINER: la revisión consulta tareas / tareas_contactos /
-- organizacion_miembros sin pasar por sus propias políticas de RLS. Así no
-- hay recursión entre políticas y la consulta es barata.
create or replace function public.contacto_en_mis_tareas(
  p_contacto text, p_org text, p_duenio text
) returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
      from public.tareas t
     where t.asignado_a = auth.uid()
       and (
             t.contacto_id::text = p_contacto
          or exists (select 1 from public.tareas_contactos tc
                      where tc.tarea_id = t.id and tc.contacto_id::text = p_contacto)
       )
       -- El contacto tiene que ser de la misma empresa que la tarea (por su
       -- org, o, en contactos viejos sin org, porque su dueño es del equipo).
       and (
             t.org_id::text = p_org
          or exists (select 1 from public.organizacion_miembros om
                      where om.org_id = t.org_id and om.user_id::text = p_duenio)
       )
  );
$$;

revoke all on function public.contacto_en_mis_tareas(text, text, text) from public;
grant execute on function public.contacto_en_mis_tareas(text, text, text) to authenticated;

alter table public.contactos enable row level security;

drop policy if exists "agente ve contactos de sus tareas asignadas" on public.contactos;

create policy "agente ve contactos de sus tareas asignadas"
  on public.contactos
  for select
  using (public.contacto_en_mis_tareas(id::text, org_id::text, user_id::text));

-- ── Resultado ──
select polname, polcmd
  from pg_policy
 where polrelid = 'public.contactos'::regclass
 order by polname;
