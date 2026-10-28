-- ══════════════════════════════════════════════════════════════════════════
-- Broquer para Empresas: solo el dueño o un administrador borra
-- contactos/clientes, inmuebles y notas de bitácora
-- ══════════════════════════════════════════════════════════════════════════
-- Problema: un agente (miembro que no es dueño ni admin) podía borrar
-- directo en la base:
--   · contactos y clientes que él mismo creó (contactos_own_delete);
--   · notas de bitácora de CUALQUIER compañero
--     ("equipo elimina notas de su empresa");
--   · inmuebles: las reglas de borrado de propiedades no están en el repo,
--     así que no se puede asegurar que no.
-- El borrado masivo ya estaba bloqueado en el servidor (routers/bulk_delete.py)
-- y la pantalla ya no ofrece "Eliminar" a los agentes; esto cierra la base.
--
-- Arreglo: un CANDADO (regla restrictiva) de borrado en cada tabla: si eres
-- agente de una empresa, no borras. Se suma a las reglas que ya existan, sin
-- tocarlas, así que funciona aunque no sepamos cuáles hay en producción.
--   · Cuentas personales y dueño/admin de empresa: borran igual que hoy.
--   · El servidor (service key) y el SQL Editor no se ven afectados.
--   · No toca datos ni las reglas de ver, crear o editar.
--
-- Idempotente: se puede correr las veces que sea. Todo en una transacción.
-- Para deshacer: 20261016-solo-admin-borra-REVERSA.sql
-- ══════════════════════════════════════════════════════════════════════════

begin;

-- ── 1) ¿Soy agente (no dueño ni admin) de una empresa? ───────────────────
-- Misma regla que el servidor (get_org_context + routers/bulk_delete.py):
-- si hay una membresía activa de dueño, gana esa; si no, en una empresa
-- solo owner/admin borran.
create or replace function public.soy_agente_de_empresa()
returns boolean
language sql stable security definer
set search_path = public, pg_temp
as $$
  select exists (
           select 1
             from public.organizacion_miembros om
             join public.organizaciones o on o.id = om.org_id
            where om.user_id = auth.uid()
              and om.activo = true
              and coalesce(o.tipo, 'personal') = 'empresa'
              and coalesce(om.rol_org, 'agente') not in ('owner', 'admin'))
     and not exists (
           select 1
             from public.organizacion_miembros om
            where om.user_id = auth.uid()
              and om.activo = true
              and om.rol_org = 'owner')
$$;

revoke all on function public.soy_agente_de_empresa() from public, anon;
grant execute on function public.soy_agente_de_empresa() to authenticated, service_role;

-- ── 2) Candado de borrado en las tres tablas ─────────────────────────────
drop policy if exists "solo dueno o admin borra" on public.contactos;
create policy "solo dueno o admin borra" on public.contactos
  as restrictive for delete to public
  using (not (select public.soy_agente_de_empresa()));

drop policy if exists "solo dueno o admin borra" on public.propiedades;
create policy "solo dueno o admin borra" on public.propiedades
  as restrictive for delete to public
  using (not (select public.soy_agente_de_empresa()));

drop policy if exists "solo dueno o admin borra" on public.actividades;
create policy "solo dueno o admin borra" on public.actividades
  as restrictive for delete to public
  using (not (select public.soy_agente_de_empresa()));

commit;

-- ── Verificación: deben salir 3 filas, una por tabla ─────────────────────
select tablename, policyname, permissive, cmd
  from pg_policies
 where schemaname = 'public' and policyname = 'solo dueno o admin borra'
 order by tablename;

-- ── Para tu revisión: todas las reglas de borrado de estas tablas ────────
-- (las "PERMISSIVE" dicen quién podría borrar; el candado "RESTRICTIVE" de
-- arriba se aplica encima de todas ellas).
select tablename, policyname, permissive, cmd, qual as condicion
  from pg_policies
 where schemaname = 'public'
   and tablename in ('contactos', 'propiedades', 'actividades')
   and cmd in ('DELETE', 'ALL')
 order by tablename, permissive, policyname;
