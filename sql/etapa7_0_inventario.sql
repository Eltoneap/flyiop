-- ============================================================================
-- Etapa 7, fatia E7-0 — Pré-voo (só leitura).
--
-- CONTEXTO: esta é a primeira fatia da Etapa 7 (criação da conta do segundo
-- usuário), que responde os 5 itens registrados em PLANO-ATIVO.md, seção
-- "Etapa 7", subseção "O que a documentação afirma e NÃO foi possível
-- confirmar". São gates de LEITURA, não pendências soltas — a E7-2 (a conta +
-- a linha de settings) não roda sem os 5 números aqui registrados.
--
-- ----------------------------------------------------------------------------
-- OVERRIDE DO GATE DA D4, REGISTRADO AQUI DE PROPÓSITO (decisão de 15/08/2026).
--
-- O texto do commit c27c7fd (PLANO-ATIVO.md, seção "Etapa 7") condiciona o
-- início desta etapa à confirmação do item 5 da verificação pós-deploy da D4
-- ("a próxima linha de PERNA em alert_log nasce com user_id PREENCHIDO"), a
-- ser conferido no log da execução de ~08h BRT de 16/08/2026. NO MOMENTO EM
-- QUE ESTE SCRIPT FOI ESCRITO, esse log AINDA NÃO FOI CONFERIDO.
--
-- O usuário decidiu explicitamente, no chat de planejamento de 15/08/2026,
-- seguir com a E7-0 mesmo assim — um OVERRIDE CONSCIENTE do próprio gate que
-- ele mesmo registrou no commit anterior. Justificativa: a E7-0 é SOMENTE
-- LEITURA — nada é criado, nada é alterado, nenhuma escrita em alert_log,
-- nenhuma conta é criada. Não há como a E7-0 sofrer o defeito que o gate
-- existe para prevenir (ela não grava nada em alert_log).
--
-- ISTO NÃO É "GATE CUMPRIDO". É um override datado, registrado como tal. A
-- EXCEÇÃO DO GATE CONTINUA VALENDO INTEGRALMENTE: se o log da execução de
-- 16/08/2026 mostrar o item 5 com defeito real (user_id NULL numa linha nova
-- de perna, erro de gravação, traceback), a Etapa 7 PAUSA antes de prosseguir
-- — e, nesse cenário, o resultado desta E7-0 NÃO autoriza seguir para a E7-1
-- ou adiante. Rodar este script não é decisão de avançar a etapa; é só
-- levantamento de terreno que precisa existir de qualquer forma antes da E7-2.
-- ----------------------------------------------------------------------------
--
-- ESCOPO: SOMENTE LEITURA. Nenhum insert/update/delete/create/alter/drop em
-- nenhum bloco. Onde uma consulta precisar de transação (personificação de
-- papel), usa-se `begin ... rollback`, mesmo padrão da D3/D4.
--
-- EXECUÇÃO: 100% MANUAL, pelo usuário, no SQL Editor do Supabase. Claude Code
-- NÃO executa SQL.
--
-- REGRA DE EXECUÇÃO BLOCO A BLOCO — NÃO COLAR O ARQUIVO INTEIRO DE UMA VEZ:
-- o SQL Editor do Supabase devolve o resultado apenas do ÚLTIMO statement de
-- um bloco múltiplo. Rodar tudo junto DESCARTA silenciosamente o resultado de
-- todos os blocos menos o último. Cada bloco lógico abaixo (Q1..Q5) é UMA
-- EXECUÇÃO SEPARADA — rodar, ler o resultado, colar no PLANO-ATIVO.md na
-- seção E7-0, e só então avançar para o próximo bloco.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- Q1 — DDL real de `settings`: todas as colunas, tipo, nullable, default vivo.
--
-- Responde de uma vez:
--   (a) o default vivo de weekend_default_ceiling é mesmo 250?
--   (b) quais colunas são nullable SEM default (alimentam a lista de
--       semeadura explícita da E7-2 — PLANO-ATIVO.md, fatia E7-2, "o insert
--       semeia TODAS as colunas de settings explicitamente")?
--   (c) display_name existe e é nullable, como a D4 registrou
--       (sql/fatia_d4_avaliacao_por_usuario.sql:19)?
--
-- Sem valor fixo a bater — é inventário. Ler linha a linha contra a lista já
-- nomeada em PLANO-ATIVO.md (fatia E7-2): window_3d_pct, window_7d_pct,
-- notification_mode, cost_per_thousand_brl, freshness_hours,
-- stale_alert_policy, realert_drop_pct, realert_days,
-- weekend_opportunity_pct, weekend_default_ceiling, display_name, user_id.
-- Qualquer coluna aqui que NÃO esteja nessa lista é achado a registrar.
-- ----------------------------------------------------------------------------
select
  column_name,
  data_type,
  is_nullable,
  column_default
  from information_schema.columns
 where table_schema = 'public'
   and table_name = 'settings'
 order by ordinal_position;


-- ----------------------------------------------------------------------------
-- Q2 — Constraints de `settings`: PK, unique, FK.
--
-- >>> GATE DE PARADA — AUSÊNCIA de unique em user_id (isolado ou como parte
--     da PK) => PARE, não avançar para a E7-2 sem resolver antes.
--     Motivo: os `upsert` do painel (docs/js/config.js:243/263,
--     docs/js/compras.js:836) dependem de um alvo de conflito único em
--     user_id. Sem ele, um upsert pode criar LINHA DUPLICADA para o mesmo
--     usuário — e linha duplicada não dobra a view (PLANO-ATIVO.md, Etapa 7,
--     item 2 da tabela "o que dobra"), ela TRIPLICA: cross join settings
--     (sql/etapa4_1_estado_por_usuario.sql:415) contra 132 pernas, com 3
--     linhas de settings (1 do Elton + 2 duplicadas do Gustavo), devolveria
--     396, não 264.
-- ----------------------------------------------------------------------------
select
  tc.constraint_name,
  tc.constraint_type,
  kcu.column_name,
  ccu.table_name  as referenced_table,
  ccu.column_name as referenced_column
  from information_schema.table_constraints tc
  left join information_schema.key_column_usage kcu
    on kcu.constraint_name = tc.constraint_name
   and kcu.table_schema = tc.table_schema
  left join information_schema.constraint_column_usage ccu
    on ccu.constraint_name = tc.constraint_name
   and ccu.table_schema = tc.table_schema
 where tc.table_schema = 'public'
   and tc.table_name = 'settings'
 order by tc.constraint_type, tc.constraint_name;


-- ----------------------------------------------------------------------------
-- Q3 — Default de `routes.user_id`.
--
-- Registrado em PLANO-ATIVO.md (Etapa 7, "O que a documentação afirma e NÃO
-- foi possível confirmar", item 3) como nunca verificado: o insert do painel
-- não manda o dono (docs/js/config.js:215-224), então se não existir
-- `default auth.uid()`, um insert feito pelo Gustavo nasceria com user_id
-- NULL. Só importa se o Gustavo for cadastrar rota flexível (sistema legado)
-- — barato de conferir agora, sem gate de parada associado.
-- ----------------------------------------------------------------------------
select
  column_name,
  data_type,
  is_nullable,
  column_default
  from information_schema.columns
 where table_schema = 'public'
   and table_name = 'routes'
   and column_name = 'user_id';


-- ----------------------------------------------------------------------------
-- Q4 — `alert_log`: contagens e marca d'água da D3.
--
-- Reconfere os números de 14-15/08/2026 (54 NULL / 78 linhas) registrados em
-- PLANO-ATIVO.md e mede o custo real de apertar a RLS do ramo de perna na
-- E7-3 (quantas linhas ficariam invisíveis à API autenticada, permanecendo
-- acessíveis pelo SQL Editor porque o dono ignora RLS).
--
-- Números MAIORES que 54/78 são crescimento esperado (robô roda 2x/dia,
-- ~1-3 linhas/dia) — não é erro. O que importa registrar é a estrutura:
-- quantas linhas de perna (leg_id not null) têm user_id NULL, e a marca
-- d'água exata das linhas anteriores ao deploy da D3.
-- ----------------------------------------------------------------------------
select
  (select count(*) from alert_log)                                          as total_linhas,
  (select count(*) from alert_log where user_id is null)                    as total_user_id_null,
  (select count(*) from alert_log where leg_id is not null)                 as total_linhas_de_perna,
  (select count(*) from alert_log
    where leg_id is not null and user_id is null)                          as linhas_de_perna_user_id_null,
  (select max(sent_at) from alert_log
    where sent_at < '2026-08-14 11:37:28.822753+00')                       as marca_dagua_d3;


-- ----------------------------------------------------------------------------
-- Q5 — Linha de base: contagem atual de `settings` e de `weekend_leg_effective`.
--
-- ESPERADO: 1 e 132. É a linha de base contra a qual a E7-2 vai medir
-- (esperado depois da E7-2: 2 e 264 — PLANO-ATIVO.md, fatia E7-2,
-- "Concluída quando").
-- ----------------------------------------------------------------------------
select
  (select count(*) from settings)                as linhas_settings,
  (select count(*) from weekend_leg_effective)    as linhas_efetivas;
