-- WhatsApp de ChatGPT: storage independiente del módulo legacy.
create table if not exists public.wac_numbers (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  business_id text,
  waba_id text not null,
  waba_name text,
  phone_number_id text not null unique,
  display_number text,
  access_token text not null,
  token_expires_at timestamptz,
  quality_rating text default 'UNKNOWN',
  status text default 'CONNECTED',
  ai_enabled boolean not null default true,
  identity_prompt text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists wac_numbers_user_id_idx on public.wac_numbers(user_id);
create index if not exists wac_numbers_waba_id_idx on public.wac_numbers(waba_id);

alter table public.wac_numbers enable row level security;

drop policy if exists "wac_numbers_owner_select" on public.wac_numbers;
create policy "wac_numbers_owner_select" on public.wac_numbers
  for select using (auth.uid() = user_id);

drop policy if exists "wac_numbers_owner_update" on public.wac_numbers;
create policy "wac_numbers_owner_update" on public.wac_numbers
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
