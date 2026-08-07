-- ============================================================================
-- Etapa 4.3, Passo 5 — VERIFICAÇÃO PÓS-DROP.
--
-- CONTEXTO: em 06/08/2026 (commit ce0d8b3) as 5 colunas legadas de
-- weekend_legs (price_ceiling, status, notes, paid_price, purchased_at) foram
-- removidas em produção pela PARTE B de sql/etapa4_3_drop_colunas_legadas.sql.
-- Aquele script terminou com um select provando `colunas_legadas_restantes =
-- 0` — mas foi o MESMO script que executou o DROP conferindo o próprio
-- resultado. Este arquivo é o SEGUNDO OLHAR, independente.
--
-- Precedente do projeto (AUDITORIA-MULTIUSUARIO.md, "Etapa 4.1 — baseline
-- antes/depois", 01/08/2026): "mexer nas policies e colunas dessa tabela é a
-- Etapa 4.3/5, não esta". A regra que vem de lá é que mudança estrutural em
-- weekend_legs se confirma com colheita independente — não se reaproveita o
-- resultado do script que fez a mudança. Por isso o BLOCO A abaixo é escrito
-- do zero e NÃO reutiliza nenhuma das guardas G0–G4 do Passo 3.
--
-- SÓ LEITURA. Todos os blocos são SELECT. Nenhum INSERT, UPDATE, DELETE ou
-- DDL em lugar nenhum deste arquivo — rodar tudo de novo é inofensivo.
--
-- COMO RODAR: um bloco por execução no SQL Editor do Supabase, na ordem A →
-- E, anotando o resultado de cada um. O SQL Editor só exibe o resultado do
-- ÚLTIMO select de uma execução: selecionar o arquivo inteiro e rodar de uma
-- vez descarta tudo menos o BLOCO E. Cada bloco abaixo é um select único
-- justamente para caber numa execução.
--
-- COMO LER: os valores esperados de cada bloco estão no rodapé do arquivo,
-- em "VALORES ESPERADOS". Divergência em qualquer bloco = PARAR e levar ao
-- chat de planejamento, não "consertar" por conta própria.
--
-- FORA DE ESCOPO, de propósito: a RLS genérica de weekend_legs (qualquer
-- autenticado edita qualquer linha) é problema conhecido e registrado, a
-- resolver antes da Etapa 7 — é pendência separada, não desta verificação. O
-- BLOCO B abaixo confirma que as policies continuam EXATAMENTE como estavam;
-- não julga se elas são boas.
-- ============================================================================


-- ============================================================================
-- BLOCO A — As 5 colunas legadas não existem mais. Consulta independente.
--
-- Escrito do zero contra information_schema.columns, sem reaproveitar a prova
-- final do Passo 3.
--
-- POR QUE TEM CONTROLE POSITIVO: uma consulta que filtra por nome de tabela
-- errado (typo, schema errado, tabela renomeada) devolve ZERO LINHAS — o
-- mesmo resultado de "as colunas sumiram". Sem controle, este bloco passaria
-- por engano justamente no cenário em que deveria gritar. Por isso ele não
-- pergunta só "as 5 sumiram?", pergunta também "eu estou realmente olhando
-- para a tabela weekend_legs?": `controle_tabela` e `controle_sobreviventes`
-- têm que vir preenchidos, senão os outros números não provam nada.
--
-- `colunas_hoje` é informativo e serve de registro: cole no PLANO-ATIVO.md
-- junto com o resultado.
-- ============================================================================
select
  -- CONTROLE 1: a tabela existe e estou olhando para ela.
  (select count(*)
     from information_schema.tables
    where table_schema = 'public'
      and table_name   = 'weekend_legs')                    as controle_tabela,

  -- CONTROLE 2: colunas que TÊM que continuar existindo. Se este número vier
  -- abaixo de 5, o DROP levou junto coisa que não devia — é falha grave.
  (select count(*)
     from information_schema.columns
    where table_schema = 'public'
      and table_name   = 'weekend_legs'
      and column_name in ('id', 'weekend_id', 'direction',
                          'current_price', 'created_at'))   as controle_sobreviventes,

  -- A PERGUNTA DO BLOCO: quantas das 5 legadas ainda estão de pé.
  (select count(*)
     from information_schema.columns
    where table_schema = 'public'
      and table_name   = 'weekend_legs'
      and column_name in ('price_ceiling', 'status', 'notes',
                          'paid_price', 'purchased_at'))    as legadas_presentes,

  -- Se `legadas_presentes` > 0, este campo diz QUAIS — evita ter que rodar
  -- outra consulta para descobrir.
  (select coalesce(string_agg(column_name, ', ' order by column_name), '(nenhuma)')
     from information_schema.columns
    where table_schema = 'public'
      and table_name   = 'weekend_legs'
      and column_name in ('price_ceiling', 'status', 'notes',
                          'paid_price', 'purchased_at'))    as legadas_quais,

  -- Retrato da tabela hoje, para registro.
  (select count(*)
     from information_schema.columns
    where table_schema = 'public'
      and table_name   = 'weekend_legs')                    as total_colunas_hoje,
  (select string_agg(column_name, ', ' order by ordinal_position)
     from information_schema.columns
    where table_schema = 'public'
      and table_name   = 'weekend_legs')                    as colunas_hoje;


-- ============================================================================
-- BLOCO B — Policies de weekend_legs, comparadas contra o baseline registrado.
--
-- Mesmo formato do Bloco B de sql/etapa4_1_verificacao.sql (policyname, cmd,
-- qual, with_check), agora com veredito calculado em vez de conferência a
-- olho.
--
-- BASELINE (AUDITORIA-MULTIUSUARIO.md, linhas 356-365, colhido em 01/08/2026,
-- reconfirmado idêntico nas linhas 375-380 depois de rodar a 4.1):
--   weekend_legs_select_authenticated | SELECT | (auth.uid() IS NOT NULL) | null
--   weekend_legs_update_authenticated | UPDATE | (auth.uid() IS NOT NULL) | (auth.uid() IS NOT NULL)
--
-- O CRITÉRIO É TEXTO IDÊNTICO, NÃO CONTAGEM. Falha inclui, todas no mesmo
-- nível de gravidade:
--   - policy a mais (uma terceira linha aparece, com veredito DIVERGENTE);
--   - policy a menos (só 1 linha volta em vez de 2);
--   - mesmo nome e mesmo cmd, mas `qual` ou `with_check` com texto diferente
--     — inclusive diferença que "parece equivalente" (por exemplo
--     `auth.uid() is not null` reescrito como `(auth.uid() IS NOT NULL) AND
--     true`, ou um with_check que deixou de ser null). Policy reescrita com
--     texto novo é mudança de superfície de segurança e tem que ser vista,
--     não normalizada.
-- Por isso a comparação abaixo é de igualdade de string crua, sem trim, sem
-- lower, sem regex.
--
-- Ler o resultado: têm que voltar EXATAMENTE 2 linhas, ambas com
-- veredito = 'OK'. Qualquer outra coisa = PARE.
-- ============================================================================
select
  policyname,
  cmd,
  qual,
  with_check,
  case
    when policyname = 'weekend_legs_select_authenticated'
     and cmd        = 'SELECT'
     and qual       = '(auth.uid() IS NOT NULL)'
     and with_check is null
      then 'OK'
    when policyname = 'weekend_legs_update_authenticated'
     and cmd        = 'UPDATE'
     and qual       = '(auth.uid() IS NOT NULL)'
     and with_check = '(auth.uid() IS NOT NULL)'
      then 'OK'
    else 'DIVERGENTE — PARE'
  end                                                       as veredito
from pg_policies
where schemaname = 'public'
  and tablename  = 'weekend_legs'
order by policyname;


-- ============================================================================
-- BLOCO C — weekend_legs continua SEM trigger própria.
--
-- Query idêntica à do Bloco C de sql/etapa4_1_verificacao.sql, de propósito:
-- é o mesmo teste, na mesma tabela, para poder ser comparado diretamente com
-- as duas colheitas de 01/08/2026 (AUDITORIA-MULTIUSUARIO.md, linhas 363-365
-- e 382-384, ambas "nenhuma linha").
--
-- `not tgisinternal` exclui as triggers que o próprio Postgres cria para
-- constraints (FK, unique) — elas não são trigger "de aplicação" e não
-- interessam aqui.
--
-- DROP COLUMN derruba em cascata qualquer trigger que dependesse só da coluna
-- removida. Como a tabela nunca teve trigger nenhuma, o esperado continua
-- sendo zero linhas — e um resultado NÃO-vazio aqui significaria que alguém
-- pendurou trigger em weekend_legs fora do registro do projeto.
-- ============================================================================
select tgname
from pg_trigger
where tgrelid = 'weekend_legs'::regclass
  and not tgisinternal;


-- ============================================================================
-- BLOCO D — Estrutura nova intacta, e a view CONFIRMADA (não assumida).
--
-- Rodar as DUAS partes abaixo (D1 e D2) em execuções separadas: são dois
-- selects, e o SQL Editor só mostra o último de cada execução.
--
-- CORREÇÃO DE PREMISSA, importante para ler este bloco: é falso que
-- weekend_leg_effective dependa só de weekend_leg_user_state. A view lê
-- weekend_legs SIM — `from weekend_legs l`, e consome de lá leg_id,
-- weekend_id, direction, current_price, current_airport, current_variant,
-- current_source, lowest_seen, lowest_seen_at e last_live_check_at
-- (sql/etapa4_1_estado_por_usuario.sql, Bloco 6). O que ela NÃO consome são
-- as 5 colunas removidas — teto, status, notas, valor pago e data de compra
-- vêm de weekend_leg_user_state (st.*), com coalesce para o padrão do
-- usuário. É por isso que o DROP não a quebrou, e é exatamente essa a
-- afirmação que o D2 existe para PROVAR em vez de supor.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- D1 — as três estruturas novas existem, respondem, e a cardinalidade fecha.
--
-- `view_linhas` é esperado = 132 × (nº de linhas em settings). A conta é feita
-- na própria query em `view_esperado`, em vez de cravar 132: a view faz
-- `cross join settings` (settings é o registro de usuários), então quando a
-- Etapa 7 criar a segunda conta o número vira 264 sem que isto aqui vire
-- falso alarme. Hoje, com 1 usuário, os dois campos têm que bater em 132.
--
-- Rodando como postgres no SQL Editor, a RLS é ignorada — os números abaixo
-- são o total real, não "o que um usuário logado enxerga". Isolamento por
-- usuário é assunto dos blocos E/F/F2 de sql/etapa4_1_verificacao.sql, que
-- continuam válidos e não são refeitos aqui.
--
-- `estado_linhas` NÃO tem valor esperado fixo: weekend_leg_user_state cresce
-- de forma legítima toda vez que o usuário mexe em teto, nota, valor pago ou
-- status no painel (modelo preguiçoso — a linha só nasce quando alguém decide
-- algo). Serve de registro, não de guarda: o que precisa ser diferente de
-- zero é só a prova de que a tabela existe e responde.
-- ----------------------------------------------------------------------------
select
  (select count(*) from weekend_leg_user_state)      as estado_linhas,
  (select count(*) from weekend_leg_ceiling_audit)   as auditoria_linhas,
  (select count(*) from weekend_leg_effective)       as view_linhas,
  (select count(*) from weekend_legs)
    * (select count(*) from settings)                as view_esperado,
  (select count(*) from weekend_legs)                as pernas,
  (select count(*) from settings)                    as usuarios;

-- ----------------------------------------------------------------------------
-- D2 — PROVA da dependência real da view sobre weekend_legs.
--
-- Lê pg_depend, que é o registro que o próprio Postgres mantém de quais
-- colunas cada view consome — não é releitura do texto do CREATE VIEW, é a
-- dependência que o banco de fato registrou. Se a view citasse alguma das 5
-- colunas removidas, o DROP COLUMN teria falhado (ou exigido CASCADE, o que
-- teria derrubado a view junto); este bloco confirma pelo lado positivo qual
-- é o acoplamento que sobrou.
--
-- Esperado: 10 linhas, uma por coluna de weekend_legs que a view usa, e
-- NENHUMA delas entre as 5 removidas — `e_coluna_legada` tem que vir false em
-- todas as linhas.
-- ----------------------------------------------------------------------------
select
  a.attname                                                 as coluna_de_weekend_legs_usada_pela_view,
  a.attname in ('price_ceiling', 'status', 'notes',
                'paid_price', 'purchased_at')               as e_coluna_legada   -- esperado: false em todas
from pg_depend d
join pg_rewrite  r on r.oid      = d.objid
join pg_class    v on v.oid      = r.ev_class
join pg_attribute a on a.attrelid = d.refobjid
                   and a.attnum   = d.refobjsubid
where v.relname   = 'weekend_leg_effective'
  and d.refobjid  = 'public.weekend_legs'::regclass
  and d.refobjsubid > 0
group by a.attname
order by a.attname;


-- ============================================================================
-- BLOCO E — Backup permanente, íntegro e ainda mapeando 1:1.
--
-- weekend_legs_legacy_columns_backup é a ÚNICA rota de volta para os dados das
-- 5 colunas (a receita de restauração vive em comentário no fim de
-- sql/etapa4_3_drop_colunas_legadas.sql). Ela é PERMANENTE: não sai em
-- limpeza de rotina, só por decisão explícita no chat de planejamento.
--
-- POR QUE CHECAR O MAPEAMENTO, e não só a contagem: a tabela foi criada SEM
-- foreign key de propósito (justificativa no `comment on column` do Passo 3 —
-- com cascade, apagar uma perna apagaria o backup dela junto; sem cascade,
-- impediria excluir pernas dali em diante). Sem FK, nada no banco garante que
-- os 132 ids do backup ainda correspondam a pernas vivas. `ids_orfaos` fecha
-- esse buraco à mão: é a checagem que a FK faria, se existisse.
--
-- `capturas_distintas` tem que ser 1: a PARTE A copiou as 132 linhas num
-- único `insert ... select`, então todas compartilham o mesmo captured_at.
-- Mais de uma captura distinta significa que alguém inseriu no backup depois
-- — o que a tabela não deveria receber nunca.
--
-- `colunas_backup` = 7: as 5 legadas + id + captured_at.
-- ============================================================================
select
  (select count(*) from weekend_legs_legacy_columns_backup)      as linhas_backup,
  (select count(*) from weekend_legs)                            as linhas_weekend_legs,

  -- Estrutura do backup não foi mexida: 7 colunas, com os nomes exatos.
  (select count(*)
     from information_schema.columns
    where table_schema = 'public'
      and table_name   = 'weekend_legs_legacy_columns_backup')   as colunas_backup,
  (select string_agg(column_name, ', ' order by ordinal_position)
     from information_schema.columns
    where table_schema = 'public'
      and table_name   = 'weekend_legs_legacy_columns_backup')   as colunas_backup_quais,

  -- Uma única captura, a da PARTE A do Passo 3 (06/08/2026).
  (select count(distinct captured_at)
     from weekend_legs_legacy_columns_backup)                    as capturas_distintas,
  (select max(captured_at)
     from weekend_legs_legacy_columns_backup)                    as capturado_em,

  -- O que a FK ausente não garante: todo id do backup ainda é uma perna viva.
  (select count(*)
     from weekend_legs_legacy_columns_backup b
    where not exists (select 1 from weekend_legs l where l.id = b.id))
                                                                  as ids_orfaos,

  -- E o inverso: nenhuma perna ficou sem linha de backup.
  (select count(*)
     from weekend_legs l
    where not exists (select 1
                        from weekend_legs_legacy_columns_backup b
                       where b.id = l.id))                        as pernas_sem_backup,

  -- RLS ligada e zero policies é o desenho declarado do Passo 3 (fecha o
  -- acesso pela API com chave anônima; notes guardava localizador e horário).
  -- Quem lê a tabela é o dono (SQL Editor) ou o robô (service_role), e os dois
  -- passam por cima de RLS.
  (select relrowsecurity
     from pg_class
    where oid = 'public.weekend_legs_legacy_columns_backup'::regclass)
                                                                  as rls_ligada,
  (select count(*)
     from pg_policies
    where schemaname = 'public'
      and tablename  = 'weekend_legs_legacy_columns_backup')      as policies_no_backup;


-- ============================================================================
-- VALORES ESPERADOS — conferir depois de rodar cada bloco no SQL Editor.
--
-- BLOCO A (1 linha)
--   controle_tabela ......... 1        <- se vier 0, a consulta não achou a
--                                        tabela e NENHUM outro número deste
--                                        bloco vale; PARE.
--   controle_sobreviventes .. 5        <- abaixo disso, o DROP levou coluna a
--                                        mais; falha grave, PARE.
--   legadas_presentes ....... 0        <- a resposta do passo.
--   legadas_quais ........... (nenhuma)
--   total_colunas_hoje ...... 13       <- DERIVADO DO REPOSITÓRIO, não do
--                                        banco: 14 do create table original
--                                        (sql/pernas_desacopladas.sql) + notes
--                                        + paid_price + current_airline +
--                                        current_departure_time
--                                        (sql/parte9_dados_voo_e_expiracao.sql)
--                                        - as 5 removidas. Se vier diferente,
--                                        NÃO é falha automática: pode ser
--                                        coluna criada fora do repositório.
--                                        Conferir `colunas_hoje` e registrar.
--   colunas_hoje ............ esperado: id, weekend_id, direction,
--                             current_price, current_airport, current_variant,
--                             current_source, lowest_seen, lowest_seen_at,
--                             last_live_check_at, created_at, current_airline,
--                             current_departure_time
--
-- BLOCO B (exatamente 2 linhas)
--   weekend_legs_select_authenticated | SELECT | (auth.uid() IS NOT NULL) | null                     | OK
--   weekend_legs_update_authenticated | UPDATE | (auth.uid() IS NOT NULL) | (auth.uid() IS NOT NULL) | OK
--   Qualquer linha com veredito 'DIVERGENTE — PARE', qualquer terceira linha,
--   ou menos de 2 linhas = falha. PARE.
--
-- BLOCO C
--   Zero linhas ("Success. No rows returned").
--
-- BLOCO D1 (1 linha)
--   estado_linhas ........... sem valor fixo; registrar (só não pode dar erro)
--   auditoria_linhas ........ sem valor fixo; registrar
--   view_linhas ............. tem que ser IGUAL a view_esperado
--   view_esperado ........... 132 hoje (132 pernas × 1 usuário)
--   pernas .................. 132
--   usuarios ................ 1
--
-- BLOCO D2 (10 linhas)
--   e_coluna_legada ......... false em TODAS as linhas.
--   Colunas esperadas: current_airport, current_price, current_source,
--   current_variant, direction, id, last_live_check_at, lowest_seen,
--   lowest_seen_at, weekend_id.
--   Zero linhas aqui seria SUSPEITO, não bom: significaria que a view deixou
--   de depender de weekend_legs, ou que ela não existe mais. PARE.
--
-- BLOCO E (1 linha)
--   linhas_backup ........... 132
--   linhas_weekend_legs ..... 132
--   colunas_backup .......... 7
--   colunas_backup_quais .... id, price_ceiling, status, notes, paid_price,
--                             purchased_at, captured_at
--   capturas_distintas ...... 1
--   capturado_em ............ um timestamp de 06/08/2026
--   ids_orfaos .............. 0
--   pernas_sem_backup ....... 0
--   rls_ligada .............. true
--   policies_no_backup ...... 0
--
-- Divergência em qualquer bloco: PARAR e levar ao chat de planejamento. Não
-- "corrigir" nada por conta própria — em especial, NUNCA refazer o backup por
-- cima para fazer o BLOCO E passar; isso apagaria a prova do que mudou.
-- ============================================================================
