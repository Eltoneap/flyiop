# Histórico — FlyIop

_Consolidado em 24/07/2026 a partir de `PLAN-FASE-A.md`, `PLAN-VALIDACAO-CRUZADA.md`, `ALVO-FINS-DE-SEMANA-2027.md` e do plano de trabalho de fins de semana (antes espalhado num arquivo de nome aleatório do Plan Mode). Registro cronológico de investigações, decisões e partes entregues. Trabalho em execução ou pendente: ver `PLANO-ATIVO.md`. Estado atual do produto: `CLAUDE.md`. Decisões de escopo/scraping ainda vigentes: `ROADMAP-AUDITORIA.md`._

---

## 1. Fase A — Qualidade do dado (rotas flexíveis), 16–22/07/2026

_Fonte: `PLAN-FASE-A.md`. Plano original de 7 etapas derivado do `ROADMAP-AUDITORIA.md` (15/07)._

**Etapa 1 (A1) — cliente v3 + comparação paralela.** Pré-passo de rate limit confirmado em 16/07 (v3: 600 req/min, folga enorme pro uso real). `get_prices_for_dates` novo em `travelpayouts_client.py`, chamando `v3/prices_for_dates`. Rodou em paralelo ao v2 por comparação (sem gravar no `price_history`) de 17 a 21/07. `found_at` confirmado ausente na resposta v3 (17/07) — decisão registrada: tratar ausência como esperada da fonte, não como anômala (ver Etapa 6 abaixo).

**Etapa 2 (A2) — portão de frescor.** `freshness_hours`/`stale_alert_policy` em `settings`; alerta com dado velho sai com aviso destacado (`warn`) ou é segurado (`suppress`), nunca silencioso. `found_at` ausente = tratado como velho.

**Etapa 3 (A3) — cooldown/deduplicação de alertas — ✅ executada 22/07/2026.** Tabela `alert_log` nova (RLS); `realert_drop_pct`/`realert_days` em `settings`; só reenvia se caiu o suficiente ou passou tempo suficiente desde o último alerta da rota.

**Etapa 4 (A5 parte 1) — autocheck estatístico anti-preço-fantasma — ✅ executada 22/07/2026.** `is_suspicious_price` em `rules.py`: preço >50% abaixo da média 30d (com histórico mínimo) vira suspeito — grava normalmente no histórico, mas não dispara alerta, com nota explicando.

**Etapa 5 (A4) — janela dupla de monitoramento (curta/longa).** Motivada por preços "pulando de mês" nos dados reais de 17–21/07 (ex.: BSB→GIG mudou de 27/11→21/11→18/09 em poucos dias). Desenho completo (colunas `monitor_short`/`monitor_long`, `window` no histórico, limiares próprios por janela) ficou registrado no plano, mas a decisão do usuário em 22/07 foi pivotar pro modelo de **datas fixas por fim de semana** (ver seção 3 abaixo) — a motivação original da janela dupla (histórico misturando datas de viagem diferentes) deixa de existir com datas fixas, então esta etapa não foi implementada.

**Etapa 6 (A1 parte 2) — corte pro v3 — ✅ executada 21/07/2026.** 5 dias de comparação paralela: preço idêntico em 100% das observações nas rotas com cobertura (BSB→GIG, GIG→BSB). v3 virou fonte oficial do `price_history`; `get_month_matrix` (v2) mantido no cliente por 1 versão como rollback. Mensagem de frescor ajustada: ausência de `found_at` na v3 vira `ℹ️ Fonte com cache de até 48h` em vez de `⚠️ Dado antigo`. Salvaguarda: idade desconhecida nunca suprime alerta. 27 testes locais verdes.

**Etapa 7 (A5 parte 2) — confirmação pontual (2ª consulta, mesma fonte Travelpayouts).** Desenhada (consulta extra com data exata no momento do alerta, selo `✅ confirmado`), mas superada pela decisão de 18/07 de usar uma fonte **independente** (Google Flights) em vez de uma segunda consulta na mesma fonte — ver Etapa 8 e o pivô da seção 4.

**Fora desta fase:** heatmap, percentil, calculadora de milhas, melhor antecedência de compra, ANAC, câmbio, ML — só começariam com novo Plan Mode.

---

## 2. Validação cruzada + revisão da regra de scraping, 18/07/2026

_Fonte: `PLAN-VALIDACAO-CRUZADA.md`, complemento ao PLAN-FASE-A.md._

**Regra de scraping revisada (18/07/2026):** consulta a fonte não-oficial (scraping) passa a ser permitida quando **todas** as condições valerem: (1) volume mínimo — só no evento de alerta, nunca na varredura diária, no máximo 1 consulta extra por alerta; (2) best-effort — falha nunca bloqueia nem atrasa o alerta; (3) sem evasão ativa — nada de proxy, spoofing, CAPTCHA, burla de login; (4) fonte degradável — sistema funciona idêntico se a fonte sumir; (5) validação prévia obrigatória (Etapa 0). Racional: a Etapa 7 valida contra a mesma fonte (Travelpayouts); uma fonte independente (Google Flights) adiciona sinal genuinamente novo, com risco aceitável só sob essas 5 condições.

> Nota de autoridade entre documentos (21/07/2026): a cláusula original "em caso de conflito, o VALIDACAO-CRUZADA prevalece" foi revogada — nenhum arquivo tem mais autoridade automática de escopo; decisões de escopo exigem aprovação explícita no chat de planejamento.

**Etapa 0 — validação do fast-flights (18/07/2026).** Script `scripts/validate_fastflights.py` (fora de `src/`, não dispara `daily.yml`). Local: 2/3 rotas com preço (BSB→GIG R$638, GIG→BSB R$757; RIA→BSB sem cobertura, erro de parser consistente com "sem resultado", não bloqueio). GitHub Actions (`validate_fastflights.yml`, `workflow_dispatch` only): 2/3 rotas também, mais rápido que local (0,5s) — runner **não bloqueado**. Critério de aprovação (≥2/3 rotas em ≥3/4 execuções) batido já nas 2 primeiras execuções. Versão validada: `fast-flights==3.0.2` (API mudou da 2.x: sem `fetch_mode`, usa `create_query`+`get_flights`; aceita `currency`/`language` nativamente; packaging não declara `typing_extensions`, corrigido no requirements). **Decisão: aprovado.**

**Etapa 8 — selo de fonte independente no alerta.** Desenhada (`src/independent_check.py`, `check_google_flights`, comparação ±30%, selo `🔎 Google Flights` ou `divergente`) mas nunca implementada como etapa própria — superada pelo pivô de 22–23/07 (fim de semana como alvo, fast-flights virando fonte primária das pernas em vez de confirmação pontual de rotas flexíveis; ver seção 4).

**Roadmap consolidado B/C/D (datas-alvo, planejado 18/07/2026) — nunca executado, superado pelo pivô.** Fase B (gráfico Plotly, heatmap, melhor antecedência, percentil), Fase C (datas fixas + bot em linguagem natural via Claude Haiku), Fase D (sazonalidade ANAC, experimento VPN, previsão simples) — todo esse roadmap foi escrito ainda no modelo de "rotas flexíveis" como produto principal. A decisão de 22/07 (pivô pro alvo de fins de semana) tornou esse roadmap obsoleto antes de qualquer item começar. O backlog atual e realista vive em `CLAUDE.md`.

---

## 3. Pivô: alvo de fins de semana RIO→BSB 2027, 22/07/2026

_Fonte: `ALVO-FINS-DE-SEMANA-2027.md`. Primeira versão do pivô — depois redesenhada (seção 4) para 66 fins de semana 2026-2027 com pernas desacopladas._

Redefinição do objetivo prático: comprar passagem para (quase) todos os fins de semana de 2027, ida RIO→BSB sexta, volta domingo ou segunda, monitorando cada fim de semana individualmente. Desenho original: ~45 fins de semana (29/01 a 03/12/2027), tabela `weekend_targets` com `outbound_date`/`return_date` únicos por alvo, teto default R$400, varredura diária de todos os alvos `monitoring`, alerta de teto + alerta de oportunidade relativa + resumo semanal, painel de compras com tabela e botão "marcar comprado". Esse desenho (RIO como código de cidade agregando GIG+SDU, alvo único ida+volta por fim de semana) foi **substituído** em 23/07/2026 depois que a Parte 2 do redesenho (seção 4) mostrou cobertura de cache insuficiente com esse modelo — motivou o desacoplamento em pernas independentes.

---

## 4. Redesenho: pernas desacopladas + fast-flights em lote, 23–24/07/2026

_Fonte: plano de trabalho de fins de semana (Plan Mode), consolidado aqui._

### Contexto e decisão

Com RIO agregado (GIG+SDU) e ida+volta como evento único, a cobertura real ficou quase zerada (2 entradas de 66 alvos no run de 23/07). Diagnóstico: cache de buscas com código de cidade genérico é mais raro que aeroportos específicos, e exigir os dois trechos baterem juntos multiplica a raridade. Decisão: desacoplar ida e volta em 132 "pernas" independentes, consultar GIG e SDU separadamente por busca one-way, complementar com lotes rotativos de `fast-flights` (Google Flights).

### Modelo de dados

`weekends` (66 linhas, sexta 04/09/2026 a sexta 03/12/2027) + `weekend_legs` (132 linhas, 2 por weekend: `direction`, `price_ceiling` default 200, `status`, `current_price`/`airport`/`variant`/`source`, `lowest_seen`, `last_live_check_at`, `purchased_at`, `notes`, depois `paid_price` — ver `PLANO-ATIVO.md`) + `weekend_leg_price_history` + `weekend_leg_run_log` + `alert_log.leg_id`. Tabelas antigas (`weekend_targets` etc.) dropadas — zero dado real perdido.

### Partes entregues

- **Parte 1 (23/07) — ✅** SQL do schema novo completo (tabelas + seed + settings).
- **Parte 2 (23/07) — ✅** `weekends.py` reescrito pra busca one-way GIG+SDU por perna. **Veredito real de produção: cache Travelpayouts insuficiente, 2 de 132 pernas** — motivou a Parte 3 redesenhada.
- **Parte 3 redesenhada (23/07) — ✅** fast-flights vira fonte primária das pernas (não mais só confirmação pontual). Janela deslizante de 6 meses (~42-52 pernas elegíveis por vez, platô calculado); lote de 20/dia cobre em 2-3 dias. Rotação por `last_live_check_at` (nunca checada primeiro), desempate por proximidade de data e distância ao teto. GIG primeiro, SDU só se GIG vazio (limitação aceita: SDU mais barato pode passar despercebido). Detector de bloqueio: ≥5 falhas seguidas OU taxa de sucesso <50% (amostra ≥8) — para o lote e avisa no Telegram, nunca contorna. Kill-switch `settings.fast_flights_enabled`. Espaçamento ~2,5s, sequencial, sem paralelismo. Arquivos: `src/live_check.py` (novo), `evaluate_and_record_leg_price` extraída em `weekends.py` pra reuso entre cache e live. Revisão de escopo registrada no `ROADMAP-AUDITORIA.md` (regra do A5 revisada: lote diário limitado autorizado, além da confirmação pontual).
- **Parte 4 — confirmação de pacote no alerta — desenhada, depois suspensa.** Ver seção 6 (Parte 7) — suspensa em 24/07 por falta de fonte round-trip sequencial confiável.
- **Parte 5 (24/07) — ✅** Painel `docs/compras.html` + `docs/js/compras.js`. Cards por fim de semana (não tabela), ordenação puramente temporal por `outbound_date` (nunca por preço — sinal de alerta não deve ser escondido). Badge de status por perna (Monitorando/Comprada), teto editável por perna + aplicar a todos com confirmação específica (não `confirm()` genérico), botão Comprei/Desfazer, abas Ativos (≥1 perna não comprada) / Comprados (as 2 compradas) — nenhum card some de Ativos por falta de preço. Indicador de progresso (X/132 pernas, Y/66 weekends).
- **Parte 5b (24/07) — ✅** Configurações reorganizada em duas seções ("Rotas flexíveis (legado)" vs "Fins de semana RIO↔BSB"), expondo o kill-switch `fast_flights_enabled` e `fast_flights_daily_batch_size` na UI pela primeira vez (antes só via SQL direto).
- **Parte 6 (24/07) — ✅** Nota de revisão de escopo no `ROADMAP-AUDITORIA.md` (item A5) documentando o lote diário como uso adicional autorizado do fast-flights.

### Ajustes de UX no painel de Compras (24/07)

Campo de notas por perna (localizador, horário) — mesmo padrão blur+salvar do teto. Favicon/apple-touch-icon novos (avião de papel) substituindo o ícone genérico "F" do iOS; emoji ✈️ do cabeçalho trocado por SVG minimalista. Correção de dois bugs visuais mobile: `.leg-row-main` sem `flex-wrap` causava overflow horizontal com título/preço longos (corrigido); `nav` sem `flex-wrap` cortava "Sair" em telas estreitas (corrigido, com breakpoint em 480px). Renomeação de `escopo-projeto-passagens.md` para `CLAUDE.md` (lido automaticamente pelo Claude Code) com conteúdo atualizado pro estado real do projeto.

Depois: horário da última checagem por perna ("atualizado há Xh"/"nunca verificado", de `last_live_check_at`) e link "Ver/comprar" por perna, abrindo o Google Flights pré-filtrado pra aquela busca exata.

---

## 5. Bug de preço do fast-flights + migração pra fli, 24/07/2026

### Descoberta

Perna "Ida (sex) 22/01, GIG→BSB" mostrou R$561 no painel (fonte live); o Google Flights mostrava R$286-346 pra mesma busca one-way. Investigação em duas frentes.

**Frente 1 — link "Ver/comprar" abria em ida-e-volta por padrão (bug real, corrigido).** `google_flights_link` (`src/links.py`, reusado em `docs/js/compras.js`) montava a URL sem instrução explícita de one-way; testado ao vivo, o Google assume ida-e-volta por padrão nesse caso. Fix: acrescentar `"one way"` no texto da query quando não há `return_date`.

**Frente 2 — preço gravado pelo `check_live_price` também estava errado (achado mais sério).** Parâmetros da consulta confirmados corretos (`trip="one-way"`, protobuf `Trip.ONE_WAY`, sem `return_date` nenhum). Três hipóteses baratas testadas e descartadas: `fetch_mode` (não existe nem em `fast-flights==3.0.2` nem em `faster-flights==3.7.0`), `language`/`currency` (já explícitos), upgrade de versão (mesmo R$561, cookie de consentimento novo não mudou nada). Causa raiz encontrada capturando o HTTP cru: a lib lê um bloco JSON (`AF_initDataCallback` `ds:1`) embutido no HTML que o Google Flights serve — payload que diverge do que a interface real renderiza (confirmado: R$286 aparece como HTML visível real, `aria-label="286 Reais brasileiros"`, fora de qualquer `<script>` — não é questão de JavaScript não ter rodado, é que `ds:1` é um payload diferente do que popula os cards reais). Bug estrutural de parsing, não de configuração.

### Migração pra `fli`

`fli` (github.com/punitarani/fli) acessa o endpoint interno `GetShoppingResults` do Google diretamente (o mesmo RPC que o JS da página chama), sem parsing de HTML. Testado com `fli` real: lista completa e corretamente ordenada, R$286 em primeiro, R$561 aparecendo corretamente mais abaixo como opção mais cara — bate com o navegador.

**Migração aprovada e implementada em 24/07/2026:**
- `src/live_check.py`: `check_live_price` migrado pra `fli`, assinatura e formato de retorno preservados (`check_and_evaluate_leg`, `select_batch`, `run_daily_batch` — kill-switch e detector de bloqueio — intocados).
- `build_package_comparison` **suspensa** (retorna `None` sempre): `fli` só faz round-trip via expansão em threads paralelas, o que viola a regra de sempre do projeto (sequencial, sem paralelismo). Comparar "avulso" correto (fli) contra "pacote" sabidamente impreciso (fast_flights) seria pior que não comparar. Reativar exige uma fonte round-trip sequencial compatível — não existe hoje. Mitigação: o link "Ver/comprar" por perna permite alternar pra ida-e-volta manualmente.
- `requirements.txt`: `fli` pinado num commit específico do GitHub (`121d34fea056dc513258958c4262cb5a4cc033c1`, não `@main` — projeto não publica no PyPI sob esse nome; requirement usa o nome real do metadata, `flights`, senão o pip rejeita por nome divergente). `fast-flights==3.0.2` mantido por 1 ciclo de release só pra rollback rápido (mesmo padrão do corte v2→v3).
- `docs/config.html`: rótulos da UI atualizados no mesmo commit ("Consulta de preço ao vivo (Google Flights)" em vez de "Fast-flights ativo"), sem mencionar a comparação de pacote suspensa. Nomes de coluna no banco inalterados.
- 120 testes locais passando (mock). Smoke test real confirmou `check_live_price('GIG','BSB','2027-01-22')` retornando R$286.
- **Confirmado em produção 24/07/2026:** `daily.yml` run #33 (commit `4db8f38`) passou com sucesso. Run diário seguinte: **20/20 pernas checadas, 20 com preço**, incluindo `[perna outbound 2027-01-22] R$ 286.00 (GIG, live)` — a mesma perna que motivou a investigação, agora com o preço correto.

### Higiene de dado

**Preços `source='live'` gravados antes de 24/07/2026 são suspeitos** (não usar pra calibrar teto nem pra análise futura de melhor antecedência de compra) — não apagar, é histórico real do que o robô viu. A partir de 24/07/2026, `source='live'` é confiável. Preços `source='cache'` (Travelpayouts) nunca foram afetados por esse bug. A rotação natural do lote diário (ordenada por `last_live_check_at`) re-checa e substitui os valores suspeitos nos primeiros 2-3 dias após a migração.

---

## 6. Parte 8 — Preço pago, Dashboard redesenhado, feriados/alta temporada, 24/07/2026

Com o preço já confiável (seção 5), fez sentido usar dados reais no lugar de placeholder. Três entregas combinadas:

- **`weekend_legs.paid_price`** (SQL): valor efetivamente pago por perna, editável em Compras (mesmo padrão blur+salvar das notas), só aparece quando a perna está `purchased`.
- **`docs/js/holidays.js`** (novo): feriados nacionais 2026/2027 calculados programaticamente (fixos + móveis a partir da Páscoa: 2026-04-05, 2027-03-28). Cruzamento com os 66 fins de semana monitorados: **24 batem** (16 feriado + 10 alta temporada, 2 sobrepostos — 2026-12-25 e 2027-01-01) — lista validada duas vezes de forma independente (cálculo próprio + script do usuário, mesmo resultado exato) antes da implementação. Selo 🎉/☀️ no card de Compras; cada card ganhou âncora `weekend-<id>` pra permitir link direto a partir do Dashboard.
- **Dashboard redesenhado** (`docs/index.html` + `docs/js/dashboard.js`), mobile-first, curto em cima: ação do dia (pernas abaixo do teto agora, tocável → Compras), urgência (fins de semana nos próximos 60 dias com pelo menos 1 perna não comprada), progresso (com barra visual nova, `.progress-bar`), melhores oportunidades (top 5 por menor distância percentual ao teto), orçamento (soma/média de `paid_price`, com estimativa explícita do que falta), saúde do sistema (última execução, pernas checadas 24h/7d, consulta ao vivo ativa/desligada, bloqueio recente), feriados/alta temporada. Conteúdo antigo (rotas flexíveis: cards, gráfico Chart.js, export CSV) movido pra uma seção `<details>` recolhida no fim, sem mudança de comportamento.
- **Backend:** `set_weekend_batch_blocked_at` (`supabase_client.py`) persiste o timestamp do detector de bloqueio na tabela `bot_state` (mesmo padrão key-value de `last_update_id`) — chamado em `live_check.py` quando o lote é bloqueado, lido pelo Dashboard em "Saúde do sistema". RLS de `bot_state` recebeu policy de select pra autenticado (não estava rastreada em nenhum `sql/*.sql` antes).

**Verificação:** 121 testes locais passando. `holidays.js` testado isolado no navegador contra os 66 fins de semana — bateu exatamente com a lista validada. Verificação visual no navegador (mobile 375px e desktop) com dados mock, sem login — dados reais dependem do login real (celular, pós-deploy).

**Checagem pós-deploy (24-25/07/2026):** a policy de select em `bot_state` (item acima) levantou dúvida se quebraria a escrita do bot do Telegram na mesma tabela. Confirmado: toda escrita do backend (`set_last_update_id`, `set_weekend_batch_blocked_at`) usa `SUPABASE_SERVICE_ROLE_KEY` (`_headers()` em `supabase_client.py`), que bypassa RLS por definição — a policy só afeta leitura via `anon key` (frontend). Teste ao vivo confirmou: mensagem de teste mandada pro bot, run manual do `bot_commands.yml` (workflow_dispatch, run #162) concluído com sucesso em todos os 8 steps, incluindo a execução do script — prova indireta forte de que a escrita funcionou (uma falha de `set_last_update_id` derrubaria o script sem try/except). Observação à parte, sem relação com RLS: o cron de 5 min do `bot_commands.yml` ficou mais de 1h sem disparar sozinho nesse intervalo — atraso de agendamento do GitHub Actions em repositório de baixo tráfego, não é bug do projeto.

---

## 7. Alerta de bloqueio com diagnóstico e escalonamento, 25/07/2026

O alerta de bloqueio do lote de consulta ao vivo era uma string fixa, sem números nem cooldown — repetia idêntico todo dia se o bloqueio persistisse, sem indicar urgência crescente nem sugerir ação.

- **`telegram_notifier.py`**: `build_block_alert_message` monta diagnóstico real (quantas consultas, quantas falharam, qual gatilho — falhas seguidas ou taxa de sucesso —, há quanto tempo foi a última consulta bem-sucedida) e escalona por dias consecutivos de bloqueio: dia 1 informativo ("nada a fazer, tenta de novo amanhã"), dia 2-3 sugere reduzir o lote em Configurações, dia 4+ recomenda desligar o kill-switch e avisa a data desde quando os preços estão parados. Sempre com link direto pra Configurações (`https://eltoneap.github.io/flyiop/config.html`, confirmado pelo usuário). Nunca sugere proxy/IP/fingerprint/evasão — a resposta a bloqueio é sempre recuar. `build_block_recovered_message`: aviso curto quando a fonte volta a funcionar.
- **`supabase_client.py`**: `get_last_successful_live_check` (lê `weekend_leg_run_log`, que `evaluate_and_record_leg_price` já grava com `outcome='ok', source='live'` em todo sucesso — sem mudança nenhuma em `weekends.py`/`live_check.py` pra alimentar essa query) e `get_weekend_block_streak`/`set_weekend_block_streak` (contador de dias consecutivos + data de início, em `bot_state`, mesmo padrão key-value de `last_update_id`). Ajuste do usuário: ao zerar o contador, a data de início órfã é apagada (não fica lixo no banco).
- **`live_check.py`**: `run_daily_batch` monta o diagnóstico e escalona a mensagem quando bloqueia (o contador de dias só avança quando o lote de fato roda — kill-switch desligado ou lote vazio não contam); quando um lote roda até o fim sem bloquear e havia uma sequência de bloqueio registrada, manda a mensagem de recuperação e zera o contador.
- **Limitação conhecida (aceita, registrada no código):** se o kill-switch for desligado no meio de uma sequência de bloqueio e religado depois, os dias pausados não entram na contagem — o contador reflete dias de bloqueio real, não tempo de calendário total.

**Verificação:** 132 testes locais passando (11 novos — 3 de streak/recuperação em `RunDailyBatchTest`, 8 de conteúdo das mensagens em `BuildBlockAlertMessageTest`, incluindo checagem negativa de que nenhuma variante menciona proxy/IP/evasão). Mensagens conferidas visualmente nos 4 níveis de escalonamento (dia 1, dia 2, dia 5, recuperação) antes do push. Sem SQL, sem mudança em `docs/**` — push tocou só `src/**`/`tests/**`, dispara `daily.yml`; confirmação em produção só ocorre organicamente, se/quando um bloqueio real acontecer.

---

## 8. Dashboard/Compras — filtros, deep-link e estado visual de campo salvo, 25/07/2026

**Investigação prévia (sem bug):** o usuário viu "Ação do dia" mostrar 4 pernas abaixo do teto quando dados de um log anterior sugeriam só 1. Revisão do código (`renderAcaoDoDia`, `dashboard.js`) confirmou que a comparação já era null-safe e numérica — nenhum bug na lógica. O usuário rodou uma consulta direta no Supabase e confirmou 3 pernas genuinamente abaixo do teto no momento (R$248/242/245, todas ≤ R$250) — a diferença era só o preço oscilando entre execuções do robô, dado mudando de verdade. Nenhuma mudança de código nessa parte.

- **Deep-link:** o link de "Ação do dia" no Dashboard agora leva pra `compras.html?filtro=abaixo-do-teto` em vez da aba inteira.
- **Chips de filtro em Compras** (`docs/compras.html`/`compras.js`): Todas / Abaixo do teto / Sem preço ainda / Feriado-alta temporada / Próximos 60 dias — mobile-first, linha rolável horizontal. Combinam com a aba atual (Ativos/Comprados) por E lógico; aplicados a nível de fim de semana (mostra o card se ao menos 1 perna bater o critério). Lê o filtro inicial da URL (`?filtro=`), com fallback pra "todas" se ausente/inválido. Predicado de "abaixo do teto" mantido em sincronia manual com o mesmo critério do Dashboard (`legBelowCeiling`/`renderAcaoDoDia` — arquivos diferentes, sem módulo compartilhado hoje).
- **Estado visual salvo/não-salvo** nos três campos editáveis (teto, notas, valor pago): botão "Salvar" fica cinza discreto + ✓ verde ao lado do campo quando o valor bate com o banco; volta a ficar azul e o ✓ some ao editar. Se o salvamento falhar, volta pro estado "não salvo" em vez de fingir sucesso. Teto ganhou rastreio de sujo/limpo que não existia antes (só salvava no clique); notas/pago já tinham a trava contra duplo-envio (blur + clique quase juntos), preservada.

**Verificação:** sem mudança em `src/**` nem SQL. Frontend testado no navegador (375px e leitura de DOM): chips renderizam e rolam horizontalmente (5 chips, só 3 cabem na tela sem rolar), estado salvo/não-salvo visualmente correto nos 3 campos. Lógica de filtro e leitura de `?filtro=` verificadas isoladamente com dados mock (incluindo `holidays.js` real) — resultados batem com o esperado, inclusive um caso em que uma data de teste caiu coincidentemente perto de um feriado real (Finados), confirmando que o predicado de feriado está genuinamente correto, não hardcoded. Push tocou só `docs/**` — não dispara `daily.yml`.

---

## 9. Verificação de menções soltas ("bot via Claude Haiku", "experimento de VPN"), 27/07/2026

Um `STATE.md` trazido de outra sessão de planejamento listava como pendência auditar a origem dessas duas menções, suspeitando de alucinação. **Não é alucinação — são reais e rastreáveis**: ambas vêm do roadmap `Fase C`/`Fase D` do antigo `PLAN-VALIDACAO-CRUZADA.md` (item 2 deste `HISTORICO.md`, "Roadmap consolidado B/C/D"), planejado em 18/07/2026 e nunca executado — superado pelo pivô pro alvo de fins de semana (22-23/07) antes de qualquer item começar. Nenhuma ação necessária; item removido da lista de pendências do `STATE.md`.

---

## 10. Redesign visual da aba Compras — Bloco A, 27/07/2026

Sessão de design visual dedicada (Plan Mode), separada da sessão funcional. Referência: `design/mockup-compras.html` (commitado isoladamente antes da implementação). Só CSS/markup — nenhuma lógica de preço/teto/alertas/robô/scraping tocada, sem SQL/RLS, sem biblioteca nova, Dashboard e Configurações intocados.

- **A1** Preço ganha semântica de cor: acima do teto (cinza), abaixo do teto (verde + badge "↓ R$X abaixo do teto"), sem preço (texto menor, cinza) + badge contextual. Badge de status agora traz o percentual acima do teto ou "ainda sem preço" em vez de só "Monitorando".
- **A2** Perna comprada: fundo verde-menta + faixa esquerda 3px, badge "✓ Comprada" sólido. Valor pago vira número grande só quando **preenchido**; se vazio (marcar como comprada não exige valor pago), o preço ao vivo continua como número principal e aparece "valor não informado" — decisão do usuário pra não inverter hierarquia com dado inexistente.
- **A3** Card do fim de semana: borda mais visível + sombra sutil + barra de progresso no topo (cinza 0/2, meio-verde 1/2, verde 2/2).
- **A4** Campos de teto/notas/valor pago: vazio = borda tracejada, preenchido = borda sólida + negrito.
- **A5** "Ver/comprar" é o único azul sólido; "Marcar como comprada" virou botão de contorno azul, largura total, abaixo dos campos — só em pernas não compradas.
- **A6** Contador "X/2 compradas" ganha cor (âmbar em 1/2, verde em 2/2).
- **A7** (era B3 no plano original, movido pra cá em Plan Mode porque é só CSS condicionado ao mesmo `is-bought` da A2): perna comprada troca o botão de ação por "Desfazer compra" em contorno verde discreto — nunca compete com o botão azul full-width da A5, que é exclusivo de pernas não compradas.

Tokens novos em `:root` (`style.css`): `--bought`/`--bought-bg`/`--bought-line` (verde de perna comprada, distinto do verde "oportunidade" que reaproveita `--good` já existente), `--amber`/`--amber-bg`/`--amber-line` (reservado pro Bloco B), `--line-strong`.

**Verificação:** sem servidor com dados reais logados disponível na sessão — montado harness estático temporário (fora do repo, removido ao final) reproduzindo o HTML exato que `compras.js` gera pros 5 estados-chave (preço acima/abaixo/sem preço, perna comprada com e sem valor pago, card 0/2 · 1/2 · 2/2), carregado com o `style.css` real em viewport 390px (uso principal é celular). Conferido visualmente: cores, badges, faixa de progresso, contorno de botões. Altura da perna cresceu (~1 linha a mais por causa do botão full-width e do badge com mais texto), mas não a ponto de justificar parar e avisar — sem testes automatizados cobrindo essas classes.

Bloco A validado pelo usuário no ar: bate com o mockup em todos os pontos, incluindo o caso de perna comprada sem valor pago.

## 11. Redesign visual da aba Compras — Bloco B, 27/07/2026

Sequência do item 10. Plan Mode dedicada de novo (o plano original já estava aprovado em alto nível; essa rodada amarrou a implementação exata em cima do código do Bloco A). Só CSS/markup + estado de UI local (dirty/collapsed, sem persistência nova) — mesmas restrições de escopo do Bloco A.

- **B1** Botão "Salvar" reflete estado sujo/limpo: `markFieldState` (em `renderLegRow`, `compras.js`) ganhou um parâmetro `input` — quando há alteração pendente, botão e campo (teto/notas/valor pago) ficam âmbar (`button.small.dirty`, `.field-dirty`); ao salvar, voltam ao estado apagado normal.
- **B2** Card 2/2 compradas colapsa por padrão: `renderCard` nasce com a classe `is-collapsed` quando as duas pernas estão compradas, mostrando só uma faixa verde (`.card-done-head`) com as datas, "2/2 compradas · ida e volta resolvidas" e o total pago. Clique expande/colapsa (toggle simples, estado só em memória). Total pago: soma cheia rotulada "total pago" só se **ambas** as pernas tiverem `paid_price`; soma só da perna com valor rotulada "total parcial" se só uma tiver; **sem bloco de total** se nenhuma tiver — nunca soma ignorando campo vazio (decisão do usuário no plano, pra não produzir total falso).

**Verificação:** harness estático temporário (removido antes do commit) cobrindo 6 casos em viewport 390px — campo com alteração pendente, campo recém-salvo, card 2/2 com total pago cheio, com total parcial, sem total, e clique expandindo o card colapsado (toggle real via JS, testado com `javascript_tool` clicando no `.card-done-head` e conferindo a classe `is-collapsed`). Screenshots enviadas e validadas pelo usuário antes do push, incluindo conferência explícita do caso de total parcial (R$240, só a perna com valor preenchido). Sem testes automatizados cobrindo essas classes.

Com isso, o redesign visual da aba Compras (Blocos A e B) está concluído e no ar.

---

## 12. Expiração por perna, dados de voo (fli) e Dashboard pós-corte, 28/07/2026

Sequência direta da investigação somente-leitura do mesmo dia (achado do bug de expiração e dos itens de melhoria do Dashboard). Plan Mode dedicada, aprovada com dois ajustes do usuário (ordem de execução da migração em destaque; listas de oportunidades com 5 itens cada, não split de um top-5 único).

**Corrigido — expiração por perna (bug real):** `get_monitoring_weekends()` (`supabase_client.py`) filtrava pela data de ida do weekend inteiro (`outbound_date`), cortando a perna de volta da rotação 2-3 dias antes da própria data dela (ela é domingo/segunda, o filtro usava sexta). Agora `get_monitoring_weekends()` filtra por `return_monday` (o limite superior seguro do weekend) e `get_active_legs()` (`weekends.py`) ganhou expiração fina por perna via `leg_expiry_date()` — ida expira pela própria `outbound_date`, volta pelo `return_monday` (cobre domingo e segunda mesmo sem `current_variant` decidido). **Decisão: expira em D+1**, não D0 — o robô roda 1x/dia às 08:00 BRT; D0 puro arriscaria perder a checagem do próprio dia do voo por atraso de execução ou o voo já ter partido de manhã. D+1 dá 1 dia de folga por perna, custo irrelevante numa janela de ~180 dias.

**Adicionado — companhia aérea e horário (fli):** a `fli` já devolvia `primary_airline_name` e `legs[0].departure_datetime` (confirmado no pacote pinado), descartados até então. Novas colunas `airline`/`departure_time` em `weekend_leg_price_history` e `current_airline`/`current_departure_time` em `weekend_legs` (`sql/parte9_dados_voo_e_expiracao.sql`) — só a fonte `live` (fli) preenche; `cache` (Travelpayouts) fica `null`, sem backfill do que já foi perdido antes. **Ordem de execução obrigatória: o SQL rodou no Supabase antes do deploy do código** — o insert quebraria em produção se as colunas não existissem ainda.

**Adicionado — Dashboard pós-corte de 29/01/2027** (data já registrada em `CLAUDE.md`/`STATE.md` como primeiro fim de semana alvo de compra real):
- `renderProgresso`: contador de pernas/fins de semana passa a considerar só `outbound_date >= 2027-01-29`. **Decisão de layout: nota de uma linha na própria seção**, não seção nova nem ocultação — o corte é só de métrica, as pernas de set/2026-jan/2027 continuam visíveis em Compras e a nota deixa isso explícito sem competir com o número principal.
- `renderOrcamento`: escopado ao mesmo corte; projeção dos restantes trocou a base de "média do que já foi pago" (instável com poucas compras reais) pra **mediana do `current_price`** das pernas ainda não compradas pós-corte — mais amostras, mais estável.
- `renderOportunidades`: virou duas listas de até 5 itens cada, sem sobreposição — "Abaixo do teto" (ação, ordenada pela distância ao teto) e "Mais baratas no momento" (informação, as demais candidatas acima do teto, ordenadas por preço absoluto) — antes misturava as duas coisas sob um rótulo só. Cada item passa a mostrar `current_source` discreto ao lado do preço.

**Entregue no chat (não executado por mim):** 4 consultas SQL somente-leitura pro usuário rodar no Supabase — contagem/histórico de `weekend_leg_price_history`, linhas brutas das voltas de R$283 (out/nov), registros `status='purchased'`, e status de `weekend_block_streak`/`weekend_batch_blocked_at`.

**Verificação:** 136 testes locais passando (`unittest discover`), incluindo os novos casos de expiração independente por perna (ida expira mesmo com volta ainda válida e vice-versa, ida seguindo checada até D+1) e de extração de `airline`/`departure_time` da `fli` (incluindo caso defensivo sem `legs`). `median()` e a divisão das duas listas de oportunidades verificadas isoladamente com dados sintéticos no console do navegador (sem depender de login). **Sem verificação visual end-to-end no Dashboard com dados reais** — exige login do usuário na sessão, que não tentei obter/preencher; a lógica está coberta por teste, mas a conferência visual final (nota de corte, mediana, duas listas) fica pro usuário no próximo acesso.

---

## 13. Resultado das 4 consultas de auditoria, 28/07/2026

Usuário rodou as 4 consultas do item 12 no Supabase e colou o resultado no chat. Fecha as pendências que a investigação da Parte 8 tinha deixado em aberto por falta de acesso ao banco.

- **(a) Volume do histórico:** 236 linhas em `weekend_leg_price_history`, observação mais antiga em 23/07/2026 (projeto tem só 5 dias de dado real ainda), média de 5,6 observações por perna.
- **(b) R$283 repetido nas 4 voltas de out/nov:** **não é cache/fallback — é coleta real e independente.** Todas as linhas são `source='live'` (fli), nunca `cache`; o preço varia dentro de cada perna ao longo dos dias (ex.: a perna de 23/10 foi 283 → 283 → 242 → 245 → 283), e uma das 4 pernas divergiu do valor das outras 3 no mesmo dia (25/07, enquanto as outras 3 seguiam em 283). Isso descarta bug de cache/fallback compartilhado — o padrão é consistente com R$283 sendo um patamar de tarifa real e comum da rota nessa época (comportamento de mercado, não bug).
- **(c) Registros `purchased`:** as 2 pernas do fim de semana de 04/09/2026 (o mais próximo, ida R$513 pago/R$555 monitorado, volta R$500 pago/R$678 monitorado — total R$1.013,00, batendo com o número visto no Dashboard). `purchased_at` é **hoje, 28/07/2026** — coerente com uma compra real feita durante esta mesma sessão de trabalho, não teste antigo nem dado sujo, mas isso não é uma inferência segura só do dado; **fica pro usuário confirmar**.
- **(d) Bloqueios registrados:** nenhum. `bot_state` não tem nenhuma linha pra `weekend_block_streak_days`, `weekend_block_streak_started_at` nem `weekend_batch_blocked_at` — o lote de 20 pernas/dia nunca disparou o detector de bloqueio até hoje.

Nenhuma mudança de código — só interpretação, registrada aqui e refletida no `STATE.md` (Parte 10 desbloqueada, ainda sem decisão de aumentar o lote).

---

## 14. Escalonamento automático da frequência de scraping (fli), 28/07/2026

Sequência direta do item 13 — usuário decidiu subir a frequência do lote `fli` via mais execuções/dia (não lote maior por execução), em estágios automáticos. Plan Mode dedicada, aprovada com um ajuste de revisão (ver abaixo).

**Estágios**: 0 (atual, 08h BRT, 20 pernas/dia) → 1 (08h+20h, 40/dia) → 2, teto automático (08h+14h+20h, 60/dia). `.github/workflows/daily.yml` ganhou cron estático com as 3 janelas sempre ativas (11h/17h/23h UTC = 08h/14h/20h BRT, Brasil sem horário de verão desde 2019) — **nunca reescrito dinamicamente**; a decisão de fazer algo ou não em cada execução é 100% em Python (`src/scrape_schedule.py`, funções puras: `current_brt_hour`, `is_primary_run`, `should_run_live_batch`, `is_last_scheduled_hour`, `evaluate_stage_transition`, `apply_block_reversion`).

**Regras**: sobe 1 estágio após 5 dias consecutivos sem bloqueio (`CLEAN_DAYS_TO_ESCALATE`); qualquer bloqueio detectado derruba pro Estágio 0 na hora e reseta a contagem, de qualquer estágio; nunca sobe sozinho além do Estágio 2 sem aprovação explícita no chat. Toda mudança de estágio (subida ou queda) dispara alerta no Telegram (`build_stage_change_message`, `telegram_notifier.py`) — nunca uma mudança silenciosa. Estado persistido em `bot_state` (mesmo padrão key-value de `weekend_block_streak_days`, sem migração SQL nova): `weekend_scrape_stage`, `weekend_scrape_clean_days`, `weekend_scrape_blocked_today`, `weekend_scrape_last_change_at/_reason` (`get_weekend_scrape_state`/`set_weekend_scrape_state`, `supabase_client.py`).

**Achado da exploração (não estava no pedido original):** `main.py` de antes rodava tudo junto a cada invocação — rotas flexíveis e a varredura cache das 132 pernas (as duas via Travelpayouts) sempre acompanhavam o lote `fli`. Rodar `daily.yml` 3x/dia sem separar isso triplicaria consumo da Travelpayouts sem necessidade — o pedido era especificamente sobre a frequência do scraping `fli` (o que tem detector de bloqueio e é o gargalo real). Solução: conceito de **execução primária** (08h BRT — roda tudo, como antes) vs. **execuções extras** do estágio (só rodam o lote `fli`; rotas flexíveis, cache Travelpayouts, notificações de rotas e resumo semanal ficam de fora). `run_daily_batch` (`live_check.py`) mudou de assinatura — devolve `(reports, blocked)` em vez de só `reports`, pra `main.py` saber na hora se precisa derrubar o estágio.

**Ajuste de revisão antes da aprovação:** o plano original não deixava explícito se a avaliação de subida de estágio (última hora agendada do dia) lia o `blocked_today` já atualizado por um bloqueio detectado nessa mesma execução, ou uma cópia desatualizada — cenário mais perigoso: bloqueio detectado exatamente na última hora agendada, o mesmo instante em que a subida seria avaliada. Corrigido explicitamente em `main.py`: a variável `scrape_state` é reatribuída (não copiada) pelo passo de reversão de bloqueio antes do passo de avaliação de subida ler `blocked_today` — e a decisão de qual hora é "a última agendada do dia" usa `initial_stage` (capturado antes de qualquer mutação nesta execução), não o estágio pós-bloqueio. Resultado: bloqueio na última hora agendada sempre termina em Estágio 0, nunca sobe e cai no mesmo ciclo.

**Dashboard**: `renderSaude()` (`dashboard.js`) ganhou linha de estágio atual, execuções/dia e dias limpos pro próximo degrau (ou "teto automático atingido" no Estágio 2) — leitura direta de `bot_state`, mesmo padrão da linha de bloqueio já existente.

**Verificação:** 154 testes locais passando (`unittest discover`) — 16 novos em `tests/test_scrape_schedule.py` (funções puras, sem mock de rede: mapeamento UTC→BRT, quais horas cada estágio roda o lote, qual é a última hora agendada, reversão de qualquer estágio, escalonamento exato no 5º dia limpo, teto no Estágio 2) e 2 em `tests/test_main.py` — o teste específico pedido na revisão (bloqueio na última hora agendada do Estágio 1 nunca sobe pro 2 na mesma execução, só 1 alerta de mudança enviado) mais um teste de controle confirmando que o mesmo cenário SEM bloqueio sobe normalmente (prova que a asserção não passa por acaso). `RunDailyBatchTest` (`test_live_check.py`) ajustado pra desempacotar `(reports, blocked)`. Três testes de integração pré-existentes de `main()` em `test_etapa3_cooldown.py` (não criados nesta parte, já cobriam `main.main()` diretamente) precisaram de mocks novos (`current_brt_hour`, `get_weekend_scrape_state`, `set_weekend_scrape_state`) pra continuar passando sem tocar rede de verdade. Sem preview de browser aplicável (mudança é robô/backend); confirmação real do escalonamento em produção é orgânica, ao longo dos próximos dias — é o que a nova linha do Dashboard passa a mostrar.

---

## 15. Bug de agendamento por hora exata: descoberta, correção e confirmação em produção, 30/07/2026

**Contexto:** na madrugada de 29/07/2026, um lote de commits (`71eb4a7`…`a9dd4f2`…`d51aec2`) consolidou Parte 9 (expiração por perna/dados de voo), Parte 10 (item 14 acima — escalonamento automático) e a Etapa 3 da iniciativa multi-usuário (`a9dd4f2`, `system_config` separada de `settings`) e foi pushado de uma vez às 23h42 BRT. `STATE.md`/`PLANO-ATIVO.md` já descreviam essas três entregas como concluídas/em produção nesse mesmo commit — mas a primeira execução real em produção desse código (disparada pelo próprio push, minutos depois) já nasceu quebrada, sem que ninguém soubesse ainda.

**Causa raiz:** `scrape_schedule.py` decidia "isso roda agora?" por igualdade exata de hora BRT contra o cron (`is_primary_run(hour) → hour == 8`; `should_run_live_batch(stage, hour) → hour in STAGE_HOURS_BRT[stage]`; `is_last_scheduled_hour` na mesma linha). O cron do GitHub Actions não garante disparo no minuto/hora exata — atraso de dezenas de minutos a mais de 1h é comum. Um atraso bastava pra `current_brt_hour()` cair fora de **todos** os "hour buckets" do dia (`{0:[8]}`, `{1:[8,20]}`, `{2:[8,14,20]}`), e `main()` pulava rotas flexíveis, cache Travelpayouts, o lote `fli` inteiro e nunca chamava `set_weekend_scrape_state` — tudo silenciosamente, exit 0, job verde.

**Como foi descoberto:** o usuário reportou o Dashboard parado (última execução carimbada do dia anterior, "pernas checadas 24h" = 0, nenhuma mensagem no Telegram, painel Compras sem atualização há 1-3 dias) apesar da run #42 aparecer verde no Actions. Investigação somente-leitura (sem acesso a log bruto nem ao Supabase — ambiente sem `gh` autenticado nem credenciais de banco): metadados públicos da API do GitHub Actions mostraram a run #42 (evento `schedule`, disparada 1h21min atrasada em relação ao cron `0 11 * * *`) completando o job em **18 segundos** — incompatível com qualquer scraping real, só dava pra 4-5 leituras rápidas ao Supabase. Leitura de código confirmou o mecanismo (`hour == 8` etc.) e a run #41 (evento `push`, disparada às 23h42 BRT — hora 23, também fora de todos os buckets) mostrou que nem a primeira execução pós-push tinha rodado de verdade. Auditoria anterior (item 13 acima) já registrava zero linhas em `bot_state` pras chaves de escalonamento — consistente com `set_weekend_scrape_state` nunca ter sido alcançado.

**Correção (`840abb9`):** `scrape_schedule.py` reescrito — `is_primary_run`, `should_run_live_batch` e `is_last_expected_batch` (substitui `is_last_scheduled_hour`) passam a decidir por **estado gravado**, não hora: `last_primary_run_date` (a primeira execução do dia, não importa a hora, é a primária), `last_batch_run_date`/`batches_run_today` (o lote `fli` roda até completar a cota do estágio atual — 1/2/3 execuções/dia —, contada por execuções reais, não por hora bater com uma lista fixa). `main.py` ajustado só nos pontos que consomem essas três funções, preservando a ordem/invariante já existente (reversão de bloqueio grava e reatribui `scrape_state` antes da avaliação de subida de estágio ler `blocked_today`). `supabase_client.py` ganhou 3 chaves novas em `bot_state` (`weekend_scrape_last_primary_run_date`, `weekend_scrape_last_batch_run_date`, `weekend_scrape_batches_run_today`) — extensão mínima e necessária do mesmo padrão key-value já existente, já que `scrape_schedule.py` é funções puras sem I/O por design. **Decisão explícita:** uma janela de tolerância de horário (`hour BETWEEN 7 AND 9`) foi descartada como solução — só adiaria o mesmo bug pra um atraso maior; o critério tinha que parar de depender do relógio.

**Verificação:** 168 testes locais passando (`unittest discover`) — `tests/test_scrape_schedule.py` reescrito com cenários dedicados aos três riscos identificados na revisão (disparo atrasado ainda executa 1x/dia; disparo atrasado não roda lote extra além da cota do estágio; disparo duplicado da mesma janela não roda em dobro); `tests/test_main.py` ganhou `DelayedScheduleDoesNotNoOpTest` (reprodução direta do incidente, primeira execução do dia processa rotas/cache/lote não importa a hora) e `DuplicateFireSameDayIsIdempotentTest` (chamada dupla no mesmo dia não reprocessa nada); `tests/test_etapa3_cooldown.py` ajustado só nos mocks (`current_brt_hour`→`current_brt_date`, novos campos default em `SCRAPE_STATE_STAGE_0`).

**Confirmação em produção:** push de `840abb9` disparou a run #43 (evento `push`, iniciada 11h16 BRT — também fora do antigo "hour bucket", agora irrelevante). O passo `python src/main.py` levou **2min08s** (contra 18s da #42) — consistente com rotas, cache e lote `fli` de fato executados. Consulta direta ao Supabase confirmou: `weekend_scrape_last_primary_run_date = 2026-07-30`, `weekend_scrape_last_batch_run_date = 2026-07-30`, `weekend_scrape_batches_run_today = 1`, `weekend_scrape_clean_days = 1` (incrementado de 0, prova que `evaluate_stage_transition` foi alcançado — só roda depois do lote completar sem bloqueio), `weekend_scrape_blocked_today = false` — a primeira gravação bem-sucedida dessas chaves desde que existem. Nenhuma mensagem chegou no Telegram nessa execução; confirmado como comportamento correto, não regressão: as 10 pernas mais próximas do teto (R$250) estavam todas em R$308 (`current_source = live`, confirmando que o lote ao vivo sobrescreveu o preço), nenhuma abaixo do teto pra alertar.

**Nota sobre o estado da documentação:** `STATE.md`/`PLANO-ATIVO.md` já descreviam Parte 9, Parte 10 e a Etapa 3 como "concluídas"/"em produção" na mesma noite do push (29/07/2026) — e, por coincidência, nenhuma delas tinha efetivamente rodado com sucesso em produção até esta correção (a run #43 de hoje é a primeira confirmação real). Motivou o reforço de uma regra em `PROTOCOLO-DE-TRABALHO.md` (30/07/2026): `STATE.md` só descreve algo como "em produção" depois do push correspondente já ter sido enviado ao remoto — nunca antes, mesmo que o commit local esteja pronto e a escrita da documentação pareça simultânea ao push.

## 16. Teste do caminho de alerta de perna de fim de semana: confirmado em produção, 01/08/2026

**Contexto:** item (a) do "Diagnóstico: caminho de alerta de perna de fim de semana" (`PLANO-ATIVO.md`, sessão de 31/07/2026) — `alert_log` nunca tinha um registro com `leg_id` desde que a coluna existe (23/07/2026), sem defeito estrutural encontrado na leitura de código. Teste em produção montado em 31/07: teto elevado manualmente para R$ 2000 em 5 pernas (`b4f28800`, `f2bfcf96`, `4a15353d`, `5fd70bb7`, `9c455da7`) e R$ 500 em `c3c514ac`, todas com preço observado ~R$ 308-309.

**Resultado da execução de 01/08/2026 (run `30698587080`, 11:53-11:55 UTC):** o Telegram recebeu 13 alertas de perna — mais que os 6 esperados pelo teste. Diagnóstico somente-leitura via log do GitHub Actions (sem credenciais de Supabase no ambiente da sessão) identificou 7 pernas com preço abaixo do teto elevado, não 6: **`e4142357` também estava com `price_ceiling = 500`**, sem registro no `PLANO-ATIVO.md` — a lista original do teste ficou incompleta desde 31/07. As 6 mensagens restantes eram alertas de oportunidade (`weekend_opportunity_pct`, "X% abaixo da média histórica") em pernas com teto normal (250), disparados organicamente pelo mesmo lote — não relacionados ao teste manual.

Consulta direta ao Supabase (feita pelo usuário) confirmou: 13 linhas em `alert_log` com `leg_id` e `sent_at` em 01/08/2026, batendo exatamente com os 13 alertas recebidos — 7 com `reason = "abaixo da meta fixa (R$ X)"` (as 7 pernas do teste, incluindo `e4142357`) e 6 com `reason` de percentual histórico (oportunidade).

**Conclusão:** o caminho de alerta de perna funciona em produção, para os dois tipos de gatilho (teto fixo e oportunidade) — confirma que ambos passam pelo mesmo `insert_weekend_alert_log` em `main.py:419-423`, sem divergência entre o que foi enviado e o que foi gravado. Esta é também a primeira confirmação em produção do caminho de oportunidade, que nunca tinha dado registro em `alert_log` antes de hoje.

**Fechamento:** tetos das 7 pernas (as 5 originais + `c3c514ac` + `e4142357`) devolvidos a R$ 250 via SQL Editor. Verificação `select count(*) from weekend_legs where price_ceiling <> 250` retornou 0 — nenhuma perna ficou presa em teto de teste.

Itens (a) e (b) do "Diagnóstico: caminho de alerta de perna" (`PLANO-ATIVO.md`, 31/07/2026) fechados nesta mesma data:

- **(a) Caminho de alerta de perna confirmado em produção** — é exatamente o teste descrito acima. A Etapa 6 da iniciativa multi-usuário (Telegram por perna × usuário) deixou de ter gate de teste; segue exigindo a revisão explícita de praxe no chat de planejamento antes de rodar.
- **(b) Gatilho `push` removido do `.github/workflows/daily.yml`.** O workflow tinha `on: push` com filtro de paths (`src/**`, `requirements.txt`, `daily.yml`), rodando o caminho primário completo contra PRODUÇÃO a cada commit nesses caminhos. Removido em Plan Mode (01/08/2026), mantendo só `schedule` + `workflow_dispatch`. Investigação em código antes da remoção confirmou que a última execução via push (mesmo dia, depois da primária das 08:55 e do lote `fli` já completos) foi um no-op seguro — `is_primary_run` e `should_run_live_batch` ambos False por cota do dia já atingida, sem chamada extra de scraping, sem risco pra execução agendada de 02/08 (`batches_run_today` zera por data, `_batches_run_today` em `src/scrape_schedule.py`). Nenhum outro workflow ou teste dependia do gatilho. **Efeito colateral aceito:** o padrão de "confirmação orgânica em produção" via push após mudanças em `src/**` (usado em sessões passadas — ver item 15 acima) deixa de existir; confirmar mudanças futuras em produção exige `workflow_dispatch` manual ou esperar a próxima janela agendada (até 24h). `README.md` linha 52 ainda descreve esse gatilho como "teste real automático" — desatualizado, registrado como pendência de escopo separado no `PLANO-ATIVO.md`.

## 17. Etapa 4.1 multi-usuário — estrutura de decisão pessoal por perna, criada e verificada, 01/08/2026

**Contexto:** Etapa 4 da iniciativa multi-usuário (`PLANO-ATIVO.md`), quebrada em três degraus para não virar uma virada única de risco alto. A 4.1 é o primeiro: **criar a estrutura nova e copiar os dados, sem que nada passe a lê-la.** Nada em `src/` ou `docs/` foi tocado — ao fim da 4.1 o sistema se comporta exatamente como antes. Implementada como dois arquivos em `sql/`, rodados manualmente no SQL Editor do Supabase (mesmo fluxo de `system_config.sql`).

**O que foi criado:**

- **`weekend_leg_user_state`** — teto/status/notas/valor pago por (perna × usuário), com RLS per-user e `user_id` com `default auth.uid()`.
- **`settings.weekend_default_ceiling`** — coluna nova, teto padrão do usuário, criada com **250** (o valor real em uso em produção, não os 200 do texto desatualizado do `CLAUDE.md`).
- **`weekend_leg_ceiling_audit`** — auditoria append-only de mudança de teto, alimentada por **trigger no banco**. Por ser trigger e não código de aplicação, captura inclusive edição feita direto no SQL Editor.
- **`weekend_leg_effective`** — view com `security_invoker = true`, que resolve o teto efetivo de cada perna para cada usuário.

**Modelo preguiçoso:** não existe uma linha de `weekend_leg_user_state` por perna por usuário. A linha só nasce quando o usuário decide algo sobre aquela perna; enquanto não decide, a view resolve o teto pelo padrão do usuário (`settings.weekend_default_ceiling`). Evita 132 linhas × N usuários de dado vazio e faz "mudar meu teto padrão" ser uma escrita só.

**Cópia dos dados:** 5 linhas de estado (as 5 pernas com `paid_price` preenchido) + 1 marco inicial de auditoria (`origin = 'migracao'`, null → 250). Nenhum teto foi copiado — o guarda 1c do script exige todas as 132 pernas em 250 no momento de rodar, então não havia teto próprio a preservar.

**Verificação (blocos A–G, [sql/etapa4_1_verificacao.sql](sql/etapa4_1_verificacao.sql), tabelas completas em `AUDITORIA-MULTIUSUARIO.md`):** A/B/C saíram **idênticos** antes e depois — contagens de `weekend_legs` intactas, as mesmas duas policies com texto idêntico, nenhuma trigger em `weekend_legs`; é a prova de que o mundo antigo não mudou. D confirmou o modelo preguiçoso (132 pernas resolvendo 250 pelo padrão, zero tetos próprios, 5 linhas de estado). E (uuid falso) devolveu 0/0/0 — sem vazamento entre usuários. F (uuid real, como usuário logado) devolveu 132/5/1 com `resolvido_250 = 132` e `com_pago = 5`. G confirmou o carimbo de origem correto nas quatro personas (`sql_editor` / `app` com `auth_uid` preservado / `robo` / override `migracao`).

**A correção pega na revisão.** A primeira versão derivava a origem da escrita de `current_user`. A revisão apontou que isso estaria errado dentro de uma função `SECURITY DEFINER`, onde `current_user` é sempre o dono da função. A correção (derivar de `request.jwt.claims`) foi **confirmada num Postgres 16.14 descartável antes de subir** — a sonda mostrou `current_user = 'postgres'` nas três personas, o que carimbaria toda escrita do robô e do painel como `sql_editor`. O bloco G reconfirmou o mesmo comportamento no Postgres 17.6 de produção. A checagem no banco descartável também cobriu idempotência (duas execuções sem duplicar), RLS de escrita, disparo seletivo da trigger (nota não gera linha, teto gera) e isolamento com duas contas reais.

**Limites conhecidos** (registrados no `PLANO-ATIVO.md`, não são pendência): a auditoria nasce com um marco, não com histórico retroativo; o append-only vale para a API, não para quem entra como `postgres` no SQL Editor; a view não tem filtro próprio de propósito (com `user_id = auth.uid()` embutido, o robô — que roda como `service_role`, com `auth.uid()` nulo — veria zero linhas); e as 5 pernas com `paid_price` e `status = 'monitoring'` foram copiadas como estão, sem normalizar a anomalia.

**Estado do código:** commit `be81384` (`sql/etapa4_1_estado_por_usuario.sql` + `sql/etapa4_1_verificacao.sql`) — pushado para `origin/main` em 02/08/2026, junto com `6e195c4` e o commit de sincronização de documentação (`51a55ce`). Duas coisas distintas, que nunca foram a mesma: a **estrutura** existe no banco de produção desde 01/08/2026, porque o script foi rodado à mão no SQL Editor, não pelo repositório; os **arquivos `sql/`** existem no repositório (e no GitHub) desde o push de 02/08/2026.

---

## 18. Etapa 4.3, Passo 3 — remoção das colunas antigas de `weekend_legs`, 06/08/2026

**Contexto:** Etapa 4.3 da iniciativa multi-usuário (`PLANO-ATIVO.md`), o terceiro degrau — remover as 5 colunas do mundo pré-multi-usuário (`price_ceiling`, `status`, `notes`, `paid_price`, `purchased_at`) de `weekend_legs`, já que a decisão por perna × usuário vive em `weekend_leg_user_state` desde a 4.1 e painel e robô leem tudo por `weekend_leg_effective` desde a 4.2. As colunas antigas só continuavam de pé como fotografia congelada. Diagnóstico fechado no chat de planejamento em 06/08/2026: nenhuma view, policy de RLS ou função de banco dependia delas; zero divergência de dado nas 132 pernas; o único caminho de código que ainda as lia (ramo degradado de `get_active_legs`) foi corrigido antes deste passo (Passo 1, commit `d5f97eb`).

**Script:** [sql/etapa4_3_drop_colunas_legadas.sql](sql/etapa4_3_drop_colunas_legadas.sql), desenhado e revisado em várias rodadas no chat de planejamento paralelo — Bloco 0 (inventário de definição das 5 colunas, só leitura), Parte A (backup em `weekend_legs_legacy_columns_backup`, com RLS ligada e zero policies), Parte B (guardas G0–G4 + `DROP` das 5 colunas), e uma receita de restauração completa em comentário.

**Inventário do Bloco 0** (rodado em produção antes do backup): os 5 tipos batiam exatamente com o `create table` da Parte A — `price_ceiling numeric not null default 200`, `status text not null default 'monitoring'::text`, `notes text`, `paid_price numeric`, `purchased_at timestamptz` — e zero constraint (check/FK/unique/exclusion) ou índice citava qualquer uma das 5 colunas. Achado registrado: o `default 200` de `price_ceiling` sempre bateu com o que o `CLAUDE.md` descrevia antes da correção da pendência 8 da Etapa 4.2 — não era documentação desatualizada, era o default do DDL coexistindo com o valor efetivo dos dados (`250`, depois `300`), dois fatos diferentes.

**Execução real (Parte B, SQL Editor de produção):** guardas G0–G4 passaram sem erro. `select` final: `colunas_legadas_restantes = 0`, `linhas_no_backup = 132`. As 5 colunas não existem mais em `weekend_legs`; o backup `weekend_legs_legacy_columns_backup` é **permanente** e contém as 132 linhas originais, com a receita de restauração completa (tipos e defaults reais, não mais marcadores) no próprio script, caso seja necessário reverter.

**Passos seguintes da Etapa 4.3** (Passo 2 desacoplado do `DROP` — vira pendência de fechamento de registro, não bloqueante; Passo 4 — notas de cabeçalho nos scripts `sql/` afetados e aposentadoria do Bloco A de `sql/etapa4_1_verificacao.sql`; Passo 5 — bloco de verificação pós-`DROP`) não iniciados, dependem de revisão explícita no chat de planejamento antes de começar. Detalhe completo em `PLANO-ATIVO.md`, seção "Etapa 4.3".

## 19. Etapa 4.3, Passos 4 e 5 — notas de cabeçalho e verificação independente pós-`DROP`: fechamento da etapa, 07/08/2026

**Contexto:** com as 5 colunas legadas de `weekend_legs` (`price_ceiling`, `status`, `notes`, `paid_price`, `purchased_at`) já removidas em produção pelo Passo 3 (item 18 acima, commit `ce0d8b3`), restavam dois passos da Etapa 4.3: carimbar os scripts `sql/` que ainda descrevem esse mundo removido (Passo 4) e confirmar, com colheita independente do próprio script que fez o `DROP`, que nada além do pretendido foi alterado (Passo 5). Precedente do projeto para essa exigência de segundo olhar: `AUDITORIA-MULTIUSUARIO.md`, "Etapa 4.1 — baseline antes/depois" (01/08/2026) — "mexer nas policies e colunas dessa tabela é a Etapa 4.3/5, não esta".

**Passo 4 — notas de cabeçalho (commit `4b02093`):** os 7 scripts `sql/` que citam alguma das 5 colunas foram carimbados com notas de estado datadas (`HISTORICO` — não re-rodar — ou `PERIGO` — não dá erro, recria coluna vazia em silêncio). Fechamento da lista fina: o `grep` de 06/08/2026 tinha apontado 7 arquivos, mas a lista final ficou diferente — `alvo_fins_de_semana.sql` **saiu** (falso positivo: as colunas citadas ali são de `weekend_targets`, tabela já dropada por `pernas_desacopladas.sql` em 23/07/2026, não de `weekend_legs`; ganhou nota própria por risco separado, fora do escopo da 4.3) e `sql/etapa4_3_drop_colunas_legadas.sql` **entrou** (único script que já tinha rodado contra produção sem carimbar isso). Fechou em 7 arquivos em escopo: os 6 que tocam as colunas removidas (`etapa4_1_estado_por_usuario.sql`, `etapa4_1_verificacao.sql`, `etapa4_2_resync.sql`, `notas_pernas.sql`, `parte8_preco_pago.sql`, `pernas_desacopladas.sql`) + o próprio script do `DROP`. Achado reforçado: `notas_pernas.sql` e `parte8_preco_pago.sql` são armadilha ativa — `alter table ... add column` sem `if not exists` e sem guarda, recriam a coluna vazia sem dar erro se re-rodados. Em `sql/etapa4_1_verificacao.sql`, só o Bloco A foi aposentado (comentado em bloco `/* */`, preservado como registro histórico) — Blocos B, C, D, E, F, F2, G e H continuam válidos e rodáveis, com E/F/F2 seguindo como a prova de produção de isolamento entre usuários e de RLS de escrita (05/08/2026, commit `f50e55a`).

**Passo 5 — verificação pós-`DROP` independente:** script [sql/etapa4_3_verificacao_pos_drop.sql](sql/etapa4_3_verificacao_pos_drop.sql), com 6 blocos (A, B, C, D1, D2, E), todos `select`, desenhados para **não reaproveitar** nenhuma das guardas G0–G4 do script do Passo 3 — colheita genuinamente independente. Rodado manualmente no SQL Editor de produção em 07/08/2026, um bloco por vez. **Resultado real: zero divergência em todos os 6 blocos.**

- **Bloco A** (colunas ausentes): `controle_tabela = 1`, `controle_sobreviventes = 5`, `legadas_presentes = 0`, `legadas_quais = (nenhuma)`, `total_colunas_hoje = 13`.
- **Bloco B** (policies vs. baseline de 01/08/2026): as 2 policies esperadas, texto idêntico, vereditos = `OK`.
- **Bloco C** (triggers): zero linhas.
- **Bloco D1** (estrutura nova, cardinalidade): `estado_linhas = 5`, `auditoria_linhas = 12`, `view_linhas = 132`, `view_esperado = 132`, `pernas = 132`, `usuarios = 1`.
- **Bloco D2** (prova via `pg_depend` de que `weekend_leg_effective` não depende de nenhuma das 5 colunas removidas): 10 linhas, `e_coluna_legada = false` em todas.
- **Bloco E** (backup permanente íntegro): `linhas_backup = 132`, `linhas_weekend_legs = 132`, `colunas_backup = 7`, `capturas_distintas = 1`, `capturado_em = 2026-08-07 01:56:43.499924+00` (06/08/2026 22:56 BRT), `ids_orfaos = 0`, `pernas_sem_backup = 0`, `rls_ligada = true`, `policies_no_backup = 0`.

**Fechamento:** com os Passos 1, 3, 4 e 5 concluídos e verificados, a **Etapa 4.3 está encerrada**. As 5 colunas legadas de `weekend_legs` não existem mais em produção, a estrutura nova (`weekend_leg_user_state`, `weekend_leg_ceiling_audit`, `weekend_leg_effective`) segue intacta e confirmada por colheita independente, o backup permanente está íntegro e mapeando 1:1 com as pernas vivas, e os scripts `sql/` obsoletos estão carimbados contra re-execução acidental. Segue em aberto só o Passo 2 — pendência paralela e não bloqueante de trazer o resultado real do resumo semanal do Telegram a partir de segunda-feira 10/08/2026 — que não é uma correção estrutural pendente, é registro de observação. Detalhe completo em `PLANO-ATIVO.md`, seção "Etapa 4.3".

## 20. Lado de leitura da RLS de `weekend_legs`/`weekends` fechado, 08/08/2026

**Contexto:** pendência registrada em `STATE.md` desde 31/07/2026 (junto com o pedido recusado de antecipar a Etapa 7): `weekend_legs`/`weekends` tinham — e no lado de leitura continuam tendo — policy `auth.uid() is not null`, sem filtro por usuário. Diferente do lado de escrita (fechado pela Etapa 4.4, 07/08/2026, por não ter consumidor legítimo restante), o lado de leitura exigia decisão de produto antes de decisão técnica: os dois usuários compram a mesma rota RIO↔BSB, então dado objetivo de voo poderia ser intencionalmente compartilhado.

**Decisão** tomada no chat de planejamento (08/08/2026): sim, compartilhado — preço atual, companhia, horário do voo encontrado pelo robô, menor preço visto e o calendário dos fins de semana são dado de mercado, não decisão pessoal; o que é pessoal (teto, status de compra, valor pago, notas — inclusive localizador e horário do voo efetivamente comprado) já vive isolado em `weekend_leg_user_state` desde a Etapa 4.1.

**Verificação:** confirmado por diagnóstico só-leitura em duas partes (inventário de catálogo de RLS + personificação de usuário fictício via `set local role authenticated`, transação com rollback): zero divergência — nenhuma tabela de decisão pessoal legível por outro usuário, tabelas de mercado visíveis como esperado.

**Fechamento:** fecha a pendência de RLS "genérica" nos dois lados; deixa de ser bloqueio da Etapa 7, que segue bloqueada pelas Etapas 5 e 6. Detalhe completo em `PLANO-ATIVO.md`, seção "Etapa 4.4".

## 21. Fatia A — tema escuro por padrão + paleta em variáveis CSS (08/08/2026)

**Contexto:** recorte puramente visual de um handoff maior de UI (multi-usuário, "camada de dois usuários") que **não está aprovado**. Só esta fatia (cor/tema) foi implementada; o resto do handoff — rótulos SÓ SEU/DOS DOIS, camada de visibilidade cruzada entre usuários (Fatia C), separação pessoal×global em Configurações (Fatia B) — segue fora de escopo, nenhum implementado, registrado aqui para não se perder e aguardando decisões próprias em revisão futura.

**O que foi feito:** as 25 variáveis já existentes em `:root` de `docs/css/style.css` ganharam um bloco `:root[data-theme="dark"]` com valores de tema escuro (nomes preservados, não renomeados). 6 variáveis novas criadas para literais de cor que não tinham token (`--field-empty-bg`, `--field-filled-border`, `--primary-tint-bg`, `--outline-border`, `--danger-hover`, `--primary-rgb`) + 3 variáveis de sombra (`--shadow-1`/`--shadow-2`/`--shadow-3`). Alternância via atributo `data-theme` em `<html>`, persistida só em `localStorage` (chave `flyiop-theme`, escuro é o padrão quando não há preferência salva). Script inline anti-flash no `<head>` das 4 páginas HTML, rodando antes da primeira pintura. Botão de alternância só em `index.html`/`compras.html`/`config.html` (nav compartilhado); `login.html` não tem botão, só herda o tema salvo. Novo módulo `docs/js/theme.js`.

**Exceção pontual de escopo:** `docs/js/dashboard.js`, linhas do Chart.js (cor hardcoded do gráfico de rota legada), foi tocado para ler a cor via CSS var e recolorir ao vivo na troca de tema, sem re-consultar o Supabase — único ponto de JS fora de CSS nesta fatia, aprovado explicitamente no chat de planejamento.

**Correção durante a implementação:** 2 dos literais `#fff` catalogados como "texto sobre cor sólida" eram na verdade fundos (`input`/`select` e `.btn-outline-full`) — se deixados como `#fff` literal, ficariam brancos sobre fundo escuro. Corrigidos para `var(--card)`. Identificado e sinalizado pelo Claude Code durante a implementação, não presumido.

**Verificação:** testado localmente (servidor estático local) com dados reais de uma sessão Supabase ativa + harness sintético para estados sem cobertura nos dados reais atuais (perna comprada, card colapsado, trend warn/info, badges feriado+alta-temporada simultâneos). Estado âmbar de edição não salva confirmado com dado real. Recoloração ao vivo do gráfico Chart.js confirmada sem nova chamada de rede. Usuário confirmou teste manual completo no navegador local antes do push, incluindo o roteiro de 6 pontos (flash ao recarregar, clique físico no botão, âmbar, persistência entre páginas, gráfico, botão outline).

**Publicado:** commit `809eb2d`, enviado a `origin/main` em 08/08/2026, junto com os 2 commits anteriores desta mesma sessão (nota de documentação sobre visibilidade cruzada de compra/táxi, e troca de `favicon.png`/`apple-touch-icon.png`).

## 22. Fatia B — separação pessoal × sistema na UI (08/08/2026)

**Contexto:** segunda fatia do handoff de UI multi-usuário, depois da Fatia A (item 21). O painel misturava, sem nenhuma pista visual, dado que é decisão pessoal do usuário logado (progresso, orçamento, tetos, rotas flexíveis) com dado do sistema, igual para todo mundo (saúde do robô, feriados). Com o segundo usuário chegando na Etapa 7, essa ambiguidade vira erro de leitura real ("esse número é meu ou é dele?"). A Fatia C (visibilidade cruzada entre usuários) **continua fora de escopo, não implementada**.

**O que foi feito.** (1) Dashboard: etiqueta de escopo por bloco — `SÓ SEU` em Ação do dia, Progresso, Melhores oportunidades, Orçamento e Rotas flexíveis (legado); `DO SISTEMA` em Saúde do sistema e Feriados/alta temporada; Urgência ficou sem etiqueta, de propósito. Implementada como mapa `BLOCK_SCOPE` + um passe único `tagBlockScopes()` ao fim de `initPage`, em vez de colar a etiqueta nos 11 pontos de `section.innerHTML` (várias funções de render têm ramo com dado e ramo vazio; colar em cada um garantiria que todo ramo novo nascesse sem etiqueta). A função é idempotente por guarda explícita. (2) Configurações: a tabela de rotas e os 6 campos de alerta legado (`window_3d_pct`, `window_7d_pct`, `notification_mode`, `freshness_hours`, `stale_alert_policy`, `cost_per_thousand_brl`) viraram uma seção única que só existe para quem tem rota própria. (3) CSS: duas classes novas (`.badge.scope-own`, `.badge.scope-system`) compostas com a `.badge` já existente — **nenhum token de cor novo**, reaproveitando `--info-bg`/`--primary` e `--neutral-bg`/`--muted`, que a Fatia A já definiu nos dois temas.

**Gate com regra deliberadamente diferente por tela.** Em Configurações conta **todas** as rotas (ativas + arquivadas): lá existem a aba "Arquivadas" e o botão "Reativar", e contar só as ativas trancaria o caminho de volta — quem arquivasse tudo perderia a seção e, junto com ela, a única forma de reativar. No Dashboard conta **só as ativas**: não há aba nem reativar, não há caminho a preservar, e contar arquivadas devolveria justamente o card vazio que a fatia elimina. O form "Adicionar rota" ficou **fora** do gate, sempre visível — é o único caminho de sair de 0 rotas para 1 pela UI.

**Estado inicial e caminho de erro.** O markup das duas telas nasce `hidden` (atributo no HTML), e não escondido por JS depois do carregamento: sem isso, o usuário sem rota veria a seção aparecer e sumir a cada load. A seção só é revelada quando a consulta a `routes` volta **com sucesso e com 1+ linhas**. Se a consulta **falhar**, a seção é revelada e o erro aparece na tela via `alert()` — mesmo padrão já usado em `initPage` (fins de semana/pernas) e em `config.js` (`loadRoutes`) — porque uma falha virando seção escondida em silêncio seria lida como "minhas rotas sumiram".

**Consequência aceita (export CSV).** O botão "Exportar CSV" vive dentro do `<details id="rotas-legado">` (`docs/index.html`). Com o gate do Dashboard contando só rotas ativas, **um usuário com 0 rotas ativas e N arquivadas perde o caminho de export na UI** — e perde algo real, porque `exportCsv` consulta `price_history` sem filtro de rota, ou seja, o CSV inclui também o histórico das rotas arquivadas (rotuladas pelo UUID, já que o mapa de rótulos só tem as ativas). Aceito conscientemente para não reabrir `docs/index.html` nesta fatia; ninguém está nessa situação hoje (o único usuário tem 3 rotas ativas). **Reversível**: basta mover o `<p class="subtitle">` para fora do `<details>` se um dia doer.

**Consulta a menos, não a mais.** `config.js` deixou de filtrar `archived` no servidor e passou a filtrar por aba no cliente, guardando a última leitura em memória — trocar de aba deixou de fazer ida à rede (confirmado: 1 requisição a `/routes` antes e depois de alternar). `dashboard.js` **não teve nenhuma query alterada** e `exportCsv` não foi tocado, então o conteúdo do CSV é bit a bit o mesmo de antes.

**Achado durante a verificação.** O gate do Dashboard, na primeira escrita, só fazia `return` no ramo de zero rotas, confiando no `hidden` do markup — o que revela, mas nunca **re-esconde** um bloco já revelado. Inalcançável em produção (a função roda uma vez por carregamento), mas inconsistente com a regra "só é revelada quando a consulta volta com 1+ linhas" e divergente do `config.js`, que já atribuía nos dois sentidos. Corrigido para atribuição explícita (`details.hidden = !routes || routes.length === 0`) antes do fim da implementação. Encontrado porque a verificação executou o módulo duas vezes no mesmo documento, não porque estivesse quebrado na tela.

**Verificação.** Servidor estático local (`.claude/launch.json`, alvo `flyiop-static`) com sessão real do Supabase. Conferido: as 7 etiquetas nos blocos certos (6 em `<h2>`, 1 no `<summary>`), Urgência sem etiqueta, cores resolvendo nos dois temas (claro `#2563eb`/`#dbeafe` e `#6b7280`/`#f1f5f9`; escuro `#5b8cff`/`rgba(91,140,255,.14)` e `#949ba7`/`#1e222a`); ausência de flash confirmada no HTML servido (`hidden` presente antes da primeira pintura nas duas telas); mobile 375px sem overflow horizontal e etiqueta sempre na mesma linha do título; troca de aba sem nova requisição; ramo de zero rotas e caminho de erro exercitados **com `fetch` interceptado no navegador, sem tocar no banco** (nenhum PATCH chegou ao Supabase; as 3 rotas seguem intactas); idempotência de `tagBlockScopes()` provada no `<summary>`, único nó que sobrevive a uma segunda execução do módulo — 1 etiqueta depois de 3 execuções. Console sem erros nas duas telas.

**Registro de apoio:** o diagnóstico de RLS de `routes`/`settings` que sustenta "o JS não precisa filtrar por usuário" foi rodado manualmente no SQL Editor de produção em 08/08/2026 e está em `AUDITORIA-MULTIUSUARIO.md`, seção "Diagnóstico de RLS de `routes`/`settings`" — oito campos, zero divergência. Ele fecha a linha "não rastreada" que `routes` ocupava na tabela da seção 2 daquele arquivo.

**Publicado:** commit `b44a353`, enviado a `origin/main` em 08/08/2026.

---

## 23. Fatia C — visibilidade de compra entre usuários (desenhada 09/08/2026, Parte 1/banco 10/08/2026, Parte 2/frontend 11/08/2026)

Terceira fatia do handoff de UI multi-usuário (depois da Fatia A, item 21, e da Fatia B, item 22) — a única das três que toca o banco, não só a UI. Motivo adicional registrado em 08/08/2026: além de sincronia geral entre os dois usuários, serve para logística de táxi.

**Regra de produto (aprovada no chat de planejamento):** o outro usuário vê QUE você comprou uma perna e EM QUAL VOO. Nunca quanto você pagou, qual seu teto, nem seu localizador. Visibilidade só depois de `status = 'purchased'` — nunca antes (a alternativa de expor antes da compra foi descartada em 08/08/2026).

**Mecanismo escolhido: tabela de projeção mantida por trigger.** `weekend_leg_purchase_shared`, alimentada por uma trigger `security definer` em `weekend_leg_user_state`, contendo só os 3 campos de voo (companhia, aeroporto, horário) + chave + timestamps — nenhum campo sensível (teto, valor pago, notas) chega a existir nessa tabela. Princípio: a garantia é **estrutural** (o dado sensível não está lá), não depende de um `WHERE` correto numa view ou função.

**Duas alternativas avaliadas e descartadas**, e por quê:
- **View com `security_invoker = off`** — daria à view acesso irrestrito às tabelas de baixo, ignorando a RLS de `weekend_leg_user_state`; um `WHERE` errado (ou um `select *` futuro) vazaria teto/pago/notas do outro usuário. Bypass de RLS.
- **Função RPC `security definer`** — mesmo problema: a função rodaria com o privilégio de quem a criou, não de quem chama, e teria que reimplementar à mão exatamente o filtro que a RLS já faz de graça. Bypass de RLS.

Ambas descartadas pelo mesmo motivo de fundo, achado no diagnóstico desta fatia (08/08/2026): **todo objeto novo em `public` neste projeto nasce com os 7 privilégios para `anon` e `authenticated`** — o Supabase aplica `alter default privileges grant all` no schema `public`. Isso já tinha corrigido a leitura do "Achado lateral" da Etapa 4.4 (item 20 acima): grant da view nunca foi só `SELECT` por padrão; era só `SELECT` funcional porque a view não é atualizável, não porque o grant fosse restrito. Numa tabela de projeção, sem esse achado, o `revoke all` explícito não seria óbvio — e sem ele, `anon` teria os 7 privilégios sobre um objeto pensado para ser só-leitura de dado compartilhado.

**Parte 1 (banco) — CONCLUÍDA e verificada em produção (10/08/2026).** [sql/fatia_c_visibilidade_compra.sql](sql/fatia_c_visibilidade_compra.sql): 3 colunas de snapshot em `weekend_leg_user_state` (`purchased_airline`, `purchased_airport`, `purchased_departure_time` — fotografia do voo comprado, independente das colunas `current_*` que o robô reescreve); tabela `weekend_leg_purchase_shared` (chave `leg_id`+`user_id`, FKs `on delete cascade`); trigger `flyiop_sync_purchase_shared` (grava/atualiza a projeção quando `status = 'purchased'`, remove em qualquer outro status ou `DELETE` — o botão "desfazer" do painel limpa a projeção sozinho); RLS ligada, `revoke all` explícito de `anon`/`authenticated` antes de qualquer grant, `grant select` só para `authenticated`, uma única policy de `SELECT` (`auth.uid() is not null`), nenhuma policy de escrita (só a trigger grava); backfill idempotente a partir do que já está `purchased` hoje (0 linhas). Guarda de inventário no início, 4 blocos de verificação no fim (estrutura, grants/policies, prova de comportamento com rollback, prova de isolamento com rollback).

**Resultado real, rodado manualmente no SQL Editor de produção em 10/08/2026:**

| bloco | resultado |
|---|---|
| G0 (inventário) | `colunas_snapshot_hoje = 0`, `projecao_existe_hoje = false`, `compradas_hoje = 0`, `linhas_estado_hoje = 5`, `pernas_hoje = 132`, `triggers_wlus_hoje = trg_audit_leg_ceiling,trg_wlus_touch` — bate 100% com o esperado |
| V1 (estrutura) | `colunas_snapshot = 3`, `projecao_existe = true`, `colunas_projecao = 7`, `colunas_sensiveis_na_projecao = 0`, `triggers_wlus = trg_audit_leg_ceiling,trg_sync_purchase_shared,trg_wlus_touch` — bate 100% |
| V2 (grants/policies) | `anon_privilegios = 0`, `authenticated_privilegios = 1`, `authenticated_so_select = true`, `rls_ligada = true`, `rls_forcada = false`, `policies = 1`, `policy_cmd = SELECT` — bate 100%. **Este é o bloco que prova que o achado do objeto novo em `public` nascendo com os 7 privilégios para `anon` foi neutralizado nesta tabela** — `anon` termina com zero privilégio, como desenhado |
| V3 (prova de comportamento, rollback) | `apos_compra = 1`, `voo_gravado = 'LATAM,GIG,2026-09-09 15:53:02.554533+00'`, `apos_desfazer = 0`, `apos_recomprar = 1`, `apos_delete_estado = 0` — bate 100%, os três ramos da trigger confirmados (insert-purchased, update-sai-de-purchased, delete) |
| V4 (prova de isolamento, rollback) | `uid_visto = 00000000-...-0001`, `papel_efetivo = authenticated`, `projecao_esp_1 = 1`, `estado_pessoal_esp_0 = 0`, `view_efetiva_esp_0_sem_valor_probatorio = 0`, `escrita_direta_esp_bloqueada = 'bloqueado 42501'` — bate 100%. **A asserção com valor probatório de isolamento é `estado_pessoal_esp_0`** — `view_efetiva_esp_0_sem_valor_probatorio` bateu 0 como esperado, mas esse zero não prova RLS (o UUID fictício não tem linha em `settings`, então o `cross join` de `weekend_leg_effective` já dá 0 mesmo com a RLS inteira desligada — ressalva escrita no próprio script) |

**Parte 2 (frontend) — CONCLUÍDA e verificada em produção (11/08/2026).** Planejada e implementada em sessão de Plan Mode própria (11/08/2026), revisada em rodadas sucessivas de diff antes da aprovação do usuário, commitada (`ca54dd8`) e enviada ao remoto no mesmo dia. Arquivos alterados:
- [docs/js/compras.js](docs/js/compras.js) — toda a lógica: 5 consultas independentes em `loadWeekends` (`weekends`, `weekend_leg_effective`, `weekend_legs` só com `current_airline`/`current_departure_time`, `weekend_leg_purchase_shared` filtrada com `.neq('user_id', ...)` pra excluir a própria linha, `weekend_leg_user_state` pro snapshot próprio); `USER_LABELS` hardcoded (uuid do usuário → "Você", fallback "Outro usuário"); linha `👥 ... já comprou` no card, condicional à existência de linha na projeção; painel de confirmação de compra (abre em vez de salvar direto, pré-preenche por snapshot → voo monitorado → vazio, aeroporto com toggle GIG/SDU que desmarca no segundo clique, validação de hora-sem-data); bloco de edição pós-compra (4 campos, 1 botão Salvar só, não recarrega a página — snapshot em memória atualizado manualmente no sucesso do save); helpers de assimetria de fuso (ver abaixo).
- [docs/css/style.css](docs/css/style.css) — classes novas pro painel de confirmação, bloco de edição de voo e linha do outro usuário, todas reaproveitando variáveis de cor já existentes (nenhuma nova); as 11 variáveis usadas foram conferidas uma a uma nos dois temas (claro e escuro) antes do commit.
- `docs/compras.html` — **não tocado.** Os cards são montados 100% em JS.
- Banco, RLS, trigger, `weekend_leg_effective`, `dashboard.js`, `config.html`, Telegram — nenhum tocado, como o escopo previa.

**Achado que mudou o desenho, documentado em comentário no próprio código:** `current_departure_time` (gravado pelo robô a partir da `fli`) é datetime NAIVE rotulado como UTC pelo Postgres — ler cru (`HH:MM`/data sem conversão de fuso) é o comportamento CORRETO, não bug a corrigir depois. Já `purchased_departure_time` (gravado por esta fatia) tem offset `-03:00` real e É convertido para `America/Sao_Paulo` na leitura. As duas funções fazem o oposto uma da outra de propósito.

**Roteiro de verificação manual — ✅ CONCLUÍDO em produção (11/08/2026), todos os itens abaixo passaram, sem erro no console, sem regressão visível:**
- ✅ Perna não comprada: "Marcar como comprada" abre o painel pré-preenchido pelo voo monitorado, hora batendo com o Google Flights (confirma o achado de fuso). Cancelar não salva nada.
- ✅ Confirmar com tudo em branco: marca como comprada mesmo assim.
- ✅ Confirmar com hora preenchida e data vazia: avisa e não salva.
- ✅ Perna comprada: bloco de edição de voo salva os 4 campos num clique só; a data/hora volta correta ao recarregar (round-trip `-03:00` → `America/Sao_Paulo` confirmado).
- ✅ Desfazer e marcar de novo: o painel volta pré-preenchido com o que tinha sido salvo antes (snapshot preservado através do desfazer).
- Linha `👥 ... já comprou` do outro usuário: comportamento de ausência confirmado (nenhuma linha aparece em nenhum card, como esperado com um usuário só) — **a verificação positiva (linha aparecendo de fato) só é possível na Etapa 7, quando a segunda conta existir.** Não é uma pendência desta fatia, é um limite estrutural do que dá para testar hoje.

**Telegram** — fica para a Etapa 6, fora do escopo desta fatia.

**Nada tocado nesta fatia:** `weekend_leg_effective`, `weekend_legs`, `settings`, as policies existentes de `weekend_leg_user_state`, `flyiop_audit_leg_ceiling`, `flyiop_touch_updated_at`, `docs/` (fora dos 2 arquivos citados), `src/`.

**Fechamento:** Parte 1 concluída e verificada em produção (10/08/2026); Parte 2 concluída e verificada em produção (11/08/2026), roteiro de verificação manual 100% passado. **Fatia C inteira concluída (11/08/2026)** — resta só, fora do escopo desta fatia, a verificação positiva da linha do outro usuário, que depende da Etapa 7 (segunda conta), e o Telegram, que fica para a Etapa 6.

---

## 24. Etapa 0 — Validação da grade de calendário (fli), 24/08/2026

**Motivação:** receio real do usuário sobre uma limitação estrutural do sistema. `LIVE_CHECK_WINDOW_DAYS = 183` (`src/live_check.py`) cobre só ~6 meses a partir de "hoje", sempre — deslizando com o tempo, mas nunca mais que isso. A maior parte do horizonte de compra real (fins de semana até 03/12/2027) fica fora dessa janela e recebe cobertura só do Travelpayouts, que erra ~98% por desenho (cache secundário desde a Parte 2, `HISTORICO.md` item 5). Hipótese a testar: `fli.search.dates.SearchDates` — endpoint de calendário do Google Flights (`GetCalendarGraph`), já dentro da mesma lib pinada usada em produção — poderia varrer preço por data em lote, em vez de 1 consulta por perna, ampliando a cobertura real sem trocar de fonte.

**Desenho da validação:** sessão de Plan Mode dedicada, com regra explícita de não tocar produção. Script de diagnóstico isolado em `scripts/etapa0_validacao/` (`grade_calendario.py`, `custo_projetado.py`), fora de `src/`; workflow `.github/workflows/etapa0-validacao.yml` só com `workflow_dispatch` (sem `schedule`/`push`), sem nenhum secret do Supabase — o job não tem acesso a escrita nem leitura no banco. Nenhuma escrita em `alert_log`/`weekend_leg_price_history`, nenhuma mensagem no Telegram. Passou por 4 rodadas de correção no chat de planejamento antes da execução real, cada uma com o diff completo revisado e aprovado pelo usuário antes do commit — ver `PROTOCOLO-DE-TRABALHO.md` para o padrão de revisão. Commitado em `9f82096` (24/08/2026), publicado em `origin/main`, e rodado via `workflow_dispatch` manual pelo usuário em **24/08/2026, 21:08 BRT**, contra o mesmo commit pinado de `fli` já em produção (`requirements.txt`).

**Resultados confirmados (rodada real em produção, não simulação nem cálculo isolado):**

1. **Paridade de preço confirmada.** `SearchDates` devolveu o MESMO preço que `SearchFlights` (fonte atual de produção) em 3 checkpoints por rota — perto (dentro dos 183 dias), longe (além dos 183 dias) e perto do teto de 305 dias (item 3 abaixo) — 6 comparações, diferença de 0,0% em todas, incluindo o checkpoint a 292 dias de distância. A grade de calendário não é uma fonte alternativa com risco de divergência — é o mesmo dado, agregado.
2. **Custo medido.** 1 bloco de 61 dias = 1 requisição HTTP real, devolvendo até 61 datas com preço numa passada só. Cobrir a janela útil real (item 3) exige 5 blocos por direção; com 4 direções (GIG→BSB, SDU→BSB, BSB→GIG, BSB→SDU — produção usa GIG com fallback SDU, `src/live_check.py`), 1 varredura completa = ~20 requisições. Rodando 4x/dia = ~80 requisições/dia, contra ~20/dia do lote atual — mas cobrindo o horizonte inteiro disponível a cada passada, não pernas rotativas escolhidas por `last_live_check_at`.
3. **Teto real de 305 dias — achado novo, não estava nas hipóteses originais.** A própria lib documenta, e o teste confirmou empiricamente contra produção, que `SearchDates` não busca além de hoje+305 dias — degrada para lista vazia, não lança erro. Isso significa que a grade de calendário NÃO cobre o horizonte inteiro do projeto (set/2026–dez/2027, ~487 dias): cobre só até ~jun/2027 a partir de qualquer "hoje". **Não é um buraco de cobertura corrigível** — são datas que as companhias aéreas ainda não abriram para venda em lugar nenhum (nem Google, nem Skyscanner, nem qualquer scraper pago); a cobertura se completa sozinha conforme o tempo passa e a janela de venda de cada companhia abre.
4. **Paralelismo confirmado como evitável, não como limitação estrutural.** Lendo `fli/search/dates.py` diretamente: `SearchDates.search` só aciona `ThreadPoolExecutor`/`parallel_map` quando o INTERVALO PEDIDO passa de `MAX_DAYS_PER_SEARCH = 61` dias numa única chamada. Fatiando manualmente em blocos <=61 dias e chamando em sequência — mesmo padrão de espaçamento ~2,5s já usado em `src/live_check.py` — não há paralelismo algum, compatível com a regra imutável do projeto ("sequencial, sem paralelismo", `CLAUDE.md`).
5. **Round-trip funciona.** Testado GIG<->BSB, setembro/2026, duração fixa de 2 dias — 30 pares (ida, volta) retornados corretamente pela `SearchDates`. Achado extra, confirmação cruzada entre os dois endpoints da `fli`: o par ida=04/09 volta=06/09 devolveu R$1.872, que bate exatamente com a soma dos dois preços one-way testados no item de paridade (R$1.406 + R$466).
6. **Bug real na versão pinada da `fli` (não é bug do projeto) — `Airport.RIA`.** `Airport.RIA` e `Airport.AJU` (Aracaju, cidade diferente) compartilham o mesmo valor descritivo ("Santa Maria Airport") na tabela de aeroportos da lib — o Python `Enum` trata isso como o MESMO membro, com `AJU` como nome canônico (o primeiro definido). Qualquer `getattr(Airport, "RIA")` na prática consulta Aracaju, silenciosamente, sem erro. Verificado independentemente que GIG, SDU, BSB, POA, CGH, GRU, CNF, FLN e IGU não têm esse problema — é isolado a RIA. **Conclusão: RIA (Santa Maria/RS) não é utilizável com esta versão pinada da `fli`** sem corrigir o alias antes (patch local, reportar upstream, ou aceitar não ter cobertura de RIA por ora). O script de diagnóstico detecta e reporta isso em vez de rodar a consulta com o alias errado — não afeta as 3 rotas flexíveis em produção (RIA→BSB já não tinha cobertura desde a Etapa 0 do fast-flights, 18/07/2026, item 1 acima, por motivo então não diagnosticado).
7. **`price_insights` não existe** nessa versão pinada da `fli` — confirmado por grep estático em `fli.models` e `fli.search`, sem nenhum campo equivalente. Não vale a pena tentar simular isso a partir de `SearchDates` sem uma amostra estatística própria.

**Decisão de arquitetura resultante — dois níveis, registrada como decisão, não só achado:**
- **RADAR** (grade de calendário, `SearchDates`, alta frequência, barato) varre o horizonte inteiro disponível (~305 dias) várias vezes ao dia, fatiado manualmente em blocos <=61 dias, sequencial e espaçado.
- **PRECISÃO** (`SearchFlights`, o método atual) roda só nas datas específicas que o radar apontar perto do teto de preço, para obter companhia/horário/link real que vira alerta.

Não muda o formato do que o usuário recebe (mesmo alerta, mesmo bot, mesmo site) — muda só a frequência de varredura e a extensão da cobertura real (de ~6 meses efetivos para ~10 meses efetivos a partir de qualquer "hoje").

**Consequência sobre a linha Apify Tipo B (Skyscanner via token móvel):** discutida e pré-aprovada em conversa anterior como override consciente, ainda **não implementada**. Com a `fli` sozinha entregando frequência alta e cobertura real ampliada sem custo e sem risco de evasão, a necessidade do Tipo B enfraqueceu bastante. Registrado como **reavaliação, não cancelamento definitivo** — decisão final cabe à próxima conversa de planejamento.

**Status: validação concluída, NÃO é implementação.** `scripts/etapa0_validacao/` continua no repositório como registro histórico da validação, mas não faz parte do pipeline de produção — `src/live_check.py` segue rodando exatamente como antes desta etapa. Desenhar e implementar o radar de calendário (substituindo ou complementando o lote rotativo atual — decisão que fica para a próxima conversa de planejamento) é a próxima fatia. Detalhe completo da revisão (4 rodadas de correção antes da execução real) e o fechamento formal da etapa em `PLANO-ATIVO.md`, seção "Etapa 0".

---

## 25. Falso bloqueio diário do lote `fli` — diagnóstico e correção de roteamento, 01/09/2026

**Sintoma:** desde que `radar_enabled` foi ligado em produção, toda execução mandava no Telegram o alerta "🚫 Consulta ao vivo bloqueada". 6 execuções entre 29/08 e 01/09/2026, todas iguais.

**Prova de que não era bloqueio real da fonte:** no MESMO run em que o lote reportava `BLOQUEADO` após 5 consultas sem preço, o `radar_check.py` completava 24/24 blocos sem nenhuma anomalia, e a camada de precisão — que usa `SearchFlights`, exatamente a mesma chamada do lote — trazia preço em 100% das candidatas testadas. Uma fonte bloqueada não responde a três caminhos e falha só no do meio.

**Causa raiz — roteamento, não fonte.** Cadeia completa, confirmada por leitura de código:

1. `batch_regime` (`src/live_check.py`) devolvia `'price'` — "o lote `fli` é a fonte de preço desta perna" — para toda perna com `travel_date > hoje + RADAR_COVERAGE_WINDOW_DAYS` (305 dias). Ou seja, mandava pro lote justamente as pernas **mais distantes**.
2. Mas os 305 dias são o teto real **da fonte**, não só do radar: `SearchDates` e `SearchFlights` batem no mesmo endpoint do Google e têm o mesmo limite (item 24, resultado 3 desta lista). Além dele a resposta **degrada para vazia, sem erro**.
3. Pernas em regime `'price'` ordenam **primeiro** no lote (`regime_rank = 0` em `sort_key`), então ocupavam todos os 20 slots do `batch_size` antes de qualquer perna consultável.
4. `check_live_price` devolve `None` tanto para exceção quanto para resposta vazia, e `check_and_evaluate_leg` traduz `None` em `ok=False`. Cinco `ok=False` seguidos disparam `BLOCK_STREAK_THRESHOLD`.

Aritmética sobre o seed real (`sql/alvo_fins_de_semana.sql`, 66 fins de semana / 132 pernas), medida em 01/09/2026: **87 pernas com data dentro dos 305 dias, 45 fora**. As 45 fora — mais que o dobro do `batch_size` — enchiam a fila inteira todo dia. O lote nunca alcançava uma perna que a fonte soubesse responder.

O "87 dentro" é contagem **geométrica** (quantas pernas têm `travel_date` dentro do horizonte, olhando só as datas) — não é o número que efetivamente entra no lote como `'metadata'` num dia qualquer, porque isso também depende de `last_live_check_at` (pernas checadas há menos de `RADAR_METADATA_REFRESH_DAYS` viram `None`, não `'metadata'`) e varia dia a dia conforme a rotação avança. O log real de 01/09/2026 mostrou **69** elegíveis a refresh de metadado naquele dia específico, não 87 — os dois números não divergem, medem coisas diferentes. **O que é estável e serve de critério de verificação é `45 além do alcance` (constante até as datas mais próximas entrarem na janela, ~2/semana) e a ausência de `BLOQUEADO`** — não o número de elegíveis do dia.

O nome da constante foi o vetor do erro de design: `RADAR_COVERAGE_WINDOW_DAYS` sugere "alcance do radar" (donde "fora do radar ⇒ o lote cobre"), quando o valor é o teto **da fonte** — fora dele nada cobre.

**Decisão (Opção A):** perna além de `RADAR_COVERAGE_WINDOW_DAYS` não entra em consulta ao vivo nenhuma — nem lote `fli`, nem radar — até a data entrar no alcance. Fica sem preço até lá, que já era a realidade: o dado não existe em nenhuma fonte (item 24, resultado 3: são datas que as companhias ainda não abriram para venda). `batch_regime` passou a devolver `None` nesse ramo.

**Não alterado, por decisão consciente:** a semântica do detector de bloqueio. Foi avaliado separar "vazio válido" de "erro/exceção" dentro de `check_live_price`, e **recusado**: um bloqueio real do Google chega como resposta **vazia**, não como exceção — parar de contar vazio como falha cegaria o detector exatamente para o caso que ele existe para pegar. A causa dos vazios era de roteamento, e foi eliminada na origem; depois disso todo vazio volta a ser sinal legítimo. O outro caminho que chama `check_and_evaluate_leg` (precisão do radar, `src/main.py`) já filtra candidatas para `[hoje, hoje+305]` em `select_precision_candidates`, então não há segunda porta produzindo vazio estrutural.

**Efeito colateral esperado, registrado e não corrigido aqui:** com o radar ligado, o lote `fli` passa a ser quase inteiramente refresh de metadado (`'metadata'`), e o preço fresco em `weekend_legs` passa a depender da camada de precisão do radar (7–10 pernas por run). Isso não foi causado por esta correção — ela só tornou visível que a lacuna "radar não escreve em `weekend_legs`" é o gargalo principal. Assunto de sessão própria (ver `PLANO-ATIVO.md`).

**Verificação:** suíte local `python -m unittest discover tests -v`, **319 testes, todos verdes** (315 antes desta sessão; +4 casos novos, e 2 casos existentes que codificavam o comportamento antigo foram invertidos com docstring explicando o porquê). Simulação com o universo real de 132 pernas confirma: antes, lote de 20 pernas todas em regime `'price'` e todas além do horizonte; depois, lote de 20 pernas todas em regime `'metadata'` e todas dentro do horizonte.

---

## 26. Radar de calendário — Fatia 2: preço na tela + persistência da comparação, 04/09/2026

**Motivação:** lacuna registrada em `PLANO-ATIVO.md` na correção de 01/09/2026 (item 25 acima) — o radar descobre preço em ~88 pernas por varredura (`weekend_radar_grid`), mas só as 7-10 que viram candidatas de precisão (`radar_check.select_precision_candidates`) chegavam a `weekend_legs.current_price`. A maioria das pernas na aba Compras mostrava preço de 2-3+ dias, mesmo o radar tendo passado de manhã.

**Investigação prévia (Plan Mode, mesma sessão):** confirmou por leitura de código que o caminho de alerta é *push*, não *pull* — `weekends.evaluate_and_record_leg_price` recebe o preço como argumento, nunca lê `weekend_legs.current_price`. O risco real estava em dois acoplamentos indiretos: (a) `weekend_leg_price_history`, que alimenta a média de 90 dias usada por `evaluate_good_price`/`is_suspicious_price`, e (b) `lowest_seen`/`lowest_seen_at`, um dos dois gatilhos da própria seleção de precisão (`new_low`). Gravar preço do radar em qualquer um dos dois contaminaria/autoextinguiria o caminho existente.

**Decisão de arquitetura — Desenho B, colunas separadas (não reuso de `current_price`/`current_source`):**
- `weekend_legs.radar_price` / `radar_price_at` / `radar_airport` — escritos SÓ pelo radar (`main.py`, novo bloco antes do laço de precisão), pra TODA perna dentro do alcance (~88, não só as 7-10 candidatas). Nunca lidos por nenhuma função do caminho de alerta.
- `weekend_legs.current_price_at` — coluna nova mesmo para o caminho que já existia. Corrige um bug pré-existente e independente desta fatia: o rótulo "atualizado há Xh" da aba Compras lia `last_live_check_at`, que avança em toda TENTATIVA (sucesso ou falha, `live_check.check_and_evaluate_leg`) e nunca era escrito pelo caminho cache — o rótulo já mentia sobre a idade do preço antes desta fatia. Passa a gravar só quando `current_price` de fato é escrito, no mesmo ponto de sempre (`weekends.evaluate_and_record_leg_price`, os dois `update_fields` — ramo `suppress_alert` e ramo normal).
- **Nada muda no disparo de alerta:** `current_price`/`current_price_at`/`lowest_seen`/`weekend_leg_price_history` continuam exclusivos do caminho confirmado (`SearchFlights` via `live_check.py`, Travelpayouts via `weekends.py`). Verificado com teste dedicado (`RadarPriceWriteTest.test_never_writes_current_price_or_lowest_seen`, `tests/test_main.py`) que o bloco novo de `main.py` nunca passa essas chaves pra `update_weekend_leg`.

**Implementação (`src/radar_check.py`):**
- `_grid_index`/`_priced_leg`/`_leg_airport` — extraídos de `select_precision_candidates` (sem mudança de comportamento) pra uso comum com a função nova.
- `resolve_radar_leg_prices(legs, grid, today)` — pura, mesma regra de casamento perna×grade de `select_precision_candidates` (menor preço entre GIG/SDU, mesma janela `RADAR_WINDOW_DAYS`), mas SEM filtro de teto/lowest_seen: aqui é descoberta pra tela, não seleção pra precisão.
- `load_radar_grid_for_legs(legs)` — extraído de `load_radar_candidates`, devolve `(today, grid)`. `main.py` chama 1x e reusa pros dois fins (gravar radar_price em todas as pernas E selecionar candidatas de precisão) — zero consulta nova à grade, zero consulta nova ao Google.
- `load_radar_candidates` ganhou parâmetros opcionais `today`/`grid` (default `None` — carrega do zero se não vierem, comportamento idêntico ao de antes desta fatia).
- `build_precision_comparison_row(candidate, report, checked_at)` — pura, monta a linha de persistência da comparação radar×precisão (item 7, abaixo) com a MESMA aritmética de `log_precision_divergence` (que continua existindo e só imprimindo).

**`main.py`:** dentro do bloco `if radar_enabled`, ANTES do laço de precisão — grava `radar_price`/`radar_price_at`/`radar_airport` de toda perna que `resolve_radar_leg_prices` devolver, cada escrita protegida por try/except individual (falha numa perna não derruba as outras nem a seleção de precisão). Depois, o laço de precisão de sempre, agora também persistindo cada comparação via `insert_radar_precision_comparison`, protegida por try/except próprio (mesmo padrão de `insert_alert_log`: falha de persistência secundária não pode cancelar um report já processado).

**Item 7 — persistência da comparação radar×precisão:** `log_precision_divergence` só imprimia no log do Actions, que expira. Tabela nova `weekend_radar_precision_log` (`sql/radar_fatia2_preco_de_tela.sql`) grava 1 linha por candidata processada (mesmo volume de sempre, 7-10/run) — `leg_id`, `travel_date`, `radar_price`/`radar_airport`, `precision_status`/`precision_price`/`precision_airport`/`precision_transfers`, `diff_pct`, `checked_at`. `precision_transfers` (escalas encontradas pela precisão, de `report["transfers"]`) foi adicionada na revisão de 04/09/2026 — sem ela o checkpoint de 01/12/2026 não tem como responder "há comparação em perna com escala", já que `precision_airport` sozinho só diz GIG/SDU. Mesmo padrão de RLS de `weekend_radar_grid` (só `service_role`, revoke de `anon`/`authenticated` — não exposta no painel nesta fatia). Sustenta o checkpoint de reavaliação de 01/12/2026 (ver `PLANO-ATIVO.md`, seção "Checkpoint — radar como gatilho de alerta").

**Correções pré-commit (revisão no chat de planejamento, mesma data):** (1) `radar_price_at` gravava `datetime.now()` no momento do run, não a idade real do preço na grade — como a grade pode ter até `RADAR_GRID_MAX_AGE_HOURS` de idade, isso carimbava preço velho como "agora" e o fazia ganhar de um confirmado genuinamente mais novo na escolha do frontend. Corrigido lendo `weekend_radar_grid.swept_at` (já existia por linha, gravado por `radar_check.run_sweep`) — `resolve_radar_leg_prices` agora devolve o `radar_price_at` de cada perna a partir da linha da grade que deu o preço, não um timestamp único por run. (2) `displayedLegPrice` (compras.js) caía em branco pra perna sem `current_price_at` nem `radar_price_at` — as ~44 pernas além do alcance da fonte nunca teriam nenhum dos dois preenchido. Ganhou fallback pra `last_live_check_at`, com o rótulo trocando de "atualizado" pra "verificado" pra não fingir que é a idade do preço. (3) descrito acima. (4) o cabeçalho do SQL dizia que `current_price_at` grava "só quando `current_price` muda de valor" — errado; o código grava toda vez que `current_price` é escrito, mesmo repetindo o valor, e isso é o comportamento CORRETO (preço reconfirmado hoje deve mostrar "atualizado hoje"). Documentação corrigida, código intocado.

**Frontend (`docs/js/compras.js`, `docs/css/style.css`) — Compras-only, decisão explícita:** `weekend_leg_effective` (a view) NÃO foi recriada — o Dashboard continua lendo só preço confirmado. A aba Compras ganhou as colunas novas pelo segundo `select` que já fazia direto em `weekend_legs` (mesmo padrão de `current_airline`/`current_departure_time`). `displayedLegPrice(leg)` decide o número principal como o MAIS RECENTE entre `radar_price_at` e `current_price_at` (decisão do usuário, não estava na proposta original da investigação) — com rótulo "não confirmado" sempre visível quando o número é do radar, e o preço confirmado mais antigo (se existir) continua na tela, em linha secundária discreta, nunca escondido. `legPriceState`/`legStatusBadge` (selo "abaixo do teto") e o filtro `isBelowCeiling` continuam lendo SÓ `current_price` — preço do radar nunca vira sinal de ação, só número + rótulo.

**Volume medido contra o seed real** (66 fins de semana, 132 pernas, hoje = 04/09/2026): 88 pernas dentro de hoje+305d (44 fora) — desliza ~2/semana. Escritas em `weekend_legs` por run sobem de 7-10 (só candidatas) pra ~88 (mais os 7-10 de sempre); ~176/dia com 2 runs. Custo desprezível no Supabase (PATCH de linha existente, sem crescimento de tabela); ~10-25s a mais de execução no Actions, contra os ~60s+ que a varredura já leva de `sleep`.

**Checkpoint de reavaliação registrado, não implementado — ver `PLANO-ATIVO.md`, seção "Checkpoint — radar como gatilho de alerta":** em 01/12/2026, reabrir no chat de planejamento (nunca implementar automaticamente) a discussão "o radar pode ter autoridade para disparar alerta de compra?" — a amostra de divergência radar×precisão hoje é pequena e concentrada (só GIG/BSB, voo direto, baixa temporada, pernas perto do teto); até 01/12 as pernas de fim de ano (29/12/2026, 06/01/2027) terão atravessado a janela de 30-60 dias antes do voo, condição de alta temporada/volatilidade real nunca coberta pela amostra atual. Gatilho de antecipação: qualquer divergência relevante antes disso reabre a discussão na hora, sem esperar a data.

**Verificação:** suíte local `.venv/bin/python -m unittest discover tests -v`, **348 testes, todos verdes** (319 antes desta sessão; +29 casos novos em `test_radar_check.py`, `test_weekends.py`, `test_main.py` e `test_supabase_client.py` — incluindo os 4 casos das correções pré-commit acima —, nenhum caso existente alterado). SQL (`sql/radar_fatia2_preco_de_tela.sql`) não rodado — pendente de execução manual pelo usuário no SQL Editor do Supabase antes do deploy do código (mesma ordem obrigatória de sempre: SQL antes do código, ou o PostgREST devolve 400 na primeira escrita).

## 27. Etapa 7 — criação da conta do segundo usuário (planejada 15/08/2026, executada E7-0 a E7-7, concluída 05/09/2026)

*Conteúdo movido integralmente do `PLANO-ATIVO.md` em 05/09/2026 (fatia E7-7), sem reescrita: as notas de override datadas, o texto histórico marcado como superado, a lista nomeada dos 11 itens e o mapa de riscos/pontos sem volta ficam como estavam — é registro de como as decisões foram tomadas no momento em que foram tomadas. O cabeçalho original da seção era:*

> Etapa 7 — criação da conta do segundo usuário (PLANEJADA E TOTALMENTE DECIDIDA em 15/08/2026; **gate do item 5 da D4 CUMPRIDO em 17/08/2026; E7-5 CONCLUÍDA em 24/08/2026, evidência ampliada em 05/09/2026** — execução em andamento, E7-0 a E7-5 concluídas, restam E7-6 e E7-7)

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

**✅ CONCLUÍDA (confirmada por evidência real de banco em 24/08/2026 — correção
de uma reclassificação incorreta feita mais cedo no mesmo dia).**

**Nota de correção, registrada porque houve erro de fato:** nesta mesma data
(24/08/2026), esta fatia foi reclassificada como "bloqueada por design,
pendente de observação real", com o argumento de que provar o fan-out exigiria
disparar um alerta de teste artificial para o Gustavo. **Esse argumento estava
errado** — a observação necessária já tinha acontecido organicamente, dias
antes, e só não tinha sido consultada. Uma leitura read-only de produção,
pedida pelo usuário logo em seguida (para calibrar a margem do gatilho do
radar de calendário), trouxe a prova que faltava. A reclassificação incorreta
foi commitada (`26972eb`) e ainda não tinha sido enviada ao remoto — corrigida
aqui antes do push.

**Evidência real — `alert_log`, consulta direta em produção (24/08/2026):**
duas ocorrências de linhas com **dois `user_id` distintos**, mesma perna,
mesma execução (`sent_at` a <1s de diferença um do outro):

| leg_id | user_id | price | ceiling | sent_at |
|---|---|---|---|---|
| `d7bf81ee…` | `c72bf50e…` (Elton) | 317 | 500 | 2026-08-21 11:17:11.147184 |
| `d7bf81ee…` | `2446ec67…` (Gustavo) | 317 | 500¹ | 2026-08-21 11:17:10.619666 |
| `b4f28800…` | `c72bf50e…` (Elton) | 316 | 500 | 2026-08-20 11:17:31.688946 |
| `b4f28800…` | `2446ec67…` (Gustavo) | 316 | 400 | 2026-08-20 11:17:31.194447 |

¹ **Nota de correção (24/08/2026, corrigindo esta mesma tabela no mesmo dia
em que foi escrita):** a coluna `ceiling` veio de um JOIN entre `alert_log`
(histórico) e `weekend_leg_effective` (estado ATUAL do teto, não um
snapshot do momento do alerta) — pega o valor certo quando o override é
anterior ao alerta (é o caso das outras três linhas), mas erra quando é
posterior. Para **esta linha específica** (Gustavo/`d7bf81ee…`, 21/08),
`weekend_leg_ceiling_audit` mostra que o override de Gustavo para 500 nessa
perna só aconteceu em **2026-08-25 00:03:36 — 3,5 dias DEPOIS** deste
alerta; o teto real no momento era o default, **R$300**. Confirmado pelo
próprio `reason` do alerta, que diz só `"15,1% abaixo da média histórica"`,
sem `"abaixo da meta fixa"` — se o teto fosse 500 (ou mesmo 300, já que
R$317 > R$300), o gatilho de meta fixa não dispararia mesmo, então o
`reason` observado é consistente com teto 300, não prova sozinho, mas bate
com a auditoria. As outras três linhas (Elton nas duas pernas, Gustavo em
`b4f28800…`) não têm esse problema — os overrides correspondentes
aconteceram **antes** dos respectivos alertas, confirmado em
`weekend_leg_ceiling_audit`. Não muda a conclusão desta fatia: o fan-out
(dois `user_id` distintos, mesma perna, mesma execução) não depende do valor
do teto, só de ele ter sido avaliado por usuário — o que aconteceu nos dois
casos, com qualquer teto.

Os 3 números do critério de conclusão batem: fila normal (mesma execução
agendada, sem alteração de volume), donos distintos confirmados (`c72bf50e…`
e `2446ec67…` na mesma perna, mesmo ciclo), `had_error` não é indicado por
nenhuma das linhas (inserção bem-sucedida nos dois casos). A segunda ocorrência
(`b4f28800…`, 20/08) mostra também que o teto é avaliado **por usuário**, não
compartilhado — Elton R$500, Gustavo R$400 na mesma perna, resultado consistente
com a garantia central da Fatia D4. Confirmação de mensagem com "Elton" e
"Gustavo" nominalmente no Telegram não foi checada nesta consulta (é de banco,
não do canal) — mas o mecanismo de `user_label` já foi confirmado
independentemente pelo item 6 da D4 (17/08, print de tela "👤 Elton").

**E7-5 está de fato concluída.** Segue para E7-6/E7-7 sem pendência.

**Evidência ampliada (05/09/2026) — confirmação sistemática, não mais ad
hoc.** A evidência de 24/08 acima (2 pares, achados manualmente enquanto se
investigava outra coisa) foi reforçada por uma consulta dedicada de
self-join em `alert_log` (mesmo `leg_id`, `user_id` distintos, `sent_at` a
poucos segundos de diferença), rodada manualmente pelo usuário no SQL
Editor, cobrindo todo o histórico disponível até hoje. Resultado: **12
pares confirmados, 6 pernas distintas, janela 20/08/2026–05/09/2026**,
sempre o mesmo par de usuários (`c72bf50e…` Elton / `2446ec67…` Gustavo),
sempre com diferença de `sent_at` **< 1 segundo**, sempre mesmo `price` nas
duas linhas de cada par. Não muda a conclusão de 24/08 — fecha de vez
qualquer dúvida remanescente sobre se os 2 casos originais eram exceção ou
padrão consistente do desenho.

---
*Texto histórico abaixo preservado como registro do estado antes desta
correção — mantido para rastreabilidade, não reflete mais o status real.*

Base de observação original (E7-2): 16/08 ~08h BRT (1 usuário, antes da
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

**E7-6 — 🟢 CONCLUÍDA (05/09/2026). Painel do Gustavo + a linha da Fatia C.
REVERSÍVEL: só leitura, exceto a compra de teste (desfeita no fim — feito).**

Verificação manual em produção, com as DUAS contas reais logadas no site
publicado (Elton e Gustavo), conduzida pelo usuário. Resultado: **passou nas
duas direções.**

1. **Visibilidade cruzada de compra (item 6 da lista dos 11) — CONFIRMADA nas
   duas direções.** Uma perna marcada como comprada de um lado aparece do
   outro como **"Outro usuário já comprou"**, e a recíproca também foi
   conferida (marcando do outro lado e olhando de volta). **É a primeira
   verificação POSITIVA deste item desde 11/08/2026** — até aqui ele estava
   registrado como "sem verificação positiva possível" (`HISTORICO.md`, item
   23), limite estrutural, não pendência. O limite caiu: a projeção
   `weekend_leg_purchase_shared`, mantida pela trigger `security definer` da
   Fatia C, está de fato entregando ao OUTRO usuário — não só ao dono.
2. **O rótulo "Você" (item 7 da lista dos 11) — CONFIRMADO.** Do lado de quem
   comprou aparece "Você"; do lado do outro, não. É a prova da E7-1, que
   corrigiu o rótulo relativo ao usuário logado ANTES de existir alguém para
   ver o defeito — a asserção lá era fraca de propósito ("só código, sem a
   segunda conta"), e é aqui que ela fecha positivamente.
3. **Compra de teste DESFEITA — e é preciso separar duas evidências
   diferentes, porque elas têm datas, técnicas e forças distintas:**
   - **Evidência NOVA, desta sessão (visual, duas contas reais):** a marcação
     usada no teste foi revertida pelo painel e a tela do outro usuário
     deixou de mostrar a linha "Outro usuário já comprou". Isto é o que foi
     observado hoje: o comportamento visível, com as duas contas logadas.
   - **Evidência REAPROVEITADA, de 10/08/2026 (SQL, prova do mecanismo):** que
     desfazer de fato REMOVE a linha da projeção `weekend_leg_purchase_shared`
     já estava provado por SQL no bloco **V3** da verificação da Fatia C
     ([fatia_c:324](sql/fatia_c_visibilidade_compra.sql:324)), que exercita os
     três ramos da trigger numa transação com rollback — compra grava (1),
     desfazer remove (0), recomprar grava de novo (1), delete do estado
     remove (0).
   **O que esta sessão NÃO fez: nenhuma consulta SQL foi rodada em 05/09/2026**
   — não houve `select` em `weekend_leg_purchase_shared` para confirmar que a
   linha sumiu da tabela. A afirmação sustentada aqui é a soma das duas
   evidências acima (mecanismo provado por SQL em 10/08; comportamento
   observado em tela hoje, com duas contas), não uma verificação de banco
   feita nesta sessão. Se um dia for preciso a prova direta de banco no estado
   de produção atual, ela ainda não existe.

**O que esta fatia NÃO cobriu, e continua em aberto:** os itens 1, 2, 3, 5 e 9
da lista dos 11 (contagem da view por navegador, isolamento positivo de
`weekend_leg_user_state` e de `weekend_leg_ceiling_audit`, a RLS apertada da
D-7 barrando o outro usuário de fato, e o `default auth.uid()` nascendo para
uma conta que não é a do usuário 1) foram cobertos pela E7-4, por SQL, não
por login — permanecem como estão. O item 10 (`notification_mode` por dono no
caminho de rota) segue sem observação: depende de o Gustavo cadastrar rota
flexível, e ele não cadastrou. Não bloqueia o fechamento da etapa; fica
registrado aqui como o único dos 11 sem observação em produção.

*Critério de conclusão do plano original ("as duas direções conferidas e a
compra de teste desfeita") — cumprido integralmente.*

**E7-7 — 🟢 CONCLUÍDA (05/09/2026). Fechamento e higiene. REVERSÍVEL:
documentação + uma mudança de código de baixo risco.**

1. **`sql/etapa4_1_verificacao.sql` marcado como parcialmente vencido** — nota
   de cabeçalho datada de 05/09/2026, no mesmo padrão da nota de 07/08/2026.
   Arquivo NÃO aposentado: os blocos B, C, E, F2, G e H continuam válidos e
   rodáveis. Venceram os números esperados do **Bloco D** (escritos em
   01/08/2026, com um usuário só): `linhas_view` 132 → **264**, e o
   `132 | 0 | 5 | 5` por três motivos independentes (teto padrão recalibrado
   pra R$300 em 04/08; overrides de teto por perna feitos pelos dois usuários
   desde 15/08; linhas de estado e preço pago crescendo com o uso). **O que
   NÃO venceu, e a nota diz isso explicitamente:** o `view_esp_132` do **Bloco
   F** continua correto — ali a view roda sob RLS como usuário autenticado,
   então 132 lá e 264 no Bloco D é o comportamento esperado, não contradição.
2. **Semântica de `get_weekend_leg_counts` decidida e implementada** — a
   decisão adiada de propósito para esta fatia, depois de observar o
   comportamento real em vez de decidir no papel. O resumo semanal passa a
   contar pernas compradas **por usuário**, uma linha por pessoa
   (`👤 Elton: 3 de 90 pernas compradas` / `👤 Gustavo: 1 de 90 …`), em vez do
   critério de interseção ("comprada só quando TODOS marcaram"), que nasceu
   com um usuário só e sub-contaria para sempre com dois — Elton e Gustavo
   compram passagens INDEPENDENTES na mesma perna, não a mesma passagem. O
   painel já contava assim desde a Etapa 4.2 (cada navegador lê a view sob RLS
   e vê só as próprias 132 linhas): esta fatia alinha o robô ao painel.
   - **Sem mudança de schema e sem consulta nova.** A view já expõe `user_id` e
     `get_effective_leg_state` já o trazia no `select` — a informação por
     usuário já chegava e era descartada no agrupamento. Continua **uma**
     leitura de `weekend_leg_effective` por execução de segunda-feira,
     agrupada em memória. **A garantia central da Fatia D4 permanece intacta:**
     nenhum caminho de scraping foi tocado, e nada passou a crescer com número
     de usuário além do número de linhas de texto da mensagem.
   - **Modo degradado tratado:** `settings` vazia → a mensagem diz "contagem
     por usuário indisponível", nunca "0 de 0 pernas compradas", que pareceria
     progresso zerado (mesmo princípio do `ceiling_label` "indisponível" no
     alerta de perna).
   - **Testes:** os 8 casos de `GetWeekendLegCountsTest` foram reescritos (o
     `test_leg_counts_purchased_only_when_all_users_agree` **foi substituído**,
     não adaptado — ele asseverava exatamente a regra revogada, e o caso novo
     carrega docstring dizendo que a revogação é decisão de produto, não
     regressão); `BuildWeeklyWeekendSummaryTest` idem; e o **ramo de
     segunda-feira do `main()`, que nunca tinha sido exercitado** (todos os
     testes do arquivo forçam `weekday = 2` justamente para evitá-lo), ganhou
     classe própria, incluindo um caso que trava a contagem em UMA chamada —
     a garantia da D4 escrita como teste. Suíte: **361 testes, todos verdes**.
3. **Conteúdo desta seção movido para o `HISTORICO.md`** (item 27), conforme a
   regra de manutenção do `PROTOCOLO-DE-TRABALHO.md`, deixando no
   `PLANO-ATIVO.md` só um ponteiro de uma linha.

**Achado colateral, corrigido em commit separado:** ao rodar a suíte inteira
apareceram 3 falhas **anteriores a esta fatia** — `tests/test_live_check.py`
passava a data fixa `"2026-09-04"` como data de viagem, que virou passado em
05/09/2026; a `fli` valida `travel_date` com pydantic e rejeita data no
passado ANTES de chegar ao código sob teste. Pior que as 3 quebras: outros 4
testes do mesmo arquivo continuavam verdes **pelo motivo errado**, recebendo o
`None` da validação de data em vez do `None` do caminho que dizem testar.
Corrigido usando `days_from_today(10)`, helper que já existia no arquivo, nas
7 chamadas.

**Higiene registrada, sem ação:** o texto da lista dos 11 itens diz "267 testes
unitários (contagem estática conferida em `tests/`: 267)" — número da era da
D4. A suíte tem 361 casos em 05/09/2026. Fica como está no texto histórico: o
267 era verdadeiro quando foi escrito, e reescrevê-lo apagaria o registro de
quanta cobertura existia no momento da decisão.

**Com isso a Etapa 7 está CONCLUÍDA (E7-0 a E7-7), e com ela a iniciativa
multi-usuário (Etapas 1 a 7).**

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

