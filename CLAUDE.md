# Projeto: FlyIop — Monitor Automático de Passagens Aéreas

## Objetivo
Sistema pessoal que pesquisa preços de passagens diariamente, compara com metas definidas pelo usuário e avisa via Telegram quando encontrar um bom preço ou uma tendência de alta preocupante. Painel web (GitHub Pages) para acompanhar tudo e marcar compras.

## Status
**Em produção.** Roda diariamente via GitHub Actions desde 13/07/2026. Dois sistemas de monitoramento convivem no mesmo backend/bot:

### 1. Fins de semana RIO↔BSB (foco principal)
- 66 fins de semana fixos, de sexta 04/09/2026 a sexta 03/12/2027 (viagem RIO→BSB na sexta, BSB→RIO no domingo ou segunda seguinte).
- Cada fim de semana vira **2 pernas independentes** (ida/volta, 132 pernas ao todo) — decisão de 23/07/2026 depois que o modelo de round-trip único mostrou cobertura de cache insuficiente.
- **Fonte primária de preço: `fast-flights`** (scraping do Google Flights, biblioteca de terceiros) — roda em lote diário (`settings.fast_flights_daily_batch_size`, default 20/dia) dentro de uma janela deslizante de 6 meses, com rotação por perna menos checada recentemente, detector de bloqueio (para o lote e avisa no Telegram) e kill-switch manual (`settings.fast_flights_enabled`). A Travelpayouts roda em paralelo como conferência secundária. Best-effort e sem evasão anti-bot (regras completas em `ROADMAP-AUDITORIA.md`, item A5).
- Cada perna tem teto de preço editável (default R$ 200, pendente de calibração com dados reais de ida vs. volta), status (monitorando/comprada) e campo de observações livre (localizador, horário) preenchido depois da compra.
- Quando uma perna dispara alerta, o robô busca a perna irmã do mesmo fim de semana e compara "avulso" (soma das duas pernas) vs. "pacote" (ida+volta junto, 1 consulta round-trip extra ao fast-flights) — decisão de compra sempre fica com o usuário.
- Painel web: `docs/compras.html` — cards por fim de semana, abas Ativos/Comprados, teto por perna (individual ou aplicar a todos os não comprados), progresso (X de 132 pernas / Y de 66 fins de semana completos).

### 2. Rotas flexíveis (legado)
- 2-4 rotas configuráveis (hoje: BSB→GIG, GIG→BSB, RIA→BSB), sem data fixa — menor preço nos próximos ~6 meses.
- Fonte: **Travelpayouts Data API** (`prices_for_dates`), 1 chamada por rota/mês/dia varrido.
- Regra de "bom preço" por rota: valor fixo e/ou percentual abaixo da média histórica própria.
- Alerta de tendência: sobe mais de X% em 3 dias ou Y% em 7 dias (limiares em Configurações).
- Painel web: `docs/config.html` (cadastro/arquivamento de rotas, tetos, preferências separadas por sistema legado vs. fins de semana).

### Regras e proteções comuns aos dois sistemas
- Cooldown de re-alerta (não repete o mesmo bom preço todo dia) e autocheck de preço suspeito (>50% abaixo da média 30d vira alerta com aviso, não silencioso).
- Portão de frescor: alerta com dado velho sai com aviso destacado, nunca suprimido silenciosamente.
- Notificação via Telegram (bot **FlyIopBot**), modo configurável (resumo diário ou só alerta), sempre com link direto pré-filtrado (rota/perna, data) para o usuário confirmar e comprar manualmente.
- Comparador milhas vs. dinheiro: usuário informa quanto paga pelo próprio milheiro; robô calcula se compensa mais pagar em dinheiro ou usar milhas (não usa média de mercado).

## Stack técnico
- **Backend**: Python (`src/`), agendado via **GitHub Actions** (`daily.yml`, roda 1x/dia).
- **Banco**: **Supabase** (Postgres + RLS + Auth) — substituiu o plano original de CSV/SQLite no repositório.
- **Frontend**: `docs/` — HTML/JS vanilla (sem build step), Supabase JS client, publicado via **GitHub Pages**. Páginas: `index.html` (Dashboard), `compras.html` (fins de semana), `config.html` (rotas + preferências), `login.html`.
- **Dados de preço**: Travelpayouts Data API v3 (`prices_for_dates`) + `fast-flights` (Google Flights) — ver detalhamento por sistema acima.
  - ~~Amadeus Self-Service~~ — descartado: portal descomissionado em 17/07/2026.
  - Kiwi Tequila / Skyscanner API oficial — descartados: exigem volume/parceria comercial incompatível com uso pessoal.
- **Notificação**: Bot do Telegram (**FlyIopBot**).

### Compra
- **Não automatizada.** Risco de segurança (dados de cartão) e barreira estrutural (sem alternativa self-service de emissão pra pessoa física). Autofill de navegador/gerenciador de senhas cobre a maior parte do preenchimento com segurança.

### Nota sobre scraping
- `fast-flights` é a única fonte de scraping em uso, e só nos moldes definidos no `ROADMAP-AUDITORIA.md` (item A5): sequencial, com espaçamento, best-effort, sem rotação de proxy/user-agent nem qualquer tática de evasão anti-bot. Se bloquear, o sistema para e avisa — nunca contorna.

## Prontas para uso imediato (referência externa, enquanto alguma cobertura faltar)
- Google Voos — monitoramento gratuito, "qualquer data", alerta por e-mail
- Skyscanner — segunda fonte de comparação
- HeyMiles — comparação dinheiro vs. milhas (Smiles/Latam Pass/Azul Fidelidade)

## Backlog (avaliar conforme o sistema atual for rodando e gerando dados reais)
- [ ] Calendário de preços (heatmap) no Dashboard
- [ ] Selo de nível de preço por percentil (baixo/típico/alto)
- [ ] Análise de "melhor antecedência de compra" com base no histórico real
- [ ] Aeroportos alternativos na mesma cidade
- [ ] Painel de sazonalidade histórica (dados ANAC, multi-ano)
- [ ] Alerta de câmbio combinado com preço (rotas internacionais)
- [ ] Regras da tarifa (bagagem, remarcação) junto no alerta
- [ ] Reavaliação pós-compra (monitorar se caiu após já ter comprado)
- [ ] Recalibrar teto por perna (R$ 200) assim que houver preços reais de ida e volta separados

Detalhamento completo de decisões técnicas e histórico de revisão de escopo: `ROADMAP-AUDITORIA.md`.
