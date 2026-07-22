-- Etapa 3 do PLAN-FASE-A.md: deduplicação/cooldown de alertas.
-- Rodar no SQL Editor do Supabase ANTES do push do código desta etapa.

create table if not exists alert_log (
  id uuid primary key default gen_random_uuid(),
  route_id uuid not null references routes(id) on delete cascade,
  sent_at timestamptz not null default now(),
  price numeric not null,
  reason text
);

alter table alert_log enable row level security;

-- Mesmo padrão de run_log/price_history: usuário autenticado só lê o
-- histórico de alerta das próprias rotas; o robô grava via service role
-- (que ignora RLS, igual já faz em price_history/run_log).
create policy "alert_log_select_own_routes"
  on alert_log for select
  using (
    route_id in (select id from routes where user_id = auth.uid())
  );

alter table settings
  add column if not exists realert_drop_pct numeric not null default 5;

alter table settings
  add column if not exists realert_days integer not null default 3;
