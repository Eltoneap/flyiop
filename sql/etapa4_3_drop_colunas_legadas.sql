-- ============================================================================
-- Etapa 4.3, Passo 3 — backup + DROP das 5 colunas legadas de weekend_legs
-- (price_ceiling, status, notes, paid_price, purchased_at).
--
-- CONTEXTO: a decisão por perna x usuário vive em weekend_leg_user_state desde
-- a Etapa 4.1, e desde a 4.2 painel e robô leem tudo por weekend_leg_effective.
-- As 5 colunas legadas em weekend_legs só continuam de pé como fotografia
-- congelada. Diagnóstico fechado no chat de planejamento (06/08/2026): nenhuma
-- view, policy de RLS ou função de banco depende delas; zero divergência de
-- dado nas 132 pernas; o único caminho de código que ainda as lia (ramo
-- degradado de get_active_legs) foi corrigido antes deste script (commit
-- d5f97eb). Detalhe completo em PLANO-ATIVO.md, "Etapa 4.3".
--
-- EXECUÇÃO: 100% MANUAL, pelo usuário, no SQL Editor do Supabase. Não há
-- credenciais de banco disponíveis para rodar isto de forma automática, e não
-- deveria haver — é DROP COLUMN em produção.
--
-- ORDEM, um bloco por execução:
--   BLOCO 0 (inventário, só leitura)  -> colar o resultado no PLANO-ATIVO.md
--   PARTE A (backup)                  -> conferir o select final antes de seguir
--   PARTE B (guardas + DROP)          -> só depois de conferir a PARTE A
--
-- NÃO RODAR O ARQUIVO INTEIRO DE UMA VEZ — copiar e rodar um bloco por vez. Se
-- selecionar tudo e executar de uma tacada, o resultado do BLOCO 0 é
-- descartado (o SQL Editor só mostra o último select) e as colunas caem sem
-- ninguém nunca ter visto o inventário de definição. A guarda G0 na PARTE B
-- detecta esse caso e barra o DROP.
-- ============================================================================


-- ============================================================================
-- BLOCO 0 — INVENTÁRIO DE DEFINIÇÃO DAS 5 COLUNAS LEGADAS.
-- RODAR PRIMEIRO. SÓ LEITURA. COLAR O RESULTADO NO PLANO-ATIVO.md ANTES DE
-- SEGUIR PARA A PARTE A.
--
-- DROP COLUMN leva junto tipo, precisão, default, not-null, check constraints
-- e índices — o backup de dados da PARTE A só guarda valores, não definição.
-- Este bloco é a única fonte da definição das colunas depois do DROP, e serve
-- de conferência: os tipos escritos no create table da PARTE A devem bater com
-- o que este bloco devolver do banco real.
--
-- Resultado único (union all) porque o SQL Editor do Supabase só mostra o
-- resultado do último select de uma execução.
--
-- JÁ EXECUTADO em 06/08/2026 — resultado registrado em PLANO-ATIVO.md, Etapa
-- 4.3, item 3: os 5 tipos batem com o create table da PARTE A, e zero
-- constraint/índice cita as 5 colunas. Re-rodar é inofensivo (é só leitura),
-- mas não é mais necessário.
-- ============================================================================
select
  'coluna'::text                 as tipo_de_linha,
  column_name                    as nome,
  data_type                      as detalhe_1,
  udt_name                       as detalhe_2,
  coalesce(numeric_precision::text, '') || '/' || coalesce(numeric_scale::text, '')
                                  as detalhe_3,
  is_nullable                    as detalhe_4,
  coalesce(column_default, '')   as detalhe_5
from information_schema.columns
where table_schema = 'public'
  and table_name = 'weekend_legs'
  and column_name in ('price_ceiling', 'status', 'notes', 'paid_price', 'purchased_at')

union all

select
  'constraint',
  conname,
  pg_get_constraintdef(oid),
  contype::text,  -- 'c'=check, 'f'=foreign key, 'u'=unique, 'x'=exclusion, 'p'=primary key
  '', '', ''
from pg_constraint
where conrelid = 'public.weekend_legs'::regclass
  -- Sem filtro por contype de propósito: QUALQUER constraint cuja definição
  -- cite uma das 5 colunas precisa entrar aqui, não só checks — uma FK, uma
  -- unique ou uma exclusion constraint passariam batido do contrário, e este
  -- bloco é a única chance de registrar isso antes do DROP.
  and pg_get_constraintdef(oid) ~ '(price_ceiling|status|notes|paid_price|purchased_at)'

union all

select
  'indice',
  indexname,
  indexdef,
  '', '', '', ''
from pg_indexes
where schemaname = 'public'
  and tablename = 'weekend_legs'
  and indexdef ~ '(price_ceiling|status|notes|paid_price|purchased_at)'

order by 1, 2;


-- ============================================================================
-- PARTE A — BACKUP. RODAR DEPOIS DO BLOCO 0, E SOZINHA.
--
-- ANTES DE RODAR: compare os 5 tipos devolvidos pelo BLOCO 0 (schema real do
-- banco de produção) com os tipos escritos no create table logo abaixo. Se
-- QUALQUER um divergir, PARE e leve ao chat de planejamento — não siga por
-- conta própria.
--
-- Os tipos abaixo foram lidos no repositório (não no banco ao vivo, sem acesso
-- a ele): price_ceiling numeric e purchased_at timestamptz em
-- sql/pernas_desacopladas.sql (linhas 36 e 45); status text também em
-- sql/pernas_desacopladas.sql (linha 37); notes text em sql/notas_pernas.sql
-- (linha 3); paid_price numeric em sql/parte8_preco_pago.sql (linha 4).
-- ============================================================================

create table weekend_legs_legacy_columns_backup (
  id            uuid primary key,
  price_ceiling numeric,
  status        text,
  notes         text,
  paid_price    numeric,
  purchased_at  timestamptz,
  captured_at   timestamptz not null default now()
);
-- Sem "if not exists" de propósito: uma segunda execução acidental tem que
-- estourar erro, não duplicar linhas em silêncio. Ver "PARA REFAZER O BACKUP"
-- no fim deste bloco.

comment on table weekend_legs_legacy_columns_backup is
  'PERMANENTE. Backup das 5 colunas legadas de weekend_legs (price_ceiling, status, notes, paid_price, purchased_at) tirado antes do DROP na Etapa 4.3, Passo 3 (06/08/2026). Não apagar ao fim da Etapa 4.3 nem em limpeza de rotina — só sai por decisão explícita no chat de planejamento.';

comment on column weekend_legs_legacy_columns_backup.id is
  'Referencia weekend_legs.id. Sem foreign key de propósito: com cascade, apagar uma perna apagaria o backup dela junto; sem cascade, bloquearia excluir pernas a partir de agora. Uma tabela de snapshot não deve restringir a tabela viva.';

alter table weekend_legs_legacy_columns_backup enable row level security;
-- Zero policies de propósito: no Supabase, tabela em public sem RLS fica
-- legível pela API com a chave anônima por padrão. RLS ligada sem nenhuma
-- policy fecha esse acesso e não atrapalha ninguém que precise da tabela: o
-- dono (postgres, o próprio SQL Editor) não é afetado por RLS, e o robô roda
-- como service_role, que também passa por cima dela. notes guarda localizador
-- e horário de voo — não deveria ficar exposta pela API.

insert into weekend_legs_legacy_columns_backup
  (id, price_ceiling, status, notes, paid_price, purchased_at)
select id, price_ceiling, status, notes, paid_price, purchased_at
from weekend_legs;

-- Conferência — resultado único. weekend_default_ceiling aparece só para
-- contexto (é o teto vivo de hoje, lido de forma determinística — menor
-- user_id, mesmo critério de src/main.py:346 / pendência 7 da Etapa 4.2); não
-- é comparado com o teto legado, que é congelado e pode ser outro número por
-- desenho (ver comentário da G3 na PARTE B).
select
  (select count(*) from weekend_legs_legacy_columns_backup)        as linhas_backup,
  (select count(*) from weekend_legs)                              as linhas_weekend_legs,
  (select min(price_ceiling) from weekend_legs)                    as teto_legado_min,
  (select max(price_ceiling) from weekend_legs)                    as teto_legado_max,
  (select count(*) from weekend_legs where price_ceiling is null)  as teto_legado_nulos,
  (select weekend_default_ceiling from settings order by user_id asc limit 1)
                                                                    as teto_padrao_hoje_informativo;

-- ----------------------------------------------------------------------------
-- PARA REFAZER O BACKUP (procedimento manual, não parte da execução normal):
-- o create table acima não tem "if not exists" de propósito, então rodar a
-- PARTE A de novo sem mais nada estoura erro em vez de duplicar dado. Para
-- refazer de verdade: `drop table weekend_legs_legacy_columns_backup;` antes
-- de rodar a PARTE A outra vez.
-- ATENÇÃO EM MAIÚSCULAS: ISSO SÓ DEVE SER FEITO SE A PARTE B AINDA NÃO TIVER
-- RODADO. DEPOIS DO DROP DAS COLUNAS (PARTE B), APAGAR ESTE BACKUP DESTRÓI A
-- ÚNICA ROTA DE VOLTA PARA OS DADOS ANTIGOS.
-- ----------------------------------------------------------------------------


-- ============================================================================
-- PARTE B — GUARDAS + DROP. SÓ RODAR DEPOIS DE CONFERIR O RESULTADO DA PARTE A.
--
-- Três instruções abaixo numa execução só (o do $$ $$, os 5 alter table, e o
-- select final) = uma transação: guarda que estoura não deixa nenhuma coluna
-- derrubada.
--
-- O QUE ESPERAR NA TELA: o SQL Editor do Supabase NÃO exibe `raise notice` —
-- a mensagem "Guardas G0-G4 passaram" no fim do bloco `do $$ $$` não vai
-- aparecer, e isso é normal, não é falha. O critério real é:
--   - ERRO EM VERMELHO NA TELA  = alguma guarda barrou, NADA foi alterado.
--   - NENHUM ERRO                = todas as guardas passaram, e a prova é o
--     `select` final logo depois dos `drop column`, que tem que devolver
--     `colunas_legadas_restantes = 0`.
-- ============================================================================

do $$
declare
  n_backup       int;
  n_legs         int;
  ultimo_backup  timestamptz;
  n_fidelidade   int;
  v_min_teto     numeric;
  v_max_teto     numeric;
  n_teto_nulo    int;
  v_padrao_hoje  numeric;
  n_g4           int;
begin
  -- G0 — guarda de PROCEDIMENTO, não de dado: é a única deste bloco que
  -- verifica COMO o script está sendo rodado, não o que está no banco. Sem
  -- ela, nada impede selecionar o arquivo inteiro (BLOCO 0 + PARTE A + PARTE
  -- B) de uma vez só: o resultado do BLOCO 0 seria descartado (o SQL Editor só
  -- mostra o último select), o backup sairia fiel por construção (acabou de
  -- ser copiado) e as guardas G1-G4 passariam todas sem ninguém nunca ter
  -- visto o inventário de definição — a única fonte dos tipos/defaults/
  -- checks/índices para a receita de restauração.
  --
  -- O SQL Editor roda o texto submetido numa transação implícita única, então
  -- `now()` fica congelado no início dela: se a PARTE A e a PARTE B rodaram
  -- juntas (ou o arquivo inteiro de uma vez), a diferença entre `now()` e
  -- `captured_at` do backup é exatamente zero, e esta guarda pega.
  select max(captured_at) into ultimo_backup from weekend_legs_legacy_columns_backup;
  if ultimo_backup is null or now() - ultimo_backup < interval '2 minutes' then
    raise exception
      'Guarda G0: o backup foi criado há menos de 2 minutos. Isso quase sempre significa que a PARTE A e a PARTE B rodaram na mesma execução (ou o arquivo inteiro foi rodado de uma vez), o que descarta o resultado do BLOCO 0 sem você ver. Nada foi alterado. Confira: (1) o resultado do BLOCO 0 está colado no PLANO-ATIVO.md? (2) o select de conferência da PARTE A foi conferido? Se sim, espere 2 minutos e rode a PARTE B sozinha.';
  end if;

  -- G1 — cobertura: toda perna foi copiada pro backup.
  select count(*) into n_backup from weekend_legs_legacy_columns_backup;
  select count(*) into n_legs   from weekend_legs;
  if n_backup <> n_legs then
    raise exception
      'Guarda G1: backup tem % linha(s), weekend_legs tem %. Confira a PARTE A antes de prosseguir.',
      n_backup, n_legs;
  end if;

  -- G2 — fidelidade: backup == weekend_legs, SEM normalização de texto (nem em
  -- status, nem em notes). O backup foi copiado de weekend_legs por
  -- `insert ... select`, sem transformação nenhuma — '' e NULL não podem
  -- divergir aqui por diferença de formato: se aparecerem diferentes, é
  -- porque o dado em weekend_legs MUDOU entre a PARTE A e a PARTE B, que é
  -- exatamente o evento que esta guarda existe para detectar. Normalizar
  -- cegaria a guarda para o único caso real que ela deveria pegar. (Contraste
  -- com a G4 abaixo, que normaliza texto por um motivo oposto.)
  --
  -- SE ESTA GUARDA ESTOURAR: PARE E LEVE AO CHAT DE PLANEJAMENTO. NUNCA
  -- REFAÇA O BACKUP POR CIMA PARA "FAZER PASSAR" — isso apagaria a prova do
  -- que mudou.
  select count(*) into n_fidelidade
  from weekend_legs l
  join weekend_legs_legacy_columns_backup b on b.id = l.id
  where l.price_ceiling is distinct from b.price_ceiling
     or l.status         is distinct from b.status
     or l.notes          is distinct from b.notes
     or l.paid_price     is distinct from b.paid_price
     or l.purchased_at   is distinct from b.purchased_at;
  if n_fidelidade > 0 then
    raise exception
      'Guarda G2: % perna(s) com valor diferente entre weekend_legs e o backup — o dado mudou depois da PARTE A. PARE, não refaça o backup por cima; leve ao chat de planejamento.',
      n_fidelidade;
  end if;

  -- G3 — uniformidade do teto legado (min = max, zero nulos em
  -- weekend_legs.price_ceiling). weekend_default_ceiling é lido só para
  -- aparecer na mensagem de erro/contexto — NÃO entra em nenhuma condição
  -- desta guarda, e um critério de desempate diferente entre usuários não
  -- mudaria a decisão. Não se exige igualdade entre os dois valores:
  -- price_ceiling está congelado desde que o painel parou de escrever nele
  -- (03/08/2026, pendências 3/4 da Etapa 4.2), enquanto weekend_default_ceiling
  -- é o teto vivo do usuário, já recalibrado uma vez (250 -> 300, 04/08/2026).
  -- São dois números diferentes por desenho — exigir igualdade faria esta
  -- guarda falhar sempre, por um motivo que não indica problema nenhum.
  select min(price_ceiling), max(price_ceiling),
         count(*) filter (where price_ceiling is null)
    into v_min_teto, v_max_teto, n_teto_nulo
  from weekend_legs;

  select weekend_default_ceiling into v_padrao_hoje
  from settings order by user_id asc limit 1;

  if v_min_teto is distinct from v_max_teto or n_teto_nulo > 0 then
    raise exception
      'Guarda G3: price_ceiling não é uniforme em weekend_legs (min=%, max=%, nulos=%). Teto padrão vivo hoje (settings.weekend_default_ceiling, só informativo aqui): %. PARE e revise antes de prosseguir.',
      v_min_teto, v_max_teto, n_teto_nulo, v_padrao_hoje;
  end if;

  -- G4 — reconfirmação da zero-divergência do diagnóstico: status/notes/
  -- paid_price/purchased_at EFETIVOS (weekend_leg_effective, mesma regra de
  -- "comprada só quando todos os usuários concordam" da pendência 13 da Etapa
  -- 4.2) batem com os valores legados. LEFT JOIN de propósito: com INNER JOIN,
  -- toda perna sem linha em weekend_leg_user_state (o modelo é preguiçoso — a
  -- linha só nasce quando alguém decide algo) sumiria da consulta e a guarda
  -- aprovaria sem ter checado quase nada. Agregado por leg_id, não linha a
  -- linha, para a guarda não multiplicar quando existir um segundo usuário.
  -- price_ceiling fica FORA desta guarda de propósito — a G3 já cobre, e
  -- divergir dele é o esperado (o legado é 1 valor global; o novo é por
  -- perna x usuário).
  --
  -- Normalização de texto (nullif(btrim(coalesce(...)))) É CORRETA aqui, ao
  -- contrário da G2: os dois lados vêm de mundos preenchidos por caminhos e
  -- épocas diferentes (coluna legada x weekend_leg_user_state), então '' de
  -- um lado e NULL do outro é ruído de formato, não divergência de decisão.
  select count(*) into n_g4
  from (
    select
      l.id,
      -- coalesce nos dois lados: status legado é not null hoje, mas sem o
      -- coalesce à esquerda um NULL futuro faria `l.status = 'purchased'`
      -- devolver NULL, e `NULL is distinct from false` marcaria divergência
      -- que não existe.
      (coalesce(l.status, 'monitoring') = 'purchased')                as legado_purchased,
      bool_and(coalesce(st.status, 'monitoring') = 'purchased')       as efetivo_purchased,
      (max(nullif(btrim(coalesce(st.notes, '')), ''))
         is distinct from nullif(btrim(coalesce(l.notes, '')), ''))   as diverge_notes,
      (max(st.paid_price)   is distinct from l.paid_price)            as diverge_paid,
      (max(st.purchased_at) is distinct from l.purchased_at)          as diverge_purchased
    from weekend_legs l
    left join weekend_leg_user_state st on st.leg_id = l.id
    group by l.id, l.status, l.notes, l.paid_price, l.purchased_at
  ) x
  where legado_purchased is distinct from efetivo_purchased
     or diverge_notes
     or diverge_paid
     or diverge_purchased;

  if n_g4 > 0 then
    raise exception
      'Guarda G4: % perna(s) com status/notes/paid_price/purchased_at efetivo divergente do legado — a zero-divergência do diagnóstico não se sustenta mais. PARE e revise antes de prosseguir.',
      n_g4;
  end if;

  -- Este raise notice NÃO aparece no SQL Editor do Supabase (ver nota no
  -- cabeçalho da PARTE B) — fica só para quem rodar via psql/outro cliente.
  raise notice 'Guardas G0-G4 passaram: % pernas, backup íntegro, teto legado uniforme em %, zero divergência efetiva.',
    n_legs, v_min_teto;
end $$;

alter table weekend_legs drop column price_ceiling;
alter table weekend_legs drop column status;
alter table weekend_legs drop column notes;
alter table weekend_legs drop column paid_price;
alter table weekend_legs drop column purchased_at;

-- Prova final — resultado único.
select
  (select count(*) from information_schema.columns
     where table_schema = 'public' and table_name = 'weekend_legs'
       and column_name in ('price_ceiling', 'status', 'notes', 'paid_price', 'purchased_at')
  )                                                                  as colunas_legadas_restantes, -- esperado 0
  (select count(*) from weekend_legs_legacy_columns_backup)          as linhas_no_backup;


-- ============================================================================
-- RECEITA DE RESTAURAÇÃO (comentário — não executa sozinho).
--
-- Devolve os DADOS e a ESTRUTURA das 5 colunas, mas NÃO desfaz nada que tenha
-- sido escrito depois do DROP (ex.: pernas novas criadas sem essas colunas,
-- ou qualquer código que passe a assumir a ausência delas).
--
-- 1) Recriar as colunas, com os tipos e defaults reais (BLOCO 0, rodado em
--    06/08/2026, registrado em PLANO-ATIVO.md, Etapa 4.3, item 3):
--
--    alter table weekend_legs add column price_ceiling numeric not null default 200;
--    alter table weekend_legs add column status        text    not null default 'monitoring'::text;
--    alter table weekend_legs add column notes         text;
--    alter table weekend_legs add column paid_price    numeric;
--    alter table weekend_legs add column purchased_at  timestamptz;
--
--    O `not null` de price_ceiling e de status SÓ é possível aqui porque cada
--    um tem `default` — sem default, adicionar coluna `not null` numa tabela
--    já populada (132 linhas) falharia, porque o Postgres precisa de um valor
--    para preencher as linhas existentes no mesmo instante em que a coluna
--    nasce not null.
--
-- 2) Repovoar a partir do backup:
--
--    update weekend_legs w
--    set price_ceiling = b.price_ceiling,
--        status         = b.status,
--        notes          = b.notes,
--        paid_price     = b.paid_price,
--        purchased_at   = b.purchased_at
--    from weekend_legs_legacy_columns_backup b
--    where b.id = w.id;
--
-- 3) Reaplicar check constraints / índices: ESTE ITEM FICA VAZIO DE PROPÓSITO,
--    não por esquecimento — o inventário do BLOCO 0, rodado em 06/08/2026,
--    não encontrou nenhuma constraint (check, FK, unique ou exclusion) nem
--    nenhum índice citando qualquer uma das 5 colunas. Foi verificado, não
--    pulado.
-- ============================================================================
