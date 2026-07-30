# Auditoria: suporte a segundo usuário (camada de decisão pessoal)

Data: 29/07/2026. Só investigação — nenhum arquivo de código/schema foi alterado.

**Limitação de método:** não há acesso direto ao Postgres do Supabase nesta sessão
(sem `.env` local com credenciais reais, só `.env.example`; as chaves reais vivem em
secrets do GitHub Actions). O levantamento abaixo é feito a partir de:
(a) migrations versionadas em `sql/*.sql`, (b) o que o código (frontend e robô)
efetivamente consulta/grava, (c) comentários que documentam decisões de RLS.
Tabelas criadas **antes** de `sql/` existir como diretório rastreado (`routes`,
`settings`, `price_history`, `run_log`, e `bot_state` antes de 24/07) não têm
migration correspondente no repo — o schema delas foi aplicado direto no SQL
Editor do Supabase em algum momento da migração inicial (commit `1d0a2fa`,
"Migra para Supabase..."). Recomendo confirmar a policy exata dessas tabelas
direto no dashboard do Supabase antes de agir sobre elas — o que segue é a
melhor reconstrução possível a partir de evidência indireta (código cliente +
um comentário em `sql/etapa3_cooldown.sql` que referencia `routes.user_id`).

---

## 1. Schema atual — tabela por tabela

| Tabela | Tem `user_id`? | Evidência | Observação |
|---|---|---|---|
| `routes` (rotas flexíveis, legado) | **Sim** | `main.py:287` lê `route["user_id"]`; `sql/etapa3_cooldown.sql:20` filtra `routes where user_id = auth.uid()` | Já suporta múltiplos donos de rota no schema. Mas o insert do frontend (`config.js:190`) **não envia `user_id`** — depende de default/trigger no banco (não verificado) ou fica nulo. |
| `settings` | **Sim** | `supabase_client.py:42` (`get_settings(user_id)`), `config.js:219/239` fazem upsert com `user_id: session.user.id` | Já é per-user por design — cada usuário logado tem sua própria linha de preferências (janelas de alerta, frescor, etc). |
| `price_history` (rotas flexíveis) | Não direto — depende de `route_id → routes.user_id` | `supabase_client.py:49-77` | Herda o dono via join com `routes`. Sem RLS de select rastreada em `sql/*.sql` (tabela pré-existente). |
| `run_log` (rotas flexíveis) | Não direto — via `route_id` | `supabase_client.py:94-111` | Idem `price_history`. |
| `alert_log` | Não — tem `route_id` (opcional) e `leg_id` (opcional), nenhum `user_id` próprio | `sql/etapa3_cooldown.sql`, `sql/pernas_desacopladas.sql` | Serve os dois sistemas (rota flexível e perna de fim de semana). Ver risco de RLS na seção 2. |
| `weekends` | **Não** | `sql/pernas_desacopladas.sql:18-24` | Estado global do produto — datas dos 66 fins de semana, sem dono. |
| `weekend_legs` (teto, status, notas, preço pago) | **Não** | `sql/pernas_desacopladas.sql:32-48`, `sql/notas_pernas.sql`, `sql/parte8_preco_pago.sql` | **Este é o núcleo da "camada de decisão pessoal"** citada na pergunta: `price_ceiling`, `status`, `notes`, `paid_price` — tudo hoje é 1 linha por perna, sem conceito de "por usuário". Assume single-user de forma explícita (ver `CLAUDE.md` e comentário em `sql/alvo_fins_de_semana.sql:24-26`, que herdou o padrão da tabela antiga `weekend_targets`). |
| `weekend_leg_price_history` | Não | `sql/pernas_desacopladas.sql:61-70` | Preço é compartilhado (mesmo robô, mesma rota) — correto não ter dono. |
| `weekend_leg_run_log` | Não | `sql/pernas_desacopladas.sql:78-86` | Log de execução do robô, sem dono — correto. |
| `bot_state` (key-value: `last_update_id`, `weekend_batch_blocked_at`, streaks, estágio de scrape) | Não | `sql/parte8_preco_pago.sql:6-15`, `supabase_client.py:248-379` | Estado global do robô/bot, 1 linha por chave. Não tem — e não deveria ter — `user_id`, é estado de infraestrutura, não de decisão pessoal. |
| `settings` (colunas específicas de fim de semana: `weekend_opportunity_pct`, `fast_flights_enabled`, `fast_flights_daily_batch_size`, etc.) | Sim (mesma linha per-user de `settings`) | `sql/alvo_fins_de_semana.sql:65-66`, `sql/pernas_desacopladas.sql:102-103` | Aqui mora um ponto de atenção: **preferências do sistema de fim de semana já são per-user no schema, mas o robô as trata como globais** — ver `main.py:310-313`: "settings do primeiro usuário definem tudo (app é single-user por design)". Ou seja, o dado é per-user, mas a leitura no robô pega a primeira linha que aparecer e aplica pra todo mundo. |
| `auth.users` (Supabase Auth) | — | ver seção 6 | Não investigável sem acesso ao dashboard/API admin. |

**Resumo da seção 1:** as tabelas de infraestrutura do robô (`weekends`, `weekend_legs`,
`weekend_leg_price_history`, `weekend_leg_run_log`, `bot_state`) são corretamente
globais — preço e agenda de voo são objetivos, compartilháveis. O problema real de
multi-usuário está concentrado em **4 colunas de uma única tabela**:
`weekend_legs.price_ceiling`, `.status`, `.notes`, `.paid_price` — hoje 1 valor por
perna, precisa virar 1 valor por (perna × usuário).

---

## 2. Políticas de RLS — tabela por tabela (a partir de `sql/*.sql`)

| Tabela | select | insert | update | delete |
|---|---|---|---|---|
| `weekends` | `auth.uid() is not null` (qualquer autenticado) | — (sem policy = bloqueado pra anon/authenticated; só service_role escreve) | — | — |
| `weekend_legs` | `auth.uid() is not null` | — | `auth.uid() is not null` (sem checar *qual* linha — qualquer autenticado pode dar update em qualquer perna) | — |
| `weekend_leg_price_history` | `auth.uid() is not null` | — | — | — |
| `weekend_leg_run_log` | `auth.uid() is not null` | — | — | — |
| `bot_state` | `auth.uid() is not null` (adicionada em `parte8_preco_pago.sql`, 24/07) | — | — | — |
| `alert_log` | `route_id in (select id from routes where user_id = auth.uid())` | — | — | — |
| `settings` | não rastreada em `sql/*.sql` (tabela pré-existente) — mas o comportamento do frontend (filtra sempre por `user_id = session.user.id`) sugere policy `user_id = auth.uid()` | idem | idem | — |
| `routes` | não rastreada — mas `sql/etapa3_cooldown.sql` referencia `routes.user_id`, então provavelmente `user_id = auth.uid()` já existe | não confirmada | não confirmada | — |
| `price_history`, `run_log` (rotas flexíveis) | não rastreada — provavelmente aberta a qualquer autenticado (mesmo padrão dos outros "\*_select_authenticated") | — | — | — |

**Achado importante — `alert_log` está quebrada para pernas de fim de semana.**
A policy de select (`sql/etapa3_cooldown.sql:17-21`) só cobre `route_id in (select
id from routes where user_id = auth.uid())`. Quando `pernas_desacopladas.sql`
introduziu `leg_id` como alternativa a `route_id` (linha 97-99: `check (route_id is
not null or leg_id is not null)`), **nenhuma migration atualizou a policy de select**
para incluir `leg_id is not null`. Resultado: linhas de `alert_log` geradas por
`insert_weekend_alert_log` (via `leg_id`, sem `route_id`) não são visíveis a
nenhum usuário autenticado sob RLS — `route_id in (select ...)` nunca é verdadeiro
quando `route_id` é `NULL`. Isso não impede o robô de gravar (ele usa service_role,
que ignora RLS), mas qualquer feature futura do frontend que tente ler alertas de
fim de semana direto de `alert_log` vai ver a tabela vazia. **Não é um problema
introduzido pela mudança multi-usuário — já existe hoje**, mas relevante porque
qualquer redesenho de RLS para multi-usuário vai mexer nessa mesma tabela.

**Padrão geral observado:** quase todas as policies de "select" são
`auth.uid() is not null` — ou seja, **qualquer usuário autenticado enxerga e
edita todos os dados**, não há isolamento por linha hoje (exceto `settings`,
`routes` e `alert_log` via `routes`, que já usam `user_id = auth.uid()`).
Isso é exatamente o esperado de um app single-user com RLS "genérica" (a barreira
é só "está logado ou não", não "é dono da linha ou não").

---

## 3. Frontend (GitHub Pages)

- Autenticação: `docs/js/supabase-client.js` cria o client com a **anon key**
  (pública, embutida no bundle — comportamento correto/esperado do modelo
  Supabase + RLS, não é um vazamento de segredo). Toda página exceto `login.html`
  chama `requireAuth()` (`auth-guard.js`), que redireciona pra login se não
  houver sessão. Todas as queries subsequentes rodam com a sessão do usuário
  logado (JWT com `auth.uid()`), e a autorização final é decidida pelo RLS no
  Postgres — não há chave de serviço nem bypass no frontend.
- **Pontos que assumem implicitamente "sou o único usuário":**
  - `docs/js/compras.js:51` — `update` em `weekend_legs` por `id`, sem qualquer
    filtro de usuário (porque a tabela não tem coluna de usuário hoje). Qualquer
    usuário autenticado pode alterar teto/status/notas/preço pago de qualquer
    perna, e a alteração é visível para todos.
  - `docs/js/dashboard.js:498` — lê `weekends.*, weekend_legs(*)` sem filtro de
    usuário: o painel de Compras mostra o mesmo estado (teto, status, notas)
    pra qualquer pessoa que logar.
  - `docs/js/config.js` — a seção de rotas flexíveis (`loadRoutes`, `insert`,
    `update`) nunca filtra nem envia `user_id` explicitamente; se a RLS de
    `routes` já isola por `user_id = auth.uid()` (não confirmado com certeza,
    só inferido), o insert sem `user_id` explícito só funciona se houver
    default/trigger no banco preenchendo `auth.uid()` automaticamente — vale
    confirmar isso direto no schema antes de assumir que já funciona pra 2
    usuários.
  - `settings`, por outro lado, já está corretamente isolado por usuário em
    todo o frontend (sempre filtra/grava com `session.user.id`).

## 4. Robô Python (GitHub Actions)

- **Chave usada: exclusivamente `SUPABASE_SERVICE_ROLE_KEY`** — confirmado em
  `src/supabase_client.py:22-28` (`_headers()`, usada por toda função do
  módulo, sem exceção) e em `.github/workflows/daily.yml:39`. Não há uso de
  anon key em nenhum ponto do robô.
- **`bot_state` / `set_last_update_id` especificamente:** confirmado que usa
  `_headers()` → service_role (linha 258-263 de `supabase_client.py`). Isso
  **bypassa RLS por completo**, então o gate de RLS adicionado em
  `sql/parte8_preco_pago.sql` (select-only, `auth.uid() is not null`) não afeta
  o robô — ele nunca teria falhado silenciosamente, porque nunca passou pela
  policy de select (é sempre insert/upsert via service_role, que ignora RLS
  independente de existir policy de insert ou não). **Risco descartado**: não
  há cenário hoje em que `set_last_update_id` falhe silenciosamente sob RLS.
  O único jeito de isso quebrar seria se a chave de ambiente virasse a anon
  key por engano — não é o caso atual.
- Todas as demais escritas do robô (preço, run_log, alert_log, weekend_legs,
  scrape_state) seguem o mesmo padrão: sempre service_role, sempre
  bypassando RLS. Ou seja, RLS hoje é 100% uma camada de proteção pro
  frontend (usuário logado via browser), nunca uma restrição pro robô.

## 5. Bot do Telegram

- `send_message` e `get_updates` (`src/telegram_notifier.py:10-30`) usam
  `TELEGRAM_BOT_TOKEN` e um **`TELEGRAM_CHAT_ID` fixo, vindo de variável de
  ambiente/secret do GitHub Actions** — não há tabela de mapeamento
  usuário↔chat_id em nenhum lugar do schema ou do código. O bot manda toda
  notificação (alertas, resumo semanal, avisos de bloqueio) pra um único chat.
  **Isso é uma dependência estrutural de usuário único**: hoje é literalmente
  impossível notificar 2 pessoas diferentes sem introduzir esse mapeamento —
  não é um ajuste de RLS, é uma tabela nova (`user_id → telegram_chat_id`) mais
  lógica para escolher a quem notificar por perna/decisão.
- Não há verificação de identidade nas mensagens recebidas via `get_updates`
  (comandos do bot, ex: `/status`) além do `chat_id` fixo implícito — o
  código que processa updates (não lido nesta auditoria, fora do escopo do
  módulo `telegram_notifier.py`) merece checagem futura para ver se assume
  que qualquer update recebido vem do único usuário confiável.

## 6. Supabase Auth

- Não foi possível consultar `auth.users` diretamente (sem credenciais de
  admin/API disponíveis nesta sessão — só a anon key pública, que não lista
  usuários). **Recomendo confirmar direto no dashboard do Supabase
  (Authentication → Users)** quantos usuários existem hoje.
- **Não existe fluxo de criação/convite de usuário no código**: nenhuma
  ocorrência de `signUp`, `inviteUserByEmail` ou `admin.createUser` em
  `docs/js/` ou `src/`. `login.js` só chama `signInWithPassword` — ou seja,
  hoje só é possível logar com uma conta já existente, criada manualmente
  (provavelmente direto no dashboard do Supabase). Adicionar um segundo
  usuário exigiria criar a conta manualmente no dashboard (ou implementar um
  fluxo de convite do zero) — não há nada pronto para isso.

---

## Resumo

### Já pronto para multi-usuário
- `settings`: schema e todo o código de frontend já são per-user
  (`user_id = auth.uid()` em toda leitura/escrita).
- `routes` (rotas flexíveis, legado): schema já tem `user_id`, e o robô
  (`main.py`) já processa settings por usuário nesse fluxo — o sistema legado
  foi desenhado com multi-usuário em mente desde o início, mesmo não sendo
  usado hoje.
- RLS básica de autenticação (bloquear anônimo) já existe em todas as tabelas
  do sistema de fins de semana.

### Precisa de `user_id` novo / RLS novo / migration
- `weekend_legs`: as 4 colunas de decisão pessoal (`price_ceiling`, `status`,
  `notes`, `paid_price`) precisam sair da própria linha da perna e virar uma
  tabela nova (`weekend_leg_user_state` ou similar, com `leg_id + user_id`
  como chave), porque hoje são 1 valor global por perna — não é possível ter
  "usuário A com teto R$200" e "usuário B com teto R$150" na mesma coluna.
- RLS de `weekend_legs` (update) precisa parar de ser "qualquer autenticado
  pode editar qualquer linha" — hoje não há sequer isolamento por linha,
  então qualquer segundo usuário já pode mexer nos dados do primeiro assim
  que logar, mesmo sem a mudança de schema.
- `alert_log`: policy de select desatualizada (não cobre `leg_id`) — vale
  corrigir junto, já que qualquer redesenho de RLS vai tocar essa tabela.
- Telegram: precisa de tabela `user_id ↔ chat_id` e lógica de roteamento de
  mensagem por decisão pessoal (ex: só notificar quem ainda não comprou
  aquela perna). Hoje é 100% hardcoded a um chat.
- Fluxo de criação de usuário: não existe hoje, precisa ser feito do zero
  (ou manual via dashboard, que é a saída mais simples).

### Riscos identificados
- **`bot_state`/RLS: risco descartado.** O robô sempre usa service_role, que
  ignora RLS — não há cenário de falha silenciosa em `set_last_update_id`
  hoje. Mencionar isso caso a chave de ambiente seja trocada por engano no
  futuro (aí sim viraria um risco real).
- **RLS "genérica" (`auth.uid() is not null`) em `weekend_legs`, `weekends`,
  `weekend_leg_price_history`, `weekend_leg_run_log`, `bot_state`**: um
  segundo usuário criado hoje, sem nenhuma mudança de schema, já enxergaria e
  poderia editar 100% dos dados do primeiro usuário (mesmo teto, mesmo
  status de compra, mesmas notas). Isso é o oposto do que a "camada de
  decisão pessoal" pretende — é o primeiro coisa a resolver, antes mesmo de
  pensar em UI.
- **`alert_log` select policy quebrada para `leg_id`** (achado colateral,
  independente da tarefa multi-usuário, mas na mesma tabela que qualquer
  redesenho vai mexer).
- Schema de tabelas pré-`sql/` (`routes`, `settings`, `price_history`,
  `run_log`) não está versionado — antes de migrar, vale rodar
  `pg_dump --schema-only` (ou o equivalente no dashboard) pra ter certeza do
  estado real antes de escrever a migration.

---

## Etapa 1 da iniciativa multi-usuário (29/07/2026) — baseline + uso real de `settings`

Executada após decisão no chat de planejamento de abrir a iniciativa
(escopo completo: alertas + painel + aba Compras próprios; Telegram em
grupo único). Ver `PLANO-ATIVO.md` para a ordem de execução completa.

### Baseline consolidado do schema legado

Achados confirmados pelo usuário direto no SQL Editor do Supabase (fecha a
incerteza que a auditoria original deste arquivo tinha deixado em aberto):
- `routes.user_id` existe e a RLS já é `auth.uid() = user_id` (select/update/
  insert) — schema pronto para múltiplos donos de rota.
- `settings.user_id` existe e a RLS também já é `auth.uid() = user_id`.

**Ainda não confirmado (não tenho acesso ao Postgres nesta sessão — sem
credenciais locais, só `.env.example`; as reais vivem em secrets do GitHub
Actions):** a lista exata de colunas/constraints de `routes`, `settings`,
`price_history` e `run_log`, e a policy exata de insert de `routes` (o
frontend em `config.js:190` insere sem enviar `user_id` explícito — só
funciona se houver `default auth.uid()` ou trigger no banco; não vi essa
definição em nenhum `sql/*.sql` rastreado). Se for necessário fechar esse
último detalhe antes da Etapa 3/4, rodar no SQL Editor:

```sql
select table_name, column_name, data_type, is_nullable, column_default
from information_schema.columns
where table_schema = 'public'
  and table_name in ('routes','settings','price_history','run_log')
order by table_name, ordinal_position;

select tablename, policyname, cmd, qual, with_check
from pg_policies
where schemaname = 'public'
order by tablename, policyname;
```

### Uso real de cada coluna de `settings` (file:line)

Objetivo: decidir a separação sistema (config única) × pessoal (per-user)
da Etapa 3. Resultado — as colunas se dividem em 3 grupos, não 2:

**A. Genuinamente per-user hoje, só usadas no sistema legado de rotas flexíveis** (nenhum acoplamento com o sistema de fim de semana):
- `window_3d_pct`, `window_7d_pct` — [rules.py:95](src/rules.py:95) (`detect_trend`), consumidas em [main.py:172](src/main.py:172) e [bot_commands.py:65](src/bot_commands.py:65), sempre via `settings_cache[route["user_id"]]`.
- `cost_per_thousand_brl` — [miles.py:1](src/miles.py:1) (`compare_cash_vs_miles`). **Achado colateral: esta função não é chamada em nenhum lugar do pipeline** (`main.py`, `bot_commands.py`, testes) — confirma o que `STATE.md` já registra em "Fora de escopo": existe campo/lógica mas nunca é alimentada. Column órfã, não é bloqueio pra nada, só não faz sentido tratá-la como prioridade na migração.
- `freshness_hours`, `stale_alert_policy` — [main.py:142](src/main.py:142) e [main.py:180](src/main.py:180) (`staleness`/`should_suppress_alert`), só no caminho de `process_route`. Confirmado que o sistema de fim de semana nunca chama `staleness`/`should_suppress_alert` (grep vazio em `weekends.py`/`live_check.py`) — alertas de perna são sempre imediatos, independente de frescor/supressão (comentário explícito em [main.py:390-393](src/main.py:390)).
  → Grupo A pode ficar exatamente como está (per-user, sem mudança).

**B. Compartilhadas entre os dois sistemas via uma função/leitura comum** — hoje aplicadas de forma efetivamente global ao sistema de fim de semana, mesmo sendo schema per-user:
- `notification_mode`, `realert_drop_pct`, `realert_days` — usadas dentro de `cooldown_blocks_alert` ([rules.py:52-66](src/rules.py:52)), que é chamada tanto por `process_route` (per-user de verdade) quanto por `evaluate_and_record_leg_price` em [weekends.py:177](src/weekends.py:177) — e nesse segundo caminho o `settings` recebido é sempre `weekend_settings` (a do "primeiro usuário", ver Grupo C), ou seja, **o cooldown de alerta de perna hoje usa o `realert_drop_pct`/`realert_days` de "qualquer usuário que apareça primeiro"**, não um valor por usuário.
  **Decisão confirmada (29/07/2026, Etapa 2): vira pessoal** (cada usuário decide sua própria sensibilidade de re-alerta).
- `suspicious_below_avg_pct` — **correção a este relatório** (a versão original da Etapa 1 classificou esta coluna como Grupo C por engano). Ela é lida em **dois** lugares: [main.py:156-157](src/main.py:156), dentro de `process_route` (rotas flexíveis, per-user de verdade), **e** [weekends.py:168-169](src/weekends.py:168), via `weekend_settings` global — exatamente o mesmo padrão das outras 3 colunas do Grupo B. Pertence aqui, não ao Grupo C.
  **Pendente:** a decisão de 29/07 ("Grupo B vira pessoal") foi tomada sem esta coluna estar no grupo — precisa confirmação explícita se `suspicious_below_avg_pct` segue a mesma decisão (vira pessoal) ou fica separada.

**C. Só usadas pelo sistema de fim de semana, hoje lidas de forma explicitamente global** (`main.py:310-313`: "settings do primeiro usuário definem tudo (app é single-user por design)"):
- `weekend_opportunity_pct` — [weekends.py:165](src/weekends.py:165).
- `fast_flights_enabled`, `fast_flights_daily_batch_size` — [live_check.py:188](src/live_check.py:188), [live_check.py:127](src/live_check.py:127) — kill-switch e tamanho de lote do scraping, decisão de infraestrutura compartilhada (não faz sentido 2 valores rodando o mesmo robô).
  → Estas 3 colunas são candidatas claras a sair de `settings` (per-user) e virar config de sistema (linha única, sem `user_id`, ou uma tabela `system_settings` dedicada). Continuar lendo "a do primeiro usuário" depois de existir um segundo usuário de verdade é uma condição de corrida (literalmente depende da ordem dos `routes` retornados) — precisa ser resolvido na Etapa 3, não é cosmético.

### Decisão final da divisão de `settings` (fechada no chat de planejamento, 29/07/2026)

**SISTEMA (config única, sem dono):**
- `suspicious_below_avg_pct` — checagem anti-fantasma é verdade sobre o dado (estatística), não preferência pessoal, mesmo sendo lida em `process_route` e `weekends.py`.
- `fast_flights_enabled`
- `fast_flights_daily_batch_size`

**PESSOAL (per-user):**
- `window_3d_pct`, `window_7d_pct` (rotas flexíveis)
- `freshness_hours`, `stale_alert_policy` (rotas flexíveis)
- `notification_mode`, `realert_drop_pct`, `realert_days`
- `weekend_opportunity_pct` — nota: diferente da recomendação original desta auditoria (que sugeria Grupo C/sistema); decisão do chat de planejamento foi tratá-la como preferência pessoal mesmo assim.

**Fora de escopo:** `cost_per_thousand_brl` — confirmado sem nenhum consumidor no pipeline (achado da Etapa 1); não migra para nenhuma das duas tabelas, fica como está. Comparador de milhas nunca foi implementado (já registrado em `STATE.md`, seção 5).

Próximo passo (**ainda não executado**): criar tabela de config de sistema
(linha única) + manter `settings` só com as colunas pessoais + migrar dados
existentes. Aguardando prompt de execução específico no chat de
planejamento antes de qualquer alteração de schema ou código.

### Rascunho da correção de `alert_log` (preparado, não aplicado)

Ver [sql/draft_alert_log_leg_policy.sql](sql/draft_alert_log_leg_policy.sql) —
arquivo novo, marcado como DRAFT no cabeçalho, não referenciado por nenhum
outro processo. Resolve o bug já registrado na auditoria original (policy de
select de `alert_log` não cobre `leg_id`) usando o mesmo padrão de
permissividade já existente em `weekend_legs`/`weekends`
(`auth.uid() is not null`) — não tenta resolver ownership por usuário aqui,
isso fica pra Etapa 4/5. Aguardando revisão no chat de planejamento (Etapa 2)
antes de rodar no SQL Editor.

---

### Estrutural vs. incremental
- **Estrutural (exige redesenho de schema + RLS + frontend):**
  - Separar `weekend_legs.{price_ceiling,status,notes,paid_price}` em uma
    tabela de decisão pessoal por usuário.
  - Mapeamento usuário↔chat_id no Telegram + lógica de roteamento de
    notificação.
  - Repensar RLS de update em `weekend_legs`/`weekends` pra não ser mais
    "qualquer autenticado edita tudo".
- **Incremental e de baixo risco:**
  - Corrigir a policy de select de `alert_log` pra incluir `leg_id`.
  - Confirmar/ajustar a RLS de `routes` e `settings` (schema já é per-user,
    só falta confirmar que insert de `routes` no frontend está de fato
    preenchendo/herdando `user_id` corretamente).
  - Criar o segundo usuário no Supabase Auth via dashboard (não exige código).
