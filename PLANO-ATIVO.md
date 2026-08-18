# Plano Ativo — FlyIop

_Atualizado em 02/08/2026. Contém só o que está em execução ou pendente de aprovação/implementação. Tudo que já foi entregue (com data e decisões tomadas) está em `HISTORICO.md` — referencie por lá em vez de reproduzir aqui._

**Regra de apresentação (24/07/2026):** ao apresentar um plano ou atualização no chat, mostrar só a seção nova/alterada, nunca o arquivo inteiro. Para contexto, referenciar a seção pelo nome (ex.: "ver Parte 8 no HISTORICO.md") em vez de reproduzir. O arquivo completo fica no disco; o chat recebe só o delta. (Ver também `PROTOCOLO-DE-TRABALHO.md`.)

---

## Diagnóstico: caminho de alerta de perna de fim de semana (31/07/2026)

`alert_log` tem 0 registros com `leg_id` desde que a coluna existe
(23/07/2026): o caminho de alerta de PERNA de fim de semana nunca disparou em
produção. Sessão de diagnóstico somente-leitura de 31/07/2026 não encontrou
defeito estrutural — `should_alert` é calculado corretamente, `is_good_price`
funciona, cooldown não bloqueia o primeiro disparo, `insert_weekend_alert_log`
roda logo após o envio sem try/except engolindo erro, `weekend_leg_run_log`
não registra nenhum `outcome = 'error'` nos checks investigados. A aparência
inicial de "oportunidades perdidas" (preços históricos abaixo do teto atual)
era artefato de comparar preço histórico contra o teto de HOJE, não contra o
teto vigente na época do check — `weekend_legs.price_ceiling` não tem
histórico/auditoria (ver pendência (d) abaixo).

### (a) e (b) ✅ CONCLUÍDOS (01/08/2026) — movidos para o `HISTORICO.md`

Caminho de alerta de perna confirmado em produção (13 alertas gravados em
`alert_log`) e gatilho `push` removido do `daily.yml`. Detalhe completo no
`HISTORICO.md`, item 16.

### (c) ✅ DECIDIDA (chat de planejamento, 02/08/2026) — reavaliação fora da coleta

`should_alert` só é calculado no momento em que a perna é checada. O robô
nunca reavalia um `current_price` já salvo contra um teto novo. Consequência:
editar o teto no site não tem efeito nenhum no Telegram até a perna voltar
na rotação (hoje ~3 dias, ver item 1 do `STATE.md`). Isso afeta diretamente
a recalibração do teto padrão (`STATE.md`, seção 3): baixar o teto não muda
comportamento de alerta até cada perna dar a volta, sem sinal disso em lugar
nenhum. Nunca foi decisão explícita — é herança do código.

**Decisão: opção (a), e vai para a Etapa 4.2.** A reavaliação roda **ao fim de
cada execução primária**, **sem nenhuma chamada extra de scraping** (reavalia
o `current_price` já salvo, não busca preço novo), com **trava de frescor**
(preço velho demais não vira alerta). Descartadas: (b) empurrar a perna pro
topo da fila e (c) documentar o atraso como esperado.

**Nasce DESLIGADA**, por chave em `system_config` — só é ligada depois que a
observação do cooldown com dado real (`STATE.md`, seção 3, item 1b) confirmar
o comportamento. Motivo: reavaliar todas as pernas a cada execução multiplica
o número de oportunidades de alerta, e o cooldown/dedup ainda nunca operou com
`alert_log` populada.

### (d) ✅ RESOLVIDA na Etapa 4.1 (01/08/2026) — `price_ceiling` agora tem auditoria

`weekend_legs.price_ceiling` era sobrescrito a cada edição, sem registro do
valor anterior nem de quando mudou — o sistema não conseguia responder "perdi
alguma oportunidade?", e foi exatamente o que travou parte do diagnóstico de
31/07.

**Resolvido:** a Etapa 4.1 criou `weekend_leg_ceiling_audit` (perna, usuário,
teto anterior, teto novo, origem, timestamp), append-only e **alimentada por
trigger no banco** — por ser trigger e não código de aplicação, captura
inclusive edição feita direto no SQL Editor. Ver `HISTORICO.md`, item 17.

Limite que permanece: a auditoria nasce com um marco inicial (`origin =
'migracao'`), não com histórico retroativo — continua impossível responder
"que teto valia em 20/07/2026?". Registrado em "Limites conhecidos da 4.1",
abaixo.

### (e) PERGUNTAS ABERTAS do diagnóstico de 31/07 (ainda sem resposta)

- Por que a perna `b4f28800` (return, voo 31/01/2027, `last_live_check_at`
  null, status monitoring) não foi a primeira do lote de 31/07, se a
  ordenação é "nulos/mais antigos primeiro"? (Resposta parcial já obtida
  para o caso específico investigado nessa sessão — a perna citada em outro
  ponto da conversa ficou fora por cair fora da janela de 183 dias, não por
  ordenação — mas vale confirmar se `b4f28800` tem o mesmo padrão.)
- Cache × live: uma perna registrou preço estável por dias via cache e depois
  um valor bem diferente no mesmo dia. Divergência entre fontes ou movimento
  real de preço?
- O alerta de perna pode disparar em cima de preço de CACHE (até 48h de
  atraso)? A mensagem diferencia a fonte, como fazem as rotas flexíveis? Uma
  mesma perna pode ser avaliada duas vezes no mesmo dia (passada de cache +
  lote fli)? `weekend_leg_run_log` sugere que sim.

---

## Iniciativa: suporte a segundo usuário (multi-usuário)

Decidido no chat de planejamento (29/07/2026): um amigo também vai comprar
RIO↔BSB em 2027. Escopo completo (alertas + painel próprio + aba Compras
própria). Telegram: grupo único compartilhado (não bot/chat separado por
pessoa) — mensagem identifica nome + valor do teto de quem disparou.
Detalhe da investigação em `AUDITORIA-MULTIUSUARIO.md` (fora dos três
arquivos oficiais, arquivo de trabalho desta iniciativa).

**Regra de trabalho:** cada etapa exige revisão explícita no chat de
planejamento antes de rodar. Nunca encadear etapas sozinho.

### Nota (08/08/2026) — motivo adicional para visibilidade cruzada de compra

Registrado no chat de planejamento: uma proposta de design (não aprovada,
fora do repositório) sugeriu uma camada de visibilidade cruzada entre
usuários — o outro vê que você comprou uma perna e em qual voo. Além de
sincronia geral, essa funcionalidade serve também para otimizar logística —
saber que o outro já tem voo comprado ajuda a decidir se vale dividir táxi.

**Escopo, se e quando essa funcionalidade for desenhada: visibilidade só
depois que `status` vira `purchased`.** A alternativa de expor a
intenção/voo *antes* da compra (mais útil ainda para coordenar táxi com
antecedência, mas vaza mais informação pessoal do outro) foi levantada e
**descartada por ora** — revisar só se a limitação de "só depois de
comprado" virar dor real na prática.

**Desenhada em 09/08/2026 — ver seção "Fatia C — visibilidade de compra
entre usuários" abaixo.**

### Ordem de execução

1. ✅ **Concluída (29/07/2026).** Consolidar baseline do schema legado +
   investigar uso real das colunas de `settings` (arquivo:linha) + preparar
   (sem aplicar) correção da policy de `alert_log`. Resultado completo em
   `AUDITORIA-MULTIUSUARIO.md` (seção "Etapa 1"): `routes`/`settings` têm
   RLS per-user confirmada; colunas de `settings` se dividem em 3 grupos
   (legado puro / compartilhadas via `cooldown_blocks_alert` / lidas como
   globais mas hoje per-user — `weekend_opportunity_pct`,
   `suspicious_below_avg_pct`, `fast_flights_enabled`,
   `fast_flights_daily_batch_size`); rascunho da correção de `alert_log` em
   `sql/draft_alert_log_leg_policy.sql` (não aplicado). **Aguardando revisão
   no chat de planejamento antes de liberar a Etapa 2.**
2. ✅ **Concluída (29/07/2026).** Policy de `alert_log` corrigida e aplicada
   em produção (cobre `route_id` e `leg_id`).
3. ✅ **Concluída (29/07/2026).** Separada `settings`: sistema (config
   única) × pessoal (per-user). Divisão final:
   - **Sistema** (agora em `system_config`, linha única, sem dono):
     `suspicious_below_avg_pct`, `fast_flights_enabled`,
     `fast_flights_daily_batch_size`.
   - **Pessoal** (continua em `settings`, per-user): `window_3d_pct`,
     `window_7d_pct`, `freshness_hours`, `stale_alert_policy`,
     `notification_mode`, `realert_drop_pct`, `realert_days`,
     `weekend_opportunity_pct`.
   - **Fora de escopo**: `cost_per_thousand_brl` (sem consumidor, fica como
     está).
   Implementado: `sql/system_config.sql` (rodado manualmente pelo usuário
   no SQL Editor do Supabase), `src/supabase_client.py`/`src/main.py` lendo
   de `system_config`, formulário de Configurações sem os 3 campos
   (edição agora é só via SQL Editor — ver `RUNBOOK.md`),
   `docs/js/dashboard.js` lendo o status do kill-switch de `system_config`
   (com degradação pra "desconhecido" se a consulta falhar). As 3 colunas
   antigas continuam em `settings`, intocadas e sem uso — **pendência**:
   Etapa 3b (remoção), só depois de alguns dias de produção estável.
   Detalhe/histórico da decisão em `AUDITORIA-MULTIUSUARIO.md`.
4. Tabela de decisão pessoal (`weekend_leg_user_state`: teto/status/notas/
   valor pago por usuário) + migrar dados atuais em 3 degraus:
   - **4.1** — ✅ **Concluída e verificada (01/08/2026).** Estrutura nova criada
     e dados copiados, sem que nada passe a lê-la. Rodada à mão no SQL Editor e
     verificada com os blocos A–G. Detalhe no `HISTORICO.md`, item 17;
     tabelas da verificação em `AUDITORIA-MULTIUSUARIO.md`.
   - **4.2** — frontend e robô passam a ler/escrever a estrutura nova.
     **Em revisão no chat de planejamento, ainda não aprovada** — pendências
     nomeadas abaixo, na seção "Etapa 4.2".
   - **4.3** — só depois, remover as colunas antigas de `weekend_legs`.
5. ✅ **Concluída por composição (08/08/2026).** Frontend: Compras/Dashboard
   por usuário logado; `weekend_legs` vira somente-leitura no navegador;
   redesenho de RLS de update. Coberta por trabalho feito sob outros nomes:
   "`weekend_legs` somente-leitura no navegador" = Etapa 4.4 (07/08/2026);
   "redesenho de RLS de update" = Etapa 4.1, RLS de
   `weekend_leg_user_state`, provada nos blocos F/F2; "Compras/Dashboard por
   usuário logado" = funcionalmente pela Etapa 4.2 (pendências 3/5, leitura
   via `weekend_leg_effective`), visualmente pela Fatia A/B (UI,
   `HISTORICO.md` itens 21/22).
6. Telegram: cooldown/dedup de `alert_log` por (perna × usuário); composição
   de mensagem com nome+valor; mantém o mesmo `TELEGRAM_CHAT_ID` (grupo).
   **Depende do teste do caminho de alerta de perna** (ver "Diagnóstico:
   caminho de alerta de perna de fim de semana" abaixo) — sem confirmação de
   que o alerta dispara em produção, não faz sentido construir
   cooldown/dedup por usuário em cima dele.
7. Criar conta do segundo usuário no Supabase Auth — **por último**, só
   depois de tudo testado. Regra dura: nenhuma conta nova antes disso.
   **Segunda regra dura (01/08/2026, Etapa 4.1):** criar a linha de
   `settings` do usuário é parte obrigatória de criar a conta, no mesmo
   ato. A view `weekend_leg_effective` usa `settings` como registro de
   usuários; conta sem linha em `settings` não aparece na view — nenhuma
   perna, nenhum alerta, painel vazio, e **sem erro em lugar nenhum**.
   O teste real de isolamento entre as duas contas (o que os blocos E e F
   da verificação da 4.1 só conseguem simular) é a primeira coisa a fazer
   depois de criar a conta, antes de ela receber qualquer dado.
   **PLANEJADA E TOTALMENTE DECIDIDA em 15/08/2026** — plano fatiado
   (E7-0 a E7-7), as quatro decisões de produto fechadas, lista do que só é
   verificável com duas contas e riscos/pontos sem volta na seção "Etapa 7"
   abaixo. **Gate estreitado (decisão de 15/08/2026, chat de acompanhamento da
   D4): execução liberada a partir do item 5 da verificação da D4** ("próxima
   linha de perna em `alert_log` nasce com `user_id` preenchido") **confirmado
   OK, mesmo com os itens 6-10 ainda em aberto** — itens 9 e 10 passam a
   verificação de cauda longa, em paralelo à execução da Etapa 7. Detalhe
   completo na abertura da seção "Etapa 7" abaixo.
   **✅ GATE CUMPRIDO em 17/08/2026** — item 5 confirmado por prova direta de
   banco (3 linhas de perna em `alert_log`, todas com `user_id` preenchido,
   zero NULL) e item 6 confirmado por print da mensagem do Telegram
   ("👤 Elton"). Fatias E7-0 a E7-4 concluídas; **E7-5 segue aberta** — o
   fan-out com dois `user_id` distintos na mesma execução continua sem
   observação.

**Correção de sequenciamento (31/07/2026):** as Etapas 4 e 5 são modelo de
dados e interface — valem independente de o alerta de perna funcionar (é o
que o segundo usuário precisa; ele não usa Telegram) — e podem começar em
paralelo ao teste do caminho de alerta. Só a Etapa 6 depende desse teste.
Formulação anterior (que tratava o teste como pré-requisito das Etapas 4/5)
foi revisada e está incorreta.

> **Premissa revista (15/08/2026, DEC-1, seção "Etapa 7"):** "ele não usa
> Telegram" não vale mais. O segundo usuário **entra no grupo do Telegram
> compartilhado** — a Fatia D4 (avaliação por usuário) vale como projetada,
> e as fatias E7-2/E7-5 da Etapa 7 dependem exatamente do envio de mensagem
> a ele. Texto mantido acima como registro histórico de 31/07/2026, não como
> premissa vigente.

**Pedido de antecipar a Etapa 7 (criação da conta do segundo usuário):
avaliado e recusado em 31/07/2026.** Motivo: `price_ceiling`/`status`/
`notes`/`paid_price` ainda são globais e a RLS de `weekend_legs` é genérica
hoje — qualquer autenticado sobrescreve o dado do outro, sem auditoria de
teto pra reconstruir depois (pendência (d) do diagnóstico — **a parte da
auditoria foi resolvida pela Etapa 4.1 em 01/08/2026**; as colunas globais e
a RLS genérica de `weekend_legs` continuam como estavam, e a recusa segue de
pé). A regra dura (conta nova só na Etapa 7, por último) permanece. Alternativa
considerada e descartada: travar `weekend_legs` como somente-leitura via
RLS temporária até a Etapa 4/5 ficarem prontas — descartada por mexer em
política de segurança em produção, risco de falha silenciosa ao salvar no
frontend, e por ser trabalho descartável (a RLS temporária seria jogada
fora assim que a Etapa 5 entregasse a versão definitiva). Enquanto isso, a
necessidade real do segundo usuário ("ver preço e saber quando comprar") é
atendida manualmente pelo usuário principal.

---

## Etapa 6 — Telegram multi-usuário, fatiada em D1-D4 (12/08/2026)

Decidido no chat de planejamento em 12/08/2026 — **primeira vez que este
fatiamento aparece em qualquer arquivo do repositório**; até esta rodada só
existia no chat. O item 6 da "Ordem de execução" acima ("Telegram:
cooldown/dedup de `alert_log` por perna × usuário; composição de mensagem
com nome+valor") vira 4 fatias menores e sequenciais:

- **D1 — filtro de janela de compra.** Alerta de perna (teto e oportunidade)
  e resumo semanal passam a considerar só fins de semana ≥ data de corte.
  **IMPLEMENTADA E PUBLICADA (commit `757ab3e`, 12/08/2026)** — verificação
  de produção em andamento. Detalhe completo na subseção "Fatia D1" abaixo.
- **D2 — `alert_log` ganha coluna de tipo de alerta.** Corrige o bug
  estrutural já registrado (`STATE.md`, seção 2, investigação de 12/08/2026):
  hoje o cooldown não distingue alerta de teto de alerta de oportunidade — um
  pode segurar o outro sem que devesse. **✅ CONCLUÍDA (14/08/2026)** —
  implementada e SQL executado em 13/08/2026, verificação pós-deploy fechada
  com dado real de produção em 14/08/2026. Detalhe completo na subseção
  "Fatia D2" abaixo.
- **D3 — `alert_log` ganha `user_id`.** **IMPLEMENTADA (14/08/2026)** —
  coluna nullable preenchida de forma assimétrica (linha de rota ganha dono,
  linha de perna fica NULL porque não há dono derivável), SQL a rodar
  manualmente e verificação pós-deploy em aberto. Detalhe completo na
  subseção "Fatia D3" abaixo.
- **D4 — avaliação por usuário.** Aposenta o MIN de teto de
  `weekends.resolve_effective_leg_state` (regra provisória desde a Etapa 4.2,
  documentada como tal no próprio código), individualiza os limiares gerais
  hoje escolhidos de forma determinística por menor `user_id`
  (`weekend_opportunity_pct`, cooldown/re-alerta, modo de notificação), e a
  mensagem passa a identificar quem disparou. **IMPLEMENTADA (15/08/2026)** —
  código e testes prontos; `sql/fatia_d4_avaliacao_por_usuario.sql` JÁ
  EXECUTADO em produção (10/10 blocos, zero gate disparado, coluna
  `display_name` criada e populada com `'Elton'`); falta publicar o código e
  fazer a verificação pós-deploy. Fecha a "JANELA ABERTA 2". Detalhe completo
  na subseção "Fatia D4" abaixo.

**D1 e D2 valem por si mesmas mesmo sem a Etapa 7 (segunda conta)
acontecer** — D1 já está em produção com uma conta só; D2 corrige um bug de
schema independente de quantos usuários existem. **D3 e D4 são a Etapa 6
propriamente dita** (fan-out por usuário) e não fazem sentido isoladas de
uma segunda conta real para testar contra.

**Ordem D1→D2→D3→D4, e por quê:**
- D2 antes de D3: as duas mexem no mesmo schema (`alert_log`) — não vale a
  pena tocar a tabela duas vezes em fatias separadas quando dá para
  sequenciar.
- D4 por último: é o bloco maior e mais sensível (aposenta uma regra
  provisória que hoje governa a fila e o teto com mais de um usuário), e tem
  um **problema de verificação conhecido, sem solução decidida ainda**: o
  fan-out por usuário é estruturalmente não verificável com uma conta só —
  mesmo limite já registrado na Fatia C, cuja linha "outro usuário já
  comprou" segue "sem verificação positiva possível" até a Etapa 7
  (`HISTORICO.md`, item 23). Opções levantadas no chat de planejamento, **a
  decidir quando chegarmos lá**:
  - fixture temporária em `settings` (linha de usuário fictício só para
    teste, removida depois);
  - teste fora de produção com dados falsos (ambiente descartável, no
    padrão já usado na investigação dos blocos E/F da Etapa 4.1);
  - aceitar explicitamente como limite estrutural até a Etapa 7 (segunda
    conta real), documentando a lacuna em vez de simular uma prova fraca.

**RESOLVIDO na implementação (15/08/2026), e a lacuna é menor do que o texto
acima supunha.** Nenhuma das três opções foi necessária como estava posta:
`resolve_effective_leg_state`, `cooldown_blocks_alert` e `evaluate_good_price`
são funções **puras**, sem I/O — a lógica de fan-out por usuário é verificável
agora, com usuários fictícios em teste unitário, e está coberta (13 testes
novos com 2 usuários: teto próprio, limiar próprio, cooldown isolado por
usuário e por tipo, fan-out de mensagem e de `alert_log`, modo degradado). O
que **não** é verificável com uma conta é o comportamento contra o banco real:
a view devolvendo 264 linhas, a RLS com dois donos e `alert_log` com dois
`user_id` distintos. Fica registrado nesses termos — nem "verificado", nem
"impossível". Prova ponta a ponta: Etapa 7.

### Fatia D1 — janela de compra no Telegram (implementada 12/08/2026, verificação em produção em andamento)

**Decisão de origem:** `STATE.md`, seção 2, 11/08/2026 — o Telegram passa a
respeitar a janela de compra (fins de semana ≥ 29/01/2027) nos dois caminhos
onde não respeitava (alerta de oportunidade e resumo semanal). **Ajuste de
12/08/2026, no mesmo chat de planejamento:** o filtro passou a cobrir os
DOIS tipos de alerta de perna — teto e oportunidade — não só oportunidade,
porque um alerta de teto para um fim de semana fora da janela mandaria
"compre" algo que por regra de escopo nunca será comprado.

**Decisão de arquitetura:** o corte vive em `system_config`
(`weekend_buying_cutoff_date`), não duplicado em Python — motivo já
registrado em `STATE.md` (hoje só existia em `docs/js/dashboard.js:83`,
inacessível do lado Python; duplicar recriaria a inconsistência que a fatia
existe para corrigir).

**As 4 decisões de desenho do Plan Mode:**
1. **Onde filtrar:** `src/weekends.py`, dentro de
   `evaluate_and_record_leg_price`, aplicado ao `would_alert` inteiro — não
   em `main.py`, porque é o único ponto compartilhado pelos dois caminhos de
   coleta (cache Travelpayouts e lote `fli`).
2. **Select compartilhado, não consulta separada:** `get_effective_leg_state`
   ganhou `outbound_date` no select (a view já expunha a coluna, nenhum
   grant novo necessário) — evita duas definições divergentes de "quais
   pernas existem".
3. **Recorte pela `outbound_date` do fim de semana** (âncora), tanto para
   ida quanto para volta — mesma coluna que o Dashboard já usa
   (`docs/js/dashboard.js`), pra painel e Telegram responderem igual.
4. **Degradação sempre mantém o filtro, nunca remove** — se a leitura do
   corte falhar ou a chave não existir, cai no fallback embutido
   (`2027-01-29`) e avisa 1x por execução no Telegram; nunca volta a
   alertar/contar as 132 pernas inteiras em silêncio.

**Arquivos alterados:** `sql/fatia_d1_janela_compra_telegram.sql` (novo);
`src/main.py`, `src/supabase_client.py`, `src/weekends.py`,
`src/telegram_notifier.py`; `tests/test_main.py`,
`tests/test_etapa3_cooldown.py`, `tests/test_supabase_client.py`,
`tests/test_weekends.py`, `tests/test_telegram.py` (novo). Commit `757ab3e`,
publicado em `origin/main`.

**Achado corrigido durante a implementação:** a degradação precisa ler o
`system_config` CRU (a resposta direta do banco, antes do merge com
`DEFAULT_SYSTEM_CONFIG`) — senão o caso "tabela sem linha" fica
indistinguível de um corte real configurado coincidentemente igual ao
fallback, e o aviso de degradação nunca dispara.

**Achados registrados sem ação nesta fatia:**
- (a) Colisão de nome evitada com `src/buying_window.py` — conceito
  diferente (antecedência recomendada de compra, 30–60 dias nacional, não
  janela de compra).
- (b) "Resumo semanal" na verdade resume só a execução de hoje, não acumula
  a semana inteira — comportamento pré-existente, só ficou mais visível com
  o filtro (listas ficam menores/vazias com mais frequência).
- (c) `get_weekend_leg_counts` vai continuar contando fins de semana já
  vencidos a partir de 2027 (a view não filtra expiração) — igual ao
  Dashboard, mantido de propósito para os dois ficarem coerentes.
- (d) Dashboard tem um terceiro lugar sem o corte (`renderAcaoDoDia`,
  `docs/js/dashboard.js:107-115`) — fora do escopo desta fatia e da D1b
  (migração do `dashboard.js` para ler `system_config`), anotado para
  decisão futura.

**Resultado real do SQL em produção**, rodado manualmente pelo usuário em
12/08/2026, todos os blocos batendo com o esperado:

| bloco | resultado |
|---|---|
| G0 (inventário) | colunas_system_config = 5 colunas sem o corte, coluna_corte_existe = false, linhas = 1, rls_ligada = true, política = `system_config_select_authenticated`, weekends_hoje = 66, pernas_hoje = 132, weekends_na_janela = 45, pernas_na_janela = 90, privilégios anon/authenticated/service_role = 7/7/7 (primeira medição) — bate 100% com o esperado |
| V1 (coluna) | coluna_existe = true, tipo = date, aceita_nulo = NO, default = 2027-01-29, valor_atual = 2027-01-29, linhas = 1 — bate 100% |
| V2 (grants/RLS inalterados) | rls_ligada = true, rls_forcada = false, política = `system_config_select_authenticated`, policy_cmd = SELECT, policies_update = 0, privilégios 7/7/7 idênticos ao G0 — bate 100% |
| V3 (denominador novo) | corte_lido = 2027-01-29, pernas_na_janela = 90, compradas_na_janela = 0, pernas_totais = 132 (coleta intacta) — bate 100% |
| V4 (linha de base, informativo) | 30 alertas de perna em 14 dias, 2 dentro da janela, 28 fora (93%) — consistente com o diagnóstico de silêncio do Telegram de 12/08/2026; valor de comparação para depois do deploy, não asserção |

**Efeito esperado, registrado antes do deploy:** resumo semanal vai encolher
muito (denominador 132→90; "mais próximas" só 2 fins de semana elegíveis
hoje por causa do cruzamento com os 183 dias do lote `fli`, crescendo ~1 por
semana); alertas de perna fora da janela (teto e oportunidade) param de
sair; coleta continua 100% intacta (132 pernas).

**VERIFICAÇÃO EM PRODUÇÃO — PENDENTE, ainda não fechada.** Falta:
1. Confirmar no log do Actions da próxima execução (hoje/amanhã) que as ~20
   pernas do lote continuam sendo checadas, o print de supressão aparece, e
   NENHUM aviso de fallback do corte foi disparado.
2. 1-2 dias: confirmar que alertas de perna fora da janela realmente
   pararam de chegar no Telegram.
3. Rodar o bloco V4 de novo e confirmar que `fora_da_janela` não cresceu
   além de 28.
4. **Só na segunda-feira 17/08/2026:** confirmar o resumo semanal real —
   denominador em 90, "mais próximas" começando em 29/01/2027.

**A Fatia D1 só deve ser marcada como CONCLUÍDA depois que os 4 itens acima
forem confirmados** — não está marcada como concluída nesta rodada de
documentação.

**Achado adicional, registrado durante a verificação da D1 (13/08/2026):**
o log do Actions da execução primária de 13/08/2026 08:37 BRT (primeira
pós-deploy do commit `757ab3e`) confirma 7 prints de supressão por janela de
compra com o corte correto (2027-01-29), zero aviso de fallback do
`system_config`, 20/20 pernas checadas, zero erro, zero alerta enviado —
`alert_log` permaneceu em 74 linhas. O mesmo log confirma que uma mesma
perna É avaliada duas vezes no mesmo dia (passada de cache + lote `fli`):
`return 2026-12-25` aparece suprimida duas vezes na mesma execução (uma via
cache, outra via live) — responde uma pergunta aberta da subseção (e) do
diagnóstico do topo deste arquivo, e é consistente com o desenho de
`dedupe_weekend_reports` (main.py): duas avaliações, um report escolhido, um
único insert em `alert_log`.

---

### Fatia D2 — `alert_log` ganha tipo de alerta (✅ CONCLUÍDA em 14/08/2026; implementada e SQL executado em 13/08/2026, verificação pós-deploy fechada com dado real de produção em 14/08/2026)

**Decisão de origem:** `STATE.md`, seção 2, investigação de 12/08/2026 — o
cooldown de perna (`get_last_weekend_leg_alert`) filtra hoje só por
`leg_id`, não por tipo de alerta (teto vs. oportunidade). Um alerta de
oportunidade pode segurar um de teto da mesma perna, e vice-versa. O bug é
real no código mas **não produziu perda observável nos últimos 14 dias**
(zero hits de teto no período — preço travado em R$334 contra teto R$300
desde 05/08/2026 — logo nenhuma colisão de fato ocorreu). Não é urgente;
precisa ser corrigido antes de D3 (`user_id` em `alert_log`) e D4 (avaliação
por usuário), que mexem no mesmo schema.

**Decisão de arquitetura — duas colunas booleanas, não uma coluna de tipo:**
`is_ceiling_alert boolean not null default false` e
`is_opportunity_alert boolean not null default false`, em vez de uma coluna
única de tipo (enum ou texto). Motivo: existem linhas reais com AMBOS os
motivos na mesma linha (`reason` composto por `;` — 2 de 52 linhas de perna,
5 de 22 linhas de rota). Uma coluna única forçaria um valor especial tipo
`'both'`, frágil para quem esquecer de tratá-lo no filtro de cooldown —
exatamente a classe de bug que esta fatia corrige. `reason` CONVIVE com as
colunas novas (não é substituído nem removido) — segue como texto livre de
forense; as colunas novas são a chave estruturada usada no cooldown.

**As decisões de desenho do Plan Mode:**
1. **Fonte das flags, não derivação por texto:** `src/rules.py` ganhou
   `evaluate_good_price(...)`, que devolve `(good, reason, ceiling_hit,
   opportunity_hit)` — as duas últimas são a fonte estruturada das colunas
   novas. `is_good_price` (assinatura antiga, 2 outros chamadores) virou um
   wrapper fino sobre ela, sem mudar comportamento. Derivar as flags de
   volta por substring do `reason` (a alternativa mais simples) foi
   descartada: acoplar a chave de cooldown a um texto de mensagem é a mesma
   fragilidade que motivou as duas colunas em vez de uma coluna de tipo.
2. **Cooldown por tipo, com `all()` e guarda de lista vazia:**
   `get_last_weekend_leg_alert(leg_id, alert_type)` ganhou o parâmetro
   `alert_type` obrigatório (`'ceiling'` ou `'opportunity'`, sem default).
   Em `weekends.py`, um alerta só é segurado por cooldown se **TODOS** os
   tipos que dispararam nesta avaliação estiverem em cooldown — um alerta de
   teto liberado nunca mais é segurado por uma oportunidade recente em
   cooldown, e vice-versa. `cooldown_blocks_alert` (rules.py) não mudou uma
   linha — continua recebendo `last_alert` já resolvido, compartilhada com o
   cooldown de rota.
3. **Consequência aceita, registrada explicitamente:** um alerta composto
   (teto E oportunidade na mesma avaliação) sai inteiro se **pelo menos um**
   dos tipos estiver liberado, e grava as **duas** flags `true` — inclusive
   renovando o relógio de cooldown do tipo que estava em cooldown. Não é bug
   nem gap de cobertura: é a leitura direta de "a mensagem inteira foi
   enviada, com as duas razões" — a alternativa (podar a razão em cooldown
   do texto da mensagem) foi descartada por reintroduzir manipulação de
   texto no caminho de decisão para ganhar quase nada.
4. **Índice novo, sem a coluna de tipo:**
   `alert_log_leg_sent_at_idx (leg_id, sent_at desc)` — um índice só serve
   os dois tipos de cooldown (o planner varre a perna já ordenada e aplica o
   filtro booleano por cima). Registro explícito, decisão aceita de
   antemão: a D3 (`user_id` em `alert_log`) provavelmente vai querer
   recriar este índice como `(leg_id, user_id, sent_at desc)` — não é
   pendência desta fatia.
   - **⚠️ EXPECTATIVA REVISTA PELA D3 (14/08/2026) — não é pendência de
     ninguém.** A D3 decidiu **não** recriar o índice: como as linhas de
     perna ficam com `user_id` NULL (não há dono derivável até a D4), a
     coluna no meio do índice não serviria nenhuma consulta existente, e a
     forma útil depende do formato final da consulta da D4 (perna + usuário
     + tipo + data). **A forma final do índice é decisão da D4.** O bloco V4
     de `sql/fatia_d3_user_id_alert_log.sql` existe justamente para provar
     que a D3 deixou este índice intacto. Registrado aqui para não virar
     pendência fantasma que uma sessão futura tente "consertar".
5. **Flags gravadas também no caminho de rota** (`insert_alert_log`), não
   só no de perna — decisão aprovada explicitamente no chat de planejamento,
   para o backfill não envelhecer no primeiro dia. O cooldown de rota
   (`get_last_alert`) **não muda** — continua filtrando só por `route_id`,
   fora de escopo desta fatia.

**Débito técnico de nomenclatura, registrado — NÃO é bug:** o report de
ROTA usa as chaves `is_ceiling_alert`/`is_opportunity_alert` (mesmo nome das
colunas do banco, porque `main.py` lê essas chaves direto do report antes
de gravar), enquanto o report de PERNA usa `is_ceiling_hit`/
`is_opportunity_hit` (nome preexistente desde antes da D2 — `is_ceiling_hit`
já era lido por `telegram_notifier.py` para escolher o cabeçalho da
mensagem, 🎯 vs. 📉). São o mesmo conceito ("esta razão bateu nesta
avaliação") com nomes diferentes por domínio — inconsistência de
nomenclatura entre os dois caminhos de report, não uma divergência de
comportamento. Unificar o nome exigiria tocar `telegram_notifier.py` e os
testes que já dependem de `is_ceiling_hit`, fora do escopo mínimo desta
fatia; fica registrado para quando D3/D4 mexerem de novo nesses reports.

**Achado que mudaria o desenho, verificado e DESCARTADO:** o prompt do
Plan Mode pedia checar se a mesma perna pode gerar duas linhas separadas em
`alert_log` na mesma execução (em vez de uma composta) — rastreei o caminho
inteiro (`is_good_price`/`evaluate_good_price` → 1 `reason` composto por
`evaluate_and_record_leg_price` → 1 report por `dedupe_weekend_reports` → 1
`insert_weekend_alert_log`) e confirmei que isso NÃO acontece. O desenho de
duas colunas booleanas por linha (em vez de duas linhas por avaliação) está
correto.

**Arquivos alterados:** `sql/fatia_d2_tipo_de_alerta.sql` (novo — Parte 1);
`src/rules.py`, `src/supabase_client.py`, `src/weekends.py`, `src/main.py`
(Parte 2); `tests/test_etapa3_cooldown.py`, `tests/test_supabase_client.py`,
`tests/test_weekends.py` (Parte 3, +11 testes novos, 220 no total — nenhuma
mudança de comportamento além de 2 asserções de assinatura atualizadas,
avisadas de antemão). `src/telegram_notifier.py` e `src/bot_commands.py`
**não mudaram** — o primeiro continua lendo `is_ceiling_hit` do report (o
valor é idêntico); o segundo continua chamando `is_good_price`, que
sobrevive como wrapper.

**Validação do SQL antes da execução manual:** rodado ponta a ponta contra
um Postgres 16 local descartável (schema stand-in de `alert_log`/
`weekend_legs`/`routes`, mesma distribuição de dados do G0 — 10/40/2 de
perna, 17/0/5 de rota) — todo bloco bateu com o valor declarado como
esperado, incluindo a prova sintética V6 (transação com rollback) e o
rollback restaurando a contagem original de linhas. Instância apagada
depois. Isso validou sintaxe e lógica antes da execução real.

**EXECUÇÃO MANUAL EM PRODUÇÃO — CONCLUÍDA E VERIFICADA (13/08/2026).**
Todos os blocos bateram com o esperado, com uma única divergência esperada
e já prevista no cabeçalho do script (crescimento orgânico entre a medição
do chat de planejamento e a execução real — o robô roda 2x/dia):

| bloco | resultado |
|---|---|
| G0 (inventário) | colunas sem as novas, RLS/policy/grants idênticos ao previsto |
| Backfill, perna | **10/41/2 (53 total, 0 órfã)** — 1 linha de oportunidade a mais que o previsto (10/40/2, 52 total); soma bate, nenhuma órfã, divergência é crescimento orgânico entre 12/08 e 13/08, não erro |
| Backfill, rota | 17/0/5 (22 total) — bate exatamente com o previsto |
| V3 (idempotência) | `UPDATE 0` na re-rodada |
| V4 (índice) | `alert_log_leg_sent_at_idx` criado com a definição certa, 2 índices no total |
| V5 (RLS/grants) | idênticos ao G0 — nenhuma mudança de postura de acesso |
| V6 (prova sintética) | confirmou o bug antigo e a correção nos dois lados (consulta velha confundiria oportunidade com teto; consulta nova resolve certo dos dois lados); `rollback` sem resíduo |

Não houve execução do robô entre o SQL e a publicação do código — commit
único, dentro da mesma janela.

**⚠️ ORDEM E JANELA DE DEPLOY — diferente da D1:** na D1 bastava rodar o SQL
antes do código. Aqui existe uma janela adicional: entre rodar o SQL e
publicar o código da Parte 2, o robô continua gravando pelo caminho antigo
— linhas nascem `false/false` mesmo com `reason` classificável (é
exatamente o que o V2 do script define como defeito). O cabeçalho do script
e o bloco V3 documentam a janela seguindo o exemplo concreto de 13/08/2026
(entre duas execuções consecutivas do robô, ~08:40–20:00 BRT) e o
procedimento de recuperação (re-rodar o Bloco 3, que só toca linha ainda
não classificada) se uma execução cair no meio.

**VERIFICAÇÃO EM PRODUÇÃO — FECHADA (14/08/2026).** Itens 1-5 concluídos; o
item 6 fica registrado como lacuna de longo prazo, não como pendência ativa
(ver abaixo):
1. ✅ Rodar o SQL (`sql/fatia_d2_tipo_de_alerta.sql`) e conferir G0-V6 contra
   os esperados declarados no próprio script, dentro da janela entre
   execuções do robô. **Concluído e verificado em 13/08/2026** — tabela de
   resultado acima.
2. ✅ Publicar o código da Parte 2, na mesma janela. **Commit `1526751`.**
3. ✅ **Evidência primária de curto prazo — CONFIRMADA (14/08/2026),
   execução das 08:37 BRT.** Verificada por SQL direto em `alert_log` no
   chat de planejamento, não só pelo log do Actions:

   | sent_at (UTC) | price | reason | is_ceiling_alert | is_opportunity_alert | tipo |
   |---|---|---|---|---|---|
   | 2026-08-14 11:37:28 | 335.00 | 15.3% abaixo da média histórica (R$ 395.67) | false | **true** | perna |
   | 2026-08-14 11:37:27 | 658.00 | abaixo da meta fixa (R$ 750.0) | **true** | false | rota |
   | 2026-08-14 11:37:27 | 544.00 | abaixo da meta fixa (R$ 750.0) | **true** | false | rota |

   As duas linhas de ROTA nasceram classificadas corretamente **pelo código
   novo, sem depender de backfill** — é exatamente o que este item pedia.
   Zero órfã e zero flag errada nas três linhas.
4. ✅ **Linha nova de PERNA — CONFIRMADA na mesma execução, antes do
   esperado.** A previsão era que pudesse demorar dias (com a D1 no ar, as
   pernas alertáveis vinham ficando fora da janela de compra). A linha de
   perna de 14/08 nasceu com `is_opportunity_alert=true` e `reason`
   coerente — confirma o mesmo caminho de gravação funcionando também para
   perna, não só para rota. Vai além do que o item 3 exigia.
5. ✅ **"Volume de alertas de oportunidade não muda" — encerrado como
   observação**, com o valor probatório baixo que já estava registrado
   (volume praticamente nulo no período). Nunca foi critério de aceite e
   não é tratado como tal aqui.
6. **LACUNA DE LONGO PRAZO — não é pendência ativa, não bloqueia nada e não
   impede a fatia de ser marcada como concluída.** A prova mais forte
   possível seria uma colisão real: um alerta de teto saindo mesmo tendo
   havido oportunidade recente na mesma perna, com dado escrito pelo próprio
   robô. Ela depende de um primeiro hit de teto, que não ocorre desde
   30/07/2026 (preço travado em R$334 contra teto R$300) — condição de
   mercado, não trabalho pendente. A prova sintética (V6, transação com
   rollback, já confirmada em produção) cobre a semântica da consulta, e os
   itens 3/4 cobrem a gravação de ponta a ponta. **Se/quando um hit de teto
   acontecer, este item pode ser fechado só observando o comportamento em
   `alert_log` — nenhuma ação é necessária agora.**

**Fatia D2 CONCLUÍDA em 14/08/2026** — SQL executado e verificado em
13/08/2026, código publicado no mesmo dia (commit `1526751`), e verificação
pós-deploy com o robô rodando o código novo fechada em 14/08/2026 com dado
real de produção (itens 1-5). Resta apenas a lacuna de longo prazo do item
6, registrada acima como tal.

---

### Fatia D3 — `alert_log` ganha `user_id` (implementada 14/08/2026; SQL executado e verificado em produção em 14/08/2026, verificação pós-deploy em aberto)

**Objetivo:** `alert_log` ganha `user_id`, preparando a D4 (avaliação por
usuário) e a Etapa 7 (segundo usuário). Hoje cooldown e histórico de alerta
são globais. **Esta fatia não individualiza nada ainda** — não muda o que é
alertado nem o que é coletado.

**O achado que define a fatia — dono de linha de perna não existe hoje.**
`weekend_legs` não tem `user_id` (as 4 colunas de decisão pessoal saíram para
`weekend_leg_user_state` na Etapa 4.1 e foram removidas de `weekend_legs` na
4.3). Quem resolve "quem monitora esta perna" é a view
`weekend_leg_effective`, que faz **cross join com `settings`**
(`sql/etapa4_1_estado_por_usuario.sql:387-414`): a perna não tem UM dono, tem
N — e o robô colapsa esses N num alerta único via MIN de teto
(`src/weekends.py:149-188`, regra provisória da Etapa 4.2).
`weekend_leg_user_state` também não resolve, por ser modelo preguiçoso.
**O número que fechou a discussão (G0, Q8, medido em 14/08/2026): 31 pernas
já alertadas, apenas 4 com linha de estado.** Logo: linha com `route_id` tem
dono trivial (`routes.user_id`); linha com `leg_id` **não tem dono
derivável** — e não se inventa um.

**Resultado do bloco G0 em produção (14/08/2026), tudo batendo com o
esperado:**

| medição | resultado |
|---|---|
| `alert_log` | 75 linhas (53 perna, 22 rota, 0 ambos, 0 nenhum, 0 órfãs) |
| `routes.user_id` | `NOT NULL`, 3 rotas, 0 sem dono, FK para `auth.users` OK |
| índices | 2 (`alert_log_pkey`, `alert_log_leg_sent_at_idx`) |
| RLS | 1 policy SELECT, 0 de escrita, privilégios 7/7/7 |
| `weekend_leg_user_state` | 5 linhas / 5 pernas (1 usuário) |
| Q8 (o que fecha a discussão) | 31 pernas já alertadas, só 4 com linha de estado |

**As 6 decisões de desenho:**

1. **Preenchimento assimétrico — coluna nullable, com FK, sem CHECK.**
   `user_id uuid references auth.users(id) on delete set null`. O backfill
   preenche as 22 linhas de rota via `routes.user_id` (100%, porque Q4
   confirmou `NOT NULL` e zero rota sem dono) e **não toca** as 53 de perna,
   que ficam NULL por desenho. Sem `not null` (metade das linhas não tem
   verdade a preencher); sem CHECK `route_id is null or user_id is not null`
   porque a garantia que ele compraria já vem do Python (keyword-only sem
   default, padrão adotado na D2) e ele custaria reescrita na D4 mais um modo
   de falha no pior lugar possível (decisão 2).
   - **Ressalva registrada sobre o `on delete set null`:** a cláusula é a
     declaração de intenção correta, mas **não é garantia de preservação de
     histórico**. As FKs existentes de `alert_log` são `on delete cascade`;
     apagar a conta apaga `routes` e cascateia as linhas de rota de
     `alert_log` antes de o `set null` ter qualquer efeito. Ele só vale para
     caminhos que não passam por `routes`. Registrado assim para não deixar
     no repositório uma garantia que o schema não dá.
2. **Risco de insert como restrição de desenho, não detalhe.** Os dois
   inserts (`src/main.py`, caminho de rota e caminho de perna) acontecem
   **depois** de a mensagem do Telegram já ter saído, e não tinham
   `try/except`; no caminho de perna o insert está **dentro de um laço**, de
   modo que uma exceção cancelava os alertas das pernas seguintes, o resumo
   semanal de segunda e o exit code correto. Daí a DDL desta fatia ser
   incapaz de rejeitar um insert que hoje passa (sem `not null`, CHECK ou
   UNIQUE). **Além disso a fatia protege os dois inserts** com `try/except`
   que marca `had_error = True` (exit 1 no fim, mesmo padrão de
   `process_route`) e loga com prefixo procurável **`[alert_log] FALHA AO
   GRAVAR`** + traceback, sem abortar o laço. Consequência aceita: sem a
   linha gravada o cooldown não é alimentado e o mesmo alerta pode sair de
   novo no dia seguinte — degradação recuperável, ao contrário de matar a
   execução com o usuário já avisado.
3. **Índice: não recriar.** A D2 previu recriá-lo como `(leg_id, user_id,
   sent_at desc)`; com as linhas de perna 100% NULL isso não serviria
   consulta nenhuma, e a forma útil depende do formato final da consulta da
   D4. A forma final do índice é decisão da D4 (correção registrada também na
   subseção "Fatia D2", decisão 4, para não virar pendência fantasma). O
   bloco V4 prova que a D3 não tocou no índice.
4. **RLS: fronteira na D4, nada em D3.** Medido: `alert_log` não tem
   consumidor além do robô (`grep` em `docs/` → zero; o robô usa
   `service_role`, que ignora RLS). Apertar o ramo de perna para
   `user_id = auth.uid()` com `user_id` NULL esconderia 100% do histórico de
   perna; o predicado só passa a ser expressável quando a D4 escrever dono em
   linha de perna. O ramo de rota já é dono-a-dono via subconsulta em
   `routes`. O bloco V5 prova que a postura de acesso não mudou.
5. **Gravação.** Rota: `insert_alert_log` ganhou `user_id` **keyword-only e
   sem default**, e `main.py` passa `r["route"]["user_id"]` (a chave existe —
   `get_routes` usa `select=*`). Perna: `insert_weekend_alert_log` **não
   ganhou parâmetro e não manda a chave** — a linha nasce NULL, com o motivo
   registrado no docstring. Descartada a alternativa de um parâmetro
   obrigatório que hoje só aceitaria `None`: assinatura que existe só para
   ser trocada na D4, sem impedir erro nenhum agora.
6. **Compatibilidade com a D4.** Deixa pronto: coluna nullable com semântica
   de NULL documentada, caminho de rota já gravando dono, `try/except` nos
   dois inserts (a D4 multiplica inserts, um por usuário por alerta) e a
   marca d'água do deploy. **Não faz, para não travar a D4:** `not null`,
   CHECK, UNIQUE, recriação de índice, mudança de RLS, backfill de linha de
   perna, e **nada** em `resolve_effective_leg_state`/MIN de teto — aposentar
   o MIN é da D4.
   - **Consequência registrada para a D4 decidir (não resolver aqui):** um
     cooldown por usuário que filtre `user_id = U` não enxerga linha
     histórica com NULL — logo após a D4 entrar, pode sair um re-alerta por
     (perna, tipo). A D4 escolhe entre filtrar `user_id = U or user_id is
     null` na transição ou aceitar o re-alerta.

**Marca d'água do deploy (bloco V6 do script) — por que existe:** depois da
D4, `user_id` NULL em linha de perna passa a ter **dois** significados
possíveis (linha anterior à individualização vs. linha nova em que a gravação
do dono falhou), e a D4 não terá como separar os dois olhando só o dado. O V6
congela a fronteira: total de linhas e `max(sent_at)` no momento do deploy.
`alert_log.id` é `uuid` (`gen_random_uuid()`), que não ordena — por isso
`max(id)` não é registrado.

> **RESULTADO REAL (V6, executado e verificado em produção em 14/08/2026),
> também copiado para o cabeçalho de `sql/fatia_d3_user_id_alert_log.sql`:**
> `marca_dagua_em` = `2026-08-15 01:03:24.670155+00` ·
> `linhas_total` = `78` · `linhas_perna` = `54` ·
> `linhas_perna_sem_dono` = `54` · `linhas_rota_com_dono` = `24` ·
> `max_sent_at` = `2026-08-14 11:37:28.822753+00`

**Arquivos alterados:** `sql/fatia_d3_user_id_alert_log.sql` (novo — Parte 1);
`src/supabase_client.py`, `src/main.py` (Parte 2);
`tests/test_supabase_client.py`, `tests/test_etapa3_cooldown.py` (Parte 3,
+7 testes novos, 227 no total, suíte verde). `rules.py`, `weekends.py`,
`live_check.py`, `telegram_notifier.py`, `bot_commands.py` e `docs/`
**não foram tocados**.

**Call sites auditados antes de mudar a assinatura** (correção pedida no chat
de planejamento): as duas funções têm **uma única chamada real cada**, ambas
em `src/main.py`; os 4 usos em `tests/test_etapa3_cooldown.py` são `patch()`,
e `docs/`/`scripts/` não as referenciam. Como o `patch()` é sem `autospec`, o
mock não valida assinatura — por isso a Parte 3 acrescentou testes que batem
na **função real** (payload e `TypeError` de assinatura), em
`tests/test_supabase_client.py`.

**ORDEM DE DEPLOY — janela mais folgada que a da D2:** SQL primeiro, código
depois. Se uma execução do robô cair no meio, **não é defeito**: a coluna é
nullable e o código antigo simplesmente não a envia, então a linha de rota
nasce NULL e é recuperada re-rodando o Bloco 2 (idempotente, guarda
`user_id is null`). Não existe aqui o análogo da "órfã classificável" da D2.

**VERIFICAÇÃO — PARCIAL.** Itens 1-3 concluídos; 4-6 dependem da próxima
execução do robô com o código publicado, ainda não aconteceu:
1. ✅ Rodar `sql/fatia_d3_user_id_alert_log.sql` no SQL Editor e conferir G0 e
   V1-V6 contra os esperados declarados no próprio script. **Concluído e
   verificado em produção em 14/08/2026** — todos os blocos (G0, Bloco 1,
   Bloco 2, V1-V6) bateram com o esperado.
2. ✅ Publicar o código da Parte 2 e re-rodar o Bloco 2 se uma execução do
   robô caiu entre o SQL e o deploy. **Código publicado no commit `5352e3f`**
   — nenhuma execução do robô caiu entre o SQL e o commit, então o Bloco 2
   não precisou ser re-rodado.
3. ✅ Copiar o resultado do V6 (marca d'água) para o cabeçalho do script e
   para a caixa acima. **Feito** — resultado real registrado nos dois
   lugares.
4. Falta: evidência de curto prazo — a próxima linha de **rota** (~1/dia,
   não passa pelo filtro de janela de compra da D1) nasce com `user_id`
   preenchido.
5. Falta: a próxima linha de **perna** nasce com `user_id` NULL —
   comportamento esperado, não defeito.
6. Falta: **`had_error` não disparou** — explicitamente, não basta "sem
   traceback novo": com o `try/except` da decisão 2, um deploy fora de ordem
   passa a degradar quieto (todo insert de rota falharia, o cooldown de rota
   pararia de ser alimentado), e o sinal fica no exit code e na linha
   `[alert_log] FALHA AO GRAVAR` do log do Actions.

**A Fatia D3 só deve ser marcada como CONCLUÍDA depois dos itens 4-6
acima** — mesmo critério de D1 e D2. SQL executado e código publicado, mas a
verificação pós-deploy com o robô rodando o código novo ainda não aconteceu.

---

### Fatia D4 — avaliação por usuário (implementada 15/08/2026; SQL executado e verificado — deploy do código e verificação pós-deploy em aberto)

Última fatia da Etapa 6. Fecha a "JANELA ABERTA 2" (acima).

**Achado que barateou a fatia:** o `user_id` **já chegava** em toda linha de
`weekend_leg_effective` (`supabase_client.get_effective_leg_state` sempre
selecionou a coluna) e era **descartado** por `resolve_effective_leg_state`,
que lia só `leg_id`, `status` e `price_ceiling`. Não foi preciso view nova,
grant novo nem mudança de RLS para ter o dono em mãos no ponto de avaliação.

**A garantia central: NENHUMA consulta de preço cresce com o número de
usuários.** A linha de corte é visível na ordem do corpo de
`evaluate_and_record_leg_price`: gravar preço, ler histórico, classificar
suspeita e resolver a janela de compra acontecem **uma vez por perna** (fatos
de mercado e regras de sistema); teto, `weekend_opportunity_pct` e cooldown
acontecem **por usuário**; `update_weekend_leg` e `insert_weekend_leg_run_log`
voltam a acontecer uma vez por perna. O `set` de `fetch_keys` de
`process_all_weekend_legs` é derivado só de (mês, aeroporto, direção) — nunca
de usuário. O leque abre **no laço de envio de `main.py`, e só nele**.

**Dois dicts com papéis distintos substituem o `weekend_settings` extinto:**
`system_config` (configuração do sistema, igual para todos) e `settings_cache`
(configuração por usuário, consultada dentro do laço). `select_batch` e
`run_daily_batch` leem **só** o primeiro; `settings_by_user` é carga opaca que
o lote transporta e nunca inspeciona.

**Regra de chaveamento — a chave é a PRESENÇA do usuário monitorando, não a
existência de teto.** `resolve_effective_leg_state` devolve
`{leg_id: {user_id: teto_ou_None}}`; usuário monitorando **sem** teto entra
como `{user_id: None}`, nunca é omitido. Com isso, **dict vazio significa
exatamente uma coisa: ninguém monitora aquela perna** — é o que torna
inequívoco o marcador do modo degradado. Espelhar ali o filtro do MIN antigo
(que descartava quem não tinha teto) faria uma perna com um único usuário sem
teto virar `{}` e ser lida como "perna sem dono".

**A bifurcação degradada sobrevive, e a ORDEM dos dois testes é a garantia.**
Em `get_active_legs`, `degraded = not state_rows` é fato da **carga inteira**
(erro de dado: o robô degrada e avisa) e **curto-circuita** o teste **por
perna** de "ninguém monitora" (estado normal: a perna terminou). Fundir os dois
num `continue` só esvaziaria a fila em silêncio no modo degradado — um erro de
dado virando "acabou o trabalho". Protegido pelo teste
`test_no_settings_keeps_the_whole_queue_without_inventing_ceiling`, que roda no
nível de `get_active_legs` de propósito: no nível do report a perna nem seria
produzida e o teste ficaria verde sobre conjunto vazio.

**Modo degradado: caminho separado, SEM sentinela em `per_user`.** Com `perna
sem dono`, `per_user` fica `[]` e a decisão vai num campo próprio
(`degraded_alert`); o laço de envio manda a mensagem e **não grava em
`alert_log`**. Uma entrada sentinela com `user_id=None` gravaria NULL e (a)
contradiria a verificação desta fatia, que declara "linha nova com NULL é
defeito", e (b) criaria um **terceiro** significado de NULL do mesmo lado da
marca d'água da D3 (`max_sent_at = 2026-08-14 11:37:28.822753+00`), que existe
justamente para separar "linha anterior à individualização" de "gravação de
dono que falhou". O limiar do ramo degradado sai de `DEFAULT_SETTINGS`, o que
**preserva** o valor que já saía nesse cenário (15%), e os filtros comuns
continuam valendo: `suspicious` e `in_buying_window` são calculados **antes**
da bifurcação, então os dois ramos leem o mesmo valor por construção — a janela
de compra da D1 (produção desde 12/08/2026) não é reaberta.

> **DIFERENÇA REAL EM RELAÇÃO A ANTES, registrada como diferença e não como
> equivalência:** no modo degradado o cooldown **deixa de ser alimentado** (não
> há linha em `alert_log`), então o mesmo alerta de oportunidade pode repetir a
> cada execução até a linha de `settings` voltar a existir. Antes da D4 isso
> não acontecia — o insert degradado gravava sem dono e o cooldown consultava
> só por `leg_id`. Aceito por três razões: o cenário exige zero linha em
> `settings` e nunca ocorreu em produção; o modo já é anunciado no Telegram a
> cada execução; e a alternativa (consultar `user_id is null`) casaria com as
> 54 linhas históricas — que são do usuário real, gravadas antes da coluna
> existir — corrompendo permanentemente a separação de significados que a D3
> construiu. Dano permanente contra incômodo temporário.

**D-4b — `notification_mode` das rotas passa a ler o dono real.** Não é escopo
novo: `main.py:455` lia de `weekend_settings` e **perde a fonte** quando a
variável é apagada; a fatia não compila sem resolver. Passa a ler
`settings_cache[route["user_id"]]`, mesmo padrão que `freshness_hours` e
`stale_alert_policy` já usavam — `notification_mode` era a única das três lendo
do "menor `user_id`", a mesma classe de bug que a D2 corrigiu no cooldown. Os
reports passam a ser agrupados por dono: um resumo por dono em `daily_summary`,
alertas individuais para donos em `alert_only`, cada um com as notas das rotas
dele. Com um usuário só, comportamento idêntico ao de antes. **Fora de escopo,
e explicitamente NÃO corrigido:** a semântica invertida de `notification_mode`
em `rules.py:80-81` (`daily_summary` **desliga** o cooldown de perna e faz o
usuário receber **mais** alertas) — bug pré-existente e independente. A D4
individualiza a **leitura** da coluna, não corrige a semântica.

**SQL executado e verificado em produção, 10/10 blocos, zero gate
disparado.** Resultados medidos:
- **G0-Q1** (antes do Bloco 1): `usuarios_settings=1`,
  `user_id=c72bf50e-16f7-48fd-9c86-7b49dea1551e`, `contas_auth=1`,
  `coluna_display_name_existe=false`.
- **G0-Q2**: `132 / 1 / 132 / 132 / 132 / 0` — granularidade exata, **zero**
  linha sem teto. Os dois gates (`usuarios_distintos > 1`,
  `linhas_sem_teto > 0`) não dispararam.
- **G0-Q3**: `weekend_opportunity_pct=15`, `realert_days=1`,
  `notification_mode=alert_only`, `weekend_default_ceiling=300`,
  `stale_alert_policy=warn`, `freshness_hours=24`.
- **G0-Q4 — PREVISÃO do re-alerta único de transição, a conferir DEPOIS do
  deploy do código: 1 perna exposta a re-alerta de TETO, 0 de OPORTUNIDADE.**
  É o número que o item 9 da verificação, abaixo, confere.
- **G0-Q5/Q6**: baseline de postura de acesso medido; `anon` vê **0** linhas
  de `settings` — o gate `linhas_settings_vistas > 0` não disparou.
- **BLOCO 1**: coluna `display_name` criada; `display_name='Elton'` gravado
  no usuário real.
- **V1 / V2-A / V2-B / V3**: idênticos ao esperado — postura de acesso
  inalterada, campo a campo. `has_column_privilege` devolvendo `true` é o
  resultado correto (privilégio herdado da tabela), não regressão.

Com o nome já gravado no banco, o item 6 da verificação (abaixo) vira
asserção afiada: a mensagem **tem** que trazer `Elton`, e um `uuid[:8]` ali é
defeito inequívoco — não mais "coluna vazia, fallback correto" indistinguível
de "lookup quebrado".

**Sem REVOKE e sem GRANT, e o motivo é de fato, não de estilo:** em Postgres o
privilégio de coluna é herdado da **tabela**, e `revoke ... (display_name) on
settings from anon` executa sem erro **sem restringir nada** — deixaria no
repositório uma garantia falsa, com verificação "passando", enquanto o acesso
continua idêntico. No lugar: **medir antes** (G0-Q5 e G0-Q6, este último
provando por personificação que `anon` vê 0 linha de `settings`) e **provar
igualdade depois** (V2, esperado literal "idêntico ao G0, campo a campo"); o V3
registra por escrito por que `has_column_privilege` devolve `true`, para
ninguém ler esse `true` no futuro como regressão introduzida aqui.

**Ordem de deploy: SQL primeiro, código depois — a janela é a mais folgada das
quatro fatias, nos dois sentidos.** SQL feito com código velho no ar: a coluna
fica inerte. Ordem invertida por acidente: `get_all_settings` usa `select=*`,
então a chave não vem, `.get("display_name")` devolve `None` e o fallback do
uuid entra — é o fallback trabalhando, não degradação. **O que muda
comportamento é o deploy do CÓDIGO**, e na primeira execução seguinte: o
re-alerta único da transição de cooldown por usuário, do tamanho exato medido
em G0-Q4. Não é defeito, é a transição prevista.
**Reversão:** `git revert` do commit de código (a coluna pode ficar);
`alter table settings drop column if exists display_name` é seguro com o código
novo no ar ou fora dele — diferente da D3, aqui não existe caminho de insert
que mande a coluna, `display_name` é só LIDO pelo robô.

**Testes: 267 passando (eram 227).** 40 novos/reescritos, nos níveis certos —
`get_active_legs` (fila), report (avaliação por usuário e ramo degradado),
`main.py` (fan-out de envio e gravação) e apresentação (`user_label`, mensagem).

**RESSALVA HERDADA DA D3, que pesa nesta fatia.** A D3 foi liberada com o item
4 da verificação **não observado**: a gravação de `user_id` em linha de **rota**
nunca foi vista em produção (a evidência de 14/08 08:37 BRT é anterior ao
deploy das 22:03, e nenhuma linha de rota nasceu desde então). Ou seja, o
caminho de rota **não serviu de ensaio** para o de perna. Se existir defeito na
montagem do payload com `user_id`, ele vai se manifestar **aqui**. Isso eleva a
importância do item 5 abaixo.

**SQL EXECUTADO E VERIFICADO (10/10 blocos, zero gate). O QUE FALTA É O
DEPLOY DO CÓDIGO E A VERIFICAÇÃO PÓS-DEPLOY.**

✅ **FECHADO — SQL (executado em produção, 15/08/2026):**
1. Script rodado bloco a bloco. Os três gates **não** dispararam:
   `usuarios_distintos=1`, `linhas_sem_teto=0`, `linhas_settings_vistas=0`.
2. Coluna `display_name` criada e populada (`'Elton'`). V1/V2/V3 conferidos:
   postura de acesso idêntica ao baseline, campo a campo.
3. Previsão do re-alerta único de transição ANOTADA em G0-Q4: **1 perna
   exposta a re-alerta de TETO, 0 de oportunidade**. É o número a conferir
   depois do deploy (item 9 abaixo).

⏳ **EM ABERTO — deploy do código e verificação pós-deploy.** **Itens 5 e 6
✅ CONFIRMADOS em 17/08/2026** (ver o texto de cada um abaixo); os demais
seguem em aberto. **A numeração NÃO foi alterada** — ver a "Nota de
numeração" no fim desta lista.
4. Publicar o código (commit único: código + testes + documentação). Janela
   de deploy: entre execuções do robô (08h–20h BRT) — mesmo cuidado dos
   deploys anteriores, evita a ordem invertida no meio de uma execução.
5. ✅ **CONFIRMADO (17/08/2026) — PROVA DIRETA DE BANCO. A linha de PERNA em
   `alert_log` nasce com `user_id` PREENCHIDO.**
   *Enunciado original:* a próxima linha de PERNA em `alert_log` nasce com
   `user_id` preenchido. Fronteira: a marca d'água da D3 —
   `max_sent_at = 2026-08-14 11:37:28.822753+00`, 78 linhas. Linha nova com
   NULL seria **defeito** — esta é a primeira observação real da gravação de
   dono em `alert_log`, não a confirmação de algo que já funcionou (ver
   "ressalva herdada da D3" acima).
   **Gatilho:** o primeiro alerta de perna real desde o deploy da D4 disparou
   sozinho em produção em **17/08/2026 ~08h16 BRT** — fim de semana de
   **29/01/2027, perna de VOLTA, R$ 334**, dentro do teto registrado na
   própria linha.
   **Evidência:** script [sql/etapa7_item5_verificacao_alerta_2908_2027.sql](sql/etapa7_item5_verificacao_alerta_2908_2027.sql)
   rodado manualmente pelo usuário no SQL Editor em 17/08/2026. Resultado
   real na janela **17/08/2026 08:00–09:00 BRT**: **3 linhas** de
   `alert_log`, **todas** com `leg_id` preenchido e **todas** com `user_id`
   preenchido com o UUID do usuário principal
   (`c72bf50e-16f7-48fd-9c86-7b49dea1551e`) — **zero NULL**. `reason` nas
   três: `abaixo da meta fixa (R$ 500.0)`.
   **Os `id` das 3 linhas não foram transcritos para o registro** — o
   resultado chegou como contagem e conteúdo dos campos, não linha a linha.
   Fica anotado como lacuna de registro, **não** como dúvida sobre o
   resultado: a asserção do item 5 (zero `user_id` NULL em linha nova de
   perna) está confirmada com o que foi observado. Se os `id` forem
   necessários depois, o script é re-rodável e a janela é a mesma.
   **Fato colateral observado, NÃO resolvido aqui:** o `reason` das três
   linhas cita **R$ 500,0** como meta, enquanto o teto padrão registrado
   neste plano e no `STATE.md` é **R$ 300** (recalibração de 04-05/08/2026) —
   e é o R$300 que aparece nas três execuções da E7-5, inclusive na de 17/08
   ~08h BRT ("2 usuários, menor teto R$ 300"). Um teto de R$500 explicaria o
   disparo a R$334, que a R$300 não teria acontecido. **Divergência
   registrada como fato, sem causa investigada** (override por perna em
   `weekend_leg_user_state`? novo save do teto padrão? outra coisa?) — não
   afeta a confirmação do item 5, que é sobre `user_id`, e não sobre qual
   teto foi usado. Fica como pendência nomeada para rodada futura.
   **LIMITE EXPLÍCITO DESTA PROVA — não é fan-out.** As 3 linhas são todas do
   **MESMO** usuário. Este resultado **NÃO** prova `alert_log` recebendo
   linhas com **dois `user_id` distintos na mesma execução** — que é
   exatamente o que continua faltando para fechar a **E7-5** por completo.
   São itens diferentes; confirmar o 5 não fecha a E7-5.
   **EVIDÊNCIA PARCIAL ADICIONAL (17-18/08/2026).** A execução primária de
   18/08 ~08h BRT (run `87096672271`) mostra, no log de execução, decisão
   **INDIVIDUAL por usuário**: os dois `user_id` reais — Elton
   (`c72bf50e...`) e Gustavo (`2446ec67...`) — aparecem processados
   **separadamente** em linhas de supressão por janela de compra. Confirma
   que o laço por usuário decide por conta própria (cada `user_id` avaliado
   e registrado à parte), mas **não fecha** o que falta: continua sem
   observação de `alert_log` recebendo linhas com dois `user_id` distintos
   **na mesma execução** — supressão por janela não é linha de alerta.
   Registrado como evidência parcial; confirmar o 5 não fecha a E7-5.
6. ✅ **CONFIRMADO (17/08/2026) — CAMADA DE MENSAGEM. A mensagem no Telegram
   traz o nome do usuário, não `uuid[:8]`.**
   *Enunciado original:* a mensagem no Telegram traz **`Elton`** — o nome
   **já está gravado** no banco — e o teto de quem disparou. Um `uuid[:8]`
   ali seria defeito inequívoco.
   **Evidência:** print de tela da mensagem real do bot, **17/08/2026 08h16
   BRT** (o mesmo alerta que serviu de gatilho ao item 5), exibindo
   **"👤 Elton"**. É prova da camada de **mensagem** (`user_label` +
   `settings.display_name`, populado na D4) — e **só** dela.
7. `had_error` **não** disparou: exit 0 no Actions e zero ocorrência de
   `[alert_log] FALHA AO GRAVAR`. Não basta "sem traceback novo".
8. Os dois avisos provisórios pararam de sair: nenhuma mensagem desse tipo no
   canal.
9. **Re-alerta de transição**: conferir que o observado bate com a previsão
   de G0-Q4 (**1 perna de teto, 0 de oportunidade**) e que **não se repete**
   na execução seguinte.
10. **Regressão: critério ESTRUTURAL, não comparação com execuções
    passadas.** Comparar com ontem **não é aferível** — o lote `fli` seleciona
    por rotação da perna menos checada, então o conjunto avaliado muda a cada
    execução por desenho; "mesmas pernas alertadas que ontem" mediria a
    rotação, não a fatia. Por perna avaliada com dono: `per_user` tem
    **exatamente 1 entrada**, o teto usado é o `weekend_default_ceiling`
    atual (lido em G0-Q3, R$300), e a decisão bate com o que
    `rules.evaluate_good_price` devolveria para aquele preço e aquele teto,
    conferido no log da própria execução. A regressão é verificada contra a
    **regra**, que é determinística, não contra a **amostra**, que é
    rotativa.

**NOTA DE NUMERAÇÃO — CORREÇÃO REGISTRADA EXPLICITAMENTE (17/08/2026).** A
numeração vigente desta lista, desde o registro original acima, é e continua
sendo:
- **item 5 = `user_id` preenchido na linha de perna em `alert_log`** — camada
  de **BANCO**, só verificável consultando o banco direto;
- **item 6 = nome do usuário na mensagem do Telegram** — camada de
  **MENSAGEM**, verificável por print de tela.

Um prompt de outro chat, **na mesma data (17/08/2026)**, descreveu
incorretamente a verificação da mensagem do Telegram como sendo o "item 5".
**Isso está errado.** Confirmar "👤 Elton" na mensagem prova o item **6**; a
prova do item **5** exigiu o `select` em `alert_log`, feito em separado. Os
dois fecharam na mesma data, por evidências de naturezas diferentes, e **a
numeração não mudou** — registrado aqui para que revisões futuras deste
arquivo não reabram a ambiguidade.

**ESTADO DOS DEMAIS ITENS — conferido no texto deste plano em 17/08/2026, não
presumido.** Os itens **4 e 7-10 seguem sem marca de fechamento** neste
arquivo; nenhuma rodada anterior os fechou aqui. Ressalva sobre o item 4
(publicar o código): as execuções registradas na E7-5 rodaram com o código
novo, o que indica que o deploy aconteceu de fato — mas **o fechamento nunca
foi registrado**, então fica como **pendência de registro**, não como item
confirmado. Itens 7-10 não foram objeto desta rodada e não foram avaliados.

**A Fatia D4 só deve ser marcada como CONCLUÍDA depois dos itens 4-10** —
mesmo critério de D1, D2 e D3. **Não foi marcada nesta rodada:** fecharam só
os itens 5 e 6.

#### Duas decisões fechadas, com gatilho de revisão nomeado (param de ricochetear)

**D-6 — índice de `alert_log`: DECIDIDO não recriar.** A D2 previu
`(leg_id, user_id, sent_at desc)` para a D3; a D3 reviu e passou a decisão para
cá. **Fica como está**: `alert_log_leg_sent_at_idx (leg_id, sent_at desc)`.
Motivo: 78 linhas na marca d'água da D3, crescendo 1-3/dia; `leg_id` já é a
coluna seletiva, e acrescentar `user_id` a um índice sobre tabela desse tamanho
não muda plano de execução nenhum. **Gatilho de revisão:** quando `alert_log`
chegar à ordem de **dezenas de milhares de linhas** (no ritmo atual, ordem de
anos) — reavaliar aí, com medição. Até lá **não é pendência**. O bloco G0-Q5
prova que a D4 não tocou no índice.

**D-7 — RLS do ramo de perna em `alert_log`: DECIDIDO não apertar aqui; vira
item NOMEADO da Etapa 7.** Depois da D4 o predicado `user_id = auth.uid()`
passa a ser *expressável* pela primeira vez (linha nova nasce com dono), mas
continua **não verificável**: `alert_log` não tem consumidor fora do robô
(`grep` em `docs/` → zero; o robô usa `service_role`, que ignora RLS) e provar
isolamento exige duas contas. Apertar agora seria mudar política de segurança
em produção sem forma de observar o efeito, e ainda esconderia as 54 linhas
históricas com `user_id` NULL. **Endereço:** item nomeado da Etapa 7 (criação
da 2ª conta), junto com a prova de isolamento ponta a ponta. **Não é pendência
solta** e não deve reaparecer como "pendente" em fatia intermediária.

> **Endereço concreto (15/08/2026):** é a fatia **E7-3** da seção "Etapa 7"
> abaixo. A ordem final ficou **depois** da criação da conta, não antes — ver
> FECHADA-3.

---

## Etapa 7 — criação da conta do segundo usuário (PLANEJADA E TOTALMENTE DECIDIDA em 15/08/2026; **gate do item 5 da D4 CUMPRIDO em 17/08/2026** — execução em andamento, E7-0 a E7-4 concluídas, E7-5 parcialmente aberta)

> **GATE CUMPRIDO (17/08/2026).** O item 5 da verificação pós-deploy da D4 —
> único bloqueio estrutural desta etapa — foi **CONFIRMADO por prova direta de
> banco** nesta data: 3 linhas de perna em `alert_log` na janela 08h–09h BRT
> de 17/08, todas com `user_id` preenchido, zero NULL (detalhe e evidência na
> subseção "Fatia D4", item 5). As fatias E7-0 a E7-4 já haviam sido
> executadas **sob override consciente**, com o gate ainda aberto (as três
> instâncias registradas abaixo); a partir desta data o gate deixa de ser
> override e passa a estar **efetivamente cumprido**. A **exceção** que
> reintroduziria o bloqueio (`user_id` NULL em linha nova de perna) **não se
> materializou** — foi medida e reprovaria; passou.

**GATE ESTREITADO (decisão de 15/08/2026, chat de acompanhamento da D4) — ele
existe e é real, só ficou mais preciso.** A verificação pós-deploy da Fatia D4
tem 6 itens em aberto (5-10, subseção "Fatia D4", acima), mas **só o item 5**
("a próxima linha de PERNA em `alert_log` nasce com `user_id` PREENCHIDO") é
pré-condição direta da Etapa 7 — é o mecanismo de gravação de dono que as
fatias E7-3/E7-4 vão medir. Os demais são qualidade da D4 em produção, não
dependência estrutural desta etapa:
- **Item 6** (nome `Elton` na mensagem do Telegram) será conferido no mesmo
  log da execução de amanhã, mas **não é condição de bloqueio**.
- **Itens 9 e 10** (re-alerta de transição não se repetir; regressão
  estrutural, que depende da mesma janela) são **explicitamente excluídos do
  gate** — são verificação de cauda longa, podem levar mais de uma execução, e
  passam a rodar **em paralelo** à execução da Etapa 7, não antes dela.
- **Itens 7 e 8** (`had_error` não disparou; os dois avisos provisórios
  pararam de sair) seguem fora do gate pelo mesmo motivo dos itens 6/9/10:
  qualidade observada da D4, não pré-condição da Etapa 7.

**Condição de liberação:** se a execução de amanhã (~08h BRT) confirmar o item
5 OK (`user_id` preenchido na linha nova de perna, sem erro/traceback de
gravação), **a Etapa 7 pode começar a ser executada a partir da E7-0**, mesmo
com os itens 6-10 ainda em aberto.

**EXCEÇÃO que reintroduz o bloqueio:** se o log de amanhã mostrar o item 5 com
defeito real — `user_id` NULL numa linha nova de perna, erro de gravação,
traceback — **a Etapa 7 PAUSA antes de prosseguir**, porque ela depende
diretamente desse mecanismo. Nenhuma fatia desta seção roda antes de o item 5
fechar OK. Esta seção existe para que, no dia em que o gate abrir, **não reste
nenhuma decisão de produto a tomar** — só execução.

**OVERRIDE CONSCIENTE registrado em 15/08/2026 (primeira instância):** no
momento em que a E7-0 foi escrita (script `sql/etapa7_0_inventario.sql`), o
log da execução de ~08h BRT de 16/08/2026 **ainda não tinha sido conferido**
— o item 5 seguia sem confirmação. O usuário decidiu, explicitamente,
escrever e ter pronta a E7-0 mesmo assim, porque ela é **somente leitura**:
nada é criado, nada é alterado, nenhuma escrita em `alert_log`, nenhuma conta
é criada — a E7-0 não pode sofrer o defeito que o gate existe para prevenir.
**Isto não foi o gate cumprido; foi um override datado.**

**ATUALIZAÇÃO DO OVERRIDE (segunda instância, mesma data de decisão) —
execução aconteceu, sem evidência a favor ou contra:** a execução de ~08h BRT
de 16/08/2026 **de fato rodou**, mas **não produziu nenhuma linha nova de
perna** nessa janela — não houve alerta disparando. O item 5 continua **SEM
CONFIRMAÇÃO**, mas agora por **AUSÊNCIA DE DADO**, não por reprovação. É uma
situação diferente das outras duas possíveis: não é "ainda não rodou" (a
primeira instância do override), e não é "rodou e mostrou defeito" (o cenário
que exigiria pausar). O usuário decidiu, conscientemente, prosseguir mesmo
assim — segunda instância do mesmo tipo de override, agora explicitamente
depois de uma chance real de observação que não gerou evidência em nenhum
sentido.

**TERCEIRA INSTÂNCIA (17/08/2026, registrada na E7-5): execução rodou, sem
gatilho de alerta** — mesmo padrão da segunda instância, ausência de dado.

**FIM DA SEQUÊNCIA DE OVERRIDES (17/08/2026).** As três instâncias acima
descrevem um gate aberto contornado por decisão consciente. **Isso terminou:**
mais tarde no mesmo dia 17/08/2026 um alerta real disparou (~08h16 BRT) e o
item 5 foi **CONFIRMADO por prova direta de banco** — 3 linhas de perna em
`alert_log`, todas com `user_id` preenchido, zero NULL. Nenhuma fatia futura
desta etapa precisa mais rodar sob override por este motivo. O texto das três
instâncias fica preservado como registro histórico de como as fatias E7-0 a
E7-4 foram executadas — sob override datado, não sob gate cumprido.

Em nenhuma das três instâncias isto foi o gate cumprido — o gate fechou
depois, por prova de banco, não por override. A exceção original **valeu até o
fim, sem enfraquecer, e foi de fato medida**: se a observação tivesse mostrado
o item 5 com defeito real — `user_id` NULL numa linha nova de perna, erro de
gravação, traceback — **a Etapa 7 pausaria antes de prosseguir, mesmo com
fatias já avançadas**. O resultado da E7-0 (abaixo, CONCLUÍDA) não é, e nunca foi,
a confirmação do item 5 — é levantamento de terreno que precisava existir de
qualquer forma antes da E7-2, feito sob um gate ainda aberto por decisão
consciente do usuário.

**Nota de origem:** o levantamento de terreno foi feito em Plan Mode em
15/08/2026 (só leitura de código, schema e documentação; nada executado) e
ficou apenas no chat. Esta é a primeira vez que ele é registrado em arquivo, já
com as quatro decisões de produto fechadas na mesma data.

**Limite operacional declarado:** a criação da conta em si e qualquer digitação
de senha são **do usuário, no dashboard do Supabase** — não são feitas pelo
Claude Code em nenhuma variante deste plano.

### As quatro decisões de produto — TODAS FECHADAS (15/08/2026)

Eram as quatro perguntas abertas do levantamento. Nenhuma resta.

**FECHADA-1 — Teto padrão do segundo usuário: R$300**, igual ao do usuário
principal. **Não** usar o default do banco. Vai **explícito** no `insert` de
`settings` da fatia E7-2.
*Por que importa:* `settings.weekend_default_ceiling` é `not null default 250`
([sql/etapa4_1_estado_por_usuario.sql:87](sql/etapa4_1_estado_por_usuario.sql:87))
e a view resolve `coalesce(st.price_ceiling, s.weekend_default_ceiling)`
([:398](sql/etapa4_1_estado_por_usuario.sql:398)) — um insert que omitisse a
coluna faria a conta nova nascer monitorando as 132 pernas a R$250, um valor
que ninguém escolheu e que diverge do teto vigente sem aviso nenhum.

**FECHADA-2 — `display_name` do segundo usuário: `Gustavo`.** Vai explícito no
**mesmo** `insert` da E7-2.
*Por que importa:* sem ele, `user_label` cai no fallback `user_id[:8]`
([src/telegram_notifier.py:154-167](src/telegram_notifier.py:154)) e um prefixo
de uuid apareceria nas mensagens do grupo compartilhado. O fallback é desenho
correto, não defeito — mas não é o que se quer em produção. Não existe UI para
essa coluna (nenhum campo em `docs/js/config.js`), então o único caminho é o
`insert`/SQL Editor.

**FECHADA-3 — D-7 (apertar a RLS do ramo de perna em `alert_log`) roda DEPOIS
da criação da conta, não antes.** Ordem real de execução:
**E7-2 (conta + linha de `settings`) → E7-3 (RLS) → E7-4 (prova de isolamento)
→ só então a credencial é entregue ao Gustavo.**

- **Renumeração:** as fatias foram renumeradas para que o número siga a ordem
  de execução. Os **nomes internos não mudaram**, só o rótulo:
  a antiga E7-3 ("conta + linha de settings") é agora **E7-2**;
  a antiga E7-2 ("RLS D-7") é agora **E7-3**.
  Registrado aqui porque o texto da decisão, no chat de 15/08/2026, usou os
  rótulos antigos ("E7-3 → E7-2") — é a mesma ordem, com a numeração corrigida.
- **RISCO ACEITO EXPLICITAMENTE, registrado como tal:** existe uma janela —
  **dentro da mesma sessão de execução, não de dias** — em que a conta do
  Gustavo já existe e a RLS de `alert_log` ainda está com a policy antiga
  (`leg_id is not null and auth.uid() is not null`, ramo de perna legível por
  qualquer autenticado). Como a credencial só é entregue **depois** da E7-4, que
  nesta ordem só roda depois da E7-3, **a janela não é explorável por ele
  mesmo** — é risco teórico. **Aceito conscientemente pelo usuário em
  15/08/2026, não esquecido.**
- **Ganho real que a ordem nova compra, e não é só conveniência:** com a conta
  existindo primeiro, o "antes" e o "depois" da E7-3 passam a ser medidos por
  personificação da **segunda conta real** — mostra-se que o Gustavo *consegue*
  ler as linhas de perna, aperta-se a policy, e mostra-se que *deixou* de
  conseguir. Na ordem antiga (RLS antes da conta) os dois lados seriam medidos
  contra um usuário fictício, que é exatamente a classe de prova fraca já
  criticada nos blocos E/F da 4.1 (revisão de 02/08/2026). A ordem nova troca um
  risco teórico por uma prova mais forte.

**FECHADA-4 — `/status` do bot não filtra por usuário: ACEITO como está.**
[src/bot_commands.py:33](src/bot_commands.py:33) lê **todas** as rotas
flexíveis (`get_routes()` roda como `service_role`), então quem digitar
`/status` no grupo recebe um bloco por rota de qualquer dono, com
`target_price` incluído. **Decisão consciente, não pendência técnica:** o
segundo usuário não pretende usar esse comando, e as rotas flexíveis são
sistema legado com um dono só hoje. **Gatilho de reabertura nomeado:** se o
Gustavo passar a usar `/status`, a discussão reabre — até lá não deve
reaparecer como "pendente".

### O terreno confirmado por leitura de código/schema (15/08/2026)

**1. Onboarding — o que precisa existir no mesmo ato.**
A view é um `cross join settings`
([sql/etapa4_1_estado_por_usuario.sql:415](sql/etapa4_1_estado_por_usuario.sql:415)):
conta sem linha em `settings` produz **zero** linha na view, e o robô nem a
enxerga (`get_active_legs` itera pernas, não usuários,
[src/weekends.py:229](src/weekends.py:229)). **Regra dura de 01/08 confirmada
sem ressalva:** painel vazio, nenhum alerta, **zero erro em lugar nenhum**.
O robô lê toda coluna de `settings` com fallback (`or DEFAULT_SETTINGS[...]` em
[rules.py:85-86](src/rules.py:85), [weekends.py:342](src/weekends.py:342),
[main.py:150/165](src/main.py:150), [live_check.py:144](src/live_check.py:144)),
então NULL degrada para o default Python em vez de estourar. **Uma exceção
nomeada:** [src/bot_commands.py:65](src/bot_commands.py:65) faz
`float(settings["window_3d_pct"])` sem fallback — só dispara para usuário que
tenha rota flexível **e** use `/status`, ou seja, coberto por FECHADA-4.

**Gatilho fora do controle do operador, e é o que torna a E7-2 um ato único:**
[docs/js/config.js:243/263](docs/js/config.js:243) e
[docs/js/compras.js:836](docs/js/compras.js:836) fazem `upsert` em `settings`.
Se a conta existir e o Gustavo salvar **qualquer** preferência ou teto no painel
antes do `insert`, a linha nasce com os defaults do banco — R$250, sem
`display_name`. Daí a credencial só ser entregue depois da E7-4.

**2. O que dobra quando a segunda linha existe.**

| O quê | Dobra? | Evidência |
|---|---|---|
| `weekend_leg_effective` lida pelo robô | **Sim** (132→264 linhas, 1 consulta) | [supabase_client.py:275](src/supabase_client.py:275); comentário em [etapa4_1:380](sql/etapa4_1_estado_por_usuario.sql:380) |
| Fila de pernas (`get_active_legs`) | **Não** — 1 entrada por perna, `ceilings_by_user` com 2 chaves | [weekends.py:229-258](src/weekends.py:229) |
| Laço de avaliação `per_user` | **Sim** | [weekends.py:338](src/weekends.py:338) |
| Cooldown (`get_last_weekend_leg_alert`) | **Sim** — até 2 SELECTs por usuário por perna que alertaria | [weekends.py:371-374](src/weekends.py:371) |
| Mensagens do Telegram + inserts em `alert_log` | **Sim** — o leque abre aqui e só aqui | [main.py:530-553](src/main.py:530) |
| Resumo semanal | **Não** — uma mensagem só | [main.py:555-557](src/main.py:555) |
| Dashboard / Compras no navegador | **Não** — `security_invoker=true` ([etapa4_1:389](sql/etapa4_1_estado_por_usuario.sql:389)) + RLS `auth.uid()=user_id` de `settings` ⇒ 132 por navegador | `AUDITORIA-MULTIUSUARIO.md`, seção 2 |

**Dois efeitos de segunda ordem que nenhum arquivo tinha nomeado ainda:**
- **`get_weekend_leg_counts` muda de significado**
  ([supabase_client.py:382](src/supabase_client.py:382)): uma perna só conta como
  comprada quando **todos** os usuários marcaram `purchased`. Com 2 contas, o
  "X de 90 pernas compradas" do resumo semanal passa a contar só as pernas que
  **os dois** compraram — que não é o número que nenhum dos dois quer ver.
  Tratado na E7-7, deliberadamente **depois** de observar o comportamento real.
- **A perna só sai da fila quando todos param de monitorar**
  ([weekends.py:185-187](src/weekends.py:185)): depois de o usuário 1 comprar, a
  perna continua na rotação do lote `fli` por causa do usuário 2. **Não** aumenta
  consulta por execução (o `batch_size` é fixo), mas dilui a cobertura por perna
  — soma-se ao achado (b) de 14/08 já registrado em `STATE.md`, seção 4.

**3. GARANTIA CENTRAL DA D4 — CONFIRMADA, nenhuma violação de escopo
encontrada.** Nenhum caminho de scraping ou de consulta de preço cresce com o
número de usuários:
- `process_all_weekend_legs`: `fetch_keys` derivado só de (mês, aeroporto,
  direção) — [weekends.py:522-530](src/weekends.py:522). Travelpayouts não
  multiplica.
- `select_batch(system_settings)` lê só `batch_size`
  ([live_check.py:111-146](src/live_check.py:111)); `settings_by_user` é carga
  opaca transportada por `run_daily_batch`
  ([live_check.py:200-230](src/live_check.py:200)) e **não passa** por ela.
- `insert_weekend_leg_price`, `get_weekend_leg_price_history`,
  `update_weekend_leg`, `insert_weekend_leg_run_log`: todos fora do laço por
  usuário ([weekends.py:300-302](src/weekends.py:300) e depois do laço).
- `build_package_comparison` retorna `None` incondicionalmente
  ([live_check.py:197](src/live_check.py:197)) e é chamada **uma vez por perna**,
  antes do laço ([main.py:513](src/main.py:513)) — zero consulta.

**O que de fato cresce:** leituras/escritas de `alert_log`, mensagens de
Telegram e o número de linhas de **uma** view. Nenhum deles toca fonte externa.
As regras de scraping ficam **intocadas** — sequencial, sem paralelismo, sem
evasão, sem proxy/spoofing/CAPTCHA. Nada neste plano as revisita.

**4. RLS — inventário do que muda com duas contas.**
- **D-7 (`alert_log`)**: a policy viva é `alert_log_select_own_routes_or_any_leg`
  com o ramo `leg_id is not null and auth.uid() is not null`
  ([sql/draft_alert_log_leg_policy.sql:19-24](sql/draft_alert_log_leg_policy.sql:19),
  confirmada em produção em 31/07/2026, ver `AUDITORIA-MULTIUSUARIO.md`). Hoje
  isso significa: o segundo usuário enxergaria **todo** o histórico de alertas de
  perna do primeiro, incluindo o `reason`, que carrega o teto por extenso
  ("R$ 304 ≤ teto R$ 300").
  **Achado que barateia a fatia:** `grep alert_log docs/` → **zero**; não há
  consumidor de frontend. E o SQL Editor roda como dono, que ignora RLS — então
  apertar para `user_id = auth.uid()` **não esconde as 54 linhas históricas do
  operador**, só da API autenticada, que ninguém usa. Custo real ≈ zero.
- **`weekend_leg_user_state`**: 4 policies `= auth.uid()` + `user_id default
  auth.uid()` ([etapa4_1:100,123-139](sql/etapa4_1_estado_por_usuario.sql:100)).
  O `upsert` do painel não manda `user_id`
  ([compras.js:58](docs/js/compras.js:58)) e depende desse default — funciona
  para o Gustavo por construção, mas **nunca foi exercido por outra conta**.
- **`weekend_leg_ceiling_audit`**: `wlca_select_own` `user_id = auth.uid()`,
  append-only sem policy de escrita
  ([etapa4_1:162-196](sql/etapa4_1_estado_por_usuario.sql:162)).
- **Fatia C (`weekend_leg_purchase_shared`)**: `auth.uid() is not null`,
  compartilhada de propósito
  ([fatia_c:209-212](sql/fatia_c_visibilidade_compra.sql:209)); o front filtra a
  própria linha com `.neq('user_id', currentUserId)`
  ([compras.js:718](docs/js/compras.js:718)).

**5. DEFEITO CONFIRMADO que só se manifesta com a segunda conta.**
[docs/js/compras.js:11](docs/js/compras.js:11) define
`USER_LABELS = { 'c72bf50e-…': 'Você' }`, usado em
[compras.js:106](docs/js/compras.js:106) **sem referência a `currentUserId`**.
Como a consulta já exclui as próprias linhas, o Gustavo só vê linhas do usuário
1 — e o lookup casa com o uuid dele. **O painel do Gustavo vai renderizar
"👥 Você já comprou · …" para uma compra que não é dele.**
**E o comentário da linha 10 prescreve a correção errada:** *"Ganha a segunda
entrada quando a segunda conta existir (Etapa 7)"* — com
`{uuid1:'Você', uuid2:'Você'}` os **dois** lados passam a ver "Você". O rótulo
tem que ser relativo ao usuário logado. Corrigido na E7-1, **antes** de a conta
existir.

### O que a documentação afirma e NÃO foi possível confirmar

Era o roteiro da E7-0 — **resolvido em 15/08/2026** (ver fatia E7-0, acima,
para os números). Mantido aqui como registro histórico do que estava em
aberto antes da fatia rodar.
1. ~~O DDL de `settings` não está versionado~~ — **resolvido pelo Q1/Q2**: 16
   colunas, `PRIMARY KEY(user_id)`, todas NOT NULL com default exceto
   `user_id` e `display_name`.
2. ~~Default vivo de `weekend_default_ceiling`~~ — **resolvido pelo Q1**:
   confirmado 250 em produção.
3. ~~`routes.user_id` teria default `auth.uid()`~~ — **resolvido pelo Q3**:
   confirmado.
4. **Estado do Supabase Auth** (confirmação de e-mail, política de senha) —
   **segue não confirmado**; a E7-0 não tinha bloco para isso. Só
   `signInWithPassword` existe no código.
5. ~~Contagens atuais de `alert_log`~~ — **resolvido pelo Q4**: 81 linhas / 55
   NULL / marca d'água `11:37:27.958458+00`.

### Contradições encontradas no repositório — registradas, não conciliadas

1. **`docs/js/compras.js:10`** — o comentário prescreve a correção que piora o
   defeito (item 5 acima).
2. **`STATE.md`, seção 3, item 2 (bullet da 4.4)** ainda descrevia o lado de
   leitura da RLS de `weekend_legs` como *"pendência separada a resolver antes
   da Etapa 7"*, enquanto a seção 4 do mesmo arquivo e a seção "Etapa 4.4"
   abaixo registram o item como **fechado em 08/08/2026**. Texto defasado, não
   pendência real — **corrigido nesta rodada** (15/08/2026).
3. **Scripts que ficam vencidos no instante da segunda linha em `settings`:**
   [sql/etapa4_1_verificacao.sql:93,152](sql/etapa4_1_verificacao.sql:93) cravam
   132 como esperado da view (viram 264 e passariam a acusar falso erro).
   Já se autoprotegem, e isso é bom sinal:
   [etapa4_1:53-56](sql/etapa4_1_estado_por_usuario.sql:53) e
   [etapa4_2_resync:268-272](sql/etapa4_2_resync.sql:268) têm guarda de
   "exatamente 1 conta";
   [etapa4_3_verificacao_pos_drop.sql:196-200](sql/etapa4_3_verificacao_pos_drop.sql:196)
   calcula dinamicamente e **sobrevive**. Tratado na E7-7.

### As fatias

Ordem de execução real, com a numeração já refletindo FECHADA-3. Cada fatia diz
o que é reversível e o que não é.

**E7-0 — 🟢 CONCLUÍDA (15/08/2026). Pré-voo (só leitura). REVERSÍVEL: total,
nada foi criado.**
Script: [sql/etapa7_0_inventario.sql](sql/etapa7_0_inventario.sql). 5 blocos
(Q1-Q5), rodados um por vez no SQL Editor pelo usuário em 15/08/2026. **Nenhum
gate de parada disparou.**

- **Q1 — DDL real de `settings` (16 colunas).** Todas NOT NULL com default,
  exceto duas: `user_id` (obrigatório, sem default — precisa vir no insert de
  qualquer forma) e `display_name` (nullable, sem default — a única que corre
  risco real de nascer vazia). Defaults confirmados:
  `window_3d_pct` numeric default 10 · `window_7d_pct` numeric default 15 ·
  `notification_mode` text default `'alert_only'` ·
  `cost_per_thousand_brl` numeric default 25 ·
  `updated_at` timestamptz default `now()` ·
  `freshness_hours` integer default 24 ·
  `stale_alert_policy` text default `'warn'` ·
  `realert_drop_pct` numeric default 5 · `realert_days` integer default 3 ·
  `suspicious_below_avg_pct` numeric default 50 ·
  `weekend_opportunity_pct` numeric default 15 ·
  `fast_flights_enabled` boolean default true ·
  `fast_flights_daily_batch_size` integer default 20 ·
  `weekend_default_ceiling` numeric default 250 **(confirmado — bate com o
  script)** · `display_name` text, nullable, sem default.
  **CORREÇÃO DE FATO sobre a decisão original de semeadura (ver E7-2
  abaixo):** o motivo que originalmente justificava semear todas as colunas
  era [src/bot_commands.py:65](src/bot_commands.py:65)
  (`window_3d_pct` sem fallback) — mas `window_3d_pct` é `NOT NULL default
  10`, estruturalmente impossível nascer NULL. O medo que motivou a decisão
  de semear tudo não se sustenta.
- **Q2 — constraints de `settings`.** `PRIMARY KEY` em `user_id`
  (`settings_pkey`) + `FOREIGN KEY settings_user_id_fkey` (`user_id` →
  `auth.users`). **Gate de parada NÃO disparado** — PK é mais forte que
  `UNIQUE` (garante unicidade + NOT NULL + alvo de conflito válido para
  `upsert`). Achado extra, não documentado antes: a FK impede inserir
  `settings` para um `user_id` que não seja conta real.
- **Q3 — default de `routes.user_id`.** `default auth.uid()` **CONFIRMADO**.
  Dúvida da auditoria ("nunca verificado") resolvida — um insert do painel
  pelo segundo usuário nasce com o dono correto automaticamente.
- **Q4 — `alert_log`.** 81 linhas totais (era 78 em 14-15/08) · 55 com
  `user_id` NULL (era 54) · 55 linhas de perna (`leg_id` not null) · 55
  linhas de perna com `user_id` NULL · marca d'água real
  `2026-08-14 11:37:27.958458+00` (documentação anterior registrava
  `11:37:28.822753+00`, diferença de 0.86s, provavelmente por desenho — a
  marca d'água é o corte exclusivo, não precisa bater ao milissegundo).
  **Achado que importa:** `total_linhas_de_perna == linhas_de_perna_user_id_null`
  (55 == 55) — **100% das linhas de perna existentes ainda têm `user_id`
  NULL**. Nenhuma linha gravada pelo mecanismo da D4 apareceu até esta
  medição — consistente com a "ausência de dado" registrada no override do
  gate, acima.
- **Q5 — linha de base.** `settings`: 1 linha · `weekend_leg_effective`: 132
  linhas. Exatamente como esperado — linha de base limpa para a E7-2 medir
  depois (esperado então: 2 e 264).

*Gates de parada (nenhum disparou):* default de `weekend_default_ceiling` ≠
250 — **não disparou, confirmado 250**; ausência de `unique(user_id)` em
`settings` — **não disparou, PK cobre o mesmo papel e é mais forte**.

**E7-1 — Rótulo de usuário relativo ao logado (só código). REVERSÍVEL:
`git revert`.**
Corrigir [compras.js:11/106](docs/js/compras.js:11) para um rótulo **constante**
("Outro usuário"), não mais um mapa por uuid, e corrigir o comentário enganoso
da linha 10. **`display_name` como fonte foi DESCARTADO (revisão de 15/08/2026,
COR-1):** a coluna mora em `settings`, cuja RLS é `auth.uid() = user_id` — o
navegador do segundo usuário não consegue ler a linha do primeiro para buscar o
nome dele. Não é necessário: a consulta a `weekend_leg_purchase_shared` já
filtra as próprias linhas com `.neq('user_id', currentUserId)`
([compras.js:718](docs/js/compras.js:718)) — tudo que sobra é do outro usuário
por definição, sem precisar de nome nenhum ali.
*Verificação:* com uma conta só o painel não muda — não existe linha
compartilhada. Asserção fraca de propósito; a prova positiva é a E7-6. Sem erro
no console, sem regressão nos cards.
*Concluída quando:* commitada, publicada e o painel atual reaberto sem
regressão.

**CONCLUÍDA em 16/08/2026 — commit `b199e80`.** Mapa `USER_LABELS` e o
comentário enganoso removidos; `formatSharedFlight` usa a constante
`DEFAULT_USER_LABEL = 'Outro usuário'` direto. Diff isolado a
`docs/js/compras.js` (1 arquivo, +1/-5). Prova positiva (rótulo aparecendo de
fato com dois usuários) segue pendente para a E7-6, como previsto.

**E7-2 — 🔒 A CONTA + A LINHA DE `settings`, NO MESMO ATO (era E7-3).
IRREVERSÍVEL NA PRÁTICA.**
O usuário cria a conta no dashboard; **imediatamente depois**, um único `insert`
em `settings` com `user_id`, `weekend_default_ceiling = 300` (FECHADA-1) e
`display_name = 'Gustavo'` (FECHADA-2) explícitos. Janela: entre execuções do
robô (08h–20h BRT), mesmo cuidado dos deploys anteriores.

**SEMEADURA SIMPLIFICADA (decisão de 15/08/2026, substitui a decisão original
de semear todas as colunas — ver achado do Q1 na fatia E7-0, acima).** O
insert fixa **explicitamente só três campos**: `user_id`,
`weekend_default_ceiling = 300` (FECHADA-1) e `display_name = 'Gustavo'`
(FECHADA-2). As demais 13 colunas ficam nos defaults do banco.

*Por que a decisão mudou:* o motivo original para semear tudo era
[src/bot_commands.py:65](src/bot_commands.py:65)
(`float(settings["window_3d_pct"])`, lido sem fallback no código Python). Mas
o Q1 da E7-0 mostrou que `window_3d_pct` — e as outras 12 colunas fora das
três fixadas — são **`NOT NULL` com default vivo confirmado em produção**
(`window_3d_pct default 10`, `window_7d_pct default 15`,
`notification_mode default 'alert_only'`, `cost_per_thousand_brl default 25`,
`freshness_hours default 24`, `stale_alert_policy default 'warn'`,
`realert_drop_pct default 5`, `realert_days default 3`,
`suspicious_below_avg_pct default 50`, `weekend_opportunity_pct default 15`,
`fast_flights_enabled default true`, `fast_flights_daily_batch_size default
20`, `updated_at default now()`). É **estruturalmente impossível** essas
colunas nascerem NULL num insert que as omite — o medo que motivou a
semeadura completa não se sustenta. `user_id` já era obrigatório de qualquer
forma (sem default, `PRIMARY KEY`); `display_name` é a única das 16 colunas
sem default que exige valor explícito para não sair no fallback
`user_id[:8]` (FECHADA-2).
*O que é reversível:* apagar a linha de `settings` devolve a view a 132 linhas e
o robô ao comportamento de hoje.
*O que NÃO é:* a trigger `trg_audit_default_ceiling_ins`
([etapa4_1:352-358](sql/etapa4_1_estado_por_usuario.sql:352)) grava uma linha
`scope='default'` em `weekend_leg_ceiling_audit`, que é append-only sem policy
de delete — fica para sempre. Inofensivo, mas é rastro permanente.
*Concluída quando:* `select count(*) from settings` = 2 e
`select count(*) from weekend_leg_effective` = 264.
**A credencial NÃO é entregue ao Gustavo nesta fatia** — só depois da E7-4. É a
regra dura do item 7 da "Ordem de execução" ("o teste real de isolamento é a
primeira coisa a fazer depois de criar a conta, antes de ela receber qualquer
dado"), aplicada literalmente.

**CONCLUÍDA em 16/08/2026 — script `sql/etapa7_2_insert_settings_gustavo.sql`,
executado manualmente pelo usuário.** BLOCO 1 (insert): sucesso. BLOCO 2
(verificação): `select count(*) from settings` = **2**,
`select count(*) from weekend_leg_effective` = **264** — exatamente como
esperado. **O fan-out real começou a partir deste momento:**
`weekend_leg_effective` está dobrada e o robô vai processar 264 linhas na
próxima execução, não mais 132. A trigger `trg_audit_default_ceiling_ins`
presumivelmente gravou a linha `scope='default'` correspondente em
`weekend_leg_ceiling_audit` — não foi verificado diretamente nesta fatia, mas
é o comportamento esperado do insert; confirmação, se desejada, pode ser um
item leve da E7-4, sem bloquear nada. **A credencial do Gustavo AINDA NÃO foi
entregue nesta fatia** — liberada só na E7-4 (prova de isolamento), que
passou em 15/08/2026; ver seção da E7-4 abaixo.

**E7-3 — D-7: apertar a RLS de `alert_log` (era E7-2). REVERSÍVEL: recriar a
policy anterior.**
Trocar o ramo de perna por `user_id = auth.uid()`. As 54 linhas NULL somem da
API autenticada e continuam acessíveis pelo SQL Editor (dono ignora RLS) —
custo medido na E7-0.
*Verificação:* a policy reescrita (`alert_log_select_own_routes_or_any_leg`,
[sql/draft_alert_log_leg_policy.sql:19-24](sql/draft_alert_log_leg_policy.sql:19))
cobre **dois ramos** — rota e perna, não só perna. Medir **antes e depois por
personificação da conta real do Gustavo** (ver o ganho registrado em
FECHADA-3), **os dois ramos, nos dois momentos**:
- **Ramo de perna** (o que esta fatia muda): antes ele lê as linhas de perna,
  depois não lê.
- **Ramo de rota** (controle negativo — não é tocado por esta fatia, mas é a
  última fatia reversível antes do passo sem volta E7-4/E7-5, então precisa
  ser confirmado, não presumido): comportamento **idêntico** antes e depois —
  o que quer que ele leia (ou não leia) de `alert_log` por `route_id` continua
  igual nos dois momentos.
`grep alert_log docs/` continua em zero; robô inalterado (`service_role`
bypassa RLS).
*Concluída quando:* a personificação do Gustavo devolver 0 linha de perna
**e** o ramo de rota devolver o mesmo resultado antes e depois; a do usuário 1
continuar devolvendo as dele nos dois ramos.

**CONCLUÍDA em 15/08/2026 — script `sql/etapa7_3_rls_alert_log.sql`, rodado
manualmente pelo usuário, os 4 blocos.**
- BLOCO 1 (antes, personificando Gustavo): `pernas_visiveis_antes` = **55**,
  `rotas_visiveis_antes` = **0**.
- BLOCO 2 (troca da policy — `alert_log_select_own_routes_or_any_leg` vira
  `alert_log_select_own_routes_or_own_leg`, ramo de perna agora
  `user_id = auth.uid()`): sucesso, sem erro.
- BLOCO 3 (depois, personificando Gustavo): `pernas_visiveis_depois` = **0**,
  `rotas_visiveis_depois` = **0**.
- BLOCO 4 (depois, personificando o usuário principal/dono):
  `pernas_visiveis_dono` = **0**, `rotas_visiveis_dono` = **26**.

Três dos quatro números bateram exatamente com o esperado: o vazamento de 55
linhas de perna confirmado no BLOCO 1 e fechado para o Gustavo no BLOCO 3
(55 → 0); o ramo de rota como controle negativo, inalterado (0 → 0).

> **⚠️ RESSALVA — um resultado divergiu do esperado: `pernas_visiveis_dono` =
> 0, não >0.**
>
> O critério de conclusão desta fatia previa que a personificação do usuário
> principal (BLOCO 4) continuasse devolvendo **as próprias** linhas de perna
> depois da troca da policy. O resultado real foi **0**, igual ao do Gustavo.
>
> **Causa raiz (já identificada e confirmada no chat de planejamento, não é
> defeito introduzido por esta fatia):** o achado do Q4 da E7-0 já mostrava
> `total_linhas_de_perna = 55` == `linhas_de_perna_user_id_null = 55` — **as
> 55 linhas de perna existentes hoje têm `user_id` NULL, nenhuma tem dono**.
> A policy antiga (`auth.uid() is not null`) só checava autenticação, não
> dono — por isso qualquer autenticado, inclusive o Gustavo, via as 55. A
> policy nova (`user_id = auth.uid()`) exige igualdade, e **NULL nunca é
> igual a nada em SQL** — então ninguém mais enxerga essas 55 linhas via API
> autenticada, nem o próprio dono dos dados. É consequência direta do item 5
> da verificação da D4 ainda não ter produzido nenhuma linha nova de perna
> com `user_id` preenchido — confirmado duas vezes agora (Q4 da E7-0 e este
> BLOCO 4).
>
> **Impacto — decisão consciente do usuário, 15/08/2026, opção "a": aceitar e
> seguir, não reverter.**
> - Zero impacto funcional hoje: `grep alert_log docs/` continua em zero
>   consumidores de frontend.
> - Robô inalterado: roda com `service_role`, que ignora RLS.
> - As 55 linhas não foram perdidas — continuam acessíveis pelo SQL Editor
>   (dono do banco ignora RLS); só ficaram invisíveis à API autenticada.
> - Linhas **novas** de perna, a partir do momento em que o item 5 da D4
>   finalmente confirmar (mecanismo gravando `user_id` corretamente), vão
>   nascer com dono e serão visíveis normalmente via API para quem é dono.
> - O histórico órfão (as 55 linhas anteriores à marca d'água da D3) fica
>   **permanentemente invisível à API autenticada, inclusive para o próprio
>   dono** — consequência aceita, não erro. A D3 já havia decidido
>   deliberadamente não retrofitar `user_id` nessas linhas.

**E7-4 — Prova de isolamento com duas contas reais (SQL, sem login).
REVERSÍVEL: leitura pura.**
Personificação das duas contas em transação com rollback, medindo
`weekend_leg_user_state`, `weekend_leg_ceiling_audit`, `alert_log` (ramo de
perna, pós-E7-3), `settings`, e a contagem de `weekend_leg_effective` **por
conta** (esperado: 132 cada, **não** 264).
*Concluída quando:* zero linha pessoal alheia em todas as tabelas e 132/132 na
view.
*Se falhar:* apagar a linha de `settings` do Gustavo devolve o sistema ao estado
de hoje sem perder nada — **é a saída de emergência desta etapa, e o motivo de
ela vir antes de qualquer login.**
**É aqui que a credencial é entregue**, e só se esta fatia passar inteira.

**CONCLUÍDA E APROVADA em 15/08/2026 — script
`sql/etapa7_4_prova_isolamento.sql`, executado manualmente pelo usuário.**

BLOCO 1 (personificando Gustavo): `wlus_total_visivel` = **0**,
`wlus_de_outro_dono` = **0**; `wlca_total_visivel` = **1**
(a linha da trigger `trg_audit_default_ceiling_ins` da E7-2, pertence a ele
mesmo), `wlca_de_outro_dono` = **0**; `alert_log_pernas_visiveis` = **0**;
`settings_total_visivel` = **1**, `settings_de_outro_dono` = **0**;
`wle_total_visivel` = **132**.

BLOCO 2 (personificando o usuário principal): `wlus_total_visivel` = **13**
(overrides de teto por perna já criados no uso real), `wlus_de_outro_dono` =
**0**; `wlca_total_visivel` = **21** (entradas de auditoria correspondentes),
`wlca_de_outro_dono` = **0**; `alert_log_pernas_visiveis` = **0**
(reconfirmação da E7-3, não descoberta nova); `settings_total_visivel` = **1**,
`settings_de_outro_dono` = **0**; `wle_total_visivel` = **132**.

**Conclusão: ZERO vazamento em qualquer tabela, para qualquer uma das duas
contas.** `weekend_leg_effective` = 132 para cada conta (não 264), confirmando
que o isolamento por navegador funciona apesar do fan-out real na leitura do
robô. A única divergência do "esperado ideal" é a mesma já registrada e aceita
na E7-3 (`alert_log_pernas_visiveis` = 0 para os dois lados, por causa do
histórico órfão sem `user_id`) — reconfirmação, não achado novo.

**A PROVA DE ISOLAMENTO COM DUAS CONTAS REAIS ESTÁ FEITA.** Isto libera
formalmente a entrega da credencial ao Gustavo — marco que esta fatia
representa. A retenção da credencial, em vigor desde a E7-2, **acabou**.

**E7-5 — Primeira execução real do robô com dois usuários. IRREVERSÍVEL: as
mensagens saem.**
Observar uma execução completa: `[main] 2 usuário(s) em settings`, fila ainda em
132 pernas, contagem de chamadas ao `fli` idêntica, `per_user` com 2 entradas
por perna, `alert_log` recebendo linhas com **dois `user_id` distintos**, e as
mensagens trazendo `Elton` e `Gustavo` (FECHADA-2 é o que torna esta asserção
afiada).
*Concluída quando:* os 3 números baterem (fila, chamadas, donos distintos) e
`had_error` não disparar.
*Efeito esperado, não defeito:* o volume de alerta no grupo pode dobrar (~30
alertas/14 dias viram ~60).

**CONFIRMADA PARCIALMENTE — NÃO CONCLUÍDA (estado em 17/08/2026).** O critério
de conclusão são 3 números (fila, chamadas ao `fli`, **donos distintos**) mais
`had_error` não disparar. Os dois primeiros bateram; **o terceiro — `alert_log`
com dois `user_id` distintos na mesma execução — segue SEM OBSERVAÇÃO**, e as
mensagens com "Elton" **e** "Gustavo" também. O alerta real de 17/08 08h16 BRT
fechou o item 5 da D4 (gravação de dono funciona) mas saiu para **um único**
dono, então **não** é a prova de fan-out que esta fatia exige. **A E7-5
permanece aberta.**

Base de observação — **três execuções** desde a criação da conta do Gustavo
(E7-2): 16/08 ~08h BRT (1 usuário, antes da
conta existir, 20/20 sem bloqueio — linha de base, não conta como evidência
de fan-out), 16/08 ~23h16 BRT (2 usuários, execução extra fora de padrão, ver
achado novo abaixo), 17/08 ~08h BRT (2 usuários, execução agendada normal,
20/20 pernas checadas, zero erro).

1. **Fan-out confirmado parcialmente.** Desde a criação da conta, toda linha
   de perna avaliada traz "2 usuários, menor teto R$ 300" — o laço `per_user`
   está rodando com os dois usuários. **Ainda NÃO confirmado:** `alert_log`
   recebendo linhas com dois `user_id` distintos, e mensagens de Telegram com
   "Elton"/"Gustavo" — porque **nenhum alerta disparou** nas três execuções
   (preço mínimo observado R$334, acima do teto de R$300 dos dois). Ausência
   de gatilho, não reprovação.
2. ~~**Item 5 da verificação da D4 segue sem confirmação**~~ — **SUPERADO NO
   MESMO DIA. ✅ ITEM 5 CONFIRMADO (17/08/2026).** O texto original deste item
   registrava a terceira instância consecutiva de "execução rodou, sem prova
   nem a favor nem contra". **Isso mudou:** às **~08h16 BRT de 17/08/2026** um
   alerta de perna disparou de verdade, sem ser provocado — fim de semana de
   **29/01/2027, perna de VOLTA, R$ 334** — e o `select` direto em `alert_log`
   (script [sql/etapa7_item5_verificacao_alerta_2908_2027.sql](sql/etapa7_item5_verificacao_alerta_2908_2027.sql),
   rodado manualmente pelo usuário) devolveu **3 linhas** na janela 08h–09h
   BRT, **todas** com `leg_id` e `user_id` preenchidos, `user_id` =
   `c72bf50e-16f7-48fd-9c86-7b49dea1551e`, **zero NULL**, `reason` =
   `abaixo da meta fixa (R$ 500.0)`.
   **É a PRIMEIRA confirmação real do mecanismo de gravação de dono em
   `alert_log`**, depois de três instâncias sem gatilho (E7-0/Q4 sob override
   inicial; execução de 16/08 ~08h BRT; execução extra de 16/08 ~23h16 BRT) —
   e vale lembrar a "ressalva herdada da D3": o caminho de rota nunca serviu
   de ensaio para o de perna, então não havia nenhuma observação anterior deste
   mecanismo em produção. Detalhe completo, incluindo a lacuna dos `id` não
   transcritos e a divergência R$500 × R$300 no `reason`, na subseção "Fatia
   D4", item 5.
   **O QUE ESTA PROVA NÃO É — e por isso a E7-5 não fecha aqui:** as 3 linhas
   são todas do **MESMO** usuário (só "Elton"; nenhuma mensagem saiu para o
   Gustavo nesta execução). **`alert_log` com dois `user_id` DISTINTOS na
   MESMA execução continua SEM OBSERVAÇÃO** — é o que falta para fechar a
   E7-5 por completo, e é item diferente do item 5 da D4.
   **O item 6 da D4 (nome na mensagem do Telegram) também fechou** neste mesmo
   alerta, por print de tela exibindo "👤 Elton" — camada de mensagem, não de
   banco. Ver a nota de numeração na subseção "Fatia D4".
3. **ACHADO NOVO — execução extra fora de padrão.** Em 16/08 ~23h16 BRT
   (perto do horário agendado de ~20h) rodou uma "execução extra" (pulando
   rotas flexíveis/Travelpayouts), não a agendada normal. Duas perguntas em
   aberto, **não investigadas ainda**:
   - (a) o que disparou essa execução extra tão perto do horário agendado —
     suspeita não confirmada: algum push/commit desta sessão de trabalho pode
     ter acionado `workflow_dispatch` coincidindo com a janela;
   - (b) ✅ **FECHADO (17/08/2026) — era TRANSITÓRIO, autorrecuperado.** Essa
     execução bateu no detector de bloqueio (falhas seguidas após 6 consultas,
     lote interrompido em 6/20 pernas) e o sistema se comportou corretamente
     (parou, não contornou). **Encerrado pela mensagem do próprio bot em
     17/08/2026 08h16 BRT:** *"✅ Consulta ao vivo normalizada — voltou a
     funcionar depois de 1 dia sem sucesso"*. Ou seja: a fonte voltou sozinha,
     sem intervenção nenhuma. **Registrado como ocorrência TRANSITÓRIA e
     autorrecuperada, NÃO como problema persistente da fonte** — não é ruído
     estrutural nem sinal relacionado à lacuna do `LIVE_CHECK_WINDOW_DAYS`, e
     **deixa de ser pendência**. Não deve reaparecer como "em aberto" em
     rodadas futuras.
   **Pendência nomeada, restringida ao subitem (a).** O subitem (b) está
   fechado (acima). Resta só **(a)**: o que disparou a execução extra tão perto
   do horário agendado — sem decisão sobre investigar, fica para rodada futura.
   **TERCEIRA OCORRÊNCIA DO PADRÃO (17/08/2026 ~23h18 BRT, run
   `86964564238`).** Mesmo padrão de horário das duas observações anteriores
   (16/08 e 16/08 execução extra bloqueada), agora sem sequer tentar
   live-check: `"[main] Estágio 0 já rodou os lotes fli esperados hoje —
   pulado nesta execução"`. Subitem (a) **permanece ABERTO** — a causa (push/
   commit disparando `workflow_dispatch`) segue suspeita não confirmada;
   `is_primary_run` não está em `main.py` e ainda não foi lida. Só registro
   da recorrência, causa não investigada nesta rodada.
4. **Execução de 17/08 ~08h BRT: limpa.** 20/20 pernas checadas, zero erro,
   zero traceback, job concluído com sucesso, 2 usuários avaliados
   corretamente em todas as pernas. **É a execução que produziu, às ~08h16
   BRT, o alerta real que fechou os itens 5 e 6 da D4 (item 2 acima) e a
   mensagem de normalização que fechou o subitem 3(b).**

**E7-6 — Painel do Gustavo + a linha da Fatia C. REVERSÍVEL: só leitura, exceto
a compra de teste (desfeita no fim).**
Login do Gustavo: Compras carrega 132 pernas com o teto dele, Dashboard idem,
`weekend_leg_user_state` nasce por `default auth.uid()` ao salvar um teto
próprio. Depois, **o item que nunca teve verificação positiva possível**: uma
perna marcada como comprada de um lado aparece do outro como **"Outro usuário já
comprou"** — e, na direção inversa, **não** como "Você" (a E7-1 é o que garante
isso).
*Concluída quando:* as duas direções conferidas e a compra de teste desfeita (a
trigger limpa a projeção sozinha,
[fatia_c:176-179](sql/fatia_c_visibilidade_compra.sql:176)).

**E7-7 — Fechamento e higiene. REVERSÍVEL: documentação.**
Marcar `sql/etapa4_1_verificacao.sql` como vencido (expectativas de 132),
decidir a semântica de `get_weekend_leg_counts` no resumo semanal com 2 usuários
— **deliberadamente adiada para cá**, depois de observar o comportamento real em
vez de decidir no papel — e mover o conteúdo desta seção para o `HISTORICO.md`
conforme a regra de manutenção do `PROTOCOLO-DE-TRABALHO.md`.

### O que SÓ é verificável com duas contas — lista nomeada (11 itens)

É o valor real da Etapa 7, e o motivo de ela não poder ser substituída por
teste. A lógica de fan-out **já está coberta** por 267 testes unitários com
usuários fictícios (contagem estática conferida em `tests/`: 267, batendo com o
registrado na D4), incluindo
`test_two_users_get_two_messages_and_two_rows_with_distinct_owners` e
`test_cooldown_matrix_user_times_type`. O que falta é tudo o que depende do
**banco real**:

1. `weekend_leg_effective` devolvendo 264 linhas ao robô e **132 a cada
   navegador** — o não-dobrar do painel.
2. Isolamento positivo de `weekend_leg_user_state` — hoje só simulado (blocos
   E/F, cuja capacidade de prova foi revisada para baixo em 02/08/2026).
3. Isolamento positivo de `weekend_leg_ceiling_audit`.
4. `alert_log` com dois `user_id` distintos gravados na mesma execução.
5. A RLS apertada da D-7 efetivamente barrando o outro usuário.
6. **A linha "outro usuário já comprou"** da Fatia C — o item explicitamente sem
   verificação positiva possível desde 11/08/2026 (`HISTORICO.md`, item 23).
7. **O defeito do rótulo "Você"** — só observável de dentro da conta do Gustavo.
8. Cooldown de um usuário não silenciando o outro, contra dado real.
9. O `default auth.uid()` de `weekend_leg_user_state` funcionando para uma conta
   que não seja a do usuário 1.
10. `notification_mode` por dono no caminho de rota (D-4b) — só se o Gustavo
    cadastrar rota flexível.
11. Duas mensagens no mesmo grupo com **nomes diferentes** — a prova final da
    D4.

### Riscos e pontos sem volta

**O único ponto verdadeiramente sem volta é a linha em `settings`** — e o
gatilho pode escapar do controle do operador: se a conta existir e o Gustavo
abrir o painel e salvar qualquer coisa, [config.js:243](docs/js/config.js:243)
ou [compras.js:836](docs/js/compras.js:836) criam a linha com os defaults do
banco. Daí a E7-2 ser um ato único e a credencial só ser entregue depois da E7-4.

**Reversível:** apagar a linha de `settings` (view volta a 132, robô volta ao
comportamento de hoje).

**NÃO reversível:** a linha de auditoria de teto (acima); e — o mais grave —
**apagar a conta do Gustavo depois de ela ter alertado**: `alert_log.user_id` é
`on delete set null`
([sql/fatia_d3_user_id_alert_log.sql:257](sql/fatia_d3_user_id_alert_log.sql:257)),
então as linhas de perna dele voltam a NULL **do lado errado da marca d'água da
D3**, criando exatamente o terceiro significado de NULL que a D3 e a D4
gastaram duas fatias para evitar. **Se a conta precisar sumir, apagar a linha de
`settings` — não a conta — é a saída limpa.**

**Ordem que reduz dano, e o porquê:** E7-0 e E7-1 antes de tudo porque são
reversíveis por revert e fecham, respectivamente, os gates de leitura e o
defeito visual **antes** de existir alguém para vê-lo. E7-4 antes de qualquer
login porque é o último ponto em que apagar uma linha desfaz tudo.

---

## Etapa 4.2 — virada de leitura (pendências 1–11 e 13 concluídas; 12 em aberto)

**Etapa 4.1 concluída e verificada em 01/08/2026.** A estrutura nova
(`weekend_leg_user_state`, `settings.weekend_default_ceiling` como teto padrão
por usuário, `weekend_leg_ceiling_audit`, view `weekend_leg_effective`) existe
no banco de produção e passou pelos blocos A–G. Detalhe no `HISTORICO.md`,
item 17; tabelas da verificação em `AUDITORIA-MULTIUSUARIO.md`. Nada lê a
estrutura nova ainda — é o que esta etapa faz.

> **O teto padrão é um valor vivo.** A fonte de verdade é
> `settings.weekend_default_ceiling`, editável no painel (Compras → "Salvar meu
> teto padrão"). Já mudou uma vez (250 → 300, em 04/08/2026) e deve mudar de
> novo conforme a calibração com preços reais de ida vs. volta avança. Nenhum
> texto de plano, código ou documentação deve fixar o número — sempre apontar
> para a coluna. Números datados em registros históricos abaixo ficam como
> estão: são fotografia do que valia naquele dia, não afirmação sobre hoje.

> ### ⚠️ REGRA DE JANELA ABERTA — vigente agora, entre a 4.1 e a 4.2
>
> Entre a 4.1 e a 4.2 **o estado vive em dois lugares**: o mundo antigo
> (`weekend_legs`) continua sendo o que o painel e o robô leem e escrevem, e o
> mundo novo (`weekend_leg_user_state`) existe mas está parado na fotografia do
> dia da cópia.
>
> Consequência prática: **teto editado no painel nesse intervalo vai para a
> coluna velha** (`weekend_legs.price_ceiling`), **a auditoria nova não
> enxerga** (a trigger está na tabela nova), e o re-sync da 4.2 vai ter que
> transformar aquele valor em **override explícito** em
> `weekend_leg_user_state.price_ceiling`, com registro próprio na auditoria.
> Se passar batido, o ajuste manual some na virada.
>
> **Enquanto a 4.2 não fechar: não editar teto no painel.**
>
> **✅ ENCERRADA (04/08/2026).** Confirmada por execução real do re-sync
> (pendências 1 e 2, `sql/etapa4_2_resync.sql`) — zero teto preso na coluna
> velha, zero campo de estado pendente de cópia. Já estava tecnicamente
> fechada desde as pendências 3/4 (03/08/2026), quando o painel parou de
> escrever em `weekend_legs.price_ceiling`; a execução do re-sync fecha
> formalmente o registro histórico do intervalo. Texto acima mantido para
> contexto de por que a regra existiu. **Não confundir com a "JANELA ABERTA 2"
> abaixo, que segue em aberto até a Etapa 6.**

> ### ⚠️ JANELA ABERTA 2 — painel novo × Telegram velho (decisão 03/08/2026)
>
> A pendência 3/4 vira só o **painel**: passa a ler/escrever
> `weekend_leg_effective` / `weekend_leg_user_state`. O robô e o Telegram
> (`src/weekends.py`, `live_check.py`, `telegram_notifier.py` — pendência 6,
> ainda não implementada) continuam lendo `weekend_legs.price_ceiling`
> diretamente. Consequência: **teto editado no painel deixa de ter qualquer
> efeito nos alertas do Telegram** até a Etapa 6 entrar.
>
> **Decisão: sem shadow-write.** Não gravar o teto nos dois lugares ao mesmo
> tempo para remendar esse intervalo — isso reintroduziria o problema que a
> Etapa 4 existe para resolver (`weekend_legs.price_ceiling` é 1 valor global,
> não comporta dois usuários com tetos diferentes). O painel mostra um aviso
> de UI simples perto do campo de teto (sem lógica nova) enquanto durar.
>
> **Fecha sozinha quando a Etapa 6 entrar** (o robô passar a ler o teto
> efetivo por usuário) — não antes.
>
> **✅ PARTE DO TETO ENCERRADA (05/08/2026, com prova de produção em
> 06/08/2026).** As pendências 6/7(leve)/8/9 fecharam a divergência de
> leitura: o robô e o Telegram passaram a ler `weekend_leg_effective`. **Teto
> editado no painel volta a valer no Telegram**, e perna marcada como comprada
> volta a sair da fila do robô. A previsão acima ("fecha só na Etapa 6") estava
> certa sobre o fan-out e errada sobre o teto — dava para separar as duas
> coisas, e foi o que se fez.
>
> A leitura funcionava desde 05/08, mas o valor lido ainda era R$250 — a
> recalibração para R$300 (04/08) não tinha persistido no banco. Corrigido
> manualmente em 05/08 (novo save, confirmado por `weekend_leg_ceiling_audit`).
> **Prova final em 06/08/2026:** execução real do robô, não pulada por cota
> diária ("20/20 pernas checadas, 20 com preço"), registrou as 22 ocorrências
> de teto no log todas em R$300, nenhuma em R$250. Fecha de vez esta parte —
> não só o caminho de leitura, mas o valor que ele lê em produção.
>
> **SEGUE ABERTO até a Etapa 6** (nada disso mudou nesta rodada):
> - **Fan-out de alerta por usuário.** O Telegram é um canal único. Com dois
>   usuários, quem receber o alerta recebe o do teto mais apertado, sem saber
>   de quem é.
> - **Cooldown/dedup por perna × usuário.** Hoje é por perna, global.
> - **Mensagem com nome e valor de cada usuário.**
> - **Limiares gerais de um usuário só** (% oportunidade, cooldown/re-alerta,
>   modo de notificação) — escolhidos de forma determinística (menor `user_id`)
>   e com aviso no Telegram quando há mais de um usuário, mas ainda não
>   individualizados.
>
> Enquanto isso, duas regras **provisórias** governam o caso multiusuário, as
> duas marcadas como tal no código (`weekends.resolve_effective_leg_state`):
> vale o **menor teto** entre os usuários que ainda monitoram a perna, e a
> perna **fica na fila enquanto pelo menos um** usuário a monitorar. Com uma
> conta só — cenário de hoje — as duas são invisíveis.
>
> **✅ ENCERRADA (15/08/2026, Fatia D4).** Os quatro pontos que seguiam
> abertos fecharam de uma vez, na implementação:
> - **Fan-out de alerta por usuário** — o laço de envio de `main.py` manda uma
>   mensagem por (perna × usuário que disparou). O canal do Telegram continua
>   sendo um só; o que mudou é que cada alerta agora é de alguém.
> - **Cooldown/dedup por perna × usuário** — `get_last_weekend_leg_alert`
>   ganhou `user_id` obrigatório, e `alert_log` de perna passou a nascer com
>   dono (a coluna que a D3 criou, agora preenchida).
> - **Mensagem com nome e valor de cada usuário** — `build_weekend_alert_message`
>   recebe a decisão daquele usuário (teto, razão, tipo) e o rótulo dele
>   (`settings.display_name`, com fallback para os 8 primeiros caracteres do
>   uuid).
> - **Limiares gerais de um usuário só** — a escolha por menor `user_id` foi
>   **extinta**, junto com o aviso de Telegram que a anunciava. Cada usuário é
>   avaliado com as configurações dele.
>
> Das duas regras provisórias, **uma morreu e a outra virou definitiva**: o
> MIN de teto entre usuários acabou (cada um leva o seu teto até o ponto de
> avaliação); a regra de fila — a perna fica enquanto **pelo menos um** usuário
> a monitorar — continua valendo e deixou de ser provisória.
>
> **Encerramento é da REGRA, não da verificação em produção**, que segue em
> aberto (código a publicar) — ver subseção "Fatia D4".

**Medição da janela aberta (03/08/2026, chat de planejamento).** Consulta
somente leitura em produção, comparando `weekend_legs` (mundo antigo) com a
fotografia da 4.1 em `weekend_leg_user_state`:

```
tetos_divergentes_janela_aberta:    0
compras_novas_sem_linha_de_estado:  0
linhas_existentes_ja_divergentes:   0
total_linhas_de_estado_hoje:        5
total_compradas_mundo_antigo:       0
total_com_valor_pago_mundo_antigo:  5
```

Confirma que a regra de janela aberta segurou 100% até agora — zero teto
editado no painel desde a 4.1 — e que zero compras/edições novas aconteceram
no intervalo (as 5 linhas de estado continuam idênticas à fotografia).
**Ressalva: isso não elimina o risco em princípio, só descreve o estado
observado nesta data** — o re-sync continua necessário, porque o intervalo
entre agora e a execução real da 4.2 pode gerar divergência nova.

### Pendências nomeadas (12 no total — 1 a 11 concluídas; resta a 12, que é backlog)

1. ✅ **Concluída e executada em produção (04/08/2026).** Re-sync do estado
   antes de virar a leitura — desenhada (03/08/2026), corrigida para a regra
   de não-sobrescrita por campo depois que as pendências 3/4 entraram antes
   do previsto, e executada via `sql/etapa4_2_resync.sql` (mantido no
   repositório, re-rodável). **Resultado: zero divergência** entre 01/08 e
   04/08/2026 — pré-voo (Bloco 0) com `p1_linhas_a_inserir` e todos os
   `p1_*_a_escrever` em 0; execução (Bloco 1) com `parte_a_linhas = 0`. Não
   havia nada a copiar: confirma e estende a medição de 03/08/2026 registrada
   abaixo. Desenho original mantido nesta seção como registro:

   A cópia da 4.1 é uma fotografia. A partir dela,
   todo `paid_price`/nota/compra novo continua indo para `weekend_legs` (mundo
   antigo) e não para `weekend_leg_user_state`. Quanto maior o intervalo 4.1 →
   4.2, mais desatualizada a cópia. O Bloco 7b é re-rodável, mas
   `on conflict do nothing` **não atualiza** linha já criada — o re-sync da 4.2
   precisa de lógica própria. Desenho decidido:
   - Trocar `on conflict do nothing` por
     `on conflict (leg_id, user_id) do update`, escrevendo
     `status`/`notes`/`paid_price`/`purchased_at` de `weekend_legs`, só quando
     o valor mudou (evitar linha de auditoria falsa em campo que não é teto).
   - Idempotência obrigatória: rodar duas vezes seguidas não pode gerar
     segunda linha de auditoria se nada mudou entre as rodadas (mesmo padrão
     já verificado na 4.1).
   - Decisão de timing: o script é genérico e re-rodável, mas só deve ser
     executado de fato imediatamente antes do deploy que vira a leitura — não
     antes.
2. ✅ **Concluída e executada em produção (04/08/2026).** Teto editado no
   painel entre a 4.1 e a 4.2 vira caso especial do re-sync — desenhada
   (03/08/2026) e executada junto com a pendência 1, via
   `sql/etapa4_2_resync.sql`. **Resultado: `p2_tetos_a_escrever = 0` e
   `parte_b_linhas = 0`** — nenhum teto ficou preso na coluna velha no
   intervalo 01/08 → 04/08/2026; confirma a medição de 03/08/2026 (zero
   divergências) e a estende até a data de execução. Desenho original mantido
   nesta seção como registro:

   O guarda 1c do script exige todas as pernas em 250 no momento de rodar, e a
   4.1 por isso não copia teto. Se um teto for editado no painel depois disso,
   ele vai para a coluna velha (`weekend_legs.price_ceiling`), a auditoria nova
   não enxerga (a trigger é na tabela nova), e o re-sync da 4.2 tem que saber
   transformar aquele valor em **override explícito** em
   `weekend_leg_user_state.price_ceiling` — e registrar isso na auditoria com
   origem própria. Se passar batido, o ajuste manual some na virada. Desenho
   decidido:
   - Toda perna onde `weekend_legs.price_ceiling <> 250` no momento em que o
     re-sync rodar de fato (calculado na hora da execução, não hardcoded a
     partir da medição de 03/08/2026, que deu zero divergências) recebe esse
     valor em `weekend_leg_user_state.price_ceiling`, com origem própria na
     auditoria: `origin = 'resync_override'` (distinta de `'migracao'` e de
     `'app'`).
3. ✅ **Concluída, commitada e enviada (03/08/2026).** **`docs/js/compras.js`**
   — ler de `weekend_leg_effective`, escrever em `weekend_leg_user_state`
   (upsert por `leg_id`, sem mandar `user_id`, que tem `default auth.uid()`),
   remover `DEFAULT_CEILING = 200`. Commits `531f34f` (implementação) e
   `9436bc0` (correção de um `return` ilegal fora de escopo de função,
   achado na verificação manual no site publicado). `origin/main == HEAD`
   confirmado após o push. Verificação manual completa (5 passos) realizada
   no site publicado, com login real.

   **Decisão 1 (chat de planejamento, 03/08/2026) — regra de "Salvar" do teto
   por perna:** ao clicar Salvar, o valor do campo naquele momento sempre vira
   override explícito em `weekend_leg_user_state.price_ceiling` — mesmo que
   numericamente coincida com o teto padrão atual do usuário. Não detectar
   "é igual ao padrão, então não é override de verdade": comportamento
   escondido, difícil de prever/debugar, e quebraria no dia em que o padrão
   mudasse (override deixaria de ser fixo, passaria a seguir o padrão novo
   por coincidência de número). Reverter um override e voltar a seguir o
   padrão é ação separada, fora do escopo desta rodada — ver item 12 abaixo.
   A view já expõe `ceiling_is_explicit` (`st.price_ceiling IS NOT NULL`),
   pronta para alimentar essa ação futura sem consulta extra.
4. ✅ **Concluída, commitada e enviada (03/08/2026).** **Botão "aplicar teto a
   todos" muda de significado** (decisão do chat de planejamento, 01/08/2026):
   virou "Salvar meu teto padrão", editando `settings.weekend_default_ceiling`,
   e **não sobrescreve** teto ajustado à mão perna a perna — o `update` em
   massa antigo em `weekend_legs` (`docs/js/compras.js:517`) foi substituído,
   sem filtro por status, e o texto do `confirm()` mudou junto. Mesmos commits
   da pendência 3 (`531f34f`, `9436bc0`).
5. ✅ **Concluída, commitada e enviada (04/08/2026).** **`docs/js/dashboard.js`**
   — mesma troca de fonte de `compras.js` (pendências 3/4): embed
   `weekends.select('*, weekend_legs(*)')` substituído por duas queries
   (`weekends` + `weekend_leg_effective`), agrupadas por `weekend_id` em JS,
   com `error` checado nas duas (antes só `weekends` era desestruturado sem
   checar) — em caso de erro, `alert()` e interrompe, sem renderizar dado
   parcial. Sem `normalizeLegRow` (`leg_id` → `id`): nenhuma função do arquivo
   referencia `leg.id`. Bootstrap virou `async function initPage(session)`
   pelo mesmo motivo do commit `9436bc0` (`return` de tratamento de erro é
   ilegal solto no escopo do módulo). Nenhuma função de render alterada.
   Commit `05c6f97`. `origin/main == HEAD` confirmado após o push.
   Verificação manual no site publicado, logado: teto individual salvo em
   Compras (perna Ida 04/09, override R$ 555) refletido no Dashboard —
   "Ação do dia" contou a perna como abaixo do teto e "Melhores
   oportunidades → Abaixo do teto" mostrou "R$ 536,00 (3% abaixo do teto)",
   consistente com o teto de R$ 555 salvo em Compras; console sem erros.
6. ✅ **Concluída (05/08/2026).** **Teto efetivo no robô e no Telegram.**
   `src/weekends.py`, `live_check.py` e `telegram_notifier.py` liam
   `weekend_legs.price_ceiling` com fallback `or 200`; passaram a ler
   `effective_ceiling`, resolvido de `weekend_leg_effective`.
   - **Ponto de origem único, confirmado antes de codar:** `select_batch`
     (live_check) e `process_all_weekend_legs` (weekends) chamam ambos
     `get_active_legs()`, que era o único chamador de `get_monitoring_legs`.
     Anexar o teto lá alimenta os três sites — não há caminho paralelo.
   - **`or 200` era inofensivo por acidente**, não a causa do bug em produção:
     `weekend_legs.price_ceiling` é `not null`, então o fallback nunca
     disparava. O bug real era ler a **coluna errada** (250 congelado desde a
     pendência 3/4) em vez do teto efetivo. O `or 200` saiu como dívida.
   - Eram **três** `or 200` no Python, não quatro. O quarto provavelmente era o
     `default 200` da coluna em `sql/pernas_desacopladas.sql:36` (DDL, não
     código de aplicação) — ou a contagem original errou.
   - **Sem fallback numérico.** Teto ausente (nenhum usuário em `settings`) é
     erro de dado: a regra de teto sai de cena (`target_price=None`), o preço
     continua sendo gravado, a regra de oportunidade continua valendo, e sai um
     aviso único no Telegram. Nunca um número inventado.
   - MIN entre usuários **restrito a quem ainda monitora** a perna: o teto de
     quem já comprou não deve governar o alerta de quem não comprou. Com um
     usuário só as duas leituras coincidem.
   - **Verificada em produção em 06/08/2026** (execução real, não pulada por
     cota diária): 22 ocorrências de teto no log da execução, todas em R$300 —
     ver "Janela Aberta 2" acima para o incidente de gravação que atrasou essa
     prova (04→05/08) e o detalhe completo.
7. ✅ **Concluída na versão leve (05/08/2026).** **`src/main.py`** — a escolha
   de quem dita os limiares gerais deixou de ser `next(iter(...))` (ordem de
   dicionário) e virou determinística (menor `user_id`) e barulhenta (aviso no
   Telegram quando há mais de um usuário, nomeando o escolhido). Vale para os
   dois sites do mesmo padrão — o de `weekend_settings` e o de
   `notification_mode`, que a pendência original não nomeava.
   - **Correção de desenho feita antes de codar:** `settings_cache` era montado
     a partir de `routes`, então a guarda "mais de um usuário" **nunca
     dispararia** no caso real (segundo usuário não terá rota flexível). Passou
     a ser montado de `get_all_settings()` — a mesma tabela que a view usa no
     cross join. `routes` só complementa usuário sem linha em `settings`.
   - **Não é o loop por usuário** — isso é a Etapa 6. Aqui só se trocou escolha
     implícita por escolha explícita e visível.
8. ✅ **Concluída (05/08/2026).** **Documentação do teto.** `CLAUDE.md` dizia
   "default R$ 200" e o cabeçalho desta seção dizia "= 250"; ambos passaram a
   apontar para `settings.weekend_default_ceiling` como fonte de verdade, **sem
   fixar número** — o valor é vivo (250 → 300 em 04/08/2026, e deve mudar de
   novo). Registros históricos datados ficaram como estão.
9. ✅ **Concluída no caso atual (05/08/2026).** **Fila de scraping por status
   efetivo.** `get_monitoring_legs` filtrava `weekend_legs.status = 'monitoring'`
   na consulta — coluna que o painel parou de escrever nas pendências 3/4.
   Consequência ativa em produção: **marcar perna como comprada no painel não a
   tirava da fila do robô**, e ela seguia gerando alerta de teto. Virou
   `get_all_weekend_legs()` (sem filtro de status) + filtro por status efetivo
   em `get_active_legs`.
   - Regra implementada (decisão do chat — **não reabrir**): a perna fica na
     fila enquanto **pelo menos um** usuário tiver status efetivo
     `'monitoring'`; sai só quando **todos** decidirem outra coisa. Ausência de
     linha em `weekend_leg_user_state` conta como `'monitoring'` — a view já faz
     `coalesce(st.status, 'monitoring')`, então nenhum coalesce foi preciso na
     aplicação.
   - **Modo degradado:** view vazia (nenhum usuário em `settings`) faz a fila
     cair no `weekend_legs.status` antigo, com aviso. Nunca esvazia a fila em
     silêncio.
10. ✅ **Concluída junto com a 6 (05/08/2026).** **Ordenação da fila:
    `price_ceiling` também ordena** (`price_gap` em `src/live_check.py`). Com
    dois tetos para a mesma perna, a ordenação usa o **MENOR teto entre os
    usuários** — quem tem o teto mais apertado puxa a perna pra cima na fila.
    (Decisão do chat de planejamento — **não reabrir**.) Implementada no mesmo
    ponto da pendência 6: `resolve_effective_leg_state` já entrega o MIN, e o
    `sort_key` só consome. Perna sem teto efetivo desempata por último
    (`inf`), como perna sem preço.
11. ✅ **Concluída (05/08/2026).** **Corrigir `sql/etapa4_1_verificacao.sql`** —
    a pendência tinha crescido além de só consolidar E e F numa linha cada,
    depois da investigação de 02/08/2026 (`AUDITORIA-MULTIUSUARIO.md`,
    "Verificação das estruturas novas" e "Lacuna de evidência no artefato de
    verificação"). Entregue: **blocos E e F substituídos e um bloco F2 novo
    inserido entre o F e o G** (desenho aprovado no chat de planejamento).
    Blocos A, B, C, D, G e H não foram tocados. **O arquivo não foi executado
    nesta rodada** — a execução no SQL Editor é manual, como sempre.
    - **Bloco E** — uma única linha de resultado, com `auth.uid()` e
      `current_user` como **colunas-guarda** ao lado das três contagens
      (`view_esp_0`, `estado_esp_0`, `auditoria_esp_0`). Resolve o defeito
      original: o SQL Editor só exibe o último `select` de cada bloco, então
      guarda em `select` separado era descartada em silêncio.
    - **Bloco F** — mesma consolidação, mais o **discriminador que faltava**:
      semeia dentro da própria transação uma linha de
      `weekend_leg_ceiling_audit` com `user_id` sintético alheio
      (`…-0002`, `new_value = 999`), antes de trocar de papel, e depois conta
      quantas o usuário legítimo enxerga (`alienigena_esp_0`, esperado 0). Isso
      só é possível porque `weekend_leg_ceiling_audit.user_id` **não tem FK**
      (decisão do Bloco 4 da 4.1). As outras colunas do bloco continuam sendo
      regressão do caminho legítimo, não prova de isolamento.
    - **Bloco F2 (novo)** — prova em produção a RLS de **escrita** de
      `weekend_leg_user_state`, que até aqui só tinha sido testada num Postgres
      descartável. Par de tentativas: insert com `user_id` alheio (deve ser
      rejeitado) e insert com `user_id` próprio (deve ser aceito), cada uma com
      o `sqlstate` capturado. O par junto é o que separa "o `with check` compara
      o uuid" de "está bloqueando tudo por outro motivo" — o que faria o teste
      passar por engano. Esperado: `bloqueado 42501` (RLS) e `aceito`; um
      `23503` no primeiro significaria que quem barrou foi a FK de
      `weekend_leg_user_state.user_id`, não a RLS.
    - Sub-item "limpar do `.sql` os resultados colados como tabelas markdown":
      **já estava resolvido ANTES desta sessão** — o arquivo já estava limpo em
      disco (restaurado ao último commit no housekeeping de 05/08, ver
      `STATE.md`). Não é entrega desta rodada; registrado só para fechar a
      lista.
    - **Limite que permanece, agora com motivo técnico documentado:** o
      isolamento de `weekend_leg_effective` e de `weekend_leg_user_state` entre
      **duas contas reais** continua **não demonstrável até a Etapa 7**. Não é
      lacuna vaga: a view depende de duas linhas em `settings`, e `settings.user_id`
      tem FK para `auth.users` (`settings_user_id_fkey`, confirmado em produção
      em 05/08/2026 — ver `AUDITORIA-MULTIUSUARIO.md`, seção 2), então não há
      como semear um segundo dono ali sem criar conta de verdade. O bloco F2
      cobre o que dava para cobrir com uma conta só (a RLS de escrita); o resto
      é o primeiro ato depois de criar a segunda conta.
    - **✅ Prova de produção (05/08/2026):** os três blocos (E, F, F2) rodaram
      no SQL Editor em produção e bateram exatamente com o esperado — ver
      `STATE.md`, entrada de sessão de 05/08/2026, para os números completos.
12. **Backlog — "limpar override" por perna** (registrado 03/08/2026, fora do
    escopo da pendência 3/4). Ação para remover a linha específica de
    `weekend_leg_user_state` (ou zerar `price_ceiling` para NULL) e a perna
    voltar a seguir o teto padrão do usuário automaticamente. A coluna
    `ceiling_is_explicit` da view já existe e está pronta para indicar quando
    esse controle deve aparecer — só falta desenhar a UI (ex.: botão
    "voltar ao padrão" ao lado do teto quando `ceiling_is_explicit = true`).
13. ✅ **Concluída (06/08/2026).** **`get_weekend_leg_counts` lendo coluna
    congelada.** `src/supabase_client.py` contava pernas compradas do resumo
    de segunda-feira lendo `weekend_legs.status` — a mesma coluna que as
    pendências 3/4 (03/08) tiraram de uso quando o painel passou a escrever
    status em `weekend_leg_user_state`. Consequência: o resumo semanal sempre
    relatava **0 compradas**, em silêncio, desde 03/08.
    - **Achada no diagnóstico da Etapa 4.3** (chat de planejamento paralelo,
      que audita o que ainda lê colunas antigas de `weekend_legs` antes do
      `DROP`), mas tratada como **bug vivo da 4.2**, não item da 4.3 — e com
      prioridade sobre a 4.3: essa mesma query quebraria de vez (erro, não
      silêncio) assim que as colunas antigas fossem derrubadas, então corrigir
      antes do `DROP` era condição para a 4.3 poder prosseguir.
    - **Correção:** passou a ler `weekend_leg_effective`. Perna conta como
      comprada só quando **todos** os usuários que a monitoram têm
      `status = 'purchased'` (`bool_and` por `leg_id`) — mesma regra de "sai da
      fila" da pendência 9, aplicada aqui ao complemento. Só existem dois
      estados possíveis hoje (`check` no schema,
      `sql/etapa4_1_estado_por_usuario.sql:91`), então comparar `==
      'purchased'` direto é seguro, sem inferir por ausência de monitoramento.
    - **Verificação:** consulta equivalente rodada no SQL Editor —
      132 pernas, 0 compradas, idêntico ao valor de hoje, sem regressão. O
      caminho de código só roda às segundas-feiras (`primary_run and
      date.today().weekday() == 0`), então não havia cron real disponível
      para observar a mensagem de verdade nesta rodada — **conferir a
      mensagem real do Telegram na próxima segunda-feira** para fechar o
      ciclo com prova de produção (mesmo padrão da pendência 6, que também
      levou dois dias entre "leitura corrigida" e "prova de produção do
      valor").
    - Commit `b22a569`, `origin/main == HEAD` confirmado. 189 testes
      passando (5 novos: contagem single-user e a regra de "todos precisam
      concordar" com múltiplos usuários).

### Limites conhecidos da 4.1 (registrados, não são pendência)

- A auditoria nasce com um marco inicial (`origin = 'migracao'`), não com
  histórico: continua impossível responder "que teto valia em 20/07/2026?".
- Append-only vale para a API (RLS sem policy de escrita), não para quem entra
  no SQL Editor como `postgres`, que é dono da tabela. Fechar isso exigiria
  `force row level security`, que bloquearia a própria trigger.
- A segurança da view é emprestada da RLS das tabelas de baixo — ela não tem
  filtro próprio, de propósito (com `user_id = auth.uid()` embutido, o robô, que
  roda como `service_role` com `auth.uid()` nulo, veria zero linhas). Qualquer
  policy nova em `settings` ou `weekend_leg_user_state` exige re-rodar os blocos
  E e F da verificação.
- As 5 pernas com `paid_price` preenchido e `status = 'monitoring'` são anomalia
  conhecida: copiadas como estão, sem normalizar (decisão do chat de
  planejamento).

---

## Etapa 4.3 — remoção das colunas antigas de `weekend_legs` (aberta 06/08/2026)

Remover de `weekend_legs` as 5 colunas do mundo pré-multi-usuário:
`price_ceiling`, `status`, `notes`, `paid_price`, `purchased_at`. A decisão
por perna × usuário vive em `weekend_leg_user_state` desde a 4.1, e desde a
4.2 painel e robô leem tudo por `weekend_leg_effective` — as colunas antigas
só continuam de pé como fotografia congelada.

**O que o diagnóstico (chat de planejamento, 06/08/2026) já estabeleceu:**

- Mapa de leitura/escrita de código levantado: depois da pendência 13, o
  último ponto vivo lendo essas colunas era o ramo degradado de
  `get_active_legs()` (passo 1 abaixo).
- **Nenhuma view** depende das 5 colunas.
- **Nenhuma policy de RLS** as referencia.
- **Zero divergência** entre `weekend_legs` e `weekend_leg_user_state` nas 132
  pernas.
- A pendência 13 da 4.2 (`get_weekend_leg_counts`) nasceu deste diagnóstico e
  foi tratada lá, por ser bug vivo e bloqueadora do `DROP`.

**Desenho aprovado, em 5 passos.** Regra: cada passo volta ao chat de
planejamento antes de rodar — nenhum passo encadeia sozinho. O detalhe fino de
cada passo futuro é discutido quando chegar a vez dele.

1. ✅ **Concluído (06/08/2026).** **Código do ramo degradado.** O filtro
   `if leg.get("status") != "monitoring": continue` saiu do ramo degradado de
   `get_active_legs()` (`src/weekends.py`). Precisava sair **antes** do `DROP`:
   sem colunas, `leg.get("status")` vira `None`, `None != "monitoring"` é
   sempre verdadeiro e toda perna cairia da fila em silêncio. Agora o modo
   degradado devolve todas as pernas não expiradas com
   `effective_ceiling = None` — não inventa teto, e `main.py` segue avisando no
   Telegram. Testes: `test_no_settings_still_respects_the_old_purchased_status`
   virou `test_no_settings_ignores_the_old_purchased_status` (asserção
   espelhada, guarda de regressão contra reintroduzir o filtro); a fixture
   `LEG_ROW` perdeu a chave `status`, que só existia por causa desse filtro.
   189 testes passando.
2. ⏸️ **DESACOPLADO do `DROP` (06/08/2026, chat de planejamento).** Era descrito
   aqui como pré-requisito técnico: esperar a segunda-feira para ver o
   `get_weekend_leg_counts` corrigido (pendência 13 da 4.2, commit `b22a569`)
   rodar de verdade, mantendo as 5 colunas antigas como rede de segurança até
   lá. **Não é mais pré-requisito.** Motivo: o código corrigido lê
   `weekend_leg_effective` e não toca mais nas colunas antigas — mantê-las de
   pé não sustenta rollback nenhum do caminho corrigido. A rota de volta real
   é o backup da Parte A do Passo 3. Segue como **pendência de fechamento de
   registro, não bloqueante**, e a Etapa 4.3 corre em paralelo a ela.
   **Ação combinada: a partir de segunda-feira 10/08/2026 o usuário traz o
   resultado real da mensagem de resumo semanal do Telegram** (contagem de
   pernas compradas — esperado: 0, sem erro) **e o resultado é registrado
   neste item.**
   - **Resultado de 10/08/2026: ✅ confirmado.** O resumo semanal do Telegram
     de segunda-feira 10/08/2026, 08:42 BRT, foi recebido pelo usuário e
     exibiu `0 de 132 pernas compradas`, sem erro na montagem da mensagem —
     resultado idêntico ao esperado. Fecha de vez a pendência 13 da Etapa 4.2
     (`get_weekend_leg_counts`, commit `b22a569`), aberta desde 06/08/2026,
     com prova de produção real, não só verificação por SQL.
   - **Achado lateral registrado na mesma checagem (09/08/2026 à noite):** o
     detector de bloqueio de scraping disparou e se recuperou corretamente
     — parou o lote após 5 consultas consecutivas sem dado, avisou no
     Telegram, e o lote voltou ao normal sozinho na execução seguinte (dia
     seguinte), sem intervenção manual. Registrado como prova de que o
     mecanismo de proteção (kill automático + aviso, sem tentativa de
     contornar) funciona como desenhado — não é incidente, é o
     comportamento correto sob bloqueio real.
3. ✅ **CONCLUÍDO (06/08/2026).** Backup + `DROP` das 5 colunas legadas
   executados em produção pelo usuário, no SQL Editor. Script:
   `sql/etapa4_3_drop_colunas_legadas.sql` — Bloco 0 (inventário de definição,
   só leitura) / Parte A (backup) / Parte B (guardas G0–G4 + `DROP`) / receita
   de restauração em comentário.
   - **Resultado real da PARTE B**, rodada no SQL Editor de produção:

     | colunas_legadas_restantes | linhas_no_backup |
     |---|---|
     | 0 | 132 |

     Nenhum erro nas guardas G0–G4 — todas passaram. **As 5 colunas
     `price_ceiling`, `status`, `notes`, `paid_price` e `purchased_at` NÃO
     EXISTEM MAIS em `weekend_legs`.** O backup
     `weekend_legs_legacy_columns_backup` é **PERMANENTE** e contém as 132
     linhas originais. A receita de restauração (mesmo arquivo SQL) já está
     com os tipos e defaults reais (`price_ceiling numeric not null default
     200`, `status text not null default 'monitoring'::text`), não mais com
     marcadores `<TIPO_DO_BLOCO_0>`.
   - **Achado no desenho:** `weekend_legs.price_ceiling` (teto legado) e
     `settings.weekend_default_ceiling` (teto padrão vivo do usuário) são dois
     números diferentes por desenho, não por defeito — o legado está congelado
     em R$250 desde que o painel parou de escrever nele (pendências 3/4,
     03/08/2026), e o padrão vivo já foi recalibrado para R$300 (04/08/2026).
     A guarda G3 exige **uniformidade** do teto legado (`min = max`, sem NULL),
     mas **não exige igualdade** com o teto padrão de hoje — que aparece na
     mensagem só como contexto.
   - **Backup de dados não preserva definição de coluna.** `DROP COLUMN` leva
     junto tipo, default, not-null, checks e índices — por isso o script
     começa com um Bloco 0 de inventário (`information_schema.columns` +
     `pg_constraint` + `pg_indexes`), cujo resultado deve ser colado abaixo
     quando o usuário rodar.
     - **Inventário de definição das 5 colunas (BLOCO 0), rodado no SQL
       Editor de produção em 06/08/2026:**

       ```
       | tipo_de_linha | nome          | detalhe_1                | detalhe_2   | detalhe_3 | detalhe_4 | detalhe_5          |
       | coluna        | notes         | text                     | text        | /         | YES       |                    |
       | coluna        | paid_price    | numeric                  | numeric     | /         | YES       |                    |
       | coluna        | price_ceiling | numeric                  | numeric     | /         | NO        | 200                |
       | coluna        | purchased_at  | timestamp with time zone | timestamptz | /         | YES       |                    |
       | coluna        | status        | text                     | text        | /         | NO        | 'monitoring'::text |
       ```

       Nenhuma linha de tipo `constraint` e nenhuma de tipo `indice` — zero
       check/FK/unique/exclusion e zero índices citando as 5 colunas.
       Os 5 tipos conferidos batem exatamente com o `create table` da Parte A
       (nenhuma divergência; a instrução de parada do cabeçalho da Parte A não
       se aplicou). Os únicos elementos de definição a reaplicar numa eventual
       restauração são o `not null` + `default` de `price_ceiling` (`200`) e
       de `status` (`'monitoring'::text`) — o resto (`notes`, `paid_price`,
       `purchased_at`) é coluna simples, nullable, sem default.
   - **`weekend_legs_legacy_columns_backup` é PERMANENTE** — não deve ser
     apagada ao fim da Etapa 4.3 nem em limpeza de rotina; só sai por decisão
     explícita no chat de planejamento.
4. ✅ **CONCLUÍDO (07/08/2026).** Notas de cabeçalho nos scripts `sql/`
   afetados + **aposentadoria do Bloco A de `sql/etapa4_1_verificacao.sql`**.
   **Fechamento da lista fina:** o `grep` de 06/08/2026 tinha apontado 7
   arquivos; a lista final é **outra**:
   - `alvo_fins_de_semana.sql` **SAIU** da lista das 5 colunas — falso
     positivo do grep: as ocorrências de `status`/`price_ceiling`/
     `purchased_at` nele são de `weekend_targets`, tabela já dropada por
     `pernas_desacopladas.sql` (23/07/2026), não de `weekend_legs`. Recebeu
     nota própria por risco separado, fora do escopo da 4.3 — o arquivo, se
     rodado hoje, não dá erro e ressuscita em silêncio a tabela zumbi
     `weekend_targets` (66 linhas de seed) e a coluna `alert_log.target_id`.
   - `sql/etapa4_3_drop_colunas_legadas.sql` **ENTROU** — não constava na
     lista original; é o único script que já rodou contra produção (Passo 3,
     06/08/2026) sem carimbar isso, e agora tem nota de execução própria.
   - **Fecha em 7 arquivos em escopo**: 6 que tocam as colunas removidas de
     `weekend_legs` (`etapa4_1_estado_por_usuario.sql`,
     `etapa4_1_verificacao.sql`, `etapa4_2_resync.sql`, `notas_pernas.sql`,
     `parte8_preco_pago.sql`, `pernas_desacopladas.sql`) + o próprio script
     do `DROP` (`etapa4_3_drop_colunas_legadas.sql`).
   - **Armadilha ativa identificada:** `notas_pernas.sql` e
     `parte8_preco_pago.sql` fazem `alter table weekend_legs add column`
     sem `if not exists` e sem guarda — rodar hoje **não dá erro**, recria a
     coluna vazia e ressuscita em silêncio parte do mundo removido.
   - `pernas_desacopladas.sql` só falha se re-rodado por **acidente de
     ordem** (para no `create table weekends`, que já existe) — não por
     proteção desenhada; não conte com essa falha como guarda.
   - Em `etapa4_1_verificacao.sql`, só o **Bloco A** foi aposentado
     (comentado em bloco `/* */`, preservado como registro histórico).
     Blocos B, C, D, E, F, F2, G e H continuam válidos e rodáveis — E, F e
     F2 seguem sendo a prova de produção de isolamento entre usuários e de
     RLS de escrita (05/08/2026, commit `f50e55a`).
5. ✅ **CONCLUÍDO (07/08/2026).** Bloco de verificação pós-`DROP`. Script
   [sql/etapa4_3_verificacao_pos_drop.sql](sql/etapa4_3_verificacao_pos_drop.sql)
   — 6 blocos (A, B, C, D1, D2, E), todos `select`, desenhados como **colheita
   independente do Passo 3**: não reaproveitam nenhuma das guardas G0–G4 de
   `sql/etapa4_3_drop_colunas_legadas.sql`, é uma consulta escrita do zero.
   Rodado manualmente no SQL Editor de produção em 07/08/2026, um bloco por
   vez. **Zero divergência — todos os 6 blocos bateram exatamente com os
   valores esperados no rodapé do script:**
   - **Bloco A** (colunas ausentes, consulta independente): `controle_tabela
     = 1`, `controle_sobreviventes = 5`, `legadas_presentes = 0`,
     `legadas_quais = (nenhuma)`, `total_colunas_hoje = 13` — `id,
     weekend_id, direction, current_price, current_airport, current_variant,
     current_source, lowest_seen, lowest_seen_at, last_live_check_at,
     created_at, current_airline, current_departure_time`.
   - **Bloco B** (policies de `weekend_legs` vs. baseline de 01/08/2026): as
     2 policies esperadas, texto idêntico ao baseline, os 2 vereditos = `OK`.
   - **Bloco C** (triggers de `weekend_legs`): zero linhas (`Success. No rows
     returned`).
   - **Bloco D1** (estrutura nova, cardinalidade): `estado_linhas = 5`,
     `auditoria_linhas = 12`, `view_linhas = 132`, `view_esperado = 132`,
     `pernas = 132`, `usuarios = 1`.
   - **Bloco D2** (prova via `pg_depend` de que `weekend_leg_effective` não
     depende de nenhuma das 5 colunas removidas): 10 linhas
     (`current_airport`, `current_price`, `current_source`,
     `current_variant`, `direction`, `id`, `last_live_check_at`,
     `lowest_seen`, `lowest_seen_at`, `weekend_id`), `e_coluna_legada = false`
     em todas.
   - **Bloco E** (backup permanente íntegro): `linhas_backup = 132`,
     `linhas_weekend_legs = 132`, `colunas_backup = 7` (`id, price_ceiling,
     status, notes, paid_price, purchased_at, captured_at`),
     `capturas_distintas = 1`, `capturado_em = 2026-08-07 01:56:43.499924+00`
     (06/08/2026 22:56 BRT — ainda dentro do dia do Passo 3), `ids_orfaos =
     0`, `pernas_sem_backup = 0`, `rls_ligada = true`, `policies_no_backup =
     0`.

---

## Etapa 4.3 — CONCLUÍDA (07/08/2026)

Todos os 5 passos verificados: Passo 1 (código do ramo degradado, commit
`d5f97eb`), Passo 3 (backup + `DROP` em produção, commit `ce0d8b3`), Passo 4
(notas de cabeçalho + aposentadoria do Bloco A, commit `4b02093`) e Passo 5
(verificação pós-`DROP` independente, acima) concluídos. **Pendência
PARALELA e NÃO BLOQUEANTE segue em aberto**: o Passo 2 (resultado real do
resumo semanal do Telegram, a partir de segunda-feira 10/08/2026) ainda não
foi trazido — isso não impede marcar a etapa como concluída; é registro
separado, de fechamento de observação, não de correção estrutural.

---

## Etapa 4.4 — RLS de weekend_legs (CONCLUÍDA, 07/08/2026)

**Achado do diagnóstico:** `weekend_legs` tinha policy de `UPDATE` para
`authenticated` — vestígio do mundo pré-4.1/4.2, quando o painel escrevia
teto/status/notas direto nessa tabela. Desde as pendências 3/4/5 da Etapa 4.2
(verificadas em produção, 03-04/08/2026), o painel escreve em
`weekend_leg_user_state` e em `settings.weekend_default_ceiling` — nunca mais
em `weekend_legs`. Quem ainda escreve em `weekend_legs` é só o robô
(`service_role`, que sempre ignora RLS). A policy ficou sem uso real, mas
continuava sendo superfície de escrita: qualquer sessão autenticada no
navegador podia, tecnicamente, dar `update` direto em `weekend_legs` via API.
**`SELECT` continua aberto para qualquer autenticado — isso não mudou.**

**Achado do Passo 1** (checagem de segurança, `grep -rn "weekend_legs"
docs/js/`, antes de tocar no banco): 11 ocorrências, todas em `compras.js` e
`dashboard.js`, todas leitura — acesso à chave `weekend_legs` de um objeto JS
vindo de um select que embute `weekend_legs(*)` dentro de `weekends`, ou
leitura de `weekend_leg_effective`. Confirmação adicional (busca de todas as
chamadas `.from(...)` + `.update(`/`.upsert(`/`.insert(` nos dois arquivos):
as únicas escritas do frontend são `.from('weekend_leg_user_state').upsert(...)`
(`compras.js:51`) e `.from('settings').upsert(...)` (`compras.js:549`). **Zero
update/upsert/insert contra `weekend_legs` em `docs/js/`** — confirma que o
frontend não dependia da policy removida; nada divergia do que o `STATE.md`
já documentava sobre as pendências 3/4/5 da Etapa 4.2.

**Script:** [sql/etapa4_4_weekend_legs_readonly.sql](sql/etapa4_4_weekend_legs_readonly.sql)
— Guarda G0 (inventário do estado atual, para não em cima de suposição),
Parte A (`revoke update on weekend_legs from anon, authenticated`), Parte B
(`drop policy weekend_legs_update_authenticated`), verificação final.

**Resultado real, rodado manualmente no SQL Editor de produção em
07/08/2026:**

| bloco | resultado |
|---|---|
| Guarda G0 | `policies_update_hoje = 1`, `view_effective_e_updatable = NO` |
| Parte A (`revoke update`) | sucesso, sem erro |
| Parte B (`drop policy`) | sucesso, sem erro |
| Verificação final | `policies_update_depois = 0`, `authenticated_ainda_pode_update = false`, `anon_ainda_pode_update = false` |

**Achado lateral:** `view_effective_e_updatable` já vinha `NO` antes deste
script rodar. `weekend_leg_effective` é uma view com join de múltiplas
tabelas (`weekend_legs` + `weekends` + `settings` + `weekend_leg_user_state`),
sem trigger `INSTEAD OF` — o Postgres nunca a considerou automaticamente
atualizável, independente de qualquer RLS ou grant em `weekend_legs`. Ou seja:
o caminho de escrita pela view nunca foi real — este script fechou o único
caminho de escrita que de fato existia (direto na tabela).

**Correção (09/08/2026):** o parágrafo acima afirmava que o grant sobre
`weekend_leg_effective` "sempre foi só de `SELECT`"
(`sql/etapa4_1_estado_por_usuario.sql`, Bloco 6). É **falso** — verificado em
produção em 08/08/2026, no diagnóstico da Fatia C: a view tem os 7
privilégios (`select`/`insert`/`update`/`delete`/`truncate`/`references`/
`trigger`) para `anon` e `authenticated`, porque o Supabase aplica
`alter default privileges grant all` no schema `public` — todo objeto novo
nasce assim, independente do `grant select` explícito escrito no script (que
só *adiciona* select, nunca restringe o que o default já concedeu). A
**conclusão do achado lateral segue válida por outro motivo**, preservado
acima: a view não é atualizável por não ter trigger `INSTEAD OF`, qualquer
que seja o grant. Ver `sql/fatia_c_visibilidade_compra.sql` para o mesmo
achado aplicado à tabela de projeção nova (revoke explícito antes de
qualquer grant).

**Escopo confirmado como respeitado:** nenhuma outra tabela foi tocada —
`weekend_leg_user_state`, `weekend_leg_effective`, `weekends` e todas as
demais ficaram intocadas. Esta etapa foi só RLS/grants de `weekend_legs`.

**Relação com a pendência de RLS "genérica" registrada em `STATE.md` (seção
4, "Bloqueios/perguntas em aberto", 31/07/2026):** essa pendência tem dois
lados — `authenticated` conseguia **ler e escrever** qualquer linha de
`weekend_legs`, sem filtro por usuário. A Etapa 4.4 fecha só o lado de
**escrita**. O lado de **leitura** (qualquer autenticado ainda enxerga todas
as linhas de `weekend_legs`/`weekends`) segue sem alteração — continua
pendência separada, a resolver antes da Etapa 7. Nota também: a alternativa
descartada em 31/07/2026 ("travar `weekend_legs` como somente-leitura via RLS
**temporária**") era outra coisa — uma trava provisória para blindar a
migração 4.1→4.2 em andamento, descartada por risco de falha silenciosa no
frontend durante a própria migração. A Etapa 4.4 é diferente: **permanente**,
rodada só depois de a migração já estar concluída e verificada (Etapas
4.1-4.3), com checagem de segurança prévia no código real antes de tocar no
banco — não é a mesma decisão sendo revertida, é um passo posterior sobre uma
base já estável.

**Lado de leitura fechado (08/08/2026).** Pergunta de produto respondida no
chat de planejamento: dado objetivo de voo é compartilhado entre usuários —
decisão consciente, não um problema de RLS a corrigir. Confirmado por
diagnóstico só-leitura, duas partes, rodado manualmente no SQL Editor de
produção:

| bloco | resultado |
|---|---|
| Parte A (catálogo de RLS, 15 tabelas + 1 view) | todas as tabelas de decisão pessoal com policy `= auth.uid()`; todas as tabelas de mercado com policy `auth.uid() is not null`; `weekend_leg_effective` sem policy própria, `security_invoker=true` |
| Parte B (personificação de usuário fictício, `00000000-…-0001`, transação com rollback) | `weekend_leg_user_state=0`, `weekend_leg_ceiling_audit=0`, `weekend_legs_legacy_columns_backup=0`, `weekend_leg_effective=0` — zero leitura de dado pessoal alheio; `weekends=66`, `weekend_legs=132`, histórico/run log de perna > 0 — dado de mercado visível, como decidido; `price_history`/`run_log` (rotas legado) = 0, protegidas por `routes.user_id` |

Achado de higiene sem ação necessária: `grant_select_anon = true` em todas as
tabelas é grant de role padrão do Supabase, não RLS — a policy de linha é quem
efetivamente barra, confirmado pela Parte B. Fecha a pendência de RLS
"genérica" registrada em `STATE.md`, seção 4, nos dois lados (escrita pela
4.4, leitura por esta decisão). Não é mais bloqueio da Etapa 7.

---

## Fatia C — visibilidade de compra entre usuários

Concluída (Parte 1/banco 10/08/2026, Parte 2/frontend 11/08/2026). Detalhe completo movido para `HISTORICO.md`, item 23.

---

## Pendência fora do escopo desta iniciativa (registrada 30/07/2026)

`CLAUDE.md` linha 14 descreve a comparação de preço "avulso vs. pacote"
(ida+volta casado) como funcionalidade ativa, mas `STATE.md` (seção
"Decisões vivas") registra que essa comparação está **suspensa** — não
existe hoje fonte que faça round-trip de forma sequencial (`fli` só faz via
paralelismo, o que fere a regra de scraping). Achado durante a revisão de
consistência de 30/07/2026, ao corrigir a troca `fast-flights`→`fli` nessa
mesma linha (só a nomenclatura foi corrigida, não o conteúdo). Não
corrigido agora — decisão de escopo, não desta iniciativa. Retomar em
ciclo de planejamento próprio.

`CLAUDE.md` referencia `ROADMAP-AUDITORIA.md` duas vezes como fonte das
regras de scraping (item A5) e do histórico de escopo. Verificado em
01/08/2026: o arquivo **existe** no repositório (`ROADMAP-AUDITORIA.md`,
raiz do repo). Sem risco — a regra dura de scraping não perdeu seu arquivo
de origem. Não corrigido agora — decisão de escopo, não desta iniciativa.

~~`CLAUDE.md` descreve o teto default por perna como R$ 200~~ — **corrigido em
05/08/2026** (pendência 8). Registro do que era: `CLAUDE.md` dizia "default
R$ 200, pendente de calibração" enquanto o valor real em produção era R$ 250
(confirmação de 01/08/2026 em `select count(*) from weekend_legs where
price_ceiling <> 250` retornando 0, registrada acima em "(a)"), e depois R$ 300
(04/08/2026). Fixar o número no texto foi a causa de ele desatualizar duas
vezes; agora aponta para `settings.weekend_default_ceiling`.

**Nota datada de 06/08/2026:** o inventário do Bloco 0 do script da Etapa 4.3,
Passo 3 (`sql/etapa4_3_drop_colunas_legadas.sql`) mostrou que o `default` da
coluna `weekend_legs.price_ceiling` no banco **sempre foi `200`**. O
`CLAUDE.md` não estava desatualizado no sentido de "valor antigo esquecido" —
ele descrevia corretamente o default do DDL da coluna, enquanto o resto da
documentação (`STATE.md`, `PLANO-ATIVO.md`) descrevia o valor efetivo das 132
linhas (`250`, depois `300`), que já divergia do default desde a criação da
tabela. Não eram duas versões conflitantes do mesmo fato — eram dois fatos
diferentes (default do DDL × valor efetivo dos dados). Registro histórico; a
coluna e o default somem com o `DROP` do Passo 3.

`README.md` tem duas descrições desatualizadas, verificadas em 01/08/2026
(linhas 3, 11 e 52 do arquivo):
- Descreve a busca de preço como "via Travelpayouts" (linhas 3 e 11). A
  fonte primária é a `fli` desde 24/07/2026; Travelpayouts é cache
  secundário — ver `CLAUDE.md` e `STATE.md`, "Decisões vivas".
- Descreve o gatilho `push` do `daily.yml` como funcionalidade proposital
  ("roda também a cada push em `src/` (teste real automático)", linha 52).
  **O gatilho não existe mais** — foi removido em 01/08/2026 (item (b) do
  diagnóstico, hoje no `HISTORICO.md`, item 16), justamente por rodar o
  caminho primário completo contra produção (consumia scraping do dia,
  gravava no Supabase, disparava Telegram) a cada commit em `src/**`. O
  `README.md` ficou descrevendo funcionalidade inexistente. Não corrigido
  agora — decisão de escopo, não desta iniciativa.
