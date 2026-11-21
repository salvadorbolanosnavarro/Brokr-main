-- Aggregate-only inventory: no raw rows, passwords, tokens or database secrets.
create temporary table qa_restore_inventory(schema_name text,table_name text,row_count bigint,data_md5 text);
do $$ declare r record; n bigint; h text; begin
 for r in select n.nspname,c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace
 where c.relkind='r' and n.nspname in ('public','auth','storage') order by 1,2 loop
  execute format('select count(*), md5(coalesce(string_agg(to_jsonb(t)::text, E''\n'' order by to_jsonb(t)::text),'''')) from %I.%I t',r.nspname,r.relname) into n,h;
  insert into qa_restore_inventory values(r.nspname,r.relname,n,h);
 end loop;
end $$;
select jsonb_build_object(
 'tables',(select jsonb_agg(to_jsonb(i) order by schema_name,table_name) from qa_restore_inventory i),
 'columns',(select jsonb_agg(to_jsonb(x) order by table_schema,table_name,ordinal_position) from (select table_schema,table_name,column_name,ordinal_position,data_type,udt_schema,udt_name,is_nullable,column_default from information_schema.columns where table_schema in ('public','auth','storage')) x),
 'policies',(select jsonb_agg(to_jsonb(p) order by schemaname,tablename,policyname) from pg_policies p where schemaname in ('public','auth','storage')),
 'functions',(select jsonb_agg(jsonb_build_object('schema',n.nspname,'name',p.proname,'args',pg_get_function_identity_arguments(p.oid),'definition_md5',md5(pg_get_functiondef(p.oid))) order by n.nspname,p.proname,p.oid) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname in ('public','auth','storage') and p.prokind in ('f','p')),
 'triggers',(select jsonb_agg(jsonb_build_object('schema',n.nspname,'table',c.relname,'name',t.tgname,'definition',pg_get_triggerdef(t.oid)) order by n.nspname,c.relname,t.tgname) from pg_trigger t join pg_class c on c.oid=t.tgrelid join pg_namespace n on n.oid=c.relnamespace where not t.tgisinternal and n.nspname in ('public','auth','storage')),
 'constraints',(select jsonb_agg(jsonb_build_object('schema',n.nspname,'table',c.relname,'name',k.conname,'definition',pg_get_constraintdef(k.oid),'validated',k.convalidated) order by n.nspname,c.relname,k.conname) from pg_constraint k join pg_class c on c.oid=k.conrelid join pg_namespace n on n.oid=c.relnamespace where n.nspname in ('public','auth','storage')),
 'indexes',(select jsonb_agg(to_jsonb(i) order by schemaname,tablename,indexname) from pg_indexes i where schemaname in ('public','auth','storage')),
 'rls',(select jsonb_agg(jsonb_build_object('schema',n.nspname,'table',c.relname,'enabled',c.relrowsecurity,'forced',c.relforcerowsecurity) order by n.nspname,c.relname) from pg_class c join pg_namespace n on n.oid=c.relnamespace where c.relkind='r' and n.nspname in ('public','auth','storage')),
 'extensions',(select jsonb_agg(jsonb_build_object('name',extname,'version',extversion) order by extname) from pg_extension),
 'roles',(select jsonb_agg(jsonb_build_object('name',rolname,'login',rolcanlogin,'superuser',rolsuper,'bypassrls',rolbypassrls) order by rolname) from pg_roles)
) as inventory;
