# Plano — Validação Cruzada de Preços + Roadmap B/C/D revisado

_Complemento ao PLAN-FASE-A.md, escrito em 18/07/2026 e ancorado no código real do repositório (commit atual de `main`). Este documento faz três coisas: (1) revisa formalmente a regra de proibição de scraping, (2) adiciona as etapas 0 e 8 ao plano da Fase A, e (3) consolida o roadmap das Fases B/C/D com datas-alvo, alinhado ao calendário real (aprendizado a partir de out/2026, compra a partir de fev/2027). Executar uma etapa por vez, com teste local antes de cada push, como no protocolo já vigente._

---

## Parte 1 — Revisão da regra de scraping (decisão registrada)

**Regra anterior** (PLAN-FASE-A.md, etapa 7): _"Proibições mantidas: nada de scraping em volume nem evasão anti-bot."_

**Regra revisada (18/07/2026):** scraping/consulta a fonte não-oficial é permitido quando TODAS as condições valerem:

1. **Volume mínimo** — só no evento de alerta (nunca na varredura diária), máximo 1 consulta extra por alerta.
2. **Best-effort obrigatório** — falha da fonte extra NUNCA bloqueia nem atrasa o alerta; padrão `try/except` silencioso igual ao `safe_v3_comparison` já existente em `src/main.py`.
3. **Sem evasão ativa** — nada de rotação de proxy, spoofing de fingerprint, resolução de CAPTCHA ou burla de login/paywall. Se a fonte bloquear, aceita-se o bloqueio (o alerta sai sem o selo extra).
4. **Fonte degradável** — o sistema inteiro deve continuar funcionando de forma idêntica se a fonte extra sumir amanhã (biblioteca quebrada, endpoint mudado). Nenhuma decisão de alerta pode DEPENDER dela; ela só ENRIQUECE.
5. **Validação prévia obrigatória** — nenhuma fonte nova entra no fluxo antes de passar no teste da Etapa 0 abaixo.

**Racional do custo-benefício:** a Etapa 7 (confirmação na 2ª consulta Travelpayouts) valida contra a MESMA fonte — pega erro de parsing e glitch pontual, mas não pega erro sistemático da própria Aviasales. Uma fonte independente (Google Flights via `fast-flights`) adiciona sinal genuinamente novo. O risco (bloqueio de IP do runner, quebra da lib por mudança no protobuf, zona cinzenta de ToS) é aceitável APENAS sob as 5 condições acima, que o tornam um enfeite opcional e não uma dependência.

---

## Parte 2 — Etapas novas da Fase A

### Etapa 0 — Validação do fast-flights (ANTES de qualquer integração)

**Objetivo:** provar que `fast-flights` funciona (a) localmente e (b) no IP do runner do GitHub Actions — que é alvo conhecido de bloqueio anti-bot — para as rotas reais monitoradas. Sem isso, as etapas 8+ não existem.

**Passos:**

1. Criar `scripts/validate_fastflights.py` (fora de `src/` para não disparar o `daily.yml` no push):
   - Adicionar `fast-flights` a um `requirements-dev.txt` novo (NÃO ao `requirements.txt` principal ainda).
   - O script lê 2–3 pares origem/destino fixos no código (usar as rotas reais ativas — conferir no Supabase antes; ex.: as rotas cadastradas hoje).
   - Para cada rota: chama `get_flights` com `fetch_mode="fallback"`, ida e volta, data ~90 dias à frente, e imprime: preço mais barato, companhia, escalas, tempo de resposta, e se houve exceção.
   - Saída final: tabela-resumo `rota | status (ok/vazio/erro) | preço | latência`.
2. Rodar localmente 2 vezes em horários diferentes. Registrar o resultado neste arquivo (seção "Resultados da Etapa 0" abaixo).
3. Criar `.github/workflows/validate_fastflights.yml` com `workflow_dispatch` APENAS (sem cron, sem push trigger), rodando o mesmo script. Disparar manualmente 2 vezes em dias diferentes.
4. **Critério de aprovação:** ≥ 2 das 3 rotas retornando preço em ≥ 3 das 4 execuções (2 locais + 2 no Actions). Se o Actions falhar sistematicamente mas o local funcionar → registrar aqui e ABORTAR as etapas 8+ (o custo de contornar não compensa; a Etapa 7 sozinha já cobre o essencial).

**Teste local:** o próprio script é o teste. Sem Supabase, sem Telegram, sem token Travelpayouts.

### Resultados da Etapa 0

_(preencher após execução)_

| Execução | Onde | Data | Rotas ok | Observações |
|---|---|---|---|---|
| 1 | local | 18/07/2026 | 2/3 | BSB→GIG R$ 638 (LATAM, 1,8s) e GIG→BSB R$ 757 (Gol, 1,6s), moeda BRL nativa. RIA→BSB: exceção no parser da lib (`TypeError` em `parse_js`) — padrão de "sem resultados no Google", não de bloqueio (as outras 2 rotas funcionaram do mesmo IP na mesma rodada). |
| 2 | local | | | |
| 3 | Actions | 18/07/2026 | 2/3 | BSB→GIG R$ 552 (0,5s) e GIG→BSB R$ 527 (0,5s) — runner do Actions NÃO bloqueado, e mais rápido que local. RIA→BSB: mesmo erro de parser das execuções locais (padrão "sem resultados", não bloqueio). |
| 4 | Actions | | | |

**Notas técnicas da implementação (18/07/2026):** versão validada é `fast-flights==3.0.2` — a API mudou em relação à 2.x citada como exemplo no plano: não existe mais `fetch_mode="fallback"`; usa-se `create_query(...)` + `get_flights(query)`. Duas vantagens da 3.0.2: `price` vem como `int` (sem parsing de string) e a query aceita `currency="BRL"` + `language="pt-BR"` nativamente — o que elimina a preocupação de moeda descrita na Etapa 8. O packaging da 3.0.2 não declara `typing_extensions` (import quebra sem ela); por isso o `requirements-dev.txt` a inclui explicitamente.

**Decisão:** ( ) aprovado — seguir para Etapa 8 · ( ) reprovado — arquivar fast-flights, Etapa 7 cobre sozinha

### Etapa 7 — mantida exatamente como está no PLAN-FASE-A.md

Nada muda. A confirmação na 2ª consulta Travelpayouts (data exata) continua sendo a primeira camada de validação e entra ANTES da Etapa 8, na ordem já planejada (após o corte v3 da etapa 6).

### Etapa 8 — Selo de fonte independente (fast-flights) no alerta

**Pré-condições:** Etapa 7 em produção e estável por ≥ 1 semana; Etapa 0 aprovada.

**Objetivo:** quando um alerta vai sair, além do selo `✅ confirmado em segunda consulta` (Etapa 7, mesma fonte), tentar UMA consulta ao Google Flights via `fast-flights` com a data exata da oferta. É a única camada que valida contra pipeline de dados independente.

**Mudanças:**

- `requirements.txt`: adicionar `fast-flights` (versão pinada — anotar a versão exata que passou na Etapa 0, ex.: `fast-flights==2.2`).
- Novo `src/independent_check.py`:
  - `check_google_flights(origin, destination, depart_date, return_date, expected_price, currency) -> str | None`
  - Chama `get_flights` com data exata, `fetch_mode="fallback"`, timeout curto (aceitar o default da lib; se expuser timeout, usar ≤ 20s).
  - Compara o mais barato retornado com `expected_price`:
    - dentro de ±30% → retorna `"🔎 Google Flights: {moeda} {preço:.2f} (fonte independente)"`
    - fora de ±30% → retorna `"🔎 Google Flights divergente: {moeda} {preço:.2f} — confirme com atenção"`
    - vazio/exceção/qualquer problema → retorna `None` (NUNCA levanta exceção pra fora; log via `print` apenas)
  - Atenção: Google Flights devolve preço na moeda da região da consulta — se a lib permitir passar moeda/país, usar `currency` da rota; se não permitir, comparar apenas ordem de grandeza e rotular a moeda que vier na resposta, nunca assumir BRL.
- `src/main.py`: no ponto onde o alerta é disparado (após `should_alert` e após a confirmação da Etapa 7), chamar `check_google_flights` e, se retornar string, anexar como linha extra do report (novo campo `independent_note`).
- `src/telegram_notifier.py` (`build_route_block`): se `report.get("independent_note")`, adicionar a linha ao bloco (depois da linha de frescor, antes dos links).
- `run_log`: anexar ao `detail` o resultado (`"gf: ok ±X%"` / `"gf: divergente"` / `"gf: falhou"`) para auditoria de quantas vezes a fonte funciona de verdade em produção.
- **Custo de chamadas:** no máximo 1 por alerta; com o cooldown da etapa 3 (A3) já limitando alertas, o volume esperado é < 5/semana. Irrelevante para qualquer rate limit.
- **Teste local (antes do push):** mockar `get_flights` nos 4 cenários (preço compatível, divergente, vazio, exceção) → conferir as 3 strings possíveis e o `None`, e que exceção nunca vaza. Mockar também o fluxo em `main.py` confirmando que `independent_note=None` não adiciona linha na mensagem.

**Cláusula de remoção:** se em 30 dias de produção o `run_log` mostrar `gf: falhou` em > 50% das tentativas, remover a Etapa 8 do fluxo (deixar o módulo no repo, desligado) e registrar aqui. A regra da Parte 1 exige que a fonte seja um enfeite — enfeite que falha na metade das vezes é ruído.

---

## Parte 3 — Roadmap consolidado B/C/D (datas-alvo)

_Ancorado no calendário real: período de aprendizado começa out/2026; compra real a partir de fev/2027. As fases B e C precisam estar prontas ANTES de outubro. Cada fase só começa com Plan Mode próprio (novo documento no repo), como manda o protocolo — o que segue são os objetivos e a ordem, não o plano de execução detalhado._

### Fase A — encerramento (21/07 → ~22/08)

| Janela | Item |
|---|---|
| 21–25/07 | Etapa 0 (validação fast-flights) em paralelo com as etapas 2–3 do PLAN-FASE-A |
| 26/07–10/08 | Etapas 4, 5 e 6 do PLAN-FASE-A (autocheck, janela dupla, corte v3) |
| 11–15/08 | Etapa 7 (confirmação 2ª consulta Travelpayouts) |
| 16–22/08 | Etapa 8 (selo fast-flights) SE Etapa 0 aprovada; senão, semana de folga/estabilização |

### Fase B — ferramentas de decisão (~23/08 → 30/09) — PRAZO DURO: pronto antes de out

Objetivos, em ordem de valor:

1. **Gráfico de evolução de preço com Plotly** no dashboard do GitHub Pages (substituir/upgrade do gráfico atual em `docs/js/dashboard.js`). Uma linha por janela (curta/longa, aproveitando o campo `window` da etapa 5). Interativo, legível no celular.
2. **Calendário/heatmap visual de preços** por mês (dado já existe no `price_history`; é visualização, não coleta nova).
3. **Melhor antecedência de compra por rota** — estatística simples sobre o próprio histórico: para cada rota, qual faixa de `days_ahead` historicamente teve os menores preços. Exibir no dashboard e na mensagem diária do Telegram ("historicamente, essa rota é mais barata com X–Y dias de antecedência").
4. _(opcional, só se sobrar tempo)_ Percentil do preço atual vs. histórico ("hoje está no P15 dos últimos 60 dias").

### Fase C — datas fixas + linguagem natural no bot (~01/09 → 15/10, sobrepõe o fim da B)

1. **Suporte a data fixa de viagem** por rota (campo novo em `routes`; o cliente v3 já aceita `departure_at=YYYY-MM-DD`, preparado para isso desde a Fase A).
2. **Busca em linguagem natural no FlyIopBot** — novo comando: usuário manda texto livre ("BSB pra Lisboa em março, ±5 dias, até R$ 4.000") e o bot interpreta e cadastra/consulta a rota. Implementação: chamada à API da Anthropic (Claude Haiku, resposta JSON estrita) dentro do `bot_commands.py` existente; secret novo `ANTHROPIC_API_KEY` no Actions. Fallback: se o parse falhar, o bot pede os campos um a um.
3. Ajustar cadência do `daily.yml` se o período de aprendizado pedir (ex.: 2×/dia para rotas com data fixa próxima).

### Fase D — avançado (nov/2026 → jan/2027, DEPOIS de acumular dados reais do aprendizado)

1. **Análise de sazonalidade** sobre o histórico acumulado (out–dez já dá 3 meses de dado denso).
2. **Experimento VPN/país** _(curiosidade, prioridade mínima)_: testar se o preço muda consultando de outro país — versão simples, sem o aparato de fingerprint do Flight Finder, respeitando a regra da Parte 1.
3. Previsão simples de preço (regressão sobre `days_ahead` × preço × sazonalidade) — só se os itens 1–2 da D e TODA a C estiverem estáveis. ML sofisticado fica explicitamente fora do escopo até depois da compra de fev/2027.

### Fora de escopo permanente (reafirmado)

Scraping em volume, evasão anti-bot ativa, qualquer fonte que exija infraestrutura 24/7 (Docker/VPS) — a arquitetura GitHub Actions + Supabase + Pages é um requisito do projeto, não um acidente.

---

## Verificação (padrão do protocolo, vale para tudo acima)

0. Teste local com mock antes de cada push — sem API real, sem Supabase.
1. Push em `src/**` dispara `daily.yml`; acompanhar pela API pública do GitHub.
2. Conferir efeito real: Telegram, `run_log`/`price_history` no Supabase, dashboard no celular.
3. SQL antes do código que depende dele, no SQL Editor do Supabase.
4. Etapa 0 tem workflow próprio (`workflow_dispatch` apenas) para não poluir o fluxo diário.
