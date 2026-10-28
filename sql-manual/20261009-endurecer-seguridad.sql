-- ══════════════════════════════════════════════════════════════════════════
-- Endurecer seguridad del esquema de producción (auditoría octubre 2026)
-- ══════════════════════════════════════════════════════════════════════════
-- Qué cierra:
--   1. admin_usuarios: respeta el RLS de "usuarios" (security_invoker) y ya
--      no la pueden leer ni anon ni authenticated. El panel de admin no la
--      usa (lee "usuarios" por el backend con service_role).
--   2. Vistas públicas del micrositio: quedan de solo lectura.
--   3. propiedades_avm: RLS encendido, lectura para anon/authenticated
--      (el plan B de routers/avm_nearby.py la lee con la llave pública) y
--      sin permisos de escritura.
--   4. wa2_numeros_backup_20260720: nadie de fuera la puede tocar.
--   5. Bucket avatares: cada quien solo puede actualizar sus propios archivos.
--   6. Funciones SECURITY DEFINER con search_path fijo.
--
-- Antes de cambiar nada guarda una foto del estado actual en el esquema
-- respaldo_seguridad_20261009 (no expuesto por la API). El script
-- 20261009-endurecer-seguridad-REVERSA.sql usa esa foto para dejar
-- todo exactamente como estaba.
--
-- Todo corre en una sola transacción: si algo falla, no cambia nada.
-- YA APLICADA a mano en producción. Vive en sql-manual/ para que la
-- integración de Supabase con GitHub no la vuelva a correr sola.
-- No toca storage.buckets.
-- ══════════════════════════════════════════════════════════════════════════

begin;

-- ── 0) Foto del estado actual ─────────────────────────────────────────────
-- Solo se toma la primera vez: si la migración se corre dos veces, la foto
-- original no se pisa con el estado ya endurecido.
do $$
begin
  if to_regclass('respaldo_seguridad_20261009.relaciones') is not null then
    raise notice 'La foto respaldo_seguridad_20261009 ya existe; no se vuelve a tomar.';
    return;
  end if;

  create schema if not exists respaldo_seguridad_20261009;
  revoke all on schema respaldo_seguridad_20261009 from public, anon, authenticated;

  create table respaldo_seguridad_20261009.relaciones (
    relacion        text primary key,   -- p. ej. public.admin_usuarios
    relkind         "char",
    relacl          aclitem[],
    relrowsecurity  boolean,
    reloptions      text[]
  );
  create table respaldo_seguridad_20261009.politicas (
    esquema     name,
    tabla       name,
    nombre      name,
    permissive  text,
    roles       name[],
    cmd         text,
    qual        text,
    with_check  text,
    primary key (esquema, tabla, nombre)
  );
  create table respaldo_seguridad_20261009.funciones (
    firma      text primary key,       -- p. ej. public.admin_update_usuario(uuid,jsonb)
    proconfig  text[]
  );
  revoke all on all tables in schema respaldo_seguridad_20261009 from public, anon, authenticated;

  insert into respaldo_seguridad_20261009.relaciones
  select n.nspname || '.' || c.relname, c.relkind, c.relacl, c.relrowsecurity, c.reloptions
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'public'
     and c.relname in ('admin_usuarios', 'usuarios_publicos', 'propiedades_publicas',
                       'propiedades_publicas_extra', 'testimonios_publicos',
                       'propiedades_avm', 'wa2_numeros_backup_20260720');

  insert into respaldo_seguridad_20261009.politicas
  select schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
    from pg_policies
   where (schemaname = 'storage' and tablename = 'objects'
          and policyname = 'usuarios pueden actualizar su avatar tk3snb_0')
      or (schemaname = 'public' and tablename = 'propiedades_avm');

  insert into respaldo_seguridad_20261009.funciones
  select p.oid::regprocedure::text, p.proconfig
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'public'
     and p.proname in ('admin_update_usuario', 'protect_usuarios_sensitive_fields')
     and p.prosecdef;
end $$;

-- ── 1) admin_usuarios ─────────────────────────────────────────────────────
do $$
begin
  if exists (select 1 from pg_class c join pg_namespace n on n.oid = c.relnamespace
              where n.nspname = 'public' and c.relname = 'admin_usuarios' and c.relkind = 'v') then
    execute 'alter view public.admin_usuarios set (security_invoker = true)';
  end if;
  if to_regclass('public.admin_usuarios') is not null then
    execute 'revoke all on public.admin_usuarios from public, anon, authenticated';
  end if;
end $$;

-- ── 2) Vistas públicas: solo lectura (SELECT se queda como está) ─────────
do $$
declare v text;
begin
  foreach v in array array['usuarios_publicos', 'propiedades_publicas',
                           'propiedades_publicas_extra', 'testimonios_publicos'] loop
    if to_regclass('public.' || v) is not null then
      execute format('revoke insert, update, delete, truncate, references, trigger on public.%I from public, anon, authenticated', v);
    end if;
  end loop;
end $$;

-- ── 3) propiedades_avm: RLS + solo lectura ───────────────────────────────
alter table public.propiedades_avm enable row level security;

drop policy if exists "propiedades_avm_lectura_publica" on public.propiedades_avm;
create policy "propiedades_avm_lectura_publica" on public.propiedades_avm
  for select to anon, authenticated
  using (true);

revoke insert, update, delete, truncate, references, trigger
  on public.propiedades_avm from public, anon, authenticated;
grant select on public.propiedades_avm to anon, authenticated;

-- ── 4) Tabla de respaldo de WhatsApp ─────────────────────────────────────
do $$
begin
  if to_regclass('public.wa2_numeros_backup_20260720') is not null then
    execute 'revoke all on public.wa2_numeros_backup_20260720 from public, anon, authenticated';
  end if;
end $$;

-- ── 5) Bucket avatares: actualizar solo lo propio ────────────────────────
drop policy if exists "usuarios pueden actualizar su avatar tk3snb_0" on storage.objects;
drop policy if exists "avatares_actualizar_solo_dueno" on storage.objects;
create policy "avatares_actualizar_solo_dueno" on storage.objects
  for update to authenticated
  using      (bucket_id = 'avatares' and owner = auth.uid())
  with check (bucket_id = 'avatares' and owner = auth.uid());

-- ── 6) search_path fijo en funciones SECURITY DEFINER ────────────────────
do $$
declare f regprocedure;
begin
  for f in
    select p.oid::regprocedure
      from pg_proc p
      join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'public'
       and p.proname in ('admin_update_usuario', 'protect_usuarios_sensitive_fields')
       and p.prosecdef
  loop
    execute format('alter function %s set search_path = public, extensions, pg_temp', f);
  end loop;
end $$;

commit;
