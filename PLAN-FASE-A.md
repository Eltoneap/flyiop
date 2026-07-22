# Plano de Execução — FASE A (Qualidade do dado)

_Plano derivado do ROADMAP-AUDITORIA.md (15/07/2026), ancorado no código real em 16/07/2026. Executar uma etapa por vez; cada etapa termina com verificação em produção (push dispara `daily.yml`, conclusão acompanhável pela API pública do GitHub, resultado conferido no Telegram e no site pelo celular)._

## Visão geral e ordem de execução

| Etapa | Item | O que muda | Risco |
|---|---|---|---|
| 1 | A1 (parte 1) | Cliente v3 + comparação paralela v2×v3 no run_log | Baixo (v2 continua mandando) |
| 2 | A2 | Portão de frescor nos alertas | Baixo |
| 3 | A3 | Cooldown/deduplicação de alertas (tabela `alert_log`) | Baixo |
| 4 | A5 (parte 1) | Autocheck estatístico anti-preço-fantasma | Baixo |
| 5 | A4 | Janela dupla (curta/longa) por rota — maior mudança | Médio (schema + robô + UI) |
| 6 | A1 (parte 2) | Corte: v3 vira fonte oficial, v2 sai | Baixo (dados já comparados) |
| 7 | A5 (parte 2) | Confirmação pontual na 2ª fonte no momento do alerta | Baixo (best-effort) |

A ordem existe por dependência: a comparação v2×v3 (etapa 1) precisa de alguns dias rodando, então ela entra primeiro e as etapas 2–5 acontecem enquanto ela coleta dados. A etapa 7 usa o cliente v3 com data exata, por isso vem depois do corte (etapa 6).

Mudanças de banco: cada etapa que altera schema entrega um script SQL pronto para colar no SQL Editor do Supabase (com RLS), como nas migrações anteriores.

**Teste local obrigatório antes de cada push (todas as etapas):** como na rodada anterior, cada etapa inclui um teste local com dados simulados (mock) — sem chamar a API real da Travelpayouts e sem gravar no Supabase — exercitando a lógica nova (parse de resposta, regra de decisão, montagem de mensagem). O push só acontece depois do teste local passar; a produção (GitHub Actions) fica como confirmação final, não como primeiro teste.

---

## Etapa 1 — A1 (parte 1): cliente v3 + comparação paralela

**Objetivo:** dados de cache de até 48h (v3) em vez de até 7 dias (v2), sem desligar o v2 antes de provar cobertura.

- **Pré-passo obrigatório (antes de qualquer execução em produção):** confirmar na documentação oficial da Travelpayouts (artigo de API rate limits do suporte) o limite de chamadas por hora/dia da Data API, e verificar que ~36 chamadas/dia (período de comparação paralela) está confortavelmente dentro do limite. Registrar o número encontrado neste arquivo antes de prosseguir. Se o limite for apertado, reduzir a comparação paralela (ex.: v3 só em 3 meses alternados) antes de rodar.
  - ✅ **Confirmado em 16/07/2026** no artigo oficial [API rate limits](https://support.travelpayouts.com/hc/en-us/articles/4402565416594-API-rate-limits) (vigente desde 14/06/2024): limites são **por minuto** — `/v2/prices/month-matrix`: **300 req/min**; `/v3/prices_for_dates`: **600 req/min**. Nosso pior caso na comparação paralela é ~36 chamadas **por dia** (≈18 por fonte, sequenciais, com 0,3s de intervalo — nunca mais que ~12/min de pico por fonte). Margem enorme; nenhum ajuste necessário. A API devolve headers `X-Rate-Limit-Remaining`/`X-Rate-Limit-Reset` e o retry 429 já existente cobre qualquer eventualidade.
- `src/travelpayouts_client.py`: nova função `get_prices_for_dates(origin, destination, currency, departure_at, one_way=False)` chamando `GET /aviasales/v3/prices_for_dates` com `departure_at=YYYY-MM` (um chamado por mês, como hoje), `sorting=price`, `limit` alto o bastante para cobrir o mês. Reusa o `_get_with_retry` existente (retry 429/5xx).
- Mapeamento para o schema atual do histórico: `price`→price, `departure_at` (parte da data)→flight_date, `return_at`→return_date, `transfers`→stops, `days_ahead` calculado como hoje (`_days_ahead` em `src/main.py`).
- **Ponto a verificar na primeira execução real:** se o v3 devolve `found_at`. Se não devolver, o campo fica nulo e a linha de frescor da mensagem passa a dizer "fonte com cache de até 48h" em vez do horário exato (nunca inventar timestamp).
  - ✅ **Confirmado em produção em 17/07/2026 (dia 1 da comparação):** o `prices_for_dates` **não devolveu `found_at`** em nenhuma das rotas com dados (BSB→GIG, GIG→BSB). Preço e cobertura bateram exatamente com o v2 nas duas rotas (BSB→GIG: 6/6 meses, R$ 520,00 nos dois; GIG→BSB: 3/6 meses, R$ 565,00 nos dois). RIA→BSB seguiu sem dados nas duas fontes, como já era esperado. **Implicação para a Etapa 6 (corte pro v3):** sem `found_at`, o campo de frescor da Etapa 2 ficará sempre "desconhecido" após o corte — decisão já prevista no design da Etapa 2 (tratar como velho/aviso, nunca como fresco), mas vale reconfirmar com o usuário no momento do corte se isso é aceitável ou se compensa manter alguma checagem alternativa de frescor.
- `src/main.py` (`process_route`): após o fluxo v2 normal, chamar o v3 para os mesmos meses e **registrar só a comparação** no `run_log` (campo `detail`, ex.: `"v3: R$ 1234 (2 meses com dados) vs v2: R$ 1180"`). O `price_history` continua recebendo apenas o v2 — não poluir a média histórica com fonte dupla.
- Rodar assim por **4–7 dias**; conferir cobertura por rota nos logs do Actions e no `run_log` antes da etapa 6.
- Custo de chamadas: dobra temporariamente (~36/dia com 3 rotas × 6 meses × 2 fontes) — aceitável e temporário, desde que confirmado no pré-passo de rate limit.
- **Teste local (antes do push):** resposta v3 simulada (JSON fixo no formato documentado) → validar parse, mapeamento de campos e texto de comparação gerado para o `run_log`, sem API real nem Supabase.

## Etapa 2 — A2: portão de frescor nos alertas

**Objetivo:** nunca mandar o usuário correr pro site por preço velho sem avisar.

- `settings` (SQL): novas colunas `freshness_hours int default 24` e `stale_alert_policy text default 'warn'` (`'warn'` = alerta com aviso destacado; `'suppress'` = segura o alerta).
- `src/main.py`: calcular a idade do `found_at` (lógica já existe em `_freshness` no `telegram_notifier.py` — extrair o cálculo de horas para reuso) e incluir `is_stale` no report. No modo alerta: se `is_stale` e política `suppress`, não envia (registra no `run_log.detail`); se `warn`, envia.
- `src/telegram_notifier.py` (`build_alert_message`): quando `is_stale`, abrir a mensagem com aviso forte (ex.: `⚠️ <b>Dado antigo (Xh)</b> — confirme no site antes de se animar`).
- `found_at` ausente = frescor desconhecido → tratar como velho (aviso), nunca como fresco.
- `docs/js/config.js` + `docs/config.html`: dois campos novos no formulário de preferências (horas de frescor; o que fazer com dado velho). Atualizar `DEFAULT_SETTINGS` nos dois lugares (`supabase_client.py` e `config.js`).
- **Teste local (antes do push):** reports simulados com `found_at` fresco, velho e ausente → conferir decisão (envia/segura) e o texto do aviso nas duas políticas, sem API nem Supabase.

## Etapa 3 — A3: deduplicação/cooldown de alertas

**Objetivo:** não repetir o mesmo "bom preço" todo dia.

- Nova tabela `alert_log` (SQL, com RLS): `id, route_id (FK routes), sent_at timestamptz default now(), price numeric, reason text`. Escrita pelo robô (service role); leitura pelo usuário autenticado (mesmo padrão do `run_log`).
- `src/supabase_client.py`: `insert_alert_log(route_id, price, reason)` e `get_last_alert(route_id)`.
- `settings` (SQL): colunas `realert_drop_pct numeric default 5` e `realert_days int default 3`.
- `src/main.py`: quando `should_alert` (modo alerta), consultar o último alerta da rota. Só reenviar se (a) preço atual ≤ preço do último alerta × (1 − realert_drop_pct/100), **ou** (b) passaram ≥ realert_days desde o último. Cooldown por rota, valendo para alerta de meta e de tendência (evita spam dos dois tipos). Todo alerta enviado grava em `alert_log`.
- Modo `daily_summary` não muda (resumo sempre sai — não é alerta repetido).
- `docs/js/config.js`: os dois campos novos no formulário de preferências.
- **Teste local (antes do push):** simular últimos alertas (ontem, há 4 dias, preço 6% menor, preço igual) → conferir que a regra reenvia/segura nos casos certos, sem API nem Supabase.

## Etapa 4 — A5 (parte 1): autocheck estatístico anti-preço-fantasma

**Objetivo:** preço absurdamente baixo não vira alerta direto — provavelmente é erro de dado.

- `src/rules.py`: nova função `is_suspicious_price(price, history_prices, threshold_pct)` — suspeito se houver histórico mínimo (≥5 registros em 30d) e o preço estiver mais de `threshold_pct` abaixo da média 30d.
- `settings` (SQL): coluna `suspicious_below_avg_pct numeric default 50`.
- `src/main.py`: preço suspeito **é gravado normalmente** no `price_history` (dado é dado), mas: `run_log` recebe `detail="suspeito: XX% abaixo da média 30d"`, o alerta não dispara, e a notificação do dia ganha uma nota (via `build_notes`) explicando que um preço suspeito foi detectado e será reavaliado amanhã (se persistir dois dias, deixa de ser suspeito — dois dias seguidos com o mesmo valor indicam preço real, não glitch de cache).
- `docs/js/config.js`: campo novo no formulário de preferências.
- **Teste local (antes do push):** históricos simulados (preço 60% abaixo da média, 30% abaixo, histórico curto demais) → conferir classificação suspeito/normal e a nota gerada, sem API nem Supabase.

## Etapa 5 — A4: janela dupla de monitoramento por rota

**⚠️ Reflexão obrigatória antes de implementar (pedido do usuário, 21/07/2026):**
Os dados reais dos primeiros dias (17–21/07) mostraram que a "data mais barata" reportada pode pular de mês de um dia pro outro — caso concreto: BSB→GIG foi de ida **27/11 → 21/11 → 18/09** em poucos dias, enquanto GIG→BSB ficou travada em 01/10. Consequência: o `price_history` de uma rota mistura datas de viagem diferentes numa série temporal única, como se fosse o mesmo produto. Isso pode **distorcer a detecção de tendência** (uma "queda" pode ser só o algoritmo trocando novembro por setembro, não o mesmo voo ficando mais barato) **e o autocheck estatístico da Etapa 4** (a média 30d compara preços de datas de viagem diferentes). Ao desenhar a Etapa 5, avaliar se separar por janela (curta/longa) **basta**, ou se é preciso ir além e rastrear o histórico por **"mês de viagem" específico** (ex.: série própria por `target_month`), para média e tendência fazerem sentido. **Trazer o raciocínio ao usuário ANTES de codar a Etapa 5** — não implementar direto.

**Objetivo (pedido explícito):** monitorar separadamente "viagem logo ali" e "viagem daqui a meses", com limiares próprios — dinâmicas de preço diferentes.

Definição das janelas:
- **Curta:** partidas em até 60 dias (varre meses 0–2 do calendário).
- **Longa:** partidas entre 120 e 180 dias (varre meses 4–6).
- Rota pode ter curta, longa ou ambas (default para rotas existentes: **ambas** — é o mais próximo do comportamento atual de varrer 6 meses).

Mudanças:
- `routes` (SQL): colunas `monitor_short boolean default true`, `monitor_long boolean default true`.
- `price_history` (SQL): coluna `window text` (`'short'`/`'long'`, nulo nas linhas antigas) + backfill das linhas existentes a partir de `days_ahead` (≤60 → short; ≥120 → long; entre 61–119 fica nulo — fora das duas janelas).
- `settings` (SQL): `long_window_3d_pct numeric default 15`, `long_window_7d_pct numeric default 20` (janela longa é mais volátil; os campos atuais `window_3d_pct`/`window_7d_pct` passam a valer para a curta).
- `src/main.py` (`process_route`): varrer só os meses das janelas ativas da rota, separar as entradas por `days_ahead`, escolher o mais barato **por janela**, gravar uma linha de histórico por janela (com o campo `window`) e avaliar meta + tendência por janela (média 30d e histórico 7d filtrados pela mesma janela). Report vira um bloco por rota+janela, rotulado ("próximos 60 dias" / "4–6 meses").
- `src/supabase_client.py`: `get_price_history` e `insert_price` ganham parâmetro `window`.
- `src/telegram_notifier.py`: rótulo da janela no bloco da rota.
- `docs/js/config.js` + `config.html`: na tabela de rotas, seleção simples da janela (curta / longa / ambas).
- `docs/js/dashboard.js`: o gráfico hoje mistura todo o histórico — passar a separar por janela (duas linhas no mesmo gráfico ou seletor curta/longa no card; decidir pelo que ficar legível no celular). Badge de status e aviso de janela de compra calculados sobre a janela exibida. Export CSV ganha a coluna `janela`.
- Chamadas à API: curta = 3 meses, longa = 3 meses; rota com ambas = 6 chamadas (igual a hoje). Rota com uma janela só fica mais barata.
- **Teste local (antes do push):** matriz de entradas simuladas com `days_ahead` variados → conferir separação por janela, mais barato por janela, avaliação de tendência com limiares distintos e rótulos das mensagens, sem API nem Supabase.

## Etapa 6 — A1 (parte 2): corte para o v3 — ✅ EXECUTADA (21/07/2026)

Pré-condição: comparação da etapa 1 mostrando cobertura v3 ≥ v2 nas rotas ativas (conferir `run_log` dos últimos 4–7 dias).

**Base da decisão (aprovada pelo usuário em 21/07):** 5 dias de comparação paralela (17–21/07). Nas duas rotas com cobertura (BSB→GIG, GIG→BSB) o v3 achou preço nos mesmos dias que o v2 com valor **idêntico em 100% das observações**, inclusive replicando a volatilidade intradiária (GIG→BSB em 18/07: dois preços diferentes no mesmo dia, os dois batidos). RIA→BSB seguiu sem cobertura nas duas fontes (paridade no vazio, não regressão). Resultado limpo o bastante para cortar no 5º dia sem esperar o teto de 7.

- `src/main.py`: v3 (`get_prices_for_dates`) virou a fonte que grava `price_history`; o loop v2 saiu, junto do andaime de comparação (`v3_comparison_detail`/`safe_v3_comparison`). `get_month_matrix` **permanece** em `travelpayouts_client.py` como rollback rápido por uma versão.
- **Mensagem de frescor:** decisão de 18/07 aplicada junto — `found_at` ausente na fonte v3 gera `ℹ️ Fonte com cache de até 48h` (campo `cache_48h` no report), não mais `⚠️ Dado antigo`. `found_at` presente e velho continua com o alarme normal.
- **Salvaguarda anti-supressão total (ajuste do usuário):** `should_suppress_alert` só suprime com idade **conhecida e velha**; idade desconhecida (v3) nunca suprime. UI: opção `suppress` desabilitada com aviso; valor `suppress` já salvo é exibido como `warn` com nota de alerta.
- **`trip_duration_weeks` sem efeito:** o v3 não tem filtro de duração. UI de Configurações marca o campo como desabilitado com nota explicativa (mesmo tratamento honesto dado ao comparador de milhas). Coluna preservada no banco.
- **Teste local:** `tests/test_etapa6_corte.py` (mapeamento de campos v3, mensagem de cache, salvaguarda) + suíte das etapas 1 e 2 ajustada — **27 testes verdes**, sem API nem Supabase.
- **Rollback:** `get_month_matrix` intacto no cliente; reverter = reverter 1 commit.

## Etapa 7 — A5 (parte 2): confirmação pontual no momento do alerta

**Objetivo:** selo "confirmado" sem scraping — usando a própria API, uma única consulta extra, só quando um alerta vai sair.

- Quando um preço bater meta e for gerar alerta: uma chamada única a `prices_for_dates` com a **data exata** (`departure_at=YYYY-MM-DD` + `return_at`) da oferta. Se vier preço na mesma ordem de grandeza (ex.: ±30%), a mensagem ganha `✅ confirmado em segunda consulta`; se falhar ou vier vazio, o alerta sai mesmo assim, sem o selo (best-effort, try/except).
- Nunca roda na varredura normal — só no evento de alerta (no máximo 1 chamada extra por alerta).
- Proibições mantidas: nada de scraping em volume nem evasão anti-bot.
- **Nota (18/07/2026):** a regra de scraping acima foi formalmente revisada no `PLAN-VALIDACAO-CRUZADA.md` (Parte 1 — 5 condições cumulativas), que também adiciona à Fase A a **Etapa 0** (validação prévia do `fast-flights`) e a **Etapa 8** (selo de fonte independente via Google Flights, condicionado à aprovação da Etapa 0). Em caso de conflito entre documentos, o `PLAN-VALIDACAO-CRUZADA.md` prevalece. Esta Etapa 7 permanece exatamente como está.
- **Teste local (antes do push):** confirmação simulada nos três cenários (preço compatível, preço muito diferente, chamada falhando) → conferir selo presente/ausente e que a falha nunca bloqueia o alerta, sem API nem Supabase.

## O que NÃO entra nesta fase

Tudo das Fases B, C e D (heatmap, percentil, calculadora de milhas, link Google Flights, melhor antecedência, data fixa, cadência maior, códigos de cidade, ANAC, câmbio, ML, pós-compra). A Fase B só começa com novo Plan Mode após a Fase A estável.

## Verificação (por etapa)

0. **Teste local primeiro:** cada etapa tem o teste com mock descrito acima — sem API real, sem Supabase. Push só depois do teste local passar.
1. Push em `src/**` dispara o `daily.yml` automaticamente (já configurado) — acompanhar a conclusão pela API pública (`api.github.com/repos/Eltoneap/flyiop/actions/runs`).
2. Conferir o efeito real: mensagem no Telegram (formato/avisos novos), `run_log` e `price_history` no Supabase, dashboard e configurações no celular.
3. Etapas com SQL: rodar o script no SQL Editor do Supabase **antes** do push do código que depende dele (passos com cliques concretos no plano de cada etapa).
4. Casos específicos: etapa 2 (simular dado velho baixando `freshness_hours` temporariamente), etapa 3 (segunda execução no mesmo dia via Run workflow — alerta não deve repetir), etapa 5 (conferir gráfico por janela no celular), etapa 6 (comparar run_log antes/depois do corte).
