-- ============================================================================
-- Etapa 4.4 — weekend_legs vira somente-leitura no navegador.
--
-- CONTEXTO: weekend_legs tinha policy de UPDATE para authenticated — vestígio
-- do mundo pré-4.1/4.2, quando o painel escrevia teto/status/notas direto
-- nessa tabela. Desde as pendências 3/4/5 da Etapa 4.2 (verificadas em
-- produção, 03-04/08/2026), o painel escreve em weekend_leg_user_state e em
-- settings.weekend_default_ceiling — nunca mais em weekend_legs. Quem ainda
-- escreve em weekend_legs é só o robô (service_role, que sempre ignora RLS).
-- A policy de UPDATE ficou sem uso real, mas continuava sendo superfície de
-- escrita: qualquer sessão autenticada no navegador podia, tecnicamente, dar
-- update direto em weekend_legs via API. Esta etapa fecha essa superfície.
--
-- SELECT continua aberto para qualquer autenticado — isso NÃO muda.
--
-- Checagem de segurança feita ANTES de rodar isto (chat de planejamento,
-- 07/08/2026): `grep -rn "weekend_legs" docs/js/` — 11 ocorrências, todas em
-- compras.js e dashboard.js, todas leitura (acesso à chave weekend_legs de um
-- objeto JS vindo de um select que embute weekend_legs(*) dentro de weekends,
-- ou leitura de weekend_leg_effective). Nenhum update/upsert/insert contra
-- weekend_legs em nenhum lugar de docs/js/. Confirmado também que as únicas
-- escritas do frontend são .from('weekend_leg_user_state').upsert(...) e
-- .from('settings').upsert(...) — consistente com o que a Etapa 4.2 já
-- havia documentado.
--
-- EXECUÇÃO: 100% MANUAL, pelo usuário, no SQL Editor do Supabase — mesmo
-- fluxo dos scripts anteriores desta iniciativa. Rodado em produção em
-- 07/08/2026.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- Guarda G0: inventário do estado atual (confirma o que o diagnóstico já
-- mostrou, evita agir sobre suposição se algo mudou entre os dois chats).
--
-- Se policies_update_hoje <> 1, PARAR e trazer o resultado de volta ao chat
-- de planejamento antes de continuar — significa que o estado mudou desde o
-- diagnóstico.
-- ----------------------------------------------------------------------------
select
  (select count(*) from pg_policies where schemaname='public' and tablename='weekend_legs' and cmd='UPDATE') as policies_update_hoje,
  (select is_updatable from information_schema.views where table_schema='public' and table_name='weekend_leg_effective') as view_effective_e_updatable;

-- RESULTADO REAL (07/08/2026): policies_update_hoje = 1,
-- view_effective_e_updatable = NO.


-- ----------------------------------------------------------------------------
-- Parte A: revoga o grant de escrita da tabela para os papéis de navegador.
-- ----------------------------------------------------------------------------
revoke update on public.weekend_legs from anon, authenticated;

-- RESULTADO REAL (07/08/2026): sucesso, sem erro.


-- ----------------------------------------------------------------------------
-- Parte B: remove a policy de update (agora vestigial, mas não deve ficar
-- pra trás).
-- ----------------------------------------------------------------------------
drop policy if exists weekend_legs_update_authenticated on public.weekend_legs;

-- RESULTADO REAL (07/08/2026): sucesso, sem erro.


-- ----------------------------------------------------------------------------
-- Verificação final: deve retornar 0 policies de update e nenhum privilégio
-- de UPDATE.
-- ----------------------------------------------------------------------------
select
  (select count(*) from pg_policies where schemaname='public' and tablename='weekend_legs' and cmd='UPDATE') as policies_update_depois,
  has_table_privilege('authenticated','public.weekend_legs','UPDATE') as authenticated_ainda_pode_update,
  has_table_privilege('anon','public.weekend_legs','UPDATE') as anon_ainda_pode_update;

-- RESULTADO REAL (07/08/2026): policies_update_depois = 0,
-- authenticated_ainda_pode_update = false, anon_ainda_pode_update = false.
-- Etapa 4.4 confirmada concluída em produção.


-- ============================================================================
-- ACHADO LATERAL: view_effective_e_updatable já vinha NO antes deste script.
--
-- weekend_leg_effective (sql/etapa4_1_estado_por_usuario.sql, Bloco 6) é uma
-- view com join de múltiplas tabelas (weekend_legs + weekends + settings +
-- weekend_leg_user_state), sem trigger INSTEAD OF — o Postgres nunca a
-- considerou automaticamente atualizável, independente de qualquer RLS ou
-- grant em weekend_legs. O grant que existe sobre ela sempre foi só de
-- SELECT ("grant select on weekend_leg_effective to authenticated,
-- service_role"). Ou seja: o caminho de escrita pela view nunca foi real —
-- este script fecha o caminho de escrita DIRETO na tabela, que era o único
-- que de fato existia.
-- ============================================================================
