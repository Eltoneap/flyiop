-- ======================================================================
-- NOTA DE ESTADO - 07/08/2026 (Etapa 4.3, Passo 4)
-- STATUS: PERIGO - NAO RE-RODAR EM HIPOTESE NENHUMA.
-- Em 06/08/2026 (commit ce0d8b3) a coluna weekend_legs.paid_price foi
-- REMOVIDA, junto com price_ceiling, status, notes e purchased_at.
-- Este arquivo executa "alter table weekend_legs add column paid_price
-- numeric;" SEM "if not exists" e SEM guarda. Rodar este script
-- hoje NAO DA ERRO - ele RECRIA a coluna paid_price, vazia, em
-- weekend_legs, ressuscitando em silencio parte do mundo removido. E
-- justamente por nao falhar que ele e perigoso.
-- Onde a verdade vive hoje: weekend_leg_user_state.paid_price, lido pela
-- view weekend_leg_effective.
-- Contexto completo: HISTORICO.md, item 18.
-- ======================================================================

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
