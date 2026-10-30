-- READ ONLY. Run in production SQL Editor, export the single JSON result.
-- No auth.users, customer rows, messages, files or secret values are read.
-- This describes the live schema so missing repo migrations can be identified.
select jsonb_pretty(jsonb_build_object(
 'columns',(select jsonb_agg(to_jsonb(x)) from (select table_schema,table_name,column_name,ordinal_position,data_type,udt_schema,udt_name,is_nullable,column_default,is_identity,identity_generation,is_generated,generation_expression from information_schema.columns where table_schema='public' order by table_name,ordinal_position)x),
 'constraints',(select jsonb_agg(to_jsonb(x)) from (select n.nspname schema,c.relname relation,con.conname name,con.contype kind,pg_get_constraintdef(con.oid,true) definition from pg_constraint con join pg_class c on c.oid=con.conrelid join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' order by c.relname,con.conname)x),
 'indexes',(select jsonb_agg(to_jsonb(x)) from (select schemaname,tablename,indexname,indexdef from pg_indexes where schemaname='public' order by tablename,indexname)x),
 'rls',(select jsonb_agg(to_jsonb(x)) from (select n.nspname schema,c.relname relation,c.relrowsecurity enabled,c.relforcerowsecurity forced from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind in('r','p'))x),
 'policies',(select jsonb_agg(to_jsonb(x)) from (select * from pg_policies where schemaname in('public','storage','auth') order by schemaname,tablename,policyname)x),
 'functions',(select jsonb_agg(to_jsonb(x)) from (select n.nspname schema,p.proname name,pg_get_functiondef(p.oid) definition from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.prokind in('f','p'))x),
 'triggers',(select jsonb_agg(to_jsonb(x)) from (select n.nspname schema,c.relname relation,pg_get_triggerdef(t.oid,true) definition,t.tgenabled enabled from pg_trigger t join pg_class c on c.oid=t.tgrelid join pg_namespace n on n.oid=c.relnamespace where n.nspname in('public','auth','storage') and not t.tgisinternal)x),
 'views',(select jsonb_agg(to_jsonb(x)) from (select schemaname,viewname,definition from pg_views where schemaname='public')x),
 'types',(select jsonb_agg(to_jsonb(x)) from (select n.nspname schema,t.typname name,e.enumlabel label,e.enumsortorder position from pg_type t join pg_namespace n on n.oid=t.typnamespace join pg_enum e on e.enumtypid=t.oid where n.nspname='public' order by t.typname,e.enumsortorder)x),
 'sequences',(select jsonb_agg(to_jsonb(x)) from (select * from pg_sequences where schemaname='public')x),
 'grants',(select jsonb_agg(to_jsonb(x)) from (select * from information_schema.role_table_grants where table_schema='public')x),
 'buckets',(select jsonb_agg(jsonb_build_object('id',id,'name',name,'public',public,'file_size_limit',file_size_limit,'allowed_mime_types',allowed_mime_types)) from storage.buckets)
)) as schema_metadata;
