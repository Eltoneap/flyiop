# FlyIop

Monitor automático de passagens aéreas. Busca preços diariamente via Travelpayouts, compara com metas configuradas e avisa por Telegram quando encontra um bom preço ou uma alta preocupante.

Escopo completo em [escopo-projeto-passagens.md](escopo-projeto-passagens.md).

## Arquitetura

- **Site (`docs/`)** — estático (HTML/JS), hospedado no GitHub Pages, com login (Supabase Auth). É onde você cadastra rotas, metas e preferências, e acompanha o histórico de preços — de qualquer dispositivo.
- **Banco (Supabase/Postgres)** — guarda rotas, histórico de preços e preferências. Protegido por Row Level Security: só o seu usuário autenticado lê/grava seus dados.
- **Robô (`src/`)** — script Python rodado diariamente pelo GitHub Actions: lê as rotas no Supabase, consulta a Travelpayouts, grava o histórico de volta no Supabase e manda alerta no Telegram quando aplicável.

## Site

Acesse o GitHub Pages do repositório e faça login com o usuário criado no Supabase (Authentication → Users). Para rodar localmente:

```bash
python3 -m http.server --directory docs 5051
```

Abre em [http://localhost:5051/login.html](http://localhost:5051/login.html).

## Robô (Python)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # preencha com seus tokens (ver abaixo)
export $(cat .env | xargs)
python src/main.py
```

## Onde colocar cada token

| Token | Local (`.env`) | GitHub Actions (Secrets) |
|---|---|---|
| `TRAVELPAYOUTS_TOKEN` | ✅ | ✅ |
| `TELEGRAM_BOT_TOKEN` | ✅ | ✅ |
| `TELEGRAM_CHAT_ID` | ✅ | ✅ |
| `SUPABASE_URL` | ✅ | ✅ |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | ✅ |

A `SUPABASE_SERVICE_ROLE_KEY` é secreta (bypassa o RLS) — nunca vai no código do site, só nos Secrets/`.env`. A `anon key` usada em `docs/js/supabase-client.js` é pública por design (protegida pelo RLS de cada tabela).

## GitHub Actions

Cadastre os 5 secrets acima em Settings → Secrets and variables → Actions. O workflow [`daily.yml`](.github/workflows/daily.yml) roda todo dia às 08:00 (horário de Brasília) e também pode ser disparado manualmente na aba Actions.

## GitHub Pages

Settings → Pages → Source: **Deploy from a branch** → Branch: `main` → pasta `/docs`.
