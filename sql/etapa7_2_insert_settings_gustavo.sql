-- ============================================================================
-- Etapa 7, fatia E7-2 — Insert em `settings` para o segundo usuário (Gustavo).
--
-- CONTEXTO: a conta do Gustavo já foi criada manualmente pelo usuário no
-- dashboard do Supabase Auth, com Auto Confirm, sem convite por e-mail.
-- UUID: 2446ec67-06b8-478c-bc5d-6a17eab1fe76.
--
-- Este é o ato que marca o INÍCIO DO FAN-OUT REAL: a partir daqui,
-- `weekend_leg_effective` passa a devolver linhas DOBRADAS (264, não 132)
-- para qualquer consumidor que leia a view sem filtrar por usuário —
-- inclusive o robô, entre uma execução e outra (janela 08h-20h BRT).
--
-- Semeadura SIMPLIFICADA (decisão de 15/08/2026, PLANO-ATIVO.md fatia E7-2):
-- só os 3 campos abaixo são explicitados. As demais 13 colunas de `settings`
-- são NOT NULL com default seguro (confirmado pela E7-0/Q1) — ficam
-- implícitas, é o próprio Postgres que aplica.
--
--   user_id                  = '2446ec67-06b8-478c-bc5d-6a17eab1fe76'
--   weekend_default_ceiling  = 300
--   display_name             = 'Gustavo'
--
-- NOTA — trigger: `trg_audit_default_ceiling_ins` vai gravar automaticamente
-- uma linha scope='default' em `weekend_leg_ceiling_audit`. É esperado, é
-- rastro permanente (append-only, sem policy de delete) — registrar no plano
-- depois, não é erro.
--
-- NOTA — credencial: a credencial de acesso do Gustavo NÃO deve ser entregue
-- a ele ainda. Só depois de a E7-4 (prova de isolamento) passar.
--
-- SAÍDA DE EMERGÊNCIA: se os números do BLOCO 2 não baterem (não for 2 e
-- 264), apagar a LINHA de settings recém-inserida (não a conta) devolve o
-- sistema ao estado anterior:
--   delete from settings where user_id = '2446ec67-06b8-478c-bc5d-6a17eab1fe76';
--
-- EXECUÇÃO: 100% MANUAL, pelo usuário, no SQL Editor do Supabase. Claude Code
-- NÃO executa SQL.
--
-- REGRA DE EXECUÇÃO BLOCO A BLOCO — NÃO COLAR O ARQUIVO INTEIRO DE UMA VEZ:
-- o SQL Editor do Supabase devolve o resultado apenas do ÚLTIMO statement de
-- um bloco múltiplo. BLOCO 1 e BLOCO 2 são EXECUÇÕES SEPARADAS — rodar o
-- BLOCO 1, depois rodar o BLOCO 2 e ler os dois números.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- BLOCO 1 — insert da linha de settings do Gustavo.
-- ----------------------------------------------------------------------------
insert into settings (user_id, weekend_default_ceiling, display_name)
values ('2446ec67-06b8-478c-bc5d-6a17eab1fe76', 300, 'Gustavo');


-- ----------------------------------------------------------------------------
-- BLOCO 2 — verificação imediata pós-insert (critério de conclusão da E7-2).
--
-- ESPERADO: linhas_settings = 2, linhas_efetivas = 264.
-- ----------------------------------------------------------------------------
select
  (select count(*) from settings)                as linhas_settings,
  (select count(*) from weekend_leg_effective)    as linhas_efetivas;
