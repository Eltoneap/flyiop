-- ======================================================================
-- NOTA DE ESTADO - 07/08/2026 (Etapa 4.3, Passo 4)
-- STATUS: PERIGO - NAO RE-RODAR EM HIPOTESE NENHUMA.
-- Em 06/08/2026 (commit ce0d8b3) a coluna weekend_legs.notes foi REMOVIDA,
-- junto com price_ceiling, status, paid_price e purchased_at.
-- Este arquivo executa "alter table weekend_legs add column notes text;"
-- SEM "if not exists" e SEM guarda. Rodar este script hoje NAO DA
-- ERRO - ele RECRIA a coluna notes, vazia, em weekend_legs, ressuscitando
-- em silencio parte do mundo removido. E justamente por nao falhar que ele
-- e perigoso.
-- Onde a verdade vive hoje: weekend_leg_user_state.notes, lido pela view
-- weekend_leg_effective.
-- Contexto completo: HISTORICO.md, item 18.
-- ======================================================================

-- Campo de observações livres por perna (localizador, horário etc.), preenchido
-- manualmente no painel de Compras depois da compra. Sem default: vazio até o usuário escrever.
alter table weekend_legs add column notes text;
