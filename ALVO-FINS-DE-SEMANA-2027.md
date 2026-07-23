# FlyIop — Alvo real definido (22/07/2026): compra de fins de semana RIO→BSB em 2027

Este documento redefine o objetivo prático do FlyIop com base na necessidade concreta do usuário. Ele NÃO substitui o roadmap técnico (ROADMAP-AUDITORIA.md) nem o CLAUDE.md — ele dá a direção que reorganiza as prioridades das fases. Executar sempre pelo fluxo normal (Plan Mode → aprovação no chat de planejamento → teste local → push).

## O objetivo, em uma frase

Comprar passagem para (quase) todos os fins de semana de 2027, ida RIO (qualquer aeroporto) → BSB, ao longo do ano, monitorando cada fim de semana individualmente até o usuário marcar cada um como comprado.

## Especificação do alvo

- **Rota:** RIO (código de cidade — agrega GIG + SDU) → BSB. Confirmar que a API Travelpayouts aceita o código de cidade RIO; se não, monitorar GIG e SDU e consolidar o menor.
- **Padrão de cada fim de semana:**
  - Ida: sexta-feira
  - Volta: domingo à noite OU madrugada de segunda — o robô considera as duas e reporta a mais barata.
- **Período:** todos os fins de semana de sexta 29/01/2027 até sexta 03/12/2027 (volta 05/12). ~45 fins de semana.
  - **Atenção ao calendário:** validar cada data de sexta programaticamente (não presumir dia da semana). O primeiro é 29/01/2027 (sexta); o último embarque de ida é 03/12/2027 (sexta).
- **1 adulto, econômica** (como já é hoje).

## Modelo de dados (mudança central)

Cada fim de semana é um "alvo de compra" independente, não um resultado de varredura flexível. Sugestão de nova tabela `weekend_targets` (ou reutilizar `routes` com campos de data fixa — decisão do Code no plano):
- `id`, `outbound_date` (sexta), `return_date` (domingo ou segunda), `status` ('monitoring' | 'purchased'), `price_ceiling` (default 400), `lowest_seen`, `current_price`, `purchased_at` (nulo até comprar).
- Histórico de preços por alvo: cada alvo tem sua própria série temporal (resolve de vez o problema antigo de "vencedor que muda de mês" — aqui as datas são fixas, cada uma comparada só consigo mesma).

## Lógica de monitoramento (varredura diária sem virar ruído)

- O robô varre **todos os alvos com status 'monitoring'** diariamente (~45 consultas/dia no pico — dentro do limite da API de 600/min com folga), considerando ida sexta + as duas voltas possíveis (domingo/segunda), gravando o menor preço de cada alvo no histórico.
- Alvos com status 'purchased' saem da varredura (não consomem chamada nem geram ruído).

## Notificações (as duas regras convivem)

1. **Alerta de teto (compra imediata):** preço do alvo ≤ `price_ceiling` (default R$ 400) → avisa no Telegram na hora. Como o objetivo é comprar de qualquer jeito abaixo do teto, esse alerta é prioritário e direto ("bom preço, compre e marque como comprado").
   - Mesmo após avisar, **continua monitorando** aquele alvo (o usuário pode querer esperar cair mais) — só para quando o usuário marcar como comprado.
   - Cooldown se aplica (não repetir o mesmo alerta idêntico todo dia; reavisar só se cair mais X% ou após Y dias — reusar lógica da Etapa 3).
2. **Alerta de oportunidade (relativo):** mesmo acima do teto, se um alvo cair significativamente vs. o próprio histórico → avisa como "oportunidade" (útil para fins de semana caros que talvez nunca cheguem a R$ 400, ex: carnaval/feriados).
3. **Resumo semanal (não diário):** um panorama consolidado 1x por semana com todos os alvos ainda em 'monitoring' — preço atual, menor já visto, quantos faltam comprar. Evita bombardeio diário.

## Painel de compras (nova aba no site)

- Tabela com todos os ~45 fins de semana: data ida/volta, preço atual, menor preço já visto, status, e botão **"Marquei como comprado"**.
- Ao marcar como comprado: alvo sai da varredura e vai para o fim da lista (ou seção "já comprados").
- Indicador de progresso: "X de 45 comprados".
- Teto de preço editável no site: global (todos) e individual por fim de semana (para ajustar datas caras/especiais como aniversários de família ou feriados).
- Sinalização proativa: se um alvo nunca chegou perto do teto após algumas semanas, sugerir revisão do teto daquele alvo.

## Como isso reorganiza o roadmap existente

- **Etapa 5 (janela dupla):** o problema que a motivava (histórico misturando meses) some com datas fixas. A janela curta/longa deixa de ser prioridade — pode ser adiada ou descartada para este caso de uso. **Trazer ao chat de planejamento antes de mexer.**
- **Etapa C1 (modo data fixa):** vira o coração do projeto agora, não item futuro. É a base deste alvo.
- **Etapa C3 (código de cidade):** necessária já (RIO agrega GIG+SDU).
- **A6 (filtro por dia da semana):** parcialmente absorvido — aqui as datas já são fixas (sexta/domingo/segunda), então o filtro por dia da semana é intrínseco ao alvo, não um filtro adicional.
- **B5 (melhor antecedência de compra):** fica mais rico com este modelo (cada alvo acumula histórico próprio ao longo de 2026-2027), mas não é bloqueante. Futuro.

## Fora de escopo (mantido)

- Bagagem/tarifa completa, milhas automáticas, emissão automática — inalterados.
- Fast-flights só como confirmação pontual A5, quando implementado.

## Pendências de calendário a validar no plano

- Gerar programaticamente a lista das ~45 sextas de 29/01 a 03/12/2027 e suas voltas (domingo e segunda), conferindo dia da semana de cada uma — não presumir.
- Confirmar suporte da API ao código de cidade RIO.
