-- ============================================================================
-- Etapa 7 — verificação do ITEM 5 da verificação pós-deploy da D4, contra o
-- PRIMEIRO ALERTA REAL DE PERNA observado.
--
-- GATILHO OBSERVADO: 17/08/2026, ~08h16 BRT — fim de semana de 29/01/2027,
-- perna de VOLTA, R$ 334 <= teto R$ 500. O alerta disparou de verdade, em
-- produção, sem ser provocado.
--
-- ----------------------------------------------------------------------------
-- CORREÇÃO DE NUMERAÇÃO (ler antes de documentar qualquer coisa a partir daqui)
-- ----------------------------------------------------------------------------
-- A numeração do projeto, desde o registro original da verificação pós-deploy
-- da D4, é:
--   item 5 = a linha em alert_log NASCE COM user_id PREENCHIDO  (camada BANCO)
--   item 6 = a mensagem do Telegram traz o NOME do usuário      (camada MENSAGEM)
--
-- A mensagem do Telegram de 17/08 08h16 exibiu "👤 Elton" (e não uuid[:8]).
-- Isso é evidência da CAMADA DE MENSAGEM: prova o ITEM 6. NÃO prova o item 5.
-- O item 5 só se confirma consultando o banco diretamente — que é exatamente
-- o que este script faz.
--
-- Um prompt de outro chat rotulou a verificação de mensagem como "item 5".
-- Isso está ERRADO. Vale a numeração acima.
--
-- ----------------------------------------------------------------------------
-- O QUE SE ESPERA
-- ----------------------------------------------------------------------------
-- Uma linha (ou mais, se houver outros alertas de perna na mesma janela de 1h)
-- com user_id preenchido com o UUID do usuário principal:
--     c72bf50e-16f7-48fd-9c86-7b49dea1551e
-- — porque a mensagem observada foi só para "Elton", não para o Gustavo.
--
-- ESCOPO DESTA EXECUÇÃO — NÃO é prova de fan-out completo. Um único dono na
-- janela não confirma alert_log com DOIS user_id DISTINTOS na MESMA execução,
-- que é justamente o que falta para fechar a E7-5. São itens diferentes.
--
-- ----------------------------------------------------------------------------
-- CRITÉRIO DE LEITURA DO RESULTADO
-- ----------------------------------------------------------------------------
-- user_id NULL nesta linha  -> ITEM 5 REPROVA. É ACHADO GRAVE: significa que a
--   linha de alert_log nasce órfã mesmo com a camada de mensagem já resolvendo
--   o nome. REPORTAR ANTES DE QUALQUER OUTRA AÇÃO — não seguir para nenhuma
--   outra fatia, não atualizar plano/estado, não corrigir nada por conta.
--
-- user_id PREENCHIDO       -> ITEM 5 CONFIRMA. A E7-5 (fan-out com dois donos
--   distintos na mesma execução) CONTINUA EM ABERTO — item diferente, este
--   resultado não fecha aquele.
--
-- ZERO LINHAS               -> resultado inconclusivo, não é aprovação nem
--   reprovação. Conferir fuso/janela antes de concluir qualquer coisa.
--
-- ----------------------------------------------------------------------------
-- NOTA — leitura pura. Um único SELECT, sem escrita, sem transação necessária.
--
-- EXECUÇÃO: 100% MANUAL, pelo usuário, no SQL Editor do Supabase. Claude Code
-- NÃO executa SQL.
--
-- Bloco único — pode colar o arquivo inteiro de uma vez.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- BLOCO ÚNICO — alertas de perna na janela 17/08/2026 08:00–09:00 BRT (-03)
-- ----------------------------------------------------------------------------
select id, leg_id, user_id, reason, sent_at
  from alert_log
 where leg_id is not null
   and sent_at >= '2026-08-17 08:00:00-03'
   and sent_at <  '2026-08-17 09:00:00-03'
 order by sent_at;
