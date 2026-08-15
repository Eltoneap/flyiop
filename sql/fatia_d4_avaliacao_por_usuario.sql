-- ============================================================================
-- Fatia D4 — avaliação por usuário (banco).
--
-- CONTEXTO: esta é a última fatia da Etapa 6. A D4 aposenta o MIN de teto em
-- weekends.resolve_effective_leg_state (regra provisória da Etapa 4.2, marcada
-- como tal no próprio código, src/weekends.py:165-169), individualiza os
-- limiares hoje escolhidos por menor user_id (src/main.py:357) e faz a mensagem
-- do Telegram identificar quem disparou. Com isso fecha a "JANELA ABERTA 2"
-- (PLANO-ATIVO.md, Etapa 4.2).
--
-- ESCOPO DESTA PARTE: só o banco, e o banco quase não muda. A D4 é uma fatia de
-- CÓDIGO — o achado que a barateou é que o user_id JÁ CHEGA hoje em toda linha
-- de weekend_leg_effective (src/supabase_client.py:275 seleciona user_id) e é
-- descartado por resolve_effective_leg_state, que lê só leg_id, status e
-- price_ceiling (src/weekends.py:176,181,184). NÃO é preciso view nova, grant
-- novo nem mudança de RLS para ter o dono em mãos no ponto de avaliação.
--
-- Portanto, a ÚNICA mudança de schema desta fatia é uma coluna de rótulo:
--   settings.display_name (text, nullable) — o nome que aparece na mensagem.
-- Fallback no Python quando ausente: 8 primeiros caracteres do uuid. A mensagem
-- nunca quebra por falta de nome.
--
-- O QUE ESTA FATIA NÃO FAZ, e são decisões FECHADAS (não pendências):
--   * Índice de alert_log: NÃO recriar. A D2 previu (leg_id, user_id, sent_at
--     desc) para a D3; a D3 revisou e passou a decisão para cá. DECIDIDO: fica
--     alert_log_leg_sent_at_idx (leg_id, sent_at desc), de
--     sql/fatia_d2_tipo_de_alerta.sql:224. Motivo: 78 linhas na marca d'água da
--     D3, crescendo 1-3/dia; leg_id já é a coluna seletiva. GATILHO DE REVISÃO:
--     quando alert_log chegar à ordem de DEZENAS DE MILHARES de linhas (ritmo
--     atual: ordem de anos). Até lá isto não é pendência. O bloco G0-Q5 prova
--     que a D4 não tocou no índice.
--   * RLS do ramo de perna em alert_log: NÃO apertar aqui. Depois da D4 o
--     predicado user_id = auth.uid() passa a ser EXPRESSÁVEL pela primeira vez
--     (linha de perna nova nasce com dono), mas continua NÃO VERIFICÁVEL:
--     alert_log não tem consumidor fora do robô (grep em docs/ → zero; o robô
--     usa service_role, que ignora RLS) e provar isolamento exige 2 contas.
--     Apertar agora ainda esconderia as 54 linhas históricas com user_id NULL.
--     ENDEREÇO: item NOMEADO da Etapa 7 (criação da 2ª conta). Não é pendência
--     solta e não deve reaparecer como "pendente" em fatia intermediária.
--
-- ----------------------------------------------------------------------------
-- SEM REVOKE E SEM GRANT — E O MOTIVO É DE FATO, NÃO DE ESTILO.
--
-- A regra do projeto "todo objeto novo em public nasce com privilégio total
-- para anon" (sql/fatia_c_visibilidade_compra.sql:191-193;
-- sql/etapa4_4_weekend_legs_readonly.sql:95-96) vale para OBJETO novo — tabela,
-- view. NÃO vale para COLUNA nova em tabela pré-existente, e o script da D3 já
-- registrou isso por escrito (sql/fatia_d3_user_id_alert_log.sql:383-387):
-- "Adicionar coluna não cria objeto novo nem concede privilégio (privilégio é
-- de TABELA em Postgres)".
--
-- Pior que inútil: em Postgres NÃO SE SUBTRAI uma coluna de um grant dado no
-- nível da tabela. `revoke ... (display_name) on settings from anon` executa
-- sem erro (no máximo um aviso de que nada pôde ser revogado) e NÃO restringe
-- nada — settings já tem privilégio de tabela para anon/authenticated, padrão
-- de fábrica do Supabase. Um bloco desses deixaria no repositório uma GARANTIA
-- FALSA, com verificação "passando", enquanto o acesso continua idêntico. É a
-- versão pior do cuidado que a D3 teve ao registrar que `on delete set null`
-- era declaração de intenção e não garantia.
--
-- EM VEZ DE REVOGAR: MEDIR ANTES (G0-Q5 e G0-Q6) e PROVAR IGUALDADE DEPOIS
-- (V2, esperado literal "idêntico ao G0, campo a campo"). O V3 registra por
-- escrito por que has_column_privilege devolve true, para ninguém ler esse
-- true no futuro como regressão.
--
-- A barreira real é a RLS de settings, que é per-user
-- (sql/etapa4_1_estado_por_usuario.sql:377-378) e foi confirmada por
-- personificação em 08/08/2026 (STATE.md, seção 2). É o que G0-Q6 mede.
--
-- Se um dia isolamento por coluna for mesmo necessário (anotado, não feito): o
-- único mecanismo que funciona é revogar o privilégio no NÍVEL DA TABELA e
-- re-conceder coluna a coluna — o que quebra a cada coluna nova que alguém
-- acrescentar e ninguém vai lembrar. Para um rótulo de nome, desproporcional.
--
-- ----------------------------------------------------------------------------
-- RESSALVA HONESTA SOBRE O ESTADO DA D3 (registrada aqui de propósito).
--
-- A Fatia D3 foi liberada com o ITEM 4 da verificação pós-deploy NÃO OBSERVADO:
--   * A evidência de 14/08/2026 08:37 BRT é ANTERIOR ao deploy da D3 — o SQL da
--     D3 rodou às 22:03 BRT do mesmo dia.
--   * A consulta de alert_log por linhas de ROTA posteriores à marca d'água
--     (2026-08-14 11:37:28.822753+00) voltou VAZIA em 15/08/2026: nenhuma linha
--     de rota nasceu desde o deploy.
--   * Ou seja: a gravação de user_id em linha de ROTA NUNCA FOI OBSERVADA em
--     produção.
--   * Os itens 5 (linha de perna nascendo com user_id NULL) e 6 (had_error não
--     disparou) FORAM confirmados, com disparo real em 15/08/2026.
--
-- CONSEQUÊNCIA DIRETA PARA A D4: se existir defeito na montagem do payload com
-- user_id, ele vai se manifestar AQUI, no caminho de PERNA, e não terá sido
-- pego antes pelo caminho de rota. O caminho de rota não serviu de ensaio. Isso
-- eleva a importância do item 4 da verificação pós-deploy desta fatia (linha de
-- perna nova com user_id PREENCHIDO) — é a primeira observação real da gravação
-- de dono em alert_log, e não uma confirmação de algo que já se viu funcionar.
--
-- ----------------------------------------------------------------------------
-- EXECUÇÃO: 100% MANUAL, pelo usuário, no SQL Editor do Supabase — mesmo fluxo
-- dos scripts anteriores desta iniciativa. Claude Code NÃO executa SQL.
--
-- REGRA DE EXECUÇÃO BLOCO A BLOCO — NÃO COLAR O ARQUIVO INTEIRO DE UMA VEZ:
-- o SQL Editor do Supabase devolve o resultado apenas do ÚLTIMO statement de um
-- bloco múltiplo. Rodar tudo junto DESCARTA silenciosamente o resultado de todos
-- os G0 menos o último — que é justamente o que este script existe para medir.
-- Cada bloco lógico abaixo (G0-Q1, G0-Q2, ..., BLOCO 1, V1, V2-A, V2-B, V3) é
-- UMA EXECUÇÃO SEPARADA, com o resultado conferido contra o ESPERADO declarado
-- logo acima dele ANTES de avançar para o próximo.
--
-- ORDEM DE DEPLOY: SQL primeiro, código depois. A janela é a mais folgada das
-- quatro fatias, nos DOIS sentidos:
--   * SQL feito, código velho no ar: nada acontece. O código velho não conhece
--     display_name; a coluna fica inerte.
--   * Ordem invertida por acidente (código novo, SQL não rodado): também não
--     quebra. get_all_settings usa select=* (src/supabase_client.py:69), então a
--     chave simplesmente não vem, .get("display_name") devolve None e o fallback
--     entra — a mensagem sai com os 8 caracteres do uuid. É o fallback fazendo o
--     trabalho dele, não degradação.
-- O que realmente muda comportamento é o deploy do CÓDIGO, e na primeira
-- execução seguinte: o re-alerta único da transição de cooldown por usuário, do
-- tamanho exato medido em G0-Q4. Não é defeito — é a transição prevista.
--
-- IDEMPOTENTE E RE-RODÁVEL: `add column if not exists` no BLOCO 1 e guarda
-- `display_name is null` no update.
--
-- RECEITA DE REVERSÃO:
--   alter table settings drop column if exists display_name;
--   (seguro com o código novo no ar ou fora dele: a coluna some do select=* e o
--    fallback de uuid[:8] assume, sem erro. Diferente da D3, aqui não existe
--    caminho de insert que mande a coluna — display_name é só LIDO pelo robô.)
-- ============================================================================


-- ----------------------------------------------------------------------------
-- BLOCO G0 — Guarda de inventário, SÓ LEITURA. Confirma o estado ANTES de agir,
-- para não operar sobre suposição. Seis execuções separadas (Q1..Q6).
--
-- RESSALVA DE CRESCIMENTO ORGÂNICO (mesmo padrão da D3,
-- sql/fatia_d3_user_id_alert_log.sql:128-132): o robô roda 2x/dia e grava ~1-3
-- linhas por dia em alert_log. Números MAIORES que os declarados nos contadores
-- de alert_log são crescimento esperado, não erro. O que tem de bater sempre é
-- a ESTRUTURA e os três GATES marcados abaixo.
--
-- OS TRÊS GATES DESTE SCRIPT (qualquer um = PARE, não avance para o BLOCO 1):
--   G0-Q2  usuarios_distintos    > 1  -> PARE
--   G0-Q2  linhas_sem_teto       > 0  -> PARE
--   G0-Q6  linhas_settings_vistas> 0  -> PARE
-- ----------------------------------------------------------------------------


-- ----------------------------------------------------------------------------
-- G0-Q1 — registro de usuários, e o user_id que o BLOCO 1 vai usar.
--
-- ESPERADO:
--   usuarios_settings         = 1
--   user_ids                  = c72bf50e-16f7-48fd-9c86-7b49dea1551e
--                               (sql/etapa4_1_estado_por_usuario.sql:36)
--   contas_auth               = 1
--   coluna_display_name_existe= false   (a coluna ainda não existe)
--   colunas_settings          — inventário, sem valor fixo a bater; serve para
--                               registrar o "antes" e confirmar que NÃO existe
--                               nenhuma coluna de nome/rótulo hoje.
--
-- ANOTAR O user_ids: é o valor que vai no update do BLOCO 1. Se divergir do
-- literal escrito lá, corrigir o BLOCO 1 — não rodar às cegas.
-- ----------------------------------------------------------------------------
select
  (select count(*) from settings)                                          as usuarios_settings,
  (select string_agg(user_id::text, ',' order by user_id) from settings)   as user_ids,
  (select count(*) from auth.users)                                        as contas_auth,
  exists (select 1 from information_schema.columns
           where table_schema='public' and table_name='settings'
             and column_name='display_name')                               as coluna_display_name_existe,
  (select string_agg(column_name, ',' order by column_name)
     from information_schema.columns
    where table_schema='public' and table_name='settings')                 as colunas_settings;


-- ----------------------------------------------------------------------------
-- G0-Q2 — granularidade da view, e DOIS GATES.
--
-- ESPERADO: 132 / 1 / 132 / 132 / 132 / 0
--   linhas_efetivas    = 132   (PLANO-ATIVO.md, G0 da D3: linhas_efetivas = 132)
--   usuarios_distintos = 1
--   pernas_distintas   = 132
--   pernas_total       = 132
--   linhas_monitoring  = 132
--   linhas_sem_teto    = 0
--
-- >>> GATE 1 — usuarios_distintos > 1  =>  PARE.
--     A fatia deixou de ser testável com uma conta só; o fan-out passa a ter
--     efeito real em produção no mesmo deploy. Leve ao chat de planejamento
--     antes de qualquer coisa.
--
-- >>> GATE 2 — linhas_sem_teto > 0  =>  PARE.
--     Hoje esse 0 é garantido por CONSTRAINT, não por sorte: price_ceiling da
--     view é coalesce(st.price_ceiling, s.weekend_default_ceiling)
--     (sql/etapa4_1_estado_por_usuario.sql:397) e weekend_default_ceiling é
--     `numeric NOT NULL default 250` (:87) — não há como resolver NULL enquanto
--     a linha de settings existir. Se vier > 0, a garantia caiu: existe usuário
--     monitorando SEM teto.
--     Por que isso é um gate e não uma curiosidade: o marcador do modo degradado
--     do código novo é "dict de tetos vazio", e ele só é inequívoco porque a
--     regra de chaveamento mantém como chave o usuário que monitora SEM teto
--     (valor None). Com linhas_sem_teto > 0, o desenho continua correto, mas
--     passa a depender inteiramente de essa regra ter sido implementada certa —
--     e isso precisa ser reconferido no plano ANTES do deploy, não depois.
-- ----------------------------------------------------------------------------
select
  (select count(*) from weekend_leg_effective)                              as linhas_efetivas,
  (select count(distinct user_id) from weekend_leg_effective)               as usuarios_distintos,
  (select count(distinct leg_id) from weekend_leg_effective)                as pernas_distintas,
  (select count(*) from weekend_legs)                                       as pernas_total,
  (select count(*) from weekend_leg_effective where status='monitoring')    as linhas_monitoring,
  (select count(*) from weekend_leg_effective where price_ceiling is null)  as linhas_sem_teto;


-- ----------------------------------------------------------------------------
-- G0-Q3 — limiares por usuário: exatamente o que a D4 individualiza.
--
-- ESPERADO: 1 linha, com
--   user_id                 = c72bf50e-16f7-48fd-9c86-7b49dea1551e
--   weekend_opportunity_pct = 15    (default do projeto)
--   realert_drop_pct        = 5
--   realert_days            = 1     (STATE.md, seção 3, item 1a — ajustado em
--                                    produção em 01/08/2026; NÃO é o default 3)
--   notification_mode       = alert_only
--   weekend_default_ceiling = 300   (STATE.md, seção 2 — recalibrado 04-05/08/2026
--                                    e provado em produção em 06/08/2026)
--   stale_alert_policy      = warn
--   freshness_hours         = 24
--
-- >>> ATENÇÃO — notification_mode = 'daily_summary' aqui é PARADA para conversa,
--     não gate automático. Motivo: por src/rules.py:80-81, 'daily_summary' faz
--     cooldown_blocks_alert retornar False SEMPRE, ou seja DESLIGA o cooldown de
--     perna e o usuário passa a receber MAIS alertas, não menos. É semântica
--     invertida, é bug PRÉ-EXISTENTE e está explicitamente FORA do escopo da D4
--     (a D4 individualiza a LEITURA da coluna, não corrige a semântica). Se o
--     valor em produção for 'daily_summary', a leitura da verificação pós-deploy
--     muda — registrar antes, não descobrir depois.
--
-- ANOTAR realert_days: é o insumo do G0-Q4.
-- ----------------------------------------------------------------------------
select user_id,
       weekend_opportunity_pct,
       realert_drop_pct,
       realert_days,
       notification_mode,
       weekend_default_ceiling,
       stale_alert_policy,
       freshness_hours
  from settings
 order by user_id;


-- ----------------------------------------------------------------------------
-- G0-Q4 — TAMANHO EXATO DA EXPOSIÇÃO DA TRANSIÇÃO DE COOLDOWN.
--
-- O QUE ESTE NÚMERO SIGNIFICA: o cooldown de perna passa a filtrar por usuário.
-- As 54 linhas históricas de perna têm user_id NULL e ficam INVISÍVEIS a esse
-- filtro — decisão tomada (predicado simples e permanente; NÃO usar
-- `user_id = U or user_id is null`, que casaria com dado de outra era: aquelas
-- linhas são do usuário real, gravadas antes de a coluna existir).
-- Consequência aceita: cada (perna, tipo) listado aqui pode render UM alerta
-- duplicado, UMA vez, na primeira execução após o deploy do código.
--
-- ESPERADO com realert_days = 1: números baixos, ordem de 0 a 3
-- (~30 alertas em 14 dias, STATE.md seção 2). Não há valor fixo a bater.
--
-- ANOTAR OS TRÊS NÚMEROS: são a PREVISÃO a conferir na verificação pós-deploy
-- (item 2 da lista de verificação). Observado muito acima do previsto = investigar.
--
-- Nota sobre o `limit 1`: com 1 usuário é exato. Com mais de um seria ambíguo —
-- mas o GATE 1 do G0-Q2 já teria parado a execução antes de chegar aqui.
-- ----------------------------------------------------------------------------
with cfg as (
  select realert_days from settings order by user_id limit 1
)
select
  (select realert_days from cfg)                                      as realert_days_vigente,
  count(distinct a.leg_id) filter (where a.is_ceiling_alert)          as pernas_expostas_teto,
  count(distinct a.leg_id) filter (where a.is_opportunity_alert)      as pernas_expostas_oportunidade,
  count(*)                                                            as linhas_na_janela
  from alert_log a, cfg
 where a.leg_id is not null
   and a.sent_at >= now() - (cfg.realert_days || ' days')::interval;


-- ----------------------------------------------------------------------------
-- G0-Q5 — POSTURA DE ACESSO de alert_log e settings. LINHA DE BASE DO V2.
--
-- ESPERADO:
--   indices_alert_log          = alert_log_leg_sent_at_idx,alert_log_pkey
--                                (2 — prova de que a decisão "não recriar
--                                 índice" está sendo cumprida)
--   rls_alert_log              = true
--   policies_alert_log         = alert_log_select_own_routes_or_any_leg
--                                (prova de que a RLS não foi apertada)
--   rls_settings               = true
--   policies_settings          — todas por auth.uid(); anotar o texto exato
--   policies_escrita_settings  — anotar (settings é escrita pelo painel via
--                                upsert, então > 0 é esperado aqui)
--   anon_select_settings       = true    <- grant de FÁBRICA do Supabase, já
--   anon_update_settings       = true       registrado como higiene aceita
--   auth_select_settings       = true       (STATE.md, 08/08/2026). NÃO é a
--   svc_select_settings        = true       barreira; a barreira é a policy,
--                                           medida no G0-Q6.
--
-- ESTE RESULTADO INTEIRO É O "ESPERADO" DO V2. Copiar/guardar a linha completa.
-- ----------------------------------------------------------------------------
select
  (select string_agg(indexname, ',' order by indexname) from pg_indexes
    where schemaname='public' and tablename='alert_log')                      as indices_alert_log,
  (select relrowsecurity from pg_class where oid='public.alert_log'::regclass) as rls_alert_log,
  (select string_agg(policyname, ',' order by policyname) from pg_policies
    where schemaname='public' and tablename='alert_log')                      as policies_alert_log,
  (select relrowsecurity from pg_class where oid='public.settings'::regclass)  as rls_settings,
  (select string_agg(policyname || '/' || cmd || '/' || coalesce(array_to_string(roles, '+'), '?'),
                     ',' order by policyname)
     from pg_policies where schemaname='public' and tablename='settings')     as policies_settings,
  (select count(*) from pg_policies where schemaname='public'
     and tablename='settings' and cmd in ('INSERT','UPDATE','DELETE','ALL'))  as policies_escrita_settings,
  has_table_privilege('anon','public.settings','SELECT')                      as anon_select_settings,
  has_table_privilege('anon','public.settings','UPDATE')                      as anon_update_settings,
  has_table_privilege('authenticated','public.settings','SELECT')             as auth_select_settings,
  has_table_privilege('service_role','public.settings','SELECT')              as svc_select_settings;


-- ----------------------------------------------------------------------------
-- G0-Q6 — GATE DO display_name: anon consegue LER LINHA de settings hoje?
--
-- POR QUE ESTE BLOCO EXISTE: listar grant e policy NÃO É PROVA. O que decide se
-- o display_name fica exposto é se alguma policy DEVOLVE LINHA para anon. Isso
-- se mede personificando o papel, não lendo catálogo. Mesma técnica dos blocos
-- E/F da Etapa 4.1 (sql/etapa4_1_verificacao.sql:111-121) e do diagnóstico de
-- isolamento de 08/08/2026: transação com `set local role` e ROLLBACK ao fim,
-- sem efeito colateral nenhum.
--
-- papel_efetivo é COLUNA-GUARDA: se não vier 'anon', o contexto de papel não
-- pegou e o número ao lado NÃO PROVA NADA — nesse caso, repetir.
--
-- ESPERADO:
--   papel_efetivo          = anon
--   linhas_settings_vistas = 0
--
-- >>> GATE 3 — linhas_settings_vistas > 0  =>  PARE E AVISE.
--     Isso é achado PRÉ-EXISTENTE e MUITO MAIOR que o display_name: significa
--     que os dados de configuração de todos os usuários já estão legíveis sem
--     autenticação, hoje, antes desta fatia. Vira ITEM PRÓPRIO, fora da D4.
--     NÃO consertar postura de RLS de produção aqui: a D4 é a fatia mais
--     sensível da etapa e não é lugar de mexer em política de segurança de
--     passagem.
-- ----------------------------------------------------------------------------
begin;
  set local idle_in_transaction_session_timeout = '30s';
  set local role anon;

  select
    current_user                          as papel_efetivo,           -- esperado: anon
    (select count(*) from settings)       as linhas_settings_vistas;  -- esperado: 0
rollback;


-- ============================================================================
-- BLOCO 1 — A MUDANÇA. Uma coluna e um update, na MESMA execução.
--
-- A coluna é nullable, sem default, sem CHECK: um rótulo de exibição não tem
-- verdade obrigatória a preencher, e nenhuma constraint aqui deve ser capaz de
-- rejeitar escrita do painel em settings.
--
-- POR QUE O UPDATE ESTÁ AQUI, e não "depois, quando der": sem nome gravado, a
-- primeira mensagem pós-deploy sai com uuid[:8] — e aí o item 5 da verificação
-- pós-deploy NÃO CONSEGUE DISTINGUIR "coluna vazia, fallback funcionando
-- corretamente" de "lookup do nome quebrado". Os dois produzem exatamente a
-- mesma saída. Com o nome gravado aqui, o item 5 vira asserção afiada: a
-- mensagem TEM que trazer o nome, e um uuid[:8] ali passa a ser defeito
-- inequívoco.
--
-- ANTES DE RODAR: conferir que o user_id abaixo bate com o user_ids medido no
-- G0-Q1. Não copiar às cegas.
--
-- O valor 'Elton' é escolha de exibição, não dado derivado — trocar aqui se
-- preferir outro rótulo. Ajustes posteriores são manuais no SQL Editor, mesmo
-- padrão de system_config documentado em RUNBOOK.md:39-48.
--
-- GUARDA DE IDEMPOTÊNCIA `display_name is null`: re-rodar este bloco NÃO
-- sobrescreve um nome já ajustado à mão depois.
--
-- Este bloco NÃO devolve resultado de SELECT (é DDL + DML). A confirmação vem
-- do V1, logo abaixo — rodar o V1 na sequência, sempre.
-- ============================================================================
alter table settings
  add column if not exists display_name text;

update settings
   set display_name = 'Elton'
 where user_id = 'c72bf50e-16f7-48fd-9c86-7b49dea1551e'
   and display_name is null;


-- ============================================================================
-- VERIFICAÇÃO — rodar depois do BLOCO 1, uma execução por bloco.
-- V1 é asserção da mudança; V2 é a PROVA DE IGUALDADE que substitui o REVOKE;
-- V3 registra por escrito o privilégio efetivo da coluna.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- V1 — a coluna existe E o nome está gravado.
--
-- ESPERADO:
--   coluna_existe     = true
--   tipo              = text
--   aceita_nulo       = YES
--   default_declarado = NULL   (não tem default, de propósito)
--   linhas_com_nome   = 1
--   nome_gravado      = Elton  (ou o rótulo escolhido no BLOCO 1)
--   user_id_do_nome   = c72bf50e-16f7-48fd-9c86-7b49dea1551e
--
-- >>> linhas_com_nome = 0  =>  PARE. Significa que o update não pegou (user_id
--     divergente do medido em G0-Q1, ou já havia um display_name não nulo).
--     Não seguir para o deploy do código: o item 5 da verificação pós-deploy
--     perde o poder de discriminar fallback correto de lookup quebrado, que é
--     exatamente o motivo de o update existir.
-- ----------------------------------------------------------------------------
select
  exists (select 1 from information_schema.columns
           where table_schema='public' and table_name='settings'
             and column_name='display_name')                           as coluna_existe,
  (select data_type from information_schema.columns
    where table_schema='public' and table_name='settings'
      and column_name='display_name')                                  as tipo,
  (select is_nullable from information_schema.columns
    where table_schema='public' and table_name='settings'
      and column_name='display_name')                                  as aceita_nulo,
  (select column_default from information_schema.columns
    where table_schema='public' and table_name='settings'
      and column_name='display_name')                                  as default_declarado,
  (select count(*) from settings where display_name is not null)       as linhas_com_nome,
  (select string_agg(display_name, ',' order by user_id)
     from settings where display_name is not null)                     as nome_gravado,
  (select string_agg(user_id::text, ',' order by user_id)
     from settings where display_name is not null)                     as user_id_do_nome;


-- ----------------------------------------------------------------------------
-- V2-A — POSTURA DE ACESSO IDÊNTICA (catálogo). É o G0-Q5 repetido SEM ALTERAR
-- UMA VÍRGULA, para comparação campo a campo.
--
-- ESPERADO: IDÊNTICO AO G0-Q5, CAMPO A CAMPO. Mesmos índices, mesma RLS, mesmas
-- policies, mesmos grants.
--
-- É um DIFF, não um REVOKE: a prova de que acrescentar a coluna não mexeu na
-- postura de acesso — que é o que substitui o bloco de REVOKE que não seria
-- capaz de fazer nada (ver cabeçalho). QUALQUER divergência aqui é defeito e
-- PARA o deploy do código.
-- ----------------------------------------------------------------------------
select
  (select string_agg(indexname, ',' order by indexname) from pg_indexes
    where schemaname='public' and tablename='alert_log')                      as indices_alert_log,
  (select relrowsecurity from pg_class where oid='public.alert_log'::regclass) as rls_alert_log,
  (select string_agg(policyname, ',' order by policyname) from pg_policies
    where schemaname='public' and tablename='alert_log')                      as policies_alert_log,
  (select relrowsecurity from pg_class where oid='public.settings'::regclass)  as rls_settings,
  (select string_agg(policyname || '/' || cmd || '/' || coalesce(array_to_string(roles, '+'), '?'),
                     ',' order by policyname)
     from pg_policies where schemaname='public' and tablename='settings')     as policies_settings,
  (select count(*) from pg_policies where schemaname='public'
     and tablename='settings' and cmd in ('INSERT','UPDATE','DELETE','ALL'))  as policies_escrita_settings,
  has_table_privilege('anon','public.settings','SELECT')                      as anon_select_settings,
  has_table_privilege('anon','public.settings','UPDATE')                      as anon_update_settings,
  has_table_privilege('authenticated','public.settings','SELECT')             as auth_select_settings,
  has_table_privilege('service_role','public.settings','SELECT')              as svc_select_settings;


-- ----------------------------------------------------------------------------
-- V2-B — POSTURA DE ACESSO IDÊNTICA (personificação). É o G0-Q6 repetido SEM
-- ALTERAR UMA VÍRGULA.
--
-- ESPERADO: IDÊNTICO AO G0-Q6 — papel_efetivo = anon, linhas_settings_vistas = 0.
-- anon continua vendo ZERO linha de settings depois da coluna existir. É esta
-- linha, e não um revoke, que sustenta a afirmação de que o display_name não
-- ficou exposto.
-- ----------------------------------------------------------------------------
begin;
  set local idle_in_transaction_session_timeout = '30s';
  set local role anon;

  select
    current_user                          as papel_efetivo,           -- esperado: anon
    (select count(*) from settings)       as linhas_settings_vistas;  -- esperado: 0
rollback;


-- ----------------------------------------------------------------------------
-- V3 — PRIVILÉGIO EFETIVO DA COLUNA, registrado por escrito.
--
-- ESPERADO:
--   anon_select_col = true
--   auth_select_col = true
--   anon_update_col = true
--   linhas_com_nome = 1
--
-- >>> LEIA ANTES DE REAGIR: esses `true` são o RESULTADO CORRETO, não um
--     defeito e não uma regressão. O privilégio de coluna é HERDADO DA TABELA em
--     Postgres, e nenhum `revoke` de coluna o remove enquanto o grant de tabela
--     existir (ver cabeçalho, e sql/fatia_d3_user_id_alert_log.sql:383-387). A
--     barreira que de fato protege o dado é a policy de linha, provada em
--     G0-Q6/V2-B: anon vê ZERO linha, então nunca chega a ler coluna nenhuma.
--
-- Este bloco existe exatamente para que ninguém, no futuro, leia esse `true`
-- como falha de segurança introduzida pela D4 — e para que ninguém tente
-- "corrigi-lo" com um revoke de coluna que não faz nada.
-- ----------------------------------------------------------------------------
select
  has_column_privilege('anon','public.settings','display_name','SELECT')          as anon_select_col,
  has_column_privilege('authenticated','public.settings','display_name','SELECT') as auth_select_col,
  has_column_privilege('anon','public.settings','display_name','UPDATE')          as anon_update_col,
  (select count(*) from settings where display_name is not null)                  as linhas_com_nome;
