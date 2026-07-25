# Plano Ativo — FlyIop

_Atualizado em 24/07/2026. Contém só o que está em execução ou pendente de aprovação/implementação. Tudo que já foi entregue (com data e decisões tomadas) está em `HISTORICO.md` — referencie por lá em vez de reproduzir aqui._

**Regra de apresentação (24/07/2026):** ao apresentar um plano ou atualização no chat, mostrar só a seção nova/alterada, nunca o arquivo inteiro. Para contexto, referenciar a seção pelo nome (ex.: "ver Parte 7 no HISTORICO.md") em vez de reproduzir. O arquivo completo fica no disco; o chat recebe só o delta. (Ver também `PROTOCOLO-DE-TRABALHO.md`.)

---

## Parte 8 — Preço pago, Dashboard redesenhado, feriados/alta temporada

**Status: plano escrito, aguardando revisão/aprovação (ainda não implementado).**

### Contexto

Com o preço confiável (Parte 7 — ver HISTORICO.md — confirmado em produção: 20/20 pernas com preço correto), faz sentido usar dados reais em vez de placeholder. Três pedidos combinados: (1) campo de preço efetivamente pago por perna; (2) o Dashboard (`docs/index.html`) hoje mostra só as 3 rotas flexíveis legadas — não reflete mais o objetivo real do projeto (fins de semana é o foco principal desde a Parte 3); (3) uma seção nova identificando fins de semana com feriado/alta temporada, pra calibrar teto individual.

### 1. SQL

```sql
alter table weekend_legs add column paid_price numeric;
```

Mais um ajuste de RLS: a tabela `bot_state` (já existe, usada hoje só pelo bot do Telegram pra `last_update_id`) não aparece em nenhum `sql/*.sql` rastreado — não dá pra confirmar que tem policy de select pra usuário autenticado. Preciso dela legível pelo Dashboard pra mostrar "bloqueio recente" (item 6 abaixo), então adiciono a policy de forma idempotente:

```sql
alter table bot_state enable row level security;

drop policy if exists "bot_state_select_authenticated" on bot_state;
create policy "bot_state_select_authenticated"
  on bot_state for select
  using (auth.uid() is not null);
```

Se a RLS/policy já existir com esse mesmo efeito, o `drop policy if exists` + `create policy` roda sem erro (idempotente). Nenhuma outra tabela precisa de policy nova — `weekend_legs`, `weekend_leg_run_log`, `weekends` já têm select para autenticado (confirmado em `sql/pernas_desacopladas.sql`).

### 2. Campo "valor pago" — `docs/js/compras.js` + `docs/css/style.css`

Mesmo padrão do campo de notas (`renderLegRow`, já usa blur + botão salvar via `updateLeg`): novo bloco `.leg-row-paid`, só renderizado quando `leg.status === 'purchased'` (não faz sentido perguntar valor pago de algo ainda não comprado) — aparece automaticamente assim que a perna vira "Comprada" (o card já re-renderiza via `loadWeekends()` depois do clique em "Comprei", então o campo surge sem precisar de prompt separado) e continua editável depois, a qualquer momento, indefinidamente.

```html
<div class="leg-row-paid">
  <label class="leg-paid-label">pago R$ <input type="number" step="0.01" min="0" placeholder="ex: 245.90" class="leg-paid-input" value="${leg.paid_price ?? ''}"></label>
  <button type="button" class="small leg-paid-save">Salvar</button>
  <span class="leg-paid-hint">valor real, com taxas — diferente do preço monitorado</span>
</div>
```
Wiring: idêntico ao de notas (`saveNotes`), trocando `notes` por `paid_price` (`Number(...) || null` em vez de `.trim() || null`; se o campo ficar vazio, salva `null`, não `0`). CSS novo: `.leg-row-paid` (flex, wrap, gap — mesmo esqueleto de `.leg-row-notes`), `.leg-paid-input` (largura ~80px, como `.leg-ceiling-input`), `.leg-paid-hint` (11px, `--muted`, itálico opcional pra reforçar "não é o preço monitorado").

### 3. Módulo de feriados — `docs/js/holidays.js` (novo)

Lista de feriados nacionais 2026/2027 (fixos + móveis calculados programaticamente a partir da Páscoa: 2026-04-05, 2027-03-28) e uma função que, dado um `weekend` (`outbound_date`, `return_sunday`, `return_monday`), devolve `{ tag: 'feriado'|'alta_temporada'|null, motivo: string }`. Sem chamada de rede — cálculo determinístico, reaproveitável se o painel cobrir 2028+ no futuro.

Regra de "feriado": feriado cai na quinta anterior à sexta (emenda), na sexta (ida), sábado, domingo (`return_sunday`), segunda (`return_monday`), ou na terça seguinte à segunda (emenda). Regra de "alta temporada" (rótulo separado, mostra os dois selos se as duas baterem): julho inteiro (só 2027 — não há weekends monitorados em julho/2026), segunda quinzena de dezembro (dias 16–31), primeira quinzena de janeiro (dias 1–15).

### Lista completa pra validação (calculada e conferida contra dia da semana, confirmado programaticamente com `datetime` do Python)

**Feriados nacionais usados** (fixos + móveis a partir da Páscoa: 2026-04-05 domingo, 2027-03-28 domingo):

| Feriado | 2026 | dia da semana | 2027 | dia da semana |
|---|---|---|---|---|
| Confraternização Universal | 01-01 | qui | 01-01 | sex |
| Carnaval (segunda) | 02-16 | seg | 02-08 | seg |
| Carnaval (terça) | 02-17 | ter | 02-09 | ter |
| Sexta-feira Santa | 04-03 | sex | 03-26 | sex |
| Tiradentes | 04-21 | ter | 04-21 | qua |
| Dia do Trabalho | 05-01 | sex | 05-01 | **sáb** |
| Corpus Christi | 06-04 | qui | 05-27 | qui |
| Independência do Brasil | 09-07 | seg | 09-07 | ter |
| Nossa Senhora Aparecida | 10-12 | seg | 10-12 | ter |
| Finados | 11-02 | seg | 11-02 | ter |
| Proclamação da República | 11-15 | **dom** | 11-15 | seg |
| Consciência Negra | 11-20 | sex | 11-20 | **sáb** |
| Natal | 12-25 | sex | 12-25 | **sáb** |

(Tiradentes/2027 cai numa quarta isolada, sem tocar quinta-antes nem terça-depois de nenhum fim de semana monitorado — por isso não aparece na lista abaixo. Dia do Trabalho/2027 sábado e Consciência Negra/2027 e Natal/2027 sábado caem fora do período coberto pelos 66 fins de semana ou emendam via a regra definida — ver tabela.)

**Fins de semana marcados como 🎉 feriado** (16 de 66):

| Sexta (ida) | Motivo |
|---|---|
| 2026-09-04 | segunda (volta, 09-07) = Independência |
| 2026-10-09 | segunda (volta, 10-12) = N. Sra. Aparecida |
| 2026-10-30 | segunda (volta, 11-02) = Finados |
| 2026-11-13 | domingo (11-15) = Proclamação da República |
| 2026-11-20 | sexta (ida) = Consciência Negra |
| 2026-12-25 | sexta (ida) = Natal *(também ☀️ alta temporada)* |
| 2027-01-01 | sexta (ida) = Confraternização *(também ☀️ alta temporada)* |
| 2027-02-05 | segunda (volta, 02-08) = Carnaval + terça seguinte (02-09) = Carnaval |
| 2027-03-26 | sexta (ida) = Sexta-feira Santa |
| 2027-04-30 | sábado (05-01) = Dia do Trabalho |
| 2027-05-28 | quinta anterior (05-27) = Corpus Christi |
| 2027-09-03 | terça seguinte (09-07) = Independência |
| 2027-10-08 | terça seguinte (10-12) = N. Sra. Aparecida |
| 2027-10-29 | terça seguinte (11-02) = Finados |
| 2027-11-12 | segunda (volta, 11-15) = Proclamação da República |
| 2027-11-19 | sábado (11-20) = Consciência Negra |

**Fins de semana marcados como ☀️ alta temporada** (10 de 66, 2 já contados acima como feriado também):

| Sexta (ida) | Motivo |
|---|---|
| 2026-12-18 | segunda quinzena de dezembro |
| 2026-12-25 | segunda quinzena de dezembro *(também 🎉 feriado)* |
| 2027-01-01 | primeira quinzena de janeiro *(também 🎉 feriado)* |
| 2027-01-08 | primeira quinzena de janeiro |
| 2027-01-15 | primeira quinzena de janeiro |
| 2027-07-02 | julho |
| 2027-07-09 | julho |
| 2027-07-16 | julho |
| 2027-07-23 | julho |
| 2027-07-30 | julho |

Total: **24 de 66 fins de semana** com algum selo (16 feriado + 10 alta temporada − 2 sobrepostos). Confirmar antes da implementação — se alguma data/motivo estiver errado ou faltando algum feriado (ex.: ponto facultativo local, feriado estadual/municipal do RJ ou DF), ajustar a lógica em `holidays.js` antes de escrever qualquer código.

### 4. `docs/compras.html` / `compras.js` — selo no card + âncora pro link do Dashboard

- `renderCard(weekend)`: `card.id = weekend-${weekend.id}` (pra permitir link direto `compras.html#weekend-<id>` a partir do Dashboard).
- No `header.innerHTML`, adicionar badge(s) do resultado de `holidays.js` ao lado do `<h3>` quando aplicável: `<span class="badge holiday">🎉 feriado</span>` e/ou `<span class="badge high-season">☀️ alta temporada</span>`.
- CSS novo: `.badge.holiday` (cor dourada/âmbar, reaproveitando o esqueleto de `.badge`) e `.badge.high-season` (cor laranja) — variáveis novas em `:root` (ex. `--holiday`/`--holiday-bg`, `--season`/`--season-bg`) seguindo o padrão de `--good`/`--good-bg` já existente.

### 5. Dashboard — `docs/index.html` + `docs/js/dashboard.js` (redesenho completo)

**Estrutura nova do `<main>`** (mobile-first, curto em cima):

```
h1 "Dashboard"
section#acao-do-dia        (a) — destaque grande, tocável → compras.html
section#urgencia           (b) — só renderiza se houver itens
section#progresso           (c) — 1 linha + barra visual
hr / spacer
section#oportunidades       (d) — top 5
section#orcamento           (e)
section#saude-sistema       (f)
section#feriados-alta-temporada (g) — lista dos 24 itens, cada um linkando pra âncora do card
details#rotas-legado        (h) — <details><summary>Rotas flexíveis (legado)</summary> conteúdo atual do dashboard.js migrado pra dentro
```

Uso `<details>/<summary>` nativo pro item (h) — colapsável sem JS extra, semântico, já com suporte de tema (funciona com o CSS atual sem trabalho adicional).

**Busca de dados** (`dashboard.js`, tudo em paralelo via `Promise.all`, mesmo padrão já usado): `weekends` com `select('*, weekend_legs(*)')` (igual `compras.js`), `settings` do usuário, `weekend_leg_run_log` (2 queries: `count` últimas 24h e últimos 7 dias, usando `ran_at >= cutoff`), `bot_state` (linha `key=eq.weekend_batch_blocked_at`), e — dentro da seção legada — os mesmos dados que `dashboard.js` já busca hoje (`routes`, `price_history`, `run_log`), só que renderizados dentro do `<details>` em vez do grid principal.

**Cálculos client-side** (sem função nova no backend Python — tudo client-side a partir do que já foi buscado):
- (a) Ação do dia: `legs.filter(l => l.status==='monitoring' && l.current_price!=null && l.current_price <= l.price_ceiling)`. Se vazio: "Nada exigindo ação hoje — todas as pernas monitoradas estão acima do teto."
- (b) Urgência: `weekends` com `daysUntil(outbound_date)` entre 0 e 60, com pelo menos 1 perna `status!=='purchased'`. Não renderiza a seção se a lista vier vazia.
- (c) Progresso: reaproveita a mesma lógica de `updateProgress()` de `compras.js` (contagem de pernas/weekends completos) — só que aqui com barra visual nova (`.progress-bar > .progress-bar-fill` com `width: ${pct}%`).
- (d) Oportunidades: `legs.filter(l => l.status==='monitoring' && l.current_price!=null)`, ordenado por `(current_price - price_ceiling) / price_ceiling` ascendente (inclui as que já bateram o teto — "mesmo sem terem batido" no pedido original significa não excluir quem não bateu, não excluir quem já bateu), top 5.
- (e) Orçamento: `legs.filter(l => l.status==='purchased' && l.paid_price!=null)` → soma, média; estimativa = soma + média × (pernas não compradas). Texto deixa claro "estimativa" e mostra o N usado pra calcular a média (ex.: "com base em 4 pernas com valor registrado").
- (f) Saúde: última execução = `MAX(ran_at)` da query de `weekend_leg_run_log` (ordenar desc, limit 1); contadores 24h/7d = `count` das queries acima; consulta ao vivo ativa = `settings.fast_flights_enabled`; bloqueio recente = `bot_state.weekend_batch_blocked_at` presente e dentro das últimas 48h.
- (g) Feriados/alta temporada: usa `holidays.js` sobre a lista de `weekends`, mostra os 24 itens (data, motivo, selo), cada um como link `<a href="compras.html#weekend-${id}">`. Texto fixo explicando: "Esses fins de semana dificilmente ficam abaixo do teto padrão — considere subir o teto individual deles em Compras."
- (h) Legado: exatamente o que `dashboard.js` já faz hoje (`renderCard`, gráfico Chart.js por rota, export CSV) — só movido de lugar, sem mudança de comportamento.

**CSS novo em `style.css`**: `.progress-bar` (trilho, `background:var(--border)`, `border-radius:999px`, altura ~8px), `.progress-bar-fill` (`background:var(--primary)`, mesma altura/radius, `width` dinâmico via inline style), `.stat-big` (número grande tipo `.card .price`, reaproveitável fora de card também), `.badge.holiday`/`.badge.high-season` (item 4).

### 6. Backend — persistir "bloqueio recente" (`src/live_check.py` + `src/supabase_client.py`)

Reusa a tabela `bot_state` (key-value) já existente, mesmo padrão de `get_last_update_id`/`set_last_update_id`:

```python
# supabase_client.py
def set_weekend_batch_blocked_at(iso: str) -> None:
    headers = {**_headers(), "Prefer": "resolution=merge-duplicates"}
    resp = requests.post(
        _url("bot_state"), headers=headers,
        json={"key": "weekend_batch_blocked_at", "value": iso}, timeout=30,
    )
    resp.raise_for_status()
```
Em `live_check.py`, dentro de `run_daily_batch`, no bloco `if blocked:` (onde já chama `send_message(BLOCK_ALERT_MESSAGE)`), adiciona 1 linha: `set_weekend_batch_blocked_at(datetime.now(timezone.utc).isoformat())`. Sem SQL novo (a tabela já existe) — só a policy de select do item 1.

### 7. Backlog (registrar, não implementar agora)

- Sugerir automaticamente um teto realista por fim de semana com base no piso observado, quando houver histórico suficiente.

### Verificação

1. Rodar o SQL (item 1) no Supabase antes do push que depende dele.
2. Testes locais Python: adicionar 1-2 testes pra `set_weekend_batch_blocked_at` (mock de `requests.post`) e rodar a suíte completa — não pode regredir.
3. `holidays.js`: antes de integrar no Dashboard, um teste manual isolado rodando a função contra os 66 fins de semana e comparando a saída com a tabela deste plano — confirma que bate exatamente antes de prosseguir.
4. Frontend: servidor estático local (`python3 -m http.server` em `docs/`) + Browser tool, sem login, conferindo que index.html carrega sem erro de console, `<details>` abre/fecha, badges aparecem em compras.html pros 24 fins de semana certos. Com login (no celular, pós-deploy): ação do dia, orçamento e saúde do sistema mostrando números reais.
5. Nenhuma mudança em `src/**` além do item 6 (1 linha + 1 função nova) — esse push especificamente dispara `daily.yml`; o resto (SQL, frontend) não dispara.
