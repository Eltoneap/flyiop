-- ============================================================================
-- APOSENTADO em 05/08/2026: hardcoded para c_default_legado = 250, valor que
-- deixou de ser o padrão em 04/08/2026 (recalibrado para 300). Não
-- re-executar sem revisar o valor. Script de migração pontual da Etapa 4.2,
-- não reutilizável como está.
-- ============================================================================
-- Nota somada em 07/08/2026 (Etapa 4.3, Passo 4): alem do hardcode do teto
-- 250 que motivou a aposentadoria em 05/08/2026, este script agora tambem
-- QUEBRA. O Bloco 0 le status, notes, paid_price, purchased_at
-- e price_ceiling de weekend_legs - colunas REMOVIDAS em 06/08/2026
-- (commit ce0d8b3). A falha ocorre no primeiro bloco do arquivo.
-- Aposentadoria reforcada: nao re-rodar, nem parcialmente.
--
-- Etapa 4.2 — re-sync do estado do mundo antigo (weekend_legs) para o mundo
-- novo (weekend_leg_user_state). Pendências 1 e 2 do PLANO-ATIVO.md.
--
-- REGRA CENTRAL (chat de planejamento, 03/08/2026): NÃO-SOBRESCRITA POR CAMPO.
-- Só escreve num campo quando ele ainda está vazio para aquele leg_id+user_id.
-- Onde o painel novo já gravou, o painel vence: o valor de weekend_legs é
-- descartado e NENHUMA linha de auditoria é gerada para aquele campo.
--
-- Motivo: as pendências 3/4 já entraram (531f34f, 9436bc0, 03/08/2026) e o
-- painel (docs/js/compras.js) já escreve em weekend_leg_user_state. O desenho
-- original assumia rodar o re-sync ANTES dessa virada; não é mais possível.
--
-- COMO RODAR: um bloco por execução no SQL Editor do Supabase, nesta ordem —
--   BLOCO 0 (pré-voo, somente leitura) -> ler o resultado
--   BLOCO 0.2 (detalhe, só se o Bloco 0 acusar linhas ambíguas/descartadas)
--   BLOCO 1 (execução)                 -> ler o relatório da última linha
--   BLOCO 2 (pós-execução/idempotência)
--
-- NÃO re-rodar o guarda 1c de sql/etapa4_1_estado_por_usuario.sql: ele exige
-- todas as pernas em price_ceiling = 250, que é exatamente o caso que a
-- pendência 2 (Parte B, abaixo) existe para tratar.
--
-- ----------------------------------------------------------------------------
-- VALIDADE: SÓ ANTES DA ETAPA 7 (registro a)
-- ----------------------------------------------------------------------------
-- A guarda G1 exige exatamente 1 conta em auth.users e 1 linha em settings.
-- As Partes A e B usam `cross join settings` para descobrir o dono do estado —
-- com duas contas isso replicaria o estado pessoal do usuário atual para o
-- outro usuário. Portanto: este script só funciona ANTES da criação da conta
-- do segundo usuário (Etapa 7). Depois dela ele para de rodar de forma
-- permanente e por design — não é bug, e a correção não é afrouxar a guarda, é
-- reescrever a atribuição de dono. Se a Etapa 7 já aconteceu, este arquivo
-- está vencido.
--
-- ----------------------------------------------------------------------------
-- LIMITES CONHECIDOS
-- ----------------------------------------------------------------------------
-- (b) A janela de 5 minutos após o marco da 4.1 (origin = 'migracao') é usada
--     para inferir "esta linha ainda é a fotografia da 4.1, o painel não
--     encostou nela". É HEURÍSTICA TEMPORAL, NÃO PROVA. A 4.1 grava o marco
--     (Bloco 7a) e as linhas de estado (Bloco 7b) na mesma transação, então na
--     prática os timestamps coincidem; a folga cobre execução fatiada. Duas
--     consequências: uma linha criada pelo painel dentro dessa janela seria
--     lida como fotografia, e uma linha que a Parte B tocou numa execução
--     anterior passa a contar como "tocada" na execução seguinte (falso
--     positivo conservador — a linha fica de fora e é reportada, nunca é
--     escrita por engano).
--
-- (c) A Parte B (pendência 2) na prática só cobre um intervalo JÁ FECHADO.
--     Desde as pendências 3/4 (03/08/2026) o painel não escreve mais em
--     weekend_legs.price_ceiling — escreve em weekend_leg_user_state. Então a
--     única janela em que um teto podia ter ido parar na coluna velha é
--     01/08 -> 03/08/2026, medida no chat de planejamento em ZERO
--     divergências. `p2_tetos_divergentes = 0` e `p2_tetos_a_escrever = 0` no
--     Bloco 0 é o RESULTADO ESPERADO, não sinal de que algo quebrou. A Parte B
--     fica no arquivo como rede de segurança e como registro do desenho.
--
-- (d) "Campo vazio" só prova "nunca escrito" em price_ceiling. O painel
--     (docs/js/compras.js) valida o teto (`!value || value <= 0` aborta) e não
--     tem ação de limpar override — então price_ceiling NULL é prova. Já
--     status/notes/paid_price/purchased_at o painel grava vazio de propósito:
--     limpar observações grava NULL, limpar valor pago grava NULL, e "Desfazer
--     compra" grava status='monitoring' + purchased_at=NULL. Por isso vazio,
--     nesses quatro, é AMBÍGUO — ver a Parte A e o contador
--     `parte_a_ambiguas_ignoradas` do relatório do Bloco 1.
--
-- (e) Escrita de teto sem linha de auditoria, caso raro: se o teto antigo
--     divergente for numericamente igual ao settings.weekend_default_ceiling
--     atual (ex.: legado 300 e padrão já mudado para 300), a Parte B grava o
--     override explícito mas a trigger não registra nada, porque o TETO
--     EFETIVO não mudou. É o desenho declarado da 4.1
--     (sql/etapa4_1_estado_por_usuario.sql:291-299), não um bug. O Bloco 0
--     mostra `teto_padrao_hoje` para o caso ficar visível antes de rodar.
--
-- (f) 250 é constante HISTÓRICA (o que "nunca foi editado" significa no mundo
--     antigo), não o teto padrão atual do usuário. Perna que continua em 250
--     segue com price_ceiling NULL e passa a valer o padrão do usuário, seja
--     ele qual for. Propriedade herdada da 4.1 (que também não copiou teto),
--     não introduzida aqui.
--
-- (g) Janela aberta 2 continua de pé: o robô e o Telegram ainda leem
--     weekend_legs.price_ceiling. Este re-sync não fecha isso — quem fecha é a
--     Etapa 6.
-- ============================================================================


-- ============================================================================
-- BLOCO 0 — PRÉ-VOO (somente leitura). Uma linha, todas as contagens.
-- Rodar sozinho e ler antes de encostar no Bloco 1.
-- ============================================================================
with t41 as (
  select max(changed_at) as ts
  from weekend_leg_ceiling_audit
  where origin = 'migracao'
), base as (
  select
    l.id                                     as leg_id,
    s.user_id                                as user_id,
    l.status                                 as ant_status,
    nullif(btrim(coalesce(l.notes, '')), '') as ant_notes,
    l.paid_price                             as ant_paid,
    l.purchased_at                           as ant_purchased,
    l.price_ceiling                          as ant_ceiling,
    st.id                                    as novo_id,
    st.status                                as novo_status,
    nullif(btrim(coalesce(st.notes, '')), '') as novo_notes,
    st.paid_price                            as novo_paid,
    st.purchased_at                          as novo_purchased,
    st.price_ceiling                         as novo_ceiling,
    -- "o painel novo encostou nesta linha" = ela NÃO é mais a fotografia
    -- intocada da 4.1. Ver limite (b) no cabeçalho.
    (st.id is not null and not (
         st.updated_at = st.created_at
     and st.created_at <= (select ts from t41) + interval '5 minutes'
    ))                                       as tocada_pelo_painel
  from weekend_legs l
  cross join settings s
  left join weekend_leg_user_state st
    on st.leg_id = l.id and st.user_id = s.user_id
)
select
  (select count(*) from auth.users)                      as usuarios_auth,
  (select count(*) from settings)                        as usuarios_settings,
  (select ts from t41)                                   as marco_4_1,
  (select weekend_default_ceiling from settings limit 1) as teto_padrao_hoje,
  count(*) filter (where ant_status not in ('monitoring','purchased'))
                                                         as g_status_invalido,

  -- Pendência 1 (Parte A) — o que SERÁ escrito
  count(*) filter (where novo_id is null and (
       ant_paid is not null or ant_notes is not null
    or ant_purchased is not null or ant_status is distinct from 'monitoring'))
                                                         as p1_linhas_a_inserir,
  count(*) filter (where novo_id is not null and not tocada_pelo_painel
    and novo_status = 'monitoring' and ant_status is distinct from 'monitoring')
                                                         as p1_status_a_escrever,
  count(*) filter (where novo_id is not null and not tocada_pelo_painel
    and novo_notes is null and ant_notes is not null)    as p1_notes_a_escrever,
  count(*) filter (where novo_id is not null and not tocada_pelo_painel
    and novo_paid is null and ant_paid is not null)      as p1_paid_a_escrever,
  count(*) filter (where novo_id is not null and not tocada_pelo_painel
    and novo_purchased is null and ant_purchased is not null)
                                                         as p1_purchased_a_escrever,

  -- Pendência 1 — linhas DEIXADAS DE FORA por ambiguidade (Correção 2):
  -- o campo está vazio no mundo novo, mas o painel já encostou na linha, então
  -- não dá para distinguir "nunca escrito" de "limpo de propósito". Estas
  -- linhas NÃO são escritas pelo Bloco 1 — vão para tratamento manual, uma a
  -- uma, pelo Bloco 0.2. Não é erro do script; é a regra funcionando.
  count(*) filter (where tocada_pelo_painel and (
       (novo_status = 'monitoring' and ant_status is distinct from 'monitoring')
    or (novo_notes is null     and ant_notes is not null)
    or (novo_paid is null      and ant_paid is not null)
    or (novo_purchased is null and ant_purchased is not null)
  ))                                                     as p1_ambiguas_ficam_de_fora,

  -- Pendência 2 (Parte B) — teto divergente do padrão histórico (250).
  -- Esperado hoje: ambos 0. Ver limite (c) no cabeçalho.
  count(*) filter (where ant_ceiling is distinct from 250)
                                                         as p2_tetos_divergentes,
  count(*) filter (where ant_ceiling is distinct from 250 and novo_ceiling is null)
                                                         as p2_tetos_a_escrever,

  -- O que a não-sobrescrita descarta porque o mundo novo tem valor DIFERENTE
  count(*) filter (where novo_id is not null and (
       (ant_notes     is not null and novo_notes     is not null and novo_notes     is distinct from ant_notes)
    or (ant_paid      is not null and novo_paid      is not null and novo_paid      is distinct from ant_paid)
    or (ant_purchased is not null and novo_purchased is not null and novo_purchased is distinct from ant_purchased)
    or (ant_ceiling is distinct from 250 and novo_ceiling is not null and novo_ceiling is distinct from ant_ceiling)
  ))                                                     as descartados_painel_vence
from base;


-- ============================================================================
-- BLOCO 0.2 — DETALHE, perna a perna. Rodar só se o Bloco 0 acusar
-- p1_ambiguas_ficam_de_fora > 0 ou descartados_painel_vence > 0.
-- É aqui que se decide manualmente o que fazer com cada linha ambígua — o
-- Bloco 1 nunca decide isso sozinho.
-- ============================================================================
with t41 as (
  select max(changed_at) as ts
  from weekend_leg_ceiling_audit
  where origin = 'migracao'
)
select
  l.id as leg_id, w.outbound_date, l.direction,
  l.status        as ant_status,     st.status        as novo_status,
  l.notes         as ant_notes,      st.notes         as novo_notes,
  l.paid_price    as ant_paid,       st.paid_price    as novo_paid,
  l.purchased_at  as ant_purchased,  st.purchased_at  as novo_purchased,
  l.price_ceiling as ant_ceiling,    st.price_ceiling as novo_ceiling,
  st.created_at, st.updated_at,
  (not (st.updated_at = st.created_at
        and st.created_at <= (select ts from t41) + interval '5 minutes'))
                                     as tocada_pelo_painel
from weekend_legs l
join weekends w on w.id = l.weekend_id
cross join settings s
join weekend_leg_user_state st
  on st.leg_id = l.id and st.user_id = s.user_id
where
     (nullif(btrim(coalesce(l.notes,'')),'') is not null
      and nullif(btrim(coalesce(st.notes,'')),'') is distinct from nullif(btrim(coalesce(l.notes,'')),''))
  or (l.paid_price   is not null and st.paid_price   is distinct from l.paid_price)
  or (l.purchased_at is not null and st.purchased_at is distinct from l.purchased_at)
  or (l.status is distinct from 'monitoring' and st.status is distinct from l.status)
  or (l.price_ceiling is distinct from 250 and st.price_ceiling is distinct from l.price_ceiling)
order by w.outbound_date, l.direction;


-- ============================================================================
-- BLOCO 1 — EXECUÇÃO.
--
-- Rodar as TRÊS instruções abaixo numa execução só (a tabela temporária, o
-- do $$ $$ e o select final). O relatório do select final é a ÚNICA forma de
-- conferir o resultado: `raise notice` não aparece no SQL Editor do Supabase,
-- que só exibe o resultado do último select de uma execução.
--
-- O do $$ $$ é uma instrução única = uma transação: guarda que estoura não
-- deixa nada escrito, e o set_config de origem da auditoria não escapa do
-- bloco.
-- ============================================================================

drop table if exists _flyiop_resync_report;
create temp table _flyiop_resync_report (
  executado_em                     timestamptz,
  marco_4_1                        timestamptz,
  teto_padrao_hoje                 numeric,
  parte_a_linhas                   int,
  parte_a_ambiguas_ignoradas       int,
  parte_b_linhas                   int,
  auditoria_linhas_novas           int,
  auditoria_resync_override_total  int
);

do $$
declare
  -- 250 é o padrão HISTÓRICO do mundo antigo — ver limite (f) no cabeçalho.
  c_default_legado constant numeric := 250;
  -- Folga da heurística temporal — ver limite (b) no cabeçalho.
  c_folga_marco    constant interval := interval '5 minutes';
  v_t41         timestamptz;
  v_padrao      numeric;
  n_users       int;
  n_settings    int;
  n_status      int;
  n_ambiguo     int;
  n_a           int;
  n_b           int;
  n_audit_ini   int;
  n_audit_fim   int;
  n_audit_over  int;
begin
  -- (G1) Uma conta só. Ver "VALIDADE: SÓ ANTES DA ETAPA 7" no cabeçalho.
  select count(*) into n_users    from auth.users;
  select count(*) into n_settings from settings;
  if n_users <> 1 or n_settings <> 1 then
    raise exception
      'Guarda G1: esperava 1 conta em auth.users e 1 linha em settings, encontrei % e %. O cross join replicaria o estado pessoal de um usuário para o outro. Se a Etapa 7 já rodou, este script está vencido — não afrouxar a guarda.',
      n_users, n_settings;
  end if;

  select weekend_default_ceiling into v_padrao from settings limit 1;

  -- (G2) O marco da 4.1 é a referência temporal de "linha ainda intocada".
  select max(changed_at) into v_t41
  from weekend_leg_ceiling_audit where origin = 'migracao';
  if v_t41 is null then
    raise exception
      'Guarda G2: não achei linha de auditoria com origin = ''migracao''. A 4.1 (Bloco 7a) não rodou, ou a auditoria foi apagada — revisar antes de rodar.';
  end if;

  -- (G3) weekend_legs.status não tem check constraint; weekend_leg_user_state
  -- tem (wlus_status_check). Valor fora do domínio estouraria no meio da cópia.
  select count(*) into n_status
  from weekend_legs where status not in ('monitoring','purchased');
  if n_status > 0 then
    raise exception
      'Guarda G3: % perna(s) com status fora de (monitoring, purchased). wlus_status_check rejeitaria a cópia — revisar antes de rodar.',
      n_status;
  end if;

  -- Contagem das linhas AMBÍGUAS, medida ANTES da Parte A (que mexe em
  -- updated_at). Estas linhas são excluídas por construção da Parte A abaixo;
  -- aqui só se conta para o relatório. Não existe "liberar geral": cada uma é
  -- decidida à mão pelo Bloco 0.2, fora deste script.
  select count(*) into n_ambiguo
  from weekend_legs l
  cross join settings s
  join weekend_leg_user_state st on st.leg_id = l.id and st.user_id = s.user_id
  where (
        (st.status = 'monitoring' and l.status is distinct from 'monitoring')
     or (nullif(btrim(coalesce(st.notes,'')),'') is null and nullif(btrim(coalesce(l.notes,'')),'') is not null)
     or (st.paid_price   is null and l.paid_price   is not null)
     or (st.purchased_at is null and l.purchased_at is not null)
  ) and not (
        st.updated_at = st.created_at
    and st.created_at <= v_t41 + c_folga_marco
  );

  select count(*) into n_audit_ini from weekend_leg_ceiling_audit;

  -- =========================================================================
  -- PARTE A — pendência 1: status / notes / paid_price / purchased_at.
  --
  -- NÃO toca em price_ceiling (nem no insert, nem no do update) — por isso não
  -- pode gerar nenhuma linha de auditoria:
  --   insert: price_ceiling = null -> teto efetivo antes = depois = padrão;
  --   update: price_ceiling ausente do SET -> old = new na trigger.
  -- Por isso a Parte A roda FORA do set_config de origem.
  -- =========================================================================
  insert into weekend_leg_user_state
    (leg_id, user_id, price_ceiling, status, notes, paid_price, purchased_at)
  select
    l.id,
    s.user_id,
    null,                                       -- teto é assunto da Parte B
    l.status,
    nullif(btrim(coalesce(l.notes, '')), ''),   -- '' do mundo antigo entra como NULL
    l.paid_price,
    l.purchased_at
  from weekend_legs l
  cross join settings s
  where l.paid_price is not null
     or nullif(btrim(coalesce(l.notes, '')), '') is not null
     or l.purchased_at is not null
     or l.status is distinct from 'monitoring'
  on conflict (leg_id, user_id) do update set
    -- Cada campo tem seu próprio guarda: uma linha que entra no update por
    -- causa de 'notes' não pode carregar 'status' junto.
    status = case
               when weekend_leg_user_state.status = 'monitoring'
                and excluded.status is distinct from 'monitoring'
               then excluded.status
               else weekend_leg_user_state.status
             end,
    notes = case
              when nullif(btrim(coalesce(weekend_leg_user_state.notes, '')), '') is null
               and excluded.notes is not null
              then excluded.notes
              else weekend_leg_user_state.notes
            end,
    paid_price   = coalesce(weekend_leg_user_state.paid_price,   excluded.paid_price),
    purchased_at = coalesce(weekend_leg_user_state.purchased_at, excluded.purchased_at)
  where
    -- (1) NÃO-SOBRESCRITA + "só quando o valor mudou": tem que existir pelo
    -- menos um campo VAZIO com valor novo para receber. É o que dá
    -- idempotência — na segunda rodada nada mais está vazio, o update não
    -- acontece e updated_at não muda.
    (
         (weekend_leg_user_state.status = 'monitoring' and excluded.status is distinct from 'monitoring')
      or (nullif(btrim(coalesce(weekend_leg_user_state.notes, '')), '') is null and excluded.notes is not null)
      or (weekend_leg_user_state.paid_price   is null and excluded.paid_price   is not null)
      or (weekend_leg_user_state.purchased_at is null and excluded.purchased_at is not null)
    )
    -- (2) AMBIGUIDADE EXCLUÍDA POR CONSTRUÇÃO: só escreve em linha que ainda é
    -- a fotografia intocada da 4.1. Em linha que o painel já encostou, vazio
    -- pode significar "limpo de propósito" (docs/js/compras.js grava
    -- notes=null, paid_price=null e status='monitoring'+purchased_at=null em
    -- "Desfazer compra") — nesse caso o script não escreve, apenas reporta em
    -- parte_a_ambiguas_ignoradas.
    and weekend_leg_user_state.updated_at = weekend_leg_user_state.created_at
    and weekend_leg_user_state.created_at <= v_t41 + c_folga_marco;

  get diagnostics n_a = row_count;

  -- =========================================================================
  -- PARTE B — pendência 2: teto editado no painel VELHO entre a 4.1 e a 4.2
  -- vira override explícito, com origem própria na auditoria.
  -- Esperado hoje: 0 linhas — ver limite (c) no cabeçalho.
  -- set_config é lido por flyiop_audit_origin()
  -- (sql/etapa4_1_estado_por_usuario.sql:206).
  -- =========================================================================
  perform set_config('flyiop.audit_origin', 'resync_override', true);

  insert into weekend_leg_user_state (leg_id, user_id, price_ceiling)
  select l.id, s.user_id, l.price_ceiling
  from weekend_legs l
  cross join settings s
  where l.price_ceiling is distinct from c_default_legado
  on conflict (leg_id, user_id) do update set
    price_ceiling = excluded.price_ceiling
  -- Não-sobrescrita EXATA: price_ceiling NULL é prova de que o painel nunca
  -- escreveu ali (ele valida `!value || value <= 0` e não tem "limpar
  -- override"). Também é o que dá idempotência: na 2ª rodada não é mais NULL,
  -- o update não acontece e não nasce segunda linha de auditoria.
  where weekend_leg_user_state.price_ceiling is null;

  get diagnostics n_b = row_count;

  -- Desarma a origem ainda dentro do bloco: flyiop_audit_origin() só usa o
  -- override quando ele é <> ''. Se o editor rodar tudo numa transação só,
  -- nada depois daqui herda 'resync_override'.
  perform set_config('flyiop.audit_origin', '', true);

  select count(*) into n_audit_fim from weekend_leg_ceiling_audit;
  select count(*) into n_audit_over
  from weekend_leg_ceiling_audit where origin = 'resync_override';

  insert into _flyiop_resync_report values (
    now(), v_t41, v_padrao,
    n_a, n_ambiguo, n_b,
    n_audit_fim - n_audit_ini, n_audit_over
  );
end $$;

-- Relatório da execução. ÚNICA forma de conferir o que o Bloco 1 fez.
-- Leitura esperada:
--   parte_a_linhas .................. linhas inseridas/atualizadas na pendência 1
--   parte_a_ambiguas_ignoradas ...... linhas NÃO escritas por ambiguidade;
--                                     tratar uma a uma pelo Bloco 0.2. Não é erro.
--   parte_b_linhas .................. overrides de teto gravados (esperado 0)
--   auditoria_linhas_novas .......... tem que ser IGUAL a parte_b_linhas
--                                     (a Parte A não pode gerar auditoria)
--   auditoria_resync_override_total . acumulado de todas as execuções
select * from _flyiop_resync_report;


-- ============================================================================
-- BLOCO 2 — PÓS-EXECUÇÃO E IDEMPOTÊNCIA. Uma linha.
--
-- Critério de aceite (Correção 3): o que importa é `pendente_de_verdade`.
--   pendente_de_verdade ........... mundo antigo tem valor, mundo novo está
--                                   vazio, e a linha NÃO é ambígua (ninguém
--                                   dos dois lados mexeu de forma conflitante).
--                                   TEM que ser 0 — se não for, o script falhou.
--   ignorado_por_nao_sobrescrita .. o mundo novo já tinha valor diferente, ou o
--                                   campo está numa linha ambígua deixada de
--                                   fora pela Parte A. Pode ser > 0 sem que
--                                   nada esteja errado: é a regra funcionando.
--                                   Se > 0, conferir pelo Bloco 0.2.
--
-- Idempotência: rodar o BLOCO 1 de novo -> relatório com parte_a_linhas = 0,
-- parte_b_linhas = 0 e auditoria_linhas_novas = 0; rodar este BLOCO 2 de novo
-- -> resultado idêntico.
-- ============================================================================
with t41 as (
  select max(changed_at) as ts
  from weekend_leg_ceiling_audit
  where origin = 'migracao'
), base as (
  select
    l.status                                  as ant_status,
    nullif(btrim(coalesce(l.notes,'')),'')    as ant_notes,
    l.paid_price                              as ant_paid,
    l.purchased_at                            as ant_purchased,
    l.price_ceiling                           as ant_ceiling,
    st.id                                     as novo_id,
    coalesce(st.status,'monitoring')          as novo_status,
    nullif(btrim(coalesce(st.notes,'')),'')   as novo_notes,
    st.paid_price                             as novo_paid,
    st.purchased_at                           as novo_purchased,
    st.price_ceiling                          as novo_ceiling,
    (st.id is not null and not (
         st.updated_at = st.created_at
     and st.created_at <= (select ts from t41) + interval '5 minutes'
    ))                                        as tocada_pelo_painel
  from weekend_legs l
  cross join settings s
  left join weekend_leg_user_state st
    on st.leg_id = l.id and st.user_id = s.user_id
)
select
  (select count(*) from weekend_leg_user_state)                                 as linhas_de_estado,
  (select count(*) from weekend_leg_user_state where status = 'purchased')      as compradas,
  (select count(*) from weekend_leg_user_state where paid_price is not null)    as com_valor_pago,
  (select count(*) from weekend_leg_user_state where price_ceiling is not null) as tetos_explicitos,
  (select string_agg(origin || '=' || n, ', ' order by origin)
     from (select origin, count(*) n from weekend_leg_ceiling_audit group by 1) x)
                                                                                as auditoria_por_origem,

  -- FALHA REAL se > 0
  count(*) filter (where
       ((not tocada_pelo_painel) and (
            (ant_status is distinct from 'monitoring' and novo_status = 'monitoring')
         or (ant_notes     is not null and novo_notes     is null)
         or (ant_paid      is not null and novo_paid      is null)
         or (ant_purchased is not null and novo_purchased is null)))
    or (ant_ceiling is distinct from 250 and novo_ceiling is null)
  )                                                                             as pendente_de_verdade,

  -- ESPERADO, não é erro: a não-sobrescrita decidiu ignorar o mundo antigo
  count(*) filter (where
       (tocada_pelo_painel and (
            (ant_status is distinct from 'monitoring' and novo_status = 'monitoring')
         or (ant_notes     is not null and novo_notes     is null)
         or (ant_paid      is not null and novo_paid      is null)
         or (ant_purchased is not null and novo_purchased is null)))
    or (ant_notes     is not null and novo_notes     is not null and novo_notes     is distinct from ant_notes)
    or (ant_paid      is not null and novo_paid      is not null and novo_paid      is distinct from ant_paid)
    or (ant_purchased is not null and novo_purchased is not null and novo_purchased is distinct from ant_purchased)
    or (ant_ceiling is distinct from 250 and novo_ceiling is not null and novo_ceiling is distinct from ant_ceiling)
  )                                                                             as ignorado_por_nao_sobrescrita
from base;
