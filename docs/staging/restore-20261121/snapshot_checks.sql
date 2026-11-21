create temporary table qa_snapshot_checks(table_name text,row_count bigint,immutable_md5 text);
do $$ declare r record;n bigint;h text;expr text;dt text;begin
 for r in select * from (values
 ('public','usuarios','created_at','full'),
 ('public','organizaciones','created_at','full'),
 ('public','organizacion_miembros','created_at','full'),
 ('public','module_sessions','ts','module'),
 ('auth','users','created_at','full'),
 ('auth','identities','created_at','full'),
 ('auth','sessions','created_at','session'),
 ('auth','refresh_tokens','created_at','refresh'),
 ('auth','mfa_amr_claims','created_at','full')) v(s,t,d,k) loop
  expr:=case r.k
   when 'module' then 'jsonb_build_object(''id'',t.id,''user_id'',t.user_id,''modulo'',t.modulo,''ts'',t.ts,''org_id'',t.org_id)'
   when 'session' then 'jsonb_build_object(''id'',t.id,''user_id'',t.user_id,''created_at'',t.created_at,''aal'',t.aal,''oauth_client_id'',t.oauth_client_id)'
   when 'refresh' then 'jsonb_build_object(''id'',t.id,''user_id'',t.user_id,''created_at'',t.created_at,''session_id'',t.session_id,''parent'',t.parent,''token'',t.token)'
   else '(to_jsonb(t)-array[''updated_at'',''last_sign_in_at''])' end;
  execute format('select count(*),md5(coalesce(string_agg((%s)::text,E''\n'' order by (%s)::text),'''')) from %I.%I t where %I <= timestamptz ''2026-11-21 07:05:17+00''',expr,expr,r.s,r.t,r.d) into n,h;
  insert into qa_snapshot_checks values(r.s||'.'||r.t,n,h);
 end loop;
end $$;
select jsonb_agg(to_jsonb(c) order by table_name) as snapshot_checks from qa_snapshot_checks c;
