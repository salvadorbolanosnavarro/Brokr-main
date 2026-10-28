-- Revisión (solo lectura): ¿algo DENTRO de Supabase lee los tokens de WhatsApp?
-- Busca funciones, vistas, triggers y tareas programadas (pg_cron) que mencionen
-- access_token, wa2_numeros o wac_numbers. Resultado esperado: 0 renglones,
-- o solo cosas que tú reconozcas. No cambia nada.
select 'función' as tipo, n.nspname || '.' || p.proname as nombre
  from pg_proc p
  join pg_namespace n on n.oid = p.pronamespace
 where n.nspname not in ('pg_catalog', 'information_schema')
   and n.nspname not like 'pg_toast%'
   and (p.prosrc ilike '%access_token%' or p.prosrc ilike '%wa2_numeros%' or p.prosrc ilike '%wac_numbers%')
   and n.nspname not in ('auth', 'storage', 'realtime', 'graphql', 'graphql_public',
                         'supabase_functions', 'vault', 'pgsodium', 'extensions', 'net', 'cron')
union all
select 'vista', schemaname || '.' || viewname
  from pg_views
 where schemaname not in ('pg_catalog', 'information_schema')
   and (definition ilike '%access_token%' or definition ilike '%wa2_numeros%' or definition ilike '%wac_numbers%')
union all
select 'trigger', c.relname || ' → ' || t.tgname
  from pg_trigger t
  join pg_class c on c.oid = t.tgrelid
  join pg_namespace n on n.oid = c.relnamespace
 where not t.tgisinternal
   and n.nspname = 'public'
   and c.relname in ('wa2_numeros', 'wac_numbers')
union all
select 'tarea programada (pg_cron)', x.nombre
  from (select unnest(xpath('/table/row/n/text()',
          query_to_xml(case when to_regclass('cron.job') is not null
                            then 'select jobname as n from cron.job where command ilike ''%access_token%'' or command ilike ''%wa2_numeros%'' or command ilike ''%wac_numbers%'''
                            else 'select null::text as n where false' end,
                       false, false, '')))::text as nombre) x;
