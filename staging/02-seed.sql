-- Run ONLY in the empty broquer-redesign-staging SQL Editor, after the exact
-- live schema has been imported. Create the test Auth user in the panel first.
-- All changes are transactional. Missing schema requirements abort everything.
begin;
-- Confirm the project name in the panel before running this acknowledgement.
set local app.broquer_stage_seed = 'broquer-redesign-staging';
do $$
begin
 if current_setting('app.broquer_stage_seed',true) is distinct from 'broquer-redesign-staging' then
  raise exception 'Set the explicit staging acknowledgement before running the seed';
 end if;
 if exists(select 1 from auth.users where email is distinct from 'qa-broquer@example.test') then
  raise exception 'Not a clean test DB: unexpected Auth users. No seed written.';
 end if;
 if not exists(select 1 from auth.users where email='qa-broquer@example.test') then
  raise exception 'Create qa-broquer@example.test using Authentication > Users > Add user first';
 end if;
end $$;

-- Use only existing columns; default values remain effective. This does not
-- alter the live schema, invent tables or bypass RLS for application requests.
create function pg_temp.seed_row(target text,payload jsonb) returns void language plpgsql as $$
declare columns_sql text; values_sql text;
begin
 if to_regclass('public.'||target) is null then raise exception 'Missing table public.%',target; end if;
 select string_agg(format('%I',a.attname),',' order by a.attnum),
        string_agg(format('r.%I',a.attname),',' order by a.attnum)
 into columns_sql,values_sql
 from pg_attribute a
 where a.attrelid=to_regclass('public.'||target) and a.attnum>0 and not a.attisdropped
 and a.attgenerated='' and a.attidentity='' and payload ? a.attname;
 if columns_sql is null then raise exception 'No matching columns for %',target; end if;
 execute format('insert into public.%I (%s) select %s from jsonb_populate_record(null::public.%I,$1) r on conflict do nothing',target,columns_sql,values_sql,target) using payload;
end $$;

do $$
declare uid uuid; c1 uuid='11111111-1111-4111-8111-111111111111'; c2 uuid='22222222-2222-4222-8222-222222222222'; p1 uuid='33333333-3333-4333-8333-333333333333'; wc uuid='66666666-6666-4666-8666-666666666666'; cv uuid='77777777-7777-4777-8777-777777777777'; base jsonb;
begin
 select id into strict uid from auth.users where email='qa-broquer@example.test';
 base=jsonb_build_object('user_id',uid);
 -- The normal Auth signup trigger should create the account profile. Do not
 -- silently grant admin, subscription or an organization without its policies.
 perform pg_temp.seed_row('contactos',base||jsonb_build_object('id',c1,'nombre','CLIENTE QA UNO','telefono','0000000000','wa','','email','cliente-uno@example.test','tipo','persona','es_potencial',true,'notas','Datos ficticios para pruebas. No contactar.'));
 perform pg_temp.seed_row('contactos',base||jsonb_build_object('id',c2,'nombre','CLIENTE QA DOS','telefono','0000000001','wa','','email','cliente-dos@example.test','tipo','persona','es_potencial',true,'notas','Datos ficticios para pruebas. No contactar.'));
 perform pg_temp.seed_row('propiedades',base||jsonb_build_object('id',p1,'titulo','Casa QA ficticia','clave_interna','QA-001','tipo','Casa','operacion','Venta','precio',1250000,'descripcion','Inmueble ficticio. Sin dirección ni fotos de clientes.'));
 perform pg_temp.seed_row('tareas',base||jsonb_build_object('id','44444444-4444-4444-8444-444444444444','titulo','Cita QA: visitar casa ficticia','fecha_entrega',now()+interval '1 day','completada',false,'contacto_id',c1,'propiedad_id',p1,'notas','No enviar recordatorios externos.'));
 perform pg_temp.seed_row('firma_documentos',base||jsonb_build_object('id','55555555-5555-4555-8555-555555555555','titulo','Contrato QA de arrendamiento — borrador','tipo','arrendamiento','nivel','simple','estado','borrador','folio','QA-BRQ-0001','propiedad_id',p1,'exige_ine',false,'mensaje','Contrato ficticio de prueba, sin firmantes reales.'));
 perform pg_temp.seed_row('wa_contacts',base||jsonb_build_object('id',wc,'wa_id','STAGING_FAKE_CONTACT_001','nombre','Conversación QA ficticia','etapa','Nuevo'));
 perform pg_temp.seed_row('wa_conversations',base||jsonb_build_object('id',cv,'contact_id',wc,'ai_enabled',false,'phone_number_id','STAGING_FAKE_NUMBER','property_ctx','Casa QA ficticia'));
 perform pg_temp.seed_row('wa_messages',base||jsonb_build_object('id','88888888-8888-4888-8888-888888888888','contact_id',wc,'conversation_id',cv,'wa_message_id','STAGING_FAKE_MESSAGE_001','direction','in','sender','lead','body','Mensaje ficticio: ¿podemos visitar la casa QA?','status','read'));
 perform pg_temp.seed_row('wa_messages',base||jsonb_build_object('id','99999999-9999-4999-8999-999999999999','contact_id',wc,'conversation_id',cv,'wa_message_id','STAGING_FAKE_MESSAGE_002','direction','out','sender','agent','body','Respuesta ficticia: agendamos una visita QA.','status','read'));
end $$;
commit;
