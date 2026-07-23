-- Alvo Fins de Semana (plano de 22/07/2026): 66 fins de semana RIO<->BSB,
-- de sexta 04/09/2026 a sexta 03/12/2027. Rodar no SQL Editor do Supabase
-- ANTES do push do código que depende dele (Parte 1 do plano).

create table if not exists weekend_targets (
  id uuid primary key default gen_random_uuid(),
  outbound_date date not null unique,
  return_sunday date not null,
  return_monday date not null,
  status text not null default 'monitoring',  -- 'monitoring' | 'purchased'
  price_ceiling numeric not null default 400,
  current_price numeric,
  current_return_variant text,                -- 'sunday' | 'monday'
  current_outbound_airport text,
  current_return_airport text,
  lowest_seen numeric,
  lowest_seen_at timestamptz,
  purchased_at timestamptz,
  created_at timestamptz not null default now()
);

alter table weekend_targets enable row level security;

-- App single-user por design (mesmo padrão documentado em main.py) — não há
-- coluna user_id porque o alvo não pertence a uma rota/usuário específico,
-- é estado global do produto. Qualquer sessão autenticada é a mesma pessoa.
create policy "weekend_targets_select_authenticated"
  on weekend_targets for select
  using (auth.uid() is not null);

create policy "weekend_targets_update_authenticated"
  on weekend_targets for update
  using (auth.uid() is not null)
  with check (auth.uid() is not null);

create table if not exists weekend_price_history (
  id uuid primary key default gen_random_uuid(),
  target_id uuid not null references weekend_targets(id) on delete cascade,
  checked_at timestamptz not null default now(),
  price numeric not null,
  return_variant text not null,
  outbound_airport text,
  return_airport text,
  transfers integer
);

alter table weekend_price_history enable row level security;

create policy "weekend_price_history_select_authenticated"
  on weekend_price_history for select
  using (auth.uid() is not null);

-- alert_log passa a servir os dois mundos (rotas flexíveis e alvos de fim
-- de semana) — route_id vira opcional, target_id é o novo opcional; uma
-- linha sempre tem exatamente uma origem preenchida.
alter table alert_log alter column route_id drop not null;

alter table alert_log
  add column if not exists target_id uuid references weekend_targets(id) on delete cascade;

alter table alert_log
  add constraint alert_log_route_or_target_check
  check (route_id is not null or target_id is not null);

alter table settings
  add column if not exists weekend_opportunity_pct numeric not null default 15;

-- Seed dos 66 alvos (datas geradas programaticamente com assert de dia da
-- semana, conferidas de forma independente pelo usuário em 22/07/2026).
insert into weekend_targets (outbound_date, return_sunday, return_monday) values
  ('2026-09-04', '2026-09-06', '2026-09-07'),
  ('2026-09-11', '2026-09-13', '2026-09-14'),
  ('2026-09-18', '2026-09-20', '2026-09-21'),
  ('2026-09-25', '2026-09-27', '2026-09-28'),
  ('2026-10-02', '2026-10-04', '2026-10-05'),
  ('2026-10-09', '2026-10-11', '2026-10-12'),
  ('2026-10-16', '2026-10-18', '2026-10-19'),
  ('2026-10-23', '2026-10-25', '2026-10-26'),
  ('2026-10-30', '2026-11-01', '2026-11-02'),
  ('2026-11-06', '2026-11-08', '2026-11-09'),
  ('2026-11-13', '2026-11-15', '2026-11-16'),
  ('2026-11-20', '2026-11-22', '2026-11-23'),
  ('2026-11-27', '2026-11-29', '2026-11-30'),
  ('2026-12-04', '2026-12-06', '2026-12-07'),
  ('2026-12-11', '2026-12-13', '2026-12-14'),
  ('2026-12-18', '2026-12-20', '2026-12-21'),
  ('2026-12-25', '2026-12-27', '2026-12-28'),
  ('2027-01-01', '2027-01-03', '2027-01-04'),
  ('2027-01-08', '2027-01-10', '2027-01-11'),
  ('2027-01-15', '2027-01-17', '2027-01-18'),
  ('2027-01-22', '2027-01-24', '2027-01-25'),
  ('2027-01-29', '2027-01-31', '2027-02-01'),
  ('2027-02-05', '2027-02-07', '2027-02-08'),
  ('2027-02-12', '2027-02-14', '2027-02-15'),
  ('2027-02-19', '2027-02-21', '2027-02-22'),
  ('2027-02-26', '2027-02-28', '2027-03-01'),
  ('2027-03-05', '2027-03-07', '2027-03-08'),
  ('2027-03-12', '2027-03-14', '2027-03-15'),
  ('2027-03-19', '2027-03-21', '2027-03-22'),
  ('2027-03-26', '2027-03-28', '2027-03-29'),
  ('2027-04-02', '2027-04-04', '2027-04-05'),
  ('2027-04-09', '2027-04-11', '2027-04-12'),
  ('2027-04-16', '2027-04-18', '2027-04-19'),
  ('2027-04-23', '2027-04-25', '2027-04-26'),
  ('2027-04-30', '2027-05-02', '2027-05-03'),
  ('2027-05-07', '2027-05-09', '2027-05-10'),
  ('2027-05-14', '2027-05-16', '2027-05-17'),
  ('2027-05-21', '2027-05-23', '2027-05-24'),
  ('2027-05-28', '2027-05-30', '2027-05-31'),
  ('2027-06-04', '2027-06-06', '2027-06-07'),
  ('2027-06-11', '2027-06-13', '2027-06-14'),
  ('2027-06-18', '2027-06-20', '2027-06-21'),
  ('2027-06-25', '2027-06-27', '2027-06-28'),
  ('2027-07-02', '2027-07-04', '2027-07-05'),
  ('2027-07-09', '2027-07-11', '2027-07-12'),
  ('2027-07-16', '2027-07-18', '2027-07-19'),
  ('2027-07-23', '2027-07-25', '2027-07-26'),
  ('2027-07-30', '2027-08-01', '2027-08-02'),
  ('2027-08-06', '2027-08-08', '2027-08-09'),
  ('2027-08-13', '2027-08-15', '2027-08-16'),
  ('2027-08-20', '2027-08-22', '2027-08-23'),
  ('2027-08-27', '2027-08-29', '2027-08-30'),
  ('2027-09-03', '2027-09-05', '2027-09-06'),
  ('2027-09-10', '2027-09-12', '2027-09-13'),
  ('2027-09-17', '2027-09-19', '2027-09-20'),
  ('2027-09-24', '2027-09-26', '2027-09-27'),
  ('2027-10-01', '2027-10-03', '2027-10-04'),
  ('2027-10-08', '2027-10-10', '2027-10-11'),
  ('2027-10-15', '2027-10-17', '2027-10-18'),
  ('2027-10-22', '2027-10-24', '2027-10-25'),
  ('2027-10-29', '2027-10-31', '2027-11-01'),
  ('2027-11-05', '2027-11-07', '2027-11-08'),
  ('2027-11-12', '2027-11-14', '2027-11-15'),
  ('2027-11-19', '2027-11-21', '2027-11-22'),
  ('2027-11-26', '2027-11-28', '2027-11-29'),
  ('2027-12-03', '2027-12-05', '2027-12-06')
on conflict (outbound_date) do nothing;
