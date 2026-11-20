-- Run ONLY against project tymhlvawnqadqgwnpruk. Disposable QA identities only.
-- No schema, RLS, role, provider credential or subscription changes.
begin;
do $$
begin
 if (select count(*) from public.usuarios where
 (id='0c823902-41d1-4df2-b357-dedf8d681a38' and email='salvadorbolanosnavarro+cecila2@gmail.com') or
 (id='04ccf4d1-e0c8-454c-b97f-e006066db7c4' and email='salvadorbolanosnavarro+cecilb2@gmail.com')) <> 2 then
 raise exception 'Staging QA identities do not match; refusing changes'; end if;
 if exists(select 1 from public.wac_numbers where phone_number_id='QA_CECIL_A2_NOT_A_META_ID' and user_id<>'0c823902-41d1-4df2-b357-dedf8d681a38') then
 raise exception 'Fixture belongs to another account'; end if;
end $$;
update public.usuarios set acceso_completo_hasta=greatest(coalesce(acceso_completo_hasta,now()),now()+interval '7 days')
where id in ('0c823902-41d1-4df2-b357-dedf8d681a38','04ccf4d1-e0c8-454c-b97f-e006066db7c4');
insert into public.wac_numbers(user_id,waba_id,waba_name,phone_number_id,display_number,access_token,ai_enabled,identity_prompt)
values('0c823902-41d1-4df2-b357-dedf8d681a38','QA_FAKE_WABA','QA staging, not a real connection','QA_CECIL_A2_NOT_A_META_ID','0000000000','QA_CECIL_INVALID_NOT_A_REAL_TOKEN',false,'Disposable QA fixture. Never deliver.')
on conflict(phone_number_id) do nothing;
commit;
