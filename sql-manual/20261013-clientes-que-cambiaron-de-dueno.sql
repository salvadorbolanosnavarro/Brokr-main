-- ══════════════════════════════════════════════════════════════════════════
-- Clientes que probablemente cambiaron de dueño sin que nadie lo notara
-- ══════════════════════════════════════════════════════════════════════════
-- SOLO LECTURA: no cambia nada. Córrelo en el SQL Editor de Supabase.
--
-- Qué pasaba: al guardar "Editar cliente", la app reenviaba el cliente
-- completo con user_id = quien guardaba. Cuando un owner/admin editaba un
-- cliente que había creado un agente, el cliente pasaba a ser del admin y el
-- agente dejaba de poder editarlo o borrarlo (y de verlo, si no lo tenía
-- asignado). Corregido en el PR de "Editar cliente sin cambiar de dueño".
--
-- La base no guarda quién creó cada cliente originalmente, así que esto
-- busca PISTAS en clientes que hoy son de un owner/admin y que se editaron
-- después de crearse:
--   · 3 puntos: su conversación de WhatsApp es del número de otra persona
--     del equipo (el lead entró por SU WhatsApp: casi seguro era suyo).
--   · 1 punto:  otra persona del equipo escribió la primera nota de la bitácora.
--   · 1 punto:  otra persona del equipo lo vinculó a una tarea.
-- Más puntos = más probable. Un cliente que el admin sí creó y luego asignó
-- puede salir con 1 punto: revísalo antes de regresarlo. Y un cliente que
-- cambió de dueño pero no deja ninguna pista no va a aparecer.
-- ══════════════════════════════════════════════════════════════════════════

with admins as (
  select org_id, user_id
    from public.organizacion_miembros
   where activo and rol_org in ('owner', 'admin')
),
sospechosos as (
  select c.id, c.nombre, c.org_id, c.user_id as dueno_actual, c.asignado_a,
         c.created_at, c.updated_at
    from public.contactos c
    join admins a on a.org_id = c.org_id and a.user_id = c.user_id
   where c.updated_at > c.created_at + interval '1 minute'
),
pistas as (
  select s.id, w.user_id as otro, 3 as puntos,
         'su WhatsApp es de esta persona' as pista
    from sospechosos s
    join public.wa2_conversaciones w
      on w.contacto_id::text = s.id::text and w.user_id <> s.dueno_actual
  union all
  select s.id, primera.user_id, 1, 'escribió la primera nota'
    from sospechosos s
    join lateral (
      select a.user_id from public.actividades a
       where a.contacto_id::text = s.id::text
       order by a.created_at
       limit 1
    ) primera on primera.user_id <> s.dueno_actual
  union all
  select distinct s.id, tc.user_id, 1, 'lo vinculó a una tarea'
    from sospechosos s
    join public.tareas_contactos tc
      on tc.contacto_id::text = s.id::text and tc.user_id <> s.dueno_actual
)
select s.id                                   as cliente_id,
       s.nombre                               as cliente,
       coalesce(ua.nombre, ua.email)          as dueno_hoy,
       coalesce(uo.nombre, uo.email)          as probable_dueno_original,
       p.otro                                 as probable_dueno_original_id,
       coalesce(ux.nombre, ux.email, '—')     as asignado_a,
       sum(p.puntos)                          as puntos,
       string_agg(distinct p.pista, ' · ')    as pistas,
       s.created_at::date                     as creado,
       s.updated_at::date                     as ultima_edicion
  from pistas p
  join sospechosos s on s.id = p.id
  -- La pista solo cuenta si viene de alguien del mismo equipo.
  join public.organizacion_miembros om on om.org_id = s.org_id and om.user_id = p.otro
  left join public.usuarios ua on ua.id = s.dueno_actual
  left join public.usuarios uo on uo.id = p.otro
  left join public.usuarios ux on ux.id = s.asignado_a
 group by s.id, s.nombre, ua.nombre, ua.email, uo.nombre, uo.email, p.otro,
          ux.nombre, ux.email, s.created_at, s.updated_at
 order by puntos desc, s.updated_at desc;

-- ── Para regresar un cliente a su dueño original (después de revisarlo) ──
-- Copia el cliente_id y el probable_dueno_original_id de la tabla de arriba:
--
-- update public.contactos
--    set user_id = '<probable_dueno_original_id>'
--  where id = '<cliente_id>';
