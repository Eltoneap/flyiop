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
