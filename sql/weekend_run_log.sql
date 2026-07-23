-- weekend_run_log: mesmo padrão do run_log das rotas flexíveis, mas por
-- alvo de fim de semana — visibilidade de "tentei e não achei" sem precisar
-- copiar log do GitHub Actions. Rodar no SQL Editor ANTES do push do código.

create table if not exists weekend_run_log (
  id uuid primary key default gen_random_uuid(),
  target_id uuid not null references weekend_targets(id) on delete cascade,
  ran_at timestamptz not null default now(),
  outcome text not null,  -- 'ok' | 'no_data' | 'error'
  price numeric,
  detail text
);

alter table weekend_run_log enable row level security;

create policy "weekend_run_log_select_authenticated"
  on weekend_run_log for select
  using (auth.uid() is not null);
