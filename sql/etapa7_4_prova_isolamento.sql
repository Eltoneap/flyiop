-- ============================================================================
-- Etapa 7, fatia E7-4 — prova de isolamento com as DUAS contas reais.
--
-- Última fatia antes de a credencial do Gustavo ser entregue. Mede, por
-- personificação de CADA conta em transação com ROLLBACK (nenhuma escrita
-- real), as tabelas que nunca tiveram prova de isolamento com conta real
-- (só simulação nos blocos E/F da 4.1):
--   - weekend_leg_user_state  (4 policies auth.uid(), user_id default auth.uid())
--   - weekend_leg_ceiling_audit (wlca_select_own, append-only)
--   - alert_log (ramo de perna — resultado já conhecido pela E7-3: 0 para
--     os dois lados, incluído aqui como registro formal, não nova descoberta)
--   - settings (cada conta deve ver só a própria linha)
--   - weekend_leg_effective, CONTADA POR CONTA (esperado: 132 para cada uma,
--     NÃO 264 — a view devolve 264 sem filtro, mas cada usuário logado no
--     navegador deve ver só as suas 132, via RLS de settings + security_invoker)
--
-- UUID do Gustavo: 2446ec67-06b8-478c-bc5d-6a17eab1fe76 (semeado na E7-2).
-- UUID do usuário principal: c72bf50e-16f7-48fd-9c86-7b49dea1551e (mesmo UUID
-- usado em sql/etapa4_1_verificacao.sql, sql/fatia_d4_avaliacao_por_usuario.sql
-- e sql/etapa7_3_rls_alert_log.sql).
--
-- CRITÉRIO DE APROVAÇÃO — esta é a fatia que, se passar, libera a entrega da
-- credencial ao Gustavo. Se qualquer "de_outro_dono" vier > 0, ou
-- weekend_leg_effective vier 264 em vez de 132 para qualquer uma das contas,
-- a fatia REPROVA — não entregar credencial, investigar antes de seguir.
--
-- NOTA — alert_log: o resultado esperado é 0/0 para os dois lados, já
-- confirmado na E7-3 (histórico órfão, sem dono). Não é uma nova descoberta,
-- é reconfirmação formal nesta fatia.
--
-- NOTA — leitura pura. Nada é escrito; tudo roda em transação com ROLLBACK.
--
-- Personificação: mesmo padrão já usado e validado na E7-3
-- (request.jwt.claims + set local role authenticated). Nenhuma técnica nova.
--
-- EXECUÇÃO: 100% MANUAL, pelo usuário, no SQL Editor do Supabase. Claude
-- Code NÃO executa SQL.
--
-- REGRA DE EXECUÇÃO BLOCO A BLOCO — NÃO COLAR O ARQUIVO INTEIRO DE UMA VEZ:
-- o SQL Editor do Supabase devolve o resultado apenas do ÚLTIMO statement de
-- um bloco múltiplo. BLOCO 1 e BLOCO 2 são EXECUÇÕES SEPARADAS.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- BLOCO 1 — personificação do GUSTAVO. Só leitura sob persona, em transação
-- com ROLLBACK — não altera nada.
--
-- Esperado: de_outro_dono = 0 em todas as tabelas aplicáveis; alert_log
-- pernas_visiveis = 0; weekend_leg_effective = 132.
-- ----------------------------------------------------------------------------
begin;
  set local idle_in_transaction_session_timeout = '30s';
  set local request.jwt.claims = '{"sub":"2446ec67-06b8-478c-bc5d-6a17eab1fe76","role":"authenticated"}';
  set local role authenticated;

  select
    (select count(*) from weekend_leg_user_state) as wlus_total_visivel,
    (select count(*) from weekend_leg_user_state
      where user_id != '2446ec67-06b8-478c-bc5d-6a17eab1fe76') as wlus_de_outro_dono,

    (select count(*) from weekend_leg_ceiling_audit) as wlca_total_visivel,
    (select count(*) from weekend_leg_ceiling_audit
      where user_id != '2446ec67-06b8-478c-bc5d-6a17eab1fe76') as wlca_de_outro_dono,

    (select count(*) from alert_log where leg_id is not null) as alert_log_pernas_visiveis,

    (select count(*) from settings) as settings_total_visivel,
    (select count(*) from settings
      where user_id != '2446ec67-06b8-478c-bc5d-6a17eab1fe76') as settings_de_outro_dono,

    (select count(*) from weekend_leg_effective) as wle_total_visivel;
rollback;


-- ----------------------------------------------------------------------------
-- BLOCO 2 — mesma medição, personificando o USUÁRIO PRINCIPAL. Mesma
-- estrutura, em transação com ROLLBACK.
--
-- Esperado: de_outro_dono = 0 em todas as tabelas aplicáveis; alert_log
-- pernas_visiveis = 0 (reconfirmação da E7-3); weekend_leg_effective = 132
-- (as dele, não as 264 somadas das duas contas).
-- ----------------------------------------------------------------------------
begin;
  set local idle_in_transaction_session_timeout = '30s';
  set local request.jwt.claims = '{"sub":"c72bf50e-16f7-48fd-9c86-7b49dea1551e","role":"authenticated"}';
  set local role authenticated;

  select
    (select count(*) from weekend_leg_user_state) as wlus_total_visivel,
    (select count(*) from weekend_leg_user_state
      where user_id != 'c72bf50e-16f7-48fd-9c86-7b49dea1551e') as wlus_de_outro_dono,

    (select count(*) from weekend_leg_ceiling_audit) as wlca_total_visivel,
    (select count(*) from weekend_leg_ceiling_audit
      where user_id != 'c72bf50e-16f7-48fd-9c86-7b49dea1551e') as wlca_de_outro_dono,

    (select count(*) from alert_log where leg_id is not null) as alert_log_pernas_visiveis,

    (select count(*) from settings) as settings_total_visivel,
    (select count(*) from settings
      where user_id != 'c72bf50e-16f7-48fd-9c86-7b49dea1551e') as settings_de_outro_dono,

    (select count(*) from weekend_leg_effective) as wle_total_visivel;
rollback;
