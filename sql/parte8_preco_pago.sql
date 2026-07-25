-- Parte 8 (24/07/2026): campo de preço efetivamente pago por perna, editável
-- no painel de Compras depois da compra. Sem default: vazio até o usuário
-- registrar.
alter table weekend_legs add column paid_price numeric;

-- bot_state (key-value, usada hoje só pelo bot do Telegram pra last_update_id)
-- não tinha policy de select rastreada em nenhum sql/*.sql — precisa ficar
-- legível pelo Dashboard pra mostrar "bloqueio recente" (weekend_batch_blocked_at).
-- Idempotente: roda sem erro mesmo se a RLS/policy já existir.
alter table bot_state enable row level security;

drop policy if exists "bot_state_select_authenticated" on bot_state;
create policy "bot_state_select_authenticated"
  on bot_state for select
  using (auth.uid() is not null);
