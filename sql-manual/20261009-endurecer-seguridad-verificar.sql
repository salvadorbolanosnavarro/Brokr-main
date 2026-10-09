-- Verificación de 20261009-endurecer-seguridad.sql (solo lectura).
-- Cada renglón trae lo esperado y lo real; la columna "ok" debe salir true en todos.
with chequeos(hueco, chequeo, esperado, real) as (values
  ('1 admin_usuarios', 'anon puede SELECT',             false, has_table_privilege('anon',          'public.admin_usuarios', 'SELECT')),
  ('1 admin_usuarios', 'authenticated puede SELECT',    false, has_table_privilege('authenticated', 'public.admin_usuarios', 'SELECT')),
  ('1 admin_usuarios', 'security_invoker=true',         true,  coalesce((select 'security_invoker=true' = any(reloptions) from pg_class where oid = 'public.admin_usuarios'::regclass), false)),

  ('2 usuarios_publicos',          'anon puede SELECT',                    true,  has_table_privilege('anon', 'public.usuarios_publicos', 'SELECT')),
  ('2 usuarios_publicos',          'anon puede INSERT/UPDATE/DELETE/TRUNCATE', false, has_table_privilege('anon', 'public.usuarios_publicos', 'INSERT,UPDATE,DELETE,TRUNCATE')),
  ('2 propiedades_publicas',       'anon puede SELECT',                    true,  has_table_privilege('anon', 'public.propiedades_publicas', 'SELECT')),
  ('2 propiedades_publicas',       'anon puede INSERT/UPDATE/DELETE/TRUNCATE', false, has_table_privilege('anon', 'public.propiedades_publicas', 'INSERT,UPDATE,DELETE,TRUNCATE')),
  ('2 propiedades_publicas_extra', 'anon puede SELECT',                    true,  has_table_privilege('anon', 'public.propiedades_publicas_extra', 'SELECT')),
  ('2 propiedades_publicas_extra', 'anon puede INSERT/UPDATE/DELETE/TRUNCATE', false, has_table_privilege('anon', 'public.propiedades_publicas_extra', 'INSERT,UPDATE,DELETE,TRUNCATE')),
  ('2 testimonios_publicos',       'anon puede SELECT',                    true,  has_table_privilege('anon', 'public.testimonios_publicos', 'SELECT')),
  ('2 testimonios_publicos',       'anon puede INSERT/UPDATE/DELETE/TRUNCATE', false, has_table_privilege('anon', 'public.testimonios_publicos', 'INSERT,UPDATE,DELETE,TRUNCATE')),
  ('2 vistas públicas',            'authenticated puede escribir en alguna', false,
     has_table_privilege('authenticated', 'public.usuarios_publicos',          'INSERT,UPDATE,DELETE,TRUNCATE')
  or has_table_privilege('authenticated', 'public.propiedades_publicas',       'INSERT,UPDATE,DELETE,TRUNCATE')
  or has_table_privilege('authenticated', 'public.propiedades_publicas_extra', 'INSERT,UPDATE,DELETE,TRUNCATE')
  or has_table_privilege('authenticated', 'public.testimonios_publicos',       'INSERT,UPDATE,DELETE,TRUNCATE')),

  ('3 propiedades_avm', 'RLS encendido (relrowsecurity)',         true,  (select relrowsecurity from pg_class where oid = 'public.propiedades_avm'::regclass)),
  ('3 propiedades_avm', 'política SELECT para anon,authenticated', true,  exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'propiedades_avm'
                                                                                   and policyname = 'propiedades_avm_lectura_publica' and cmd = 'SELECT'
                                                                                   and roles @> array['anon','authenticated']::name[])),
  ('3 propiedades_avm', 'anon puede SELECT',                      true,  has_table_privilege('anon', 'public.propiedades_avm', 'SELECT')),
  ('3 propiedades_avm', 'anon puede INSERT/UPDATE/DELETE/TRUNCATE', false, has_table_privilege('anon', 'public.propiedades_avm', 'INSERT,UPDATE,DELETE,TRUNCATE')),
  ('3 propiedades_avm', 'authenticated puede INSERT/UPDATE/DELETE/TRUNCATE', false, has_table_privilege('authenticated', 'public.propiedades_avm', 'INSERT,UPDATE,DELETE,TRUNCATE')),

  ('4 wa2_numeros_backup_20260720', 'anon tiene algún permiso',          false, has_table_privilege('anon',          'public.wa2_numeros_backup_20260720', 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')),
  ('4 wa2_numeros_backup_20260720', 'authenticated tiene algún permiso', false, has_table_privilege('authenticated', 'public.wa2_numeros_backup_20260720', 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')),

  ('5 avatares', 'política vieja tk3snb_0 existe', false, exists (select 1 from pg_policies where schemaname = 'storage' and tablename = 'objects'
                                                                    and policyname = 'usuarios pueden actualizar su avatar tk3snb_0')),
  ('5 avatares', 'política nueva exige owner = auth.uid()', true, exists (select 1 from pg_policies where schemaname = 'storage' and tablename = 'objects'
                                                                    and policyname = 'avatares_actualizar_solo_dueno' and cmd = 'UPDATE'
                                                                    and qual like '%owner = auth.uid()%' and with_check like '%owner = auth.uid()%')),

  ('6 admin_update_usuario',              'search_path fijo', true, coalesce((select bool_and('search_path=public, extensions, pg_temp' = any(proconfig)) from pg_proc
                                                                       where pronamespace = 'public'::regnamespace and proname = 'admin_update_usuario' and prosecdef), false)),
  ('6 protect_usuarios_sensitive_fields', 'search_path fijo', true, coalesce((select bool_and('search_path=public, extensions, pg_temp' = any(proconfig)) from pg_proc
                                                                       where pronamespace = 'public'::regnamespace and proname = 'protect_usuarios_sensitive_fields' and prosecdef), false)),

  ('foto para reversa', 'esquema respaldo_seguridad_20261009 existe', true, exists (select 1 from pg_namespace where nspname = 'respaldo_seguridad_20261009'))
)
select hueco, chequeo, esperado, real, (esperado = real) as ok
  from chequeos;
