-- STAGING ONLY: tymhlvawnqadqgwnpruk. Never apply to production.
begin;
do $$ begin
 if not exists(select 1 from public.usuarios where id='bd7e565d-c0c7-46d1-9cc2-70399ed97a91' and email='salvadorbolanosnavarro+cecila3@gmail.com') then
 raise exception 'Expected staging A3 identity missing'; end if;
end $$;
create table if not exists public.cecil_staging_pilot (
 user_id uuid primary key references auth.users(id) on delete cascade,
 enabled boolean not null default false,
 updated_at timestamptz not null default now()
);
alter table public.cecil_staging_pilot enable row level security;
revoke all on public.cecil_staging_pilot from anon, authenticated;
grant select on public.cecil_staging_pilot to authenticated;
drop policy if exists cecil_pilot_read_own on public.cecil_staging_pilot;
create policy cecil_pilot_read_own on public.cecil_staging_pilot for select to authenticated using ((select auth.uid())=user_id);
create table if not exists public.cecil_staging_error_receipts (
 event_id uuid primary key,
 user_id uuid not null references auth.users(id) on delete cascade,
 sentry_accepted boolean not null,
 created_at timestamptz not null default now()
);
alter table public.cecil_staging_error_receipts enable row level security;
revoke all on public.cecil_staging_error_receipts from anon, authenticated;
grant select,insert on public.cecil_staging_error_receipts to authenticated;
drop policy if exists cecil_error_read_own on public.cecil_staging_error_receipts;
create policy cecil_error_read_own on public.cecil_staging_error_receipts for select to authenticated using ((select auth.uid())=user_id);
drop policy if exists cecil_error_insert_own on public.cecil_staging_error_receipts;
create policy cecil_error_insert_own on public.cecil_staging_error_receipts for insert to authenticated with check (
 (select auth.uid())=user_id and exists(select 1 from public.cecil_staging_pilot where user_id=(select auth.uid()) and enabled)
);
insert into public.cecil_staging_pilot(user_id,enabled) values('bd7e565d-c0c7-46d1-9cc2-70399ed97a91',true) on conflict(user_id) do update set enabled=excluded.enabled,updated_at=now();
commit;
