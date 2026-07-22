# Roadmap FlyIop — Auditoria de 15/07/2026

Resultado da auditoria externa (chat de planejamento) comparando o estado atual com Google Flights, Hopper e projetos open-source de monitoramento. Executar em fases, uma por vez, seguindo o PROTOCOLO-DE-TRABALHO.md (Plan Mode antes de cada fase; plano revisado no chat de planejamento antes de executar).

---

## FASE A — Qualidade do dado (prioridade máxima: ataca a dor "preço real")

**A1. Migrar de `v2/prices/month-matrix` para a família v3 da Travelpayouts**
- `v3/prices_for_dates` e/ou `v3/grouped_prices` usam cache das últimas **48 horas** (vs até 7 dias do v2) — a própria Travelpayouts recomenda o v3 no lugar dos métodos antigos.
- `prices_for_dates` aceita `departure_at` como `YYYY-MM` (mês flexível — Fase 1) ou `YYYY-MM-DD` (data fixa — Fase 2), com `one_way=false` para ida-e-volta. Um endpoint cobre as duas fases do projeto.
- Manter o schema do histórico compatível (price, return_date, found_at, stops, days_ahead).
- Testar cobertura das rotas atuais no v3 antes de desligar o v2 (rodar os dois em paralelo por alguns dias e comparar no run_log).

**A2. Portão de frescor nos alertas**
- Se o preço que dispararia alerta tiver `found_at` mais velho que um limiar (sugestão: 24h), o alerta deve sair com aviso destacado de dado velho — ou ser suprimido (configurável em settings).
- Objetivo: nunca fazer o usuário correr pro site por um preço fantasma.

**A3. Deduplicação/cooldown de alertas**
- Não re-alertar o mesmo "bom preço" todo dia. Regra sugerida: re-alertar somente se (a) o preço caiu mais X% desde o último alerta, ou (b) passaram Y dias (sugestão: 3) desde o último alerta daquela rota.
- Registrar último alerta enviado por rota em `bot_state` ou tabela própria.

**A4. Janela dupla de monitoramento por rota (pedido explícito do usuário)**
- Cada rota passa a ter configuração de horizonte: **janela curta** (ex: 30–60 dias à frente) e/ou **janela longa** (ex: 4–6 meses à frente).
- Limiares de tendência independentes por janela (preço a 45 dias tem dinâmica diferente de preço a 5 meses).
- UI de Configurações: seleção simples das janelas por rota (curta, longa, ambas).

**A5. Dupla checagem de coerência do preço (anti-preço-fantasma)**
- **Autocheck estatístico (sempre, sem scraping):** antes de alertar, comparar o preço novo com o histórico da própria rota. Se estiver anormalmente abaixo (sugestão: >50% abaixo da média 30d), marcar como "suspeito" — registrar no run_log e não disparar alerta direto (ou alertar com aviso forte de possível erro de dado).
- **Confirmação pontual (opcional, só no momento do alerta):** quando um preço bater a meta e for gerar alerta, permitir uma verificação única numa segunda fonte (ex: abrir a busca correspondente e comparar ordem de grandeza). Best-effort: se falhar/bloquear, o alerta sai mesmo assim, apenas sem o selo "confirmado". NUNCA rodar essa verificação em toda consulta da varredura diária — só no evento de alerta.
- Proibido: scraping em volume (toda rota/data/dia) e táticas de evasão anti-bot (decisão de escopo antiga, inalterada).

**Decisão de implementação da "confirmação pontual" — biblioteca `fast-flights` (registrada em 21/07/2026):** a segunda fonte independente citada acima será o Google Flights, consultado via `fast-flights` (biblioteca de terceiros que faz scraping do resultado do Google Flights — não é API oficial). Essa escolha já estava implícita na redação original do A5 ("abrir a busca correspondente"); o que faltou até aqui foi deixar explícito qual mecanismo faz essa busca. Regras de implementação, todas obrigatórias:
1. **No máximo 1 chamada por alerta disparado** — nunca na varredura diária (as 18–36 chamadas/dia à Travelpayouts continuam intocadas; o fast-flights não entra nesse loop).
2. **Best-effort** — se a consulta falhar, travar ou vier vazia, o alerta sai normalmente, sem o selo de confirmação. Nenhuma falha do fast-flights pode atrasar ou bloquear um alerta.
3. Documentação desta decisão vive aqui, no `ROADMAP-AUDITORIA.md` — não em arquivo de plano separado.
4. **Escopo permanece contido:** nada de bagagem, tarifa completa ou regras de remarcação (fora de escopo desde o `CLAUDE.md` original); nada de scraping em volume ou evasão anti-bot (proibição de sempre, inalterada). É uma única consulta pontual no momento do alerta — nada além disso.

O trabalho de validação já feito antes desta decisão ser esclarecida (script `scripts/validate_fastflights.py`, 2 execuções locais e 2 no Actions, ambas com 2 de 3 rotas retornando preço) segue válido como evidência técnica de viabilidade — reaproveitar quando a implementação for planejada, sem precisar repetir do zero.

---

## FASE B — Ferramentas de decisão (paridade com Google Flights onde importa)

**B1. Calendário de preços (heatmap) no Dashboard**
- Os dados por dia do mês já são coletados; falta exibir como calendário com cores (barato → caro), estilo date grid do Google Flights.
- Por rota, com navegação entre meses.

**B2. Selo de nível de preço por percentil**
- Quando a rota tiver histórico suficiente (sugestão: ≥30 registros), classificar o preço atual em percentil: "baixo" (≤p25), "típico" (p25–p75), "alto" (≥p75).
- Substituir/complementar o badge atual. Incluir o selo no alerta do Telegram.

**B3. Calculadora manual de milhas (destino final do miles.py)**
- Sem fonte gratuita de dados de milhas — decisão: input manual.
- No site: campo "quantas milhas o programa está pedindo?" por rota → resposta imediata se compensa vs preço em dinheiro atual, usando o custo do milheiro já configurado.
- No Telegram: comando `/milhas <rota> <quantidade>` com a mesma lógica.
- Remover qualquer expectativa de automação de milhas da documentação.

**B4. Melhorar o link do Google Flights**
- Hoje o link não codifica passageiros nem garante ida-e-volta. Investigar codificação completa do deep-link; se instável, manter o link Aviasales como primário (já verificado) e o Google Flights como secundário com rota+datas.

**B5. Análise de "melhor antecedência de compra" com base no histórico (pedido explícito do usuário)**
- Como o robô já varre múltiplas datas futuras a cada execução (`days_ahead` já é gravado no histórico), dá pra responder: "historicamente, pra essa rota, comprar com quantos dias de antecedência costuma dar o menor preço?"
- Implementação: agrupar `price_history` por faixas de `days_ahead` (ex: 15–30, 30–45, 45–60, 60–90, 90–120, 120–180 dias) e calcular o preço médio/mediano de cada faixa, por rota.
- Exibir no Dashboard como um gráfico simples (eixo X = faixa de antecedência, eixo Y = preço médio) — a faixa mais barata fica destacada.
- **Limitação honesta a documentar:** isso só fica estatisticamente confiável depois de meses de coleta (cada `target_date` precisa ter sido observado em várias antecedências diferentes ao longo do tempo). Nos primeiros meses, mostrar o gráfico com aviso "dados insuficientes ainda" em vez de sugerir uma conclusão precoce.
- Essa funcionalidade se conecta com `buying_window.py` (já existe lógica parecida) — avaliar se é extensão do mesmo módulo ou peça nova.

---

## FASE C — Fase 2 do projeto + cobertura (preparação out/nov)

**C1. Modo data fixa por rota**
- Rota pode ter `departure_date`/`return_date` exatos (Fase 2: compras a partir de outubro pra fev/2027+).
- Usa o mesmo `prices_for_dates` com data exata. Alertas passam a comparar o preço daquela data específica com seu próprio histórico.

**C2. Cadência maior perto da viagem**
- Quando a data fixa estiver a <60 dias, aumentar frequência de checagem (ex: 2x/dia). Ajustar cron do daily.yml condicionalmente ou criar workflow separado.

**C3. Códigos de cidade para cobertura multi-aeroporto**
- A API aceita código IATA de cidade (ex: SAO, RIO) — agrega todos os aeroportos da cidade numa consulta.
- Configuração de rota passa a permitir "cidade" além de "aeroporto" — resolve o backlog "aeroportos alternativos" e é a saída para rotas de aeroporto pequeno sem cobertura (ex: RIA→BSB pode virar POA→BSB ou cidade equivalente, decisão do usuário).

---

## FASE D — v3+ (só depois de A–C estáveis)

- Sazonalidade histórica com dados ANAC (rotas domésticas, multi-ano)
- Alerta de câmbio combinado com preço (rotas internacionais)
- Previsão compre/espere com ML simples (tipo LightGBM), quando houver meses de histórico próprio
- Reavaliação pós-compra (monitorar preço após a compra pra remarcação/reembolso quando a tarifa permitir)

---

## Limitações permanentes (documentar, não tentar resolver)

- Preço comprável em tempo real: só com API comercial paga. O produto é um monitor de tendência com confirmação manual no link — e é honesto sobre isso.
- Regras de tarifa/bagagem no alerta: sem fonte gratuita. O link de compra serve de conferência.
- Emissão automática: fora do escopo por decisão de segurança (inalterado).
