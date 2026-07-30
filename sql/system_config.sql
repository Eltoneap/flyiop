-- Etapa 3 multi-usuário: config de sistema separada de settings (per-user).
-- Rodar manualmente no SQL Editor do Supabase ANTES de subir o código.
create table if not exists system_config (
  id smallint primary key default 1 check (id = 1),
  suspicious_below_avg_pct numeric not null default 50,
  fast_flights_enabled boolean not null default true,
  fast_flights_daily_batch_size integer not null default 20,
  updated_at timestamptz not null default now()
);
alter table system_config enable row level security;
drop policy if exists "system_config_select_authenticated" on system_config;
create policy "system_config_select_authenticated"
  on system_config for select
  using (auth.uid() is not null);
insert into system_config (id, suspicious_below_avg_pct, fast_flights_enabled,
                           fast_flights_daily_batch_size)
values (1, 50, true, 20)
on conflict (id) do nothing;
