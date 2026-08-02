# Auditoria: suporte a segundo usuário (camada de decisão pessoal)

> **Arquivo de trabalho, não é fonte da verdade.** Fotografia do estado do
> sistema na data de cada seção; não é atualizado quando o sistema muda. Em
> caso de divergência, `STATE.md` e `PLANO-ATIVO.md` prevalecem. (Aviso
> acrescentado em 31/07/2026, depois que a seção 2 abaixo — desatualizada
> desde a correção da policy de `alert_log` em 29/07 — quase levou um
> diagnóstico de produção pro caminho errado.)

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

**Achado histórico (29/07/2026), já corrigido — ver nota abaixo.**
Na data desta seção, a policy de select (`sql/etapa3_cooldown.sql:17-21`) só
cobria `route_id in (select id from routes where user_id = auth.uid())`.
Quando `pernas_desacopladas.sql` introduziu `leg_id` como alternativa a
`route_id` (linha 97-99: `check (route_id is not null or leg_id is not
null)`), nenhuma migration tinha atualizado a policy de select ainda para
incluir `leg_id is not null`. Resultado na época: linhas de `alert_log`
geradas por `insert_weekend_alert_log` (via `leg_id`, sem `route_id`) não
eram visíveis a nenhum usuário autenticado sob RLS. Isso nunca impediu o
robô de gravar (sempre usa service_role, que ignora RLS).

> **Correção confirmada em produção (verificado 31/07/2026 via
> `select * from pg_policies where tablename = 'alert_log'`):** a policy
> real hoje é `alert_log_select_own_routes_or_any_leg`, cobrindo
> `route_id is not null and route_id in (...)` **ou** `leg_id is not null
> and auth.uid() is not null` — aplicada na Etapa 2 (29/07/2026, ver
> `PLANO-ATIVO.md`). O achado acima descreve o estado **antes** da correção;
> mantido como registro histórico da investigação, não como estado atual.

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
- ~~`alert_log`: policy de select desatualizada (não cobre `leg_id`)~~ —
  **corrigida em produção em 29/07/2026** (ver seção 2, nota de 31/07).
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
- ~~**`alert_log` select policy quebrada para `leg_id`**~~ — **corrigida em
  produção em 29/07/2026** (ver seção 2, nota de 31/07).
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

---

## Etapa 4.1 — baseline antes/depois (01/08/2026)

Fotografia do estado do banco colhida no SQL Editor com os blocos A, B e C de
[sql/etapa4_1_verificacao.sql](sql/etapa4_1_verificacao.sql), **antes** de rodar
[sql/etapa4_1_estado_por_usuario.sql](sql/etapa4_1_estado_por_usuario.sql).

**Os três blocos têm que sair idênticos nas duas colheitas.** É a verificação de
que a 4.1 não mudou comportamento nenhum: A prova que a cópia de dados não
alterou o mundo antigo, e **B e C são a prova de que a 4.1 não tocou em policy
nem pendurou trigger em `weekend_legs`** (mexer nas policies e colunas dessa
tabela é a Etapa 4.3/5, não esta).

### ANTES — colhido em 01/08/2026, antes de rodar o script

**Bloco A — `weekend_legs`**

| legs | teto_250 | monitorando | com_pago | com_nota |
|---:|---:|---:|---:|---:|
| 132 | 132 | 132 | 5 | 0 |

**Bloco B — policies de `weekend_legs`**

| policyname | cmd | qual | with_check |
|---|---|---|---|
| `weekend_legs_select_authenticated` | SELECT | `(auth.uid() IS NOT NULL)` | null |
| `weekend_legs_update_authenticated` | UPDATE | `(auth.uid() IS NOT NULL)` | `(auth.uid() IS NOT NULL)` |

**Bloco C — triggers de `weekend_legs`**

Nenhuma linha — a tabela não tem trigger própria.

### DEPOIS — colhido em 01/08/2026, depois de rodar o script

**Bloco A — `weekend_legs`**

| legs | teto_250 | monitorando | com_pago | com_nota |
|---:|---:|---:|---:|---:|
| 132 | 132 | 132 | 5 | 0 |

**Bloco B — policies de `weekend_legs`**

| policyname | cmd | qual | with_check |
|---|---|---|---|
| `weekend_legs_select_authenticated` | SELECT | `(auth.uid() IS NOT NULL)` | null |
| `weekend_legs_update_authenticated` | UPDATE | `(auth.uid() IS NOT NULL)` | `(auth.uid() IS NOT NULL)` |

**Bloco C — triggers de `weekend_legs`**

Nenhuma linha (`Success. No rows returned`).

**Os três blocos saíram idênticos ao ANTES** — mesma contagem em A, mesmas duas
policies em B com `qual`/`with_check` de texto idêntico, mesma ausência de
trigger em C. É a prova de que a 4.1 não alterou o mundo antigo: não mexeu em
policy e não pendurou trigger em `weekend_legs`.

### Verificação das estruturas novas (blocos D–G) — 01/08/2026

**D — estado inicial das estruturas novas** (rodado como `postgres`, que ignora
RLS):

| medida | valor |
|---|---:|
| `weekend_leg_user_state` | 5 linhas |
| `weekend_leg_ceiling_audit` | 1 linha (`scope 'default'`, `origin 'migracao'`, null → 250) |
| `weekend_leg_effective` | 132 linhas |
| `resolvido_250` | 132 |
| `com_teto_proprio` | 0 |
| `com_linha_de_estado` | 5 |

Confirma o **modelo preguiçoso**: ninguém tem teto próprio ainda
(`com_teto_proprio = 0`), todas as 132 pernas resolvem o teto pelo padrão do
usuário (`settings.weekend_default_ceiling = 250`), e só as 5 pernas com
`paid_price` têm linha de estado.

**E e F — comportamento confirmado, capacidade de prova dos blocos revisada
(02/08/2026).** Sessão de investigação separada reproduziu fielmente o script
e os dois blocos num Postgres 16.14 descartável (schema, RLS e papéis
`anon`/`authenticated`/`service_role` imitando o Supabase, dados equivalentes
aos 66 fins de semana / 132 pernas / 5 `paid_price` de produção). Resultado:
**a estrutura se comporta corretamente** — uuid falso vê 0/0/0, uuid real vê
132/5/1 — mas os dois blocos, como escritos hoje, têm capacidade de prova
mais fraca do que a redação anterior desta seção afirmava. Detalhe completo:

- **Bloco E — o registro de produção é sólido, com uma ressalva.** O único
  resultado colado no arquivo (`audit_deve_ser_zero = 0`) **não poderia** ter
  vindo de um `select` rodado fora do contexto de papel simulado — rodado
  isolado, sem o `begin`/`set local role`, o mesmo `select` devolve **1**, não
  0 (reproduzido no banco descartável). Nesse ponto específico, o `0`
  registrado prova o que diz provar.
  **Ressalva:** se o `set local request.jwt.claims` falhar mas o `set local
  role authenticated` funcionar, `auth.uid()` vem NULL e o resultado também
  sai 0/0/0 — **idêntico ao pass legítimo**. A única evidência que separaria
  os dois casos é o `select auth.uid() as uid_falso` da linha 114, que é
  justamente o comando que o SQL Editor descarta por não ser o último do
  bloco. Não é possível descartar esse cenário com o artefato hoje disponível
  (ver "Lacuna de evidência", abaixo).
- **Bloco F não discrimina.** Reproduzido no banco descartável, o bloco F
  rodado no contexto correto (claims do usuário real) e o mesmo `select`
  rodado isolado, como dono do banco, **devolvem resultado idêntico** —
  132/5/1, igual ao próprio bloco D. Motivo estrutural, não falha de
  execução: com uma única conta no banco, "o que o dono do banco enxerga" e
  "o que o usuário legítimo enxerga" coincidem em todas as contagens. O
  bloco F, como está, **não é hoje prova de isolamento positivo** — é
  redundante com o D.
- **Conclusão a registrar:** não há indício de vazamento entre usuários — o
  que está fraco é o instrumento de medição, não o comportamento observado.
  O teste real de isolamento só é possível com **duas contas**, o que reforça
  (não contradiz) a regra dura da Etapa 7: o primeiro ato depois de criar a
  segunda conta é testar isolamento de verdade.

### Lacuna de evidência no artefato de verificação

`sql/etapa4_1_verificacao.sql` tem, hoje, apenas resultados **parciais**
colados como tabelas markdown — reflexo direto do defeito descrito em
"Pendências operacionais da 4.1" (SQL Editor só exibe o resultado do último
`select` de cada bloco colado):

- **Bloco E:** só `audit_deve_ser_zero`. `view_deve_ser_zero`,
  `estado_deve_ser_zero` e `uid_falso` não têm resultado colado no arquivo.
- **Bloco F:** só `uid_real`, `audit_deve_ser_1` e a linha `132 | 5`
  (`resolvido_250 | com_pago`). `view_deve_ser_132` e `estado_deve_ser_5` não
  têm resultado colado no arquivo.

Os demais números citados nesta seção (view 0/estado 0 no E; view 132/estado 5
no F) vieram do relato do usuário durante a sessão em que a verificação foi
rodada, não do artefato — e **não são reconstituíveis a partir do
repositório** hoje. Registrado como lacuna conhecida; os números não foram
removidos porque não há motivo para desconfiar deles especificamente (o
comportamento reproduzido no banco descartável bate com o que foi relatado),
só não há como provar a partir do arquivo sozinho.

**G — personas e carimbo de origem.** O `origin` saiu correto nas quatro
situações, todas com `current_user = 'postgres'`:

| persona | origin | auth_uid | current_user |
|---|---|---|---|
| SQL Editor (sem claims) | `sql_editor` | null | `postgres` |
| app (claims de usuário logado) | `app` | `c72bf50e-…` (preservado) | `postgres` |
| robô (`role: service_role`) | `robo` | null | `postgres` |
| override explícito | `migracao` | null | `postgres` |

Confirma **em produção** o motivo da correção 1: a origem tem que vir de
`request.jwt.claims`, não de `current_user` — dentro de uma função
`SECURITY DEFINER` o `current_user` é sempre o dono da função (`postgres`), nas
quatro personas. Derivar a origem dali carimbaria toda escrita do robô e do
painel como `sql_editor`. Note também que o `auth_uid` do painel foi
**preservado** através do `SECURITY DEFINER`, que é o que permite a auditoria
saber de quem foi a edição.

### Pendências operacionais da 4.1

- **Defeito no arquivo [sql/etapa4_1_verificacao.sql](sql/etapa4_1_verificacao.sql):
  os blocos E e F contêm vários `select`, e o SQL Editor do Supabase só exibe o
  resultado do ÚLTIMO comando** — os anteriores somem em silêncio, sem aviso de
  que houve resultado descartado. O bloco E precisou ser rodado de novo como
  consulta única para se ler os três números. **Correção pendente:** consolidar E
  e F para devolverem uma única linha de resultado cada. Não corrigido nesta
  passagem (a verificação já foi feita à mão); pendência registrada também no
  `PLANO-ATIVO.md`, item 11 da Etapa 4.2.
- **Bloco H — ✅ CONCLUÍDO em 02/08/2026.** `drop function flyiop_audit_selftest()`
  rodado sem `cascade` (nada dependia da função — confirma o que o comentário do
  bloco já previa: as triggers usam `flyiop_audit_origin()`, que fica). Confirmação
  numa consulta única, depois do drop: `sondas_restantes = 0`, `estado = 5`,
  `auditoria = 1`, `view_efetiva = 132` — a sonda saiu do banco e nada mais foi
  afetado.

### Checagem do script num Postgres real (chat de planejamento, 01/08/2026)

Antes de rodar em produção, o script foi executado de ponta a ponta num
**Postgres 16.14 descartável**, com `auth.uid()`, `auth.users` e os papéis do
Supabase imitados. Resultado:

- Rodou inteiro, sem erro de sintaxe nem de dependência.
- **Idempotência confirmada:** duas execuções seguidas, sem duplicar nada.
- Guardas, cópia (1 linha de auditoria + 5 de estado) e view: OK.
- **View:** 132 pernas para o usuário logado (caso positivo) e 0 para um uuid
  estranho (caso negativo).
- **A correção 1 era necessária:** a sonda confirmou `current_user = 'postgres'`
  dentro do `security definer` — derivar a origem dali carimbaria toda escrita
  do robô como `sql_editor`. Com a derivação por `request.jwt.claims`, o
  `origin` saiu correto nas três personas (`app` / `robo` / `sql_editor`).
- **RLS de escrita:** insert do painel sem `user_id` funciona (pega o
  `default auth.uid()`); insert com uuid alheio é rejeitado; `delete` na
  auditoria dá `permission denied`.
- **Auditoria dispara só no que deve:** editar nota não gera linha, editar teto
  gera. A ida e volta 250 → 320 → 280 → delete produziu 3 linhas coerentes.
- **Isolamento com DUAS contas reais** (no banco descartável): cada usuário vê
  só os próprios tetos e valores pagos; `service_role` vê 264 linhas (132 × 2).

**Ressalvas.** Rodou em PG 16, não no 17.6 da produção (`security_invoker`
existe desde o 15 e o comportamento é o mesmo), e os papéis do Supabase foram
imitados, não são os reais. Isso torna a checagem uma boa prova de sintaxe,
lógica e desenho — **não** substitui o bloco F (teste positivo com o uuid real)
rodado no banco de produção.
