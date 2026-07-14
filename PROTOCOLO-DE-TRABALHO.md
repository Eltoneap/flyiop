# Protocolo de Trabalho — FlyIop

## Status Atual

_Verificado em 14/07/2026 direto no código e na infraestrutura real — não no que o `escopo-projeto-passagens.md` previa._

### Arquitetura em produção

- **Fonte de dados**: Travelpayouts Data API (`v2/prices/month-matrix`), ida e volta (`one_way=false`), varrendo os próximos 6 meses de calendário por rota a cada execução (até 18 chamadas/dia com as 3 rotas atuais).
- **Banco de dados**: Supabase (Postgres na nuvem), não SQLite/CSV. Tabelas: `routes`, `price_history`, `settings`, `bot_state`. Todas com Row Level Security.
- **Site**: estático em `docs/`, hospedado no GitHub Pages, login via Supabase Auth. Duas telas: Dashboard (histórico, gráfico, badge de status, aviso de janela de compra) e Configurações (CRUD de rotas com busca de aeroportos por nome/cidade, abas de rotas ativas/arquivadas, preferências de tendência e milhas).
- **Automação**: dois workflows do GitHub Actions —
  - `daily.yml`: roda 1x/dia (08:00 BRT), busca preços e grava no Supabase, dispara alerta no Telegram quando aplicável
  - `bot_commands.yml`: roda a cada 5 min, escuta comandos recebidos no Telegram (`/status`, `/precos`, `/rotas`) e responde sob demanda com o estado atual das rotas ativas
- **Repositório**: público (`github.com/Eltoneap/flyiop`) — necessário para GitHub Pages gratuito.

### Funciona e foi testado ponta a ponta

- Busca de preço real (ida e volta) → gravação no Supabase → avaliação de meta/tendência → alerta no Telegram
- Login no site, cadastro/edição/arquivamento de rotas, gráfico de histórico no Dashboard
- Detecção de tendência de alta **e** queda (mesmo limiar configurado, nas duas direções)
- Aviso de janela de compra: regra geral (pesquisa de mercado) até haver histórico suficiente; depois disso, cálculo dinâmico com o histórico real da própria rota

### Limitações e funcionalidades "mortas" conhecidas

- **Comparador de milhas (`miles.py`)**: código correto, mas nunca recebe dado real — a Travelpayouts não retorna campo de milhas nesse endpoint. Sempre cai no caminho "sem opção em milhas para comparar".
- **Exportação CSV**: não implementada (estava no escopo original).
- **Link de compra**: usa busca genérica do Google Flights (rota + data); não codifica número de passageiros nem garante abrir como ida-e-volta.
- **Cobertura de dados por rota é desigual**: RIA→BSB e GIG→BSB não retornam nenhum preço (nem ida e volta, nem só ida) — limitação de cache da Travelpayouts pra essas rotas específicas, não é bug.
- Pasta `data/` (SQLite/CSV do design antigo) ainda existe no repo, vazia, sem uso — não removida na migração para Supabase.

### Divergências do escopo original

Ver comparação detalhada entregue em 14/07/2026 (arquitetura de dados, frequência de chamadas, interface web inteira, comando sob demanda no Telegram, e mais — nenhuma dessas mudanças está refletida no texto do `escopo-projeto-passagens.md`, que continua descrevendo o plano original de 12/07/2026).

### Não implementado (backlog original, segue válido)

- Aeroportos alternativos na mesma cidade
- Painel de sazonalidade histórica com dados ANAC
- Alerta de câmbio combinado com preço
- Regras da tarifa (bagagem, remarcação) no alerta
- Reavaliação pós-compra
