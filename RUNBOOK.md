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
