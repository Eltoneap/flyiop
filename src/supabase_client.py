import os
from datetime import date, datetime, timedelta, timezone

import requests

DEFAULT_SETTINGS = {
    "window_3d_pct": 10,
    "window_7d_pct": 15,
    "notification_mode": "alert_only",
    "cost_per_thousand_brl": 25,
    "freshness_hours": 24,
    "stale_alert_policy": "warn",  # 'warn' = alerta com aviso; 'suppress' = segura o alerta
    "realert_drop_pct": 5,
    "realert_days": 3,
    "suspicious_below_avg_pct": 50,
    "weekend_opportunity_pct": 15,
    "fast_flights_enabled": True,
    "fast_flights_daily_batch_size": 20,
}

DEFAULT_SYSTEM_CONFIG = {
    "suspicious_below_avg_pct": 50,
    "fast_flights_enabled": True,
    "fast_flights_daily_batch_size": 20,
    # Fallback, NÃO fonte de verdade — usado só se a leitura de system_config
    # falhar ou a chave ainda não existir (código subiu antes do SQL). Fonte
    # de verdade é sql/fatia_d1_janela_compra_telegram.sql, coluna
    # weekend_buying_cutoff_date. Mantém o filtro de janela ativo mesmo
    # degradado — nunca deixa o Telegram voltar a alertar/contar as 132
    # pernas inteiras em silêncio (main.py avisa quando cai aqui).
    "weekend_buying_cutoff_date": "2027-01-29",
}


def _headers() -> dict:
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _url(path: str) -> str:
    base = os.environ["SUPABASE_URL"].rstrip("/")
    return f"{base}/rest/v1/{path}"


def get_routes() -> list[dict]:
    resp = requests.get(_url("routes?select=*&archived=eq.false"), headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_settings(user_id: str) -> dict | None:
    resp = requests.get(_url(f"settings?user_id=eq.{user_id}&select=*"), headers=_headers(), timeout=30)
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None


def get_all_settings() -> list[dict]:
    """Todos os usuários registrados, ordenados por user_id — `settings` é o
    registro de usuários do sistema (é a mesma tabela que a view
    `weekend_leg_effective` usa no cross join). Deliberadamente NÃO derivado de
    `routes`: usuário sem rota flexível cadastrada continua sendo usuário, e as
    pernas de fim de semana não podem ficar reféns de existir alguma rota
    (Etapa 4.2, pendência 7)."""
    params = {"select": "*", "order": "user_id.asc"}
    resp = requests.get(_url("settings"), headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_system_config() -> dict | None:
    # select explícito das colunas (não select=*): id/updated_at
    # contaminariam o merge com settings em main.py.
    resp = requests.get(
        _url(
            "system_config?select=suspicious_below_avg_pct,fast_flights_enabled,"
            "fast_flights_daily_batch_size,weekend_buying_cutoff_date&limit=1"
        ),
        headers=_headers(), timeout=30,
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None


def insert_price(route_id: str, flight_date: str, price: float, currency: str,
                 return_date: str | None = None, found_at: str | None = None,
                 stops: int | None = None, days_ahead: int | None = None) -> None:
    payload = {
        "route_id": route_id,
        "flight_date": flight_date,
        "price": price,
        "currency": currency,
        "return_date": return_date,
        "found_at": found_at,
        "stops": stops,
        "days_ahead": days_ahead,
    }
    resp = requests.post(_url("price_history"), headers=_headers(), json=payload, timeout=30)
    resp.raise_for_status()


def get_price_history(route_id: str, days: int | None = None) -> list[dict]:
    params = {
        "route_id": f"eq.{route_id}",
        "select": "checked_at,price",
        "order": "checked_at.asc",
    }
    if days is not None:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        params["checked_at"] = f"gte.{since}"
    resp = requests.get(_url("price_history"), headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_latest_price_full(route_id: str) -> dict | None:
    """Última linha completa do histórico (todas as colunas), para o /status."""
    params = {
        "route_id": f"eq.{route_id}",
        "select": "*",
        "order": "checked_at.desc",
        "limit": 1,
    }
    resp = requests.get(_url("price_history"), headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None


def insert_run_log(route_id: str, outcome: str, price: float | None = None, detail: str | None = None) -> None:
    """Registra o resultado de uma rota em uma execução: 'ok', 'no_data' ou 'error'."""
    payload = {"route_id": route_id, "outcome": outcome, "price": price, "detail": detail}
    resp = requests.post(_url("run_log"), headers=_headers(), json=payload, timeout=30)
    resp.raise_for_status()


def get_recent_run_outcomes(route_id: str, limit: int = 30) -> list[str]:
    """Outcomes mais recentes da rota (desc), para detectar sequência sem cobertura."""
    params = {
        "route_id": f"eq.{route_id}",
        "select": "outcome",
        "order": "ran_at.desc",
        "limit": limit,
    }
    resp = requests.get(_url("run_log"), headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return [r["outcome"] for r in resp.json()]


def insert_alert_log(route_id: str, price: float, reason: str | None, *,
                     is_ceiling_alert: bool, is_opportunity_alert: bool,
                     user_id: str | None) -> None:
    """Registra um alerta efetivamente enviado (Etapa 3), pra calcular o cooldown.

    `is_ceiling_alert`/`is_opportunity_alert` (Fatia D2, 13/08/2026):
    keyword-only e sem default de propósito — sem isso seria possível
    adicionar um caminho de gravação novo e esquecer de classificar o
    alerta, a mesma classe de bug que esta fatia corrige. Cooldown de rota
    (`get_last_alert`) continua por `route_id` só, fora do escopo da D2; as
    colunas são gravadas aqui por consistência de schema com `alert_log` de
    perna, não porque o cooldown de rota as use ainda.

    `user_id` (Fatia D3, 14/08/2026): keyword-only e sem default, mesmo
    motivo acima. Linha de ROTA tem dono trivial — `routes.user_id`, que o
    chamador passa direto do dict da rota. A coluna é nullable no banco e
    NÃO tem CHECK: um `None` aqui grava `null` e o insert continua aceito,
    de propósito (o insert acontece DEPOIS de a mensagem do Telegram já ter
    saído — constraint que rejeita insert derrubaria a execução nesse
    ponto; ver `sql/fatia_d3_user_id_alert_log.sql`). O cooldown de rota
    NÃO passa a filtrar por usuário nesta fatia — isso é D4."""
    payload = {
        "route_id": route_id, "price": price, "reason": reason,
        "is_ceiling_alert": is_ceiling_alert, "is_opportunity_alert": is_opportunity_alert,
        "user_id": user_id,
    }
    resp = requests.post(_url("alert_log"), headers=_headers(), json=payload, timeout=30)
    resp.raise_for_status()


def get_last_alert(route_id: str) -> dict | None:
    """Último alerta enviado da rota (mais recente), para a regra de cooldown."""
    params = {
        "route_id": f"eq.{route_id}",
        "select": "sent_at,price",
        "order": "sent_at.desc",
        "limit": 1,
    }
    resp = requests.get(_url("alert_log"), headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None


def get_monitoring_weekends() -> list[dict]:
    """Weekends com pelo menos uma perna possivelmente ainda válida —
    filtro por `return_monday` (a data mais tardia possível do weekend, D+1
    de margem), não por `outbound_date`: expirar pela ida cortava a perna de
    volta 2-3 dias antes da própria data dela (Parte 9, 28/07/2026). A
    expiração fina por perna (ida vs. volta, cada uma com sua própria data)
    acontece depois, em `get_active_legs` (weekends.py)."""
    cutoff = (date.today() - timedelta(days=1)).isoformat()
    params = {
        "return_monday": f"gte.{cutoff}",
        "select": "id,outbound_date,return_sunday,return_monday",
        "order": "outbound_date.asc",
    }
    resp = requests.get(_url("weekends"), headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_weekend(weekend_id: str) -> dict | None:
    """Weekend por id, sem filtro de data — usado pra montar a data do pacote
    (regra 4, Parte 4) mesmo se a perna irmã já foi comprada/expirou."""
    params = {"id": f"eq.{weekend_id}", "select": "*"}
    resp = requests.get(_url("weekends"), headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None


def get_weekend_legs_by_weekend(weekend_id: str) -> list[dict]:
    """Todas as pernas do weekend, qualquer status — pra achar a perna irmã
    na comparação avulso×pacote mesmo se ela já foi comprada."""
    params = {"weekend_id": f"eq.{weekend_id}", "select": "*"}
    resp = requests.get(_url("weekend_legs"), headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_all_weekend_legs() -> list[dict]:
    """Todas as pernas (ida e volta), SEM filtro de status na consulta.

    Até a Etapa 4.2 esta função filtrava `status = 'monitoring'` no servidor,
    lendo `weekend_legs.status` — coluna que o painel parou de escrever nas
    pendências 3/4 (o estado passou a viver em `weekend_leg_user_state`). O
    filtro de status agora é o *status efetivo por usuário*, aplicado em
    `get_active_legs` (weekends.py) a partir de `weekend_leg_effective`.
    `weekend_legs.status` continua vindo na linha, mas só é usado no modo
    degradado (nenhum usuário em `settings`). O filtro de weekend expirado
    segue cruzado pelo chamador com get_monitoring_weekends."""
    params = {"select": "*"}
    resp = requests.get(_url("weekend_legs"), headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_effective_leg_state() -> list[dict]:
    """Estado efetivo por perna × usuário, da view `weekend_leg_effective`
    (Etapa 4.1). Uma linha por (perna, usuário registrado em `settings`).

    `price_ceiling` já vem resolvido pela view
    (`coalesce(override_do_usuario, settings.weekend_default_ceiling)`) e
    `status` já vem como `coalesce(estado_do_usuario, 'monitoring')` — ausência
    de linha em `weekend_leg_user_state` significa "segue o padrão", não
    "sem dado". Nenhum coalesce do lado da aplicação é necessário.

    O robô roda como `service_role`, que bypassa RLS: aqui vêm as linhas de
    TODOS os usuários, sem filtro (é intencional e está documentado em
    `sql/etapa4_1_estado_por_usuario.sql`). Quem colapsa isso para uma decisão
    por perna é `get_active_legs` (weekends.py).

    `outbound_date` (Fatia D1, 12/08/2026): acrescentado ao select — a view já
    expõe a coluna (`w.outbound_date`, sql/etapa4_1_estado_por_usuario.sql:394),
    nenhum grant novo é necessário. Usado por `get_weekend_leg_counts` (abaixo)
    para recortar o denominador pela janela de compra. `get_active_legs`
    (weekends.py) só lê `leg_id`/`status`/`price_ceiling` destas linhas — o
    campo extra é inerte para ela, as datas que ela usa vêm de
    `get_monitoring_weekends()`, não daqui."""
    params = {"select": "leg_id,user_id,price_ceiling,status,outbound_date"}
    resp = requests.get(_url("weekend_leg_effective"), headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def update_weekend_leg(leg_id: str, **fields) -> None:
    resp = requests.patch(_url(f"weekend_legs?id=eq.{leg_id}"), headers=_headers(), json=fields, timeout=30)
    resp.raise_for_status()


def insert_weekend_leg_price(leg_id: str, price: float, airport: str | None, variant: str | None,
                             source: str, transfers: int | None,
                             airline: str | None = None, departure_time: str | None = None) -> None:
    payload = {
        "leg_id": leg_id, "price": price, "airport": airport, "variant": variant,
        "source": source, "transfers": transfers,
        "airline": airline, "departure_time": departure_time,
    }
    resp = requests.post(_url("weekend_leg_price_history"), headers=_headers(), json=payload, timeout=30)
    resp.raise_for_status()


def get_weekend_leg_price_history(leg_id: str, days: int | None = None) -> list[dict]:
    params = {
        "leg_id": f"eq.{leg_id}",
        "select": "checked_at,price",
        "order": "checked_at.asc",
    }
    if days is not None:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        params["checked_at"] = f"gte.{since}"
    resp = requests.get(_url("weekend_leg_price_history"), headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def insert_weekend_alert_log(leg_id: str, price: float, reason: str | None, *,
                             is_ceiling_alert: bool, is_opportunity_alert: bool,
                             user_id: str | None) -> None:
    """Mesma tabela alert_log das rotas flexíveis (Etapa 3), só que via leg_id.

    `is_ceiling_alert`/`is_opportunity_alert` (Fatia D2, 13/08/2026):
    keyword-only e sem default — ver `insert_alert_log` acima, mesmo motivo.
    Um alerta composto (as duas razões concatenadas por `;` numa linha só,
    nunca duas linhas separadas) grava as duas flags `true`.

    `user_id` (Fatia D4, 15/08/2026): keyword-only e sem default, mesmo motivo.
    A D3 (14/08/2026) deixou esta chave FORA do payload de propósito, porque
    naquele momento não havia dono derivável para uma perna — o alerta saía de
    uma avaliação já colapsada por MIN de teto entre usuários. A D4 aposenta o
    MIN: a decisão passa a ser tomada POR USUÁRIO, e a linha registra
    exatamente qual usuário recebeu aquele alerta. Passa a ser a chave do
    cooldown, junto com `leg_id` e o tipo (`get_last_weekend_leg_alert`).

    Todo alerta de perna enviado pelo caminho normal grava aqui com `user_id`
    preenchido. O único caminho que NÃO chama esta função é o modo degradado
    (`perna sem dono`, nenhum usuário em `settings`): ele manda a mensagem e
    não grava, em vez de gravar NULL — gravar NULL criaria um terceiro
    significado para a coluna, indistinguível de "gravação de dono que falhou"
    do lado de cá da marca d'água da D3. A coluna segue nullable e sem CHECK no
    banco (o insert acontece DEPOIS de a mensagem já ter saído; constraint que
    rejeita insert derrubaria a execução nesse ponto)."""
    payload = {
        "leg_id": leg_id, "price": price, "reason": reason,
        "is_ceiling_alert": is_ceiling_alert, "is_opportunity_alert": is_opportunity_alert,
        "user_id": user_id,
    }
    resp = requests.post(_url("alert_log"), headers=_headers(), json=payload, timeout=30)
    resp.raise_for_status()


def insert_weekend_leg_run_log(leg_id: str, outcome: str, price: float | None = None,
                               source: str | None = None, detail: str | None = None) -> None:
    """Mesmo padrão do insert_run_log das rotas flexíveis, por perna de fim de semana."""
    payload = {"leg_id": leg_id, "outcome": outcome, "price": price, "source": source, "detail": detail}
    resp = requests.post(_url("weekend_leg_run_log"), headers=_headers(), json=payload, timeout=30)
    resp.raise_for_status()


def get_weekend_leg_counts(cutoff: str) -> tuple[int, int]:
    """(pernas dentro da janela de compra, quantas já compradas) — pro resumo
    semanal.

    Lê `weekend_leg_effective` (Etapa 4.2, pendência 13) em vez de
    `weekend_legs.status` — coluna congelada desde as pendências 3/4 (o painel
    passou a escrever status em `weekend_leg_user_state`, não mais em
    `weekend_legs`). `weekend_legs.status` sempre reportava 0 compradas.

    A view é perna × usuário (cross join com `settings`); uma perna conta como
    comprada só quando TODOS os usuários que a monitoram marcaram
    'purchased' — mesma regra de "sai da fila" da pendência 9, aplicada aqui
    ao complemento. Só existem dois estados hoje
    (`check (status in ('monitoring','purchased'))`,
    `sql/etapa4_1_estado_por_usuario.sql:91`), então checar `== 'purchased'`
    diretamente é seguro e explícito — nenhuma inferência por ausência.

    `cutoff` (Fatia D1, 12/08/2026): recorta pela `outbound_date` do fim de
    semana (âncora), pernas com `outbound_date < cutoff` não entram no total
    nem no numerador — mesma regra que `docs/js/dashboard.js` já aplica pro
    progresso/orçamento (renderProgresso/renderOrcamento) desde 28/07/2026.
    A COLETA não é afetada: esta função só monta o número do resumo semanal,
    não decide o que o robô consulta ou grava."""
    rows = [r for r in get_effective_leg_state() if r["outbound_date"] >= cutoff]
    legs: dict[str, list[str]] = {}
    for row in rows:
        legs.setdefault(row["leg_id"], []).append(row["status"])
    purchased = sum(1 for statuses in legs.values() if all(s == "purchased" for s in statuses))
    return len(legs), purchased


def get_last_weekend_leg_alert(leg_id: str, alert_type: str, user_id: str) -> dict | None:
    """Último alerta enviado da perna, DO TIPO PEDIDO e DAQUELE USUÁRIO.

    `alert_type` (Fatia D2, 13/08/2026): antes só filtrava por `leg_id`,
    deixando um alerta de teto segurar um de oportunidade e vice-versa (bug
    estrutural documentado em `STATE.md`, seção 2). Obrigatório e sem default,
    exatamente 'ceiling' ou 'opportunity' — a coluna filtrada é
    `is_ceiling_alert` ou `is_opportunity_alert`, sempre `is.true` (nunca
    `is.false`, que devolveria o último alerta que NÃO foi desse tipo, sem
    sentido pra cooldown).

    `user_id` (Fatia D4, 15/08/2026): obrigatório e NUNCA `None`. Só é chamada
    de dentro do laço por usuário; o modo degradado não entra nesse laço e por
    isso não precisa de um caminho com `None` aqui. O predicado é simples e
    permanente — `eq.{user_id}`, SEM `or user_id is null`: as linhas históricas
    com NULL são do usuário real, gravadas antes de a coluna existir, e
    casá-las com um filtro de "sem dono" suprimiria alerta com base em dado de
    outra era. Consequência aceita e prevista: na primeira execução após o
    deploy da D4, as linhas de perna anteriores ficam invisíveis ao cooldown e
    um alerta pode repetir uma vez (tamanho medido antes do deploy, bloco G0-Q4
    de `sql/fatia_d4_avaliacao_por_usuario.sql`)."""
    if alert_type == "ceiling":
        type_column = "is_ceiling_alert"
    elif alert_type == "opportunity":
        type_column = "is_opportunity_alert"
    else:
        raise ValueError(f"alert_type inválido: {alert_type!r} (esperado 'ceiling' ou 'opportunity')")
    params = {
        "leg_id": f"eq.{leg_id}",
        "user_id": f"eq.{user_id}",
        type_column: "is.true",
        "select": "sent_at,price",
        "order": "sent_at.desc",
        "limit": 1,
    }
    resp = requests.get(_url("alert_log"), headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None


def get_last_update_id() -> int:
    """Último update_id do Telegram já processado (evita reprocessar/reresponder mensagens antigas)."""
    resp = requests.get(
        _url("bot_state?key=eq.last_update_id&select=value"), headers=_headers(), timeout=30
    )
    resp.raise_for_status()
    rows = resp.json()
    return int(rows[0]["value"]) if rows else 0


def set_last_update_id(update_id: int) -> None:
    headers = {**_headers(), "Prefer": "resolution=merge-duplicates"}
    resp = requests.post(
        _url("bot_state"), headers=headers, json={"key": "last_update_id", "value": str(update_id)}, timeout=30
    )
    resp.raise_for_status()


def set_weekend_batch_blocked_at(iso: str) -> None:
    """Registra quando o detector de bloqueio do lote de consulta ao vivo
    disparou pela última vez (Parte 8) — lido pelo Dashboard em 'Saúde do
    sistema'. Mesmo padrão key-value de set_last_update_id."""
    headers = {**_headers(), "Prefer": "resolution=merge-duplicates"}
    resp = requests.post(
        _url("bot_state"), headers=headers,
        json={"key": "weekend_batch_blocked_at", "value": iso}, timeout=30,
    )
    resp.raise_for_status()


def get_last_successful_live_check() -> str | None:
    """ran_at do check mais recente com outcome='ok' e source='live' em
    weekend_leg_run_log — usado no diagnóstico do alerta de bloqueio
    (evaluate_and_record_leg_price, em weekends.py, já grava essas linhas
    em todo sucesso, cache ou live)."""
    resp = requests.get(
        _url("weekend_leg_run_log?outcome=eq.ok&source=eq.live&select=ran_at&order=ran_at.desc&limit=1"),
        headers=_headers(), timeout=30,
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0]["ran_at"] if rows else None


def get_weekend_block_streak() -> tuple[int, str | None]:
    """(dias consecutivos de bloqueio, data ISO de início da sequência atual)."""
    resp = requests.get(
        _url("bot_state?key=in.(weekend_block_streak_days,weekend_block_streak_started_at)&select=key,value"),
        headers=_headers(), timeout=30,
    )
    resp.raise_for_status()
    rows = {r["key"]: r["value"] for r in resp.json()}
    days = int(rows.get("weekend_block_streak_days") or 0)
    return days, rows.get("weekend_block_streak_started_at")


def set_weekend_block_streak(days: int, started_at: str | None) -> None:
    """Ajuste do usuário (24/07): ao zerar (days=0), apaga
    weekend_block_streak_started_at em vez de deixar a data antiga órfã no
    banco.

    Limitação conhecida (aceita, não resolvida agora): se o kill-switch for
    desligado no meio de uma sequência de bloqueio e religado depois, os dias
    pausados não contam — o contador só soma dias em que o lote realmente
    rodou e bateu bloqueio. A mensagem de recuperação ("normalizada depois de
    N dias") reflete dias de bloqueio real, não o tempo de calendário total."""
    headers = {**_headers(), "Prefer": "resolution=merge-duplicates"}
    resp = requests.post(
        _url("bot_state"), headers=headers,
        json={"key": "weekend_block_streak_days", "value": str(days)}, timeout=30,
    )
    resp.raise_for_status()
    if started_at is not None:
        resp2 = requests.post(
            _url("bot_state"), headers=headers,
            json={"key": "weekend_block_streak_started_at", "value": started_at}, timeout=30,
        )
        resp2.raise_for_status()
    elif days == 0:
        resp3 = requests.delete(
            _url("bot_state?key=eq.weekend_block_streak_started_at"), headers=_headers(), timeout=30,
        )
        resp3.raise_for_status()


WEEKEND_SCRAPE_STATE_KEYS = (
    "weekend_scrape_stage", "weekend_scrape_clean_days", "weekend_scrape_blocked_today",
    "weekend_scrape_last_change_at", "weekend_scrape_last_change_reason",
    "weekend_scrape_last_primary_run_date", "weekend_scrape_last_batch_run_date",
    "weekend_scrape_batches_run_today",
)


def get_weekend_scrape_state() -> dict:
    """Estado do escalonamento automático de frequência (Parte 10, 28/07/2026)
    — mesmo padrão key-value de weekend_block_streak_days, sem schema fixo
    novo. Defaults: Estágio 0, 0 dias limpos, sem bloqueio hoje.

    `last_primary_run_date`/`last_batch_run_date`/`batches_run_today`
    (correção de 30/07/2026, ver scrape_schedule.py): substituem a hora BRT
    exata como critério de "isso já rodou hoje" — sobrevivem a atraso de
    disparo do cron do GitHub Actions."""
    resp = requests.get(
        _url(f"bot_state?key=in.({','.join(WEEKEND_SCRAPE_STATE_KEYS)})&select=key,value"),
        headers=_headers(), timeout=30,
    )
    resp.raise_for_status()
    rows = {r["key"]: r["value"] for r in resp.json()}
    return {
        "stage": int(rows.get("weekend_scrape_stage") or 0),
        "clean_days": int(rows.get("weekend_scrape_clean_days") or 0),
        "blocked_today": (rows.get("weekend_scrape_blocked_today") or "false") == "true",
        "last_change_at": rows.get("weekend_scrape_last_change_at"),
        "last_change_reason": rows.get("weekend_scrape_last_change_reason"),
        "last_primary_run_date": rows.get("weekend_scrape_last_primary_run_date"),
        "last_batch_run_date": rows.get("weekend_scrape_last_batch_run_date"),
        "batches_run_today": int(rows.get("weekend_scrape_batches_run_today") or 0),
    }


def set_weekend_scrape_state(**fields) -> None:
    """Grava só as chaves passadas (stage/clean_days/blocked_today/
    last_change_at/last_change_reason/last_primary_run_date/
    last_batch_run_date/batches_run_today) — mesmo padrão merge-duplicates
    das outras funções de bot_state."""
    key_by_field = {
        "stage": "weekend_scrape_stage",
        "clean_days": "weekend_scrape_clean_days",
        "blocked_today": "weekend_scrape_blocked_today",
        "last_change_at": "weekend_scrape_last_change_at",
        "last_change_reason": "weekend_scrape_last_change_reason",
        "last_primary_run_date": "weekend_scrape_last_primary_run_date",
        "last_batch_run_date": "weekend_scrape_last_batch_run_date",
        "batches_run_today": "weekend_scrape_batches_run_today",
    }
    headers = {**_headers(), "Prefer": "resolution=merge-duplicates"}
    for field, value in fields.items():
        if field not in key_by_field or value is None:
            continue
        str_value = "true" if value is True else "false" if value is False else str(value)
        resp = requests.post(
            _url("bot_state"), headers=headers,
            json={"key": key_by_field[field], "value": str_value}, timeout=30,
        )
        resp.raise_for_status()
