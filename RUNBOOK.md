# Runbook — operações manuais

Procedimentos manuais que não têm UI própria. Config de sistema
(`system_config`) só é editável via SQL Editor do Supabase — ver
`CLAUDE.md`/`PLANO-ATIVO.md` (Etapa 3, iniciativa multi-usuário) para o
contexto de por que essas 3 colunas saíram do formulário de Configurações.

Caminho do SQL Editor: **Supabase → projeto FlyIop → SQL Editor.**

## Kill-switch (lote diário de consulta ao vivo — Google Flights)

**Alerta de bloqueio no Telegram: normalmente não requer ação.** O sistema
já reverte sozinho pro Estágio 0 e zera a contagem de dias limpos. Agir só
se houver bloqueio em 3 dias seguidos, ou se o próprio alerta indicar
escalada.

Ver estado atual:
```sql
select * from system_config;
```

Desligar (pausa completamente o lote fli; rotas flexíveis e o cache
Travelpayouts continuam rodando sozinhos):
```sql
update system_config set fast_flights_enabled = false, updated_at = now();
```
Efeito no próximo ciclo (próxima execução do `daily.yml`).

Religar:
```sql
update system_config set fast_flights_enabled = true, updated_at = now();
```
**Religar não devolve o estágio anterior** — o escalonamento de frequência
volta pro Estágio 0 e sobe de novo pela regra normal (5 dias limpos por
estágio).

Conferir efeito: Dashboard → seção "Saúde do sistema".

## Radar de calendário (grade via SearchDates — descoberta de preço em lote)

**Kill-switch PRÓPRIO, separado do lote fli (`fast_flights_enabled`).** Nasce
`radar_enabled = false` — desligar o lote fli não desliga o radar e
vice-versa. Ligar exige rodar `sql/radar_calendario.sql` primeiro (schema)
e revisar V1-V3.

Ver estado atual:
```sql
select radar_enabled, radar_sweeps_per_day, radar_precision_max_per_run from system_config;
```

Ligar (depois do SQL rodado e do código em produção):
```sql
update system_config set radar_enabled = true, updated_at = now();
```

Desligar (volta a descoberta de preço 100% pro lote fli, regime 'price' pra
toda perna — nenhuma mudança de comportamento além dessa):
```sql
update system_config set radar_enabled = false, updated_at = now();
```

`radar_sweeps_per_day` (varreduras completas da grade por dia, default 2) e
`radar_precision_max_per_run` (candidatas de precisão/SearchFlights por
execução, default 10) seguem o mesmo padrão de `update`. Subir os dois é
decisão de chat de planejamento — cada varredura completa já custa ~20
requisições (4 direções × ~5 blocos de <=61 dias).

Alerta de anomalia de volume no Telegram ("Radar de calendário — anomalia de
volume") normalmente não requer ação — a próxima varredura tenta do zero.
Persistindo, considere desligar o radar por aqui até investigar.

## Outros ajustes de sistema

`suspicious_below_avg_pct` (limiar de preço suspeito) e
`fast_flights_daily_batch_size` (pernas checadas por dia) seguem o mesmo
padrão de `update`. Exemplo:
```sql
update system_config set fast_flights_daily_batch_size = 20, updated_at = now();
```
Lote acima de 20 pernas/dia é decisão de chat de planejamento, não operação
de rotina — não subir sozinho sem essa revisão.

## Consultar estágio do escalonamento automático (lote fli)

Ver estágio atual:
```sql
select value from bot_state where key = 'weekend_scrape_stage';
```

Nota: stage NÃO fica em `system_config` (só `suspicious_below_avg_pct`,
`fast_flights_enabled`, `fast_flights_daily_batch_size`) — fica em
`bot_state`, chave `weekend_scrape_stage`.

## Ambiente local (nota, não produção)

Em 02/08/2026 foi instalado `postgresql@16` via Homebrew na máquina do
usuário (não havia Postgres local) para reproduzir a verificação da Etapa
4.1 num cluster descartável, fora de produção. O cluster ficou em
`scratchpad/pgdata`, parado. Desfazer, se desejado:
```bash
brew uninstall postgresql@16
```
