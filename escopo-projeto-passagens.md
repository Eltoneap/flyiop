# Projeto: FlyIop — Monitor Automático de Passagens Aéreas

## Objetivo
Sistema pessoal que pesquisa preços de passagens diariamente em 2-4 rotas, compara com metas definidas pelo usuário e avisa via Telegram quando encontrar um bom preço ou uma tendência de alta preocupante.

## Escopo v1 (MVP)

### Rotas e busca
- 2 a 4 rotas configuráveis
- Fase 1 (atual): sem data fixa → menor preço nos próximos meses (usando Amadeus Flight Cheapest Date Search, 1 chamada por rota/dia)
- Fase 2 (a partir de out/nov): datas fixas, viagens a partir de fev/2027
- Ida e volta, 1 adulto, classe econômica

### Regra de "bom preço" (por rota, configurável)
- Valor fixo (ex: abaixo de R$ X) **e/ou**
- Percentual abaixo da média histórica da própria rota

### Detecção de tendência ruim
- Alerta se subir mais de 10% em 3 dias, ou mais de 15% em 7 dias (ajustável depois de calibrar com dados reais)

### Notificação
- Telegram (bot próprio, separado de outros bots existentes)
- Modo configurável: resumo diário **ou** só alerta (quando bate meta ou tendência de alta)
- Mensagem inclui link direto pré-filtrado (rota, data, passageiros) para o usuário confirmar e comprar manualmente

### Stack técnico
- Dados: **Travelpayouts Data API** (Aviasales) — endpoint `month-matrix` (preço mais barato por dia do mês) e `prices/cheap`. Cadastro gratuito e individual, sem exigência de volume mínimo. Dado vem de cache de até 7 dias — adequado pro nosso uso (tendência diária, não compra em tempo real).
  - ~~Amadeus Self-Service~~ — descartado: portal será descomissionado em 17/07/2026 (chaves desativadas, sem alternativa self-service pra pessoa física; só resta Enterprise, que exige contrato comercial)
  - Kiwi Tequila — descartado: acesso de produção via Travelpayouts exige projeto com 50.000+ usuários ativos/mês
  - Skyscanner API oficial — descartado: parceria comercial, não aceita uso não-comercial/baixo tráfego
- Agendamento: GitHub Actions (roda diariamente, sem custo)
- Histórico: CSV ou SQLite no próprio repositório
- Notificação: Bot do Telegram (**FlyIop**)

### Comparador milhas vs. dinheiro (personalizado)
- Usuário define quanto paga pelo próprio milheiro (cartão, clube, etc.)
- App calcula, pra cada busca, se compensa mais pagar em dinheiro ou usar milhas, com base no valor real do usuário (não numa média de mercado)

### Exportação de dados
- Exportar histórico de preços para CSV, com opção de integração futura com Google Sheets

### Compra
- **Não automatizada.** Risco de segurança (dados de cartão) e barreira estrutural (Amadeus Self-Service não permite emissão direta para pessoa física).
- Autofill de navegador/gerenciador de senhas cobre a maior parte da automação de preenchimento com segurança.

### Nota sobre scraping
- Scraping direto de sites de companhias/OTAs fica **fora do MVP**.
- Se entrar no futuro como fonte extra (bônus, não pilar central), será de forma simples e transparente — sem táticas de evasão de bloqueio (user-agents rotativos, atrasos para simular humano etc.), que representam risco maior de violação de Termos de Uso e exigem manutenção constante.

## Prontas para uso imediato (enquanto o app não fica pronto)
- Google Voos — monitoramento gratuito, "qualquer data", alerta por e-mail
- Skyscanner — segunda fonte de comparação
- HeyMiles — comparação dinheiro vs. milhas (Smiles/Latam Pass/Azul Fidelidade)

## Backlog (v2+, avaliar depois que o MVP estiver rodando)
- [ ] Aeroportos alternativos na mesma cidade
- [ ] Painel de sazonalidade histórica (dados ANAC, multi-ano) — lacuna real, nenhuma ferramenta pronta resolve
- [ ] Alerta de câmbio combinado com preço (rotas internacionais) — lacuna real
- [ ] Regras da tarifa (bagagem, remarcação) junto no alerta
- [ ] Reavaliação pós-compra (monitorar se caiu após já ter comprado)

## Pré-requisitos para começar a construir
1. Conta no Travelpayouts (programa de afiliados) → obter token de acesso à Data API
2. Bot no Telegram (via @BotFather) → token + chat_id
3. Conta no GitHub → repositório para hospedar o script e o agendamento

## Status
Escopo fechado em 12/07/2026. Pré-requisitos concluídos em 13/07/2026: conta Travelpayouts + token, bot Telegram (FlyIopBot) + chat_id, repositório `flyiop` no GitHub (privado). Pronto para início da construção do script.
