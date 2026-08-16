-- ============================================================================
-- Etapa 7, fatia E7-3 (D-7) — aperto da RLS de alert_log no ramo de perna.
--
-- CONTEXTO: a policy viva hoje, alert_log_select_own_routes_or_any_leg
-- (sql/draft_alert_log_leg_policy.sql), cobre dois ramos:
--   - rota:  route_id is not null and route_id in (select id from routes
--            where user_id = auth.uid())           -- já filtra por dono
--   - perna: leg_id is not null and auth.uid() is not null
--            -- qualquer autenticado lê QUALQUER linha de perna (vazamento)
--
-- Esta fatia troca só o ramo de perna para user_id = auth.uid(). O ramo de
-- rota fica INALTERADO — ele serve de controle negativo na verificação: se
-- os números de rota mudarem entre antes/depois, a policy quebrou algo que
-- não devia ter sido tocado.
--
-- grep alert_log docs/ já confirmado como zero consumidores de frontend —
-- custo de apertar é baixo, mas a verificação de dois ramos continua
-- obrigatória (medir só perna deixaria o ramo de rota sem controle).
--
-- NOTA — robô: usa service_role, que ignora RLS. Esta fatia não o afeta.
--
-- NOTA — reversão manual: recriar a policy anterior. SQL exato no
-- comentário do BLOCO 2.
--
-- NOTA — 55 linhas históricas de perna com user_id NULL: somem da leitura
-- autenticada depois desta fatia (não têm dono que bata com auth.uid()).
-- Continuam acessíveis via SQL Editor, porque o dono do banco ignora RLS.
--
-- Verificação por PERSONIFICAÇÃO DA CONTA REAL do Gustavo (não mais de
-- usuário fictício — correção registrada no plano: a policy cobre dois
-- ramos, medir só perna deixaria o ramo de rota sem controle negativo).
-- UUID do Gustavo: 2446ec67-06b8-478c-bc5d-6a17eab1fe76 (semeado na E7-2).
-- UUID do usuário principal: c72bf50e-16f7-48fd-9c86-7b49dea1551e (mesmo
-- UUID usado em sql/etapa4_1_verificacao.sql e sql/fatia_d4_avaliacao_por_usuario.sql).
--
-- EXECUÇÃO: 100% MANUAL, pelo usuário, no SQL Editor do Supabase. Claude
-- Code NÃO executa SQL.
--
-- REGRA DE EXECUÇÃO BLOCO A BLOCO — NÃO COLAR O ARQUIVO INTEIRO DE UMA VEZ:
-- o SQL Editor do Supabase devolve o resultado apenas do ÚLTIMO statement de
-- um bloco múltiplo. BLOCO 1, BLOCO 2, BLOCO 3 e BLOCO 4 são EXECUÇÕES
-- SEPARADAS.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- BLOCO 1 — medição ANTES, por personificação do Gustavo. Só leitura sob
-- persona, em transação com ROLLBACK — não altera nada.
--
-- Esperado ramo de perna (ANTES): todas as linhas de perna (vazamento —
-- Gustavo enxerga pernas que não são dele).
-- Esperado ramo de rota (ANTES): comportamento normal — é o controle,
-- registre o número, não precisa ser um valor específico.
-- ----------------------------------------------------------------------------
begin;
  set local idle_in_transaction_session_timeout = '30s';
  set local request.jwt.claims = '{"sub":"2446ec67-06b8-478c-bc5d-6a17eab1fe76","role":"authenticated"}';
  set local role authenticated;

  select
    (select count(*) from alert_log where leg_id is not null)   as pernas_visiveis_antes,
    (select count(*) from alert_log where route_id is not null) as rotas_visiveis_antes;
rollback;


-- ----------------------------------------------------------------------------
-- BLOCO 2 — a alteração da policy. Ramo de perna troca para
-- user_id = auth.uid(). Ramo de rota INALTERADO.
-- ----------------------------------------------------------------------------
drop policy if exists "alert_log_select_own_routes_or_any_leg" on alert_log;

create policy "alert_log_select_own_routes_or_own_leg"
  on alert_log for select
  using (
    (route_id is not null and route_id in (select id from routes where user_id = auth.uid()))
    or (leg_id is not null and user_id = auth.uid())
  );

-- ROLLBACK MANUAL (só se a medição "depois" não bater) — recria a policy
-- anterior, exatamente como estava em sql/draft_alert_log_leg_policy.sql:
--
-- drop policy if exists "alert_log_select_own_routes_or_own_leg" on alert_log;
--
-- create policy "alert_log_select_own_routes_or_any_leg"
--   on alert_log for select
--   using (
--     (route_id is not null and route_id in (select id from routes where user_id = auth.uid()))
--     or (leg_id is not null and auth.uid() is not null)
--   );


-- ----------------------------------------------------------------------------
-- BLOCO 3 — medição DEPOIS, mesmo padrão do BLOCO 1, mesma personificação
-- do Gustavo, em transação com ROLLBACK.
--
-- Esperado ramo de perna (DEPOIS): 0 — Gustavo não tem linha de perna
-- própria ainda, nunca alertou.
-- Esperado ramo de rota (DEPOIS): MESMO NÚMERO do BLOCO 1 — controle
-- negativo; se mudou, a policy quebrou o ramo de rota.
-- ----------------------------------------------------------------------------
begin;
  set local idle_in_transaction_session_timeout = '30s';
  set local request.jwt.claims = '{"sub":"2446ec67-06b8-478c-bc5d-6a17eab1fe76","role":"authenticated"}';
  set local role authenticated;

  select
    (select count(*) from alert_log where leg_id is not null)   as pernas_visiveis_depois,
    (select count(*) from alert_log where route_id is not null) as rotas_visiveis_depois;
rollback;


-- ----------------------------------------------------------------------------
-- BLOCO 4 — verificação adicional, personificando o USUÁRIO PRINCIPAL (não
-- o Gustavo), mesma técnica, em transação com ROLLBACK. Confirma que a
-- nova policy não quebrou a leitura própria: o usuário principal ainda
-- enxerga as linhas de perna com user_id = auth.uid() dele.
-- ----------------------------------------------------------------------------
begin;
  set local idle_in_transaction_session_timeout = '30s';
  set local request.jwt.claims = '{"sub":"c72bf50e-16f7-48fd-9c86-7b49dea1551e","role":"authenticated"}';
  set local role authenticated;

  select
    (select count(*) from alert_log where leg_id is not null)   as pernas_visiveis_dono,
    (select count(*) from alert_log where route_id is not null) as rotas_visiveis_dono;
rollback;
