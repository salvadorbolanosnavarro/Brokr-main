-- =============================================================================
-- Broquer — Reparar filas huérfanas de empresa (org_id NULL)
-- Copiar TODO, pegar en Supabase > SQL Editor, botón Run.
--
-- QUÉ ARREGLA
--   Los inmuebles y contactos que el backend crea con la service key (por
--   ejemplo, los que Broq da de alta desde WhatsApp) nacían SIN org_id,
--   porque sin sesión de usuario la base no puede deducir la empresa.
--   El borrado de la plataforma filtra por org_id, así que esas filas
--   quedaban imposibles de eliminar: "No tienes permiso".
--
--   Esto les pone su org_id correcto, tomado de la membresía activa del
--   dueño de cada fila. A partir del despliegue del backend parchado, las
--   filas nuevas ya nacen con org_id y esto no vuelve a pasar.
--
-- NO ROMPE NADA. Solo toca filas con org_id NULL cuyo dueño tiene una
-- membresía activa. Es seguro correrlo más de una vez. Si algo saliera
-- mal, se deshace solo.
-- =============================================================================

begin;

-- ── 1. Inmuebles huérfanos ──
with reparadas as (
  update public.propiedades p
     set org_id = m.org_id
    from public.organizacion_miembros m
   where p.org_id is null
     and m.user_id = p.user_id
     and m.activo = true
  returning p.id
)
select count(*) as inmuebles_reparados from reparadas;

-- ── 2. Contactos huérfanos ──
with reparados as (
  update public.contactos c
     set org_id = m.org_id
    from public.organizacion_miembros m
   where c.org_id is null
     and m.user_id = c.user_id
     and m.activo = true
  returning c.id
)
select count(*) as contactos_reparados from reparados;

-- ── 3. Reporte: ¿quedó algo huérfano? ──
-- Si estos números salen en cero, todo quedó sano. Si sale algo, son filas
-- cuyo dueño no tiene membresía activa en ninguna empresa (raro): avísale
-- a Claude con el user_id para revisarlo.
select 'propiedades sin org tras reparar' as tabla,
       user_id, count(*) as filas
  from public.propiedades
 where org_id is null
 group by user_id
union all
select 'contactos sin org tras reparar',
       user_id, count(*)
  from public.contactos
 where org_id is null
 group by user_id;

commit;
