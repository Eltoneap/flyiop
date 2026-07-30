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


def insert_alert_log(route_id: str, price: float, reason: str | None = None) -> None:
    """Registra um alerta efetivamente enviado (Etapa 3), pra calcular o cooldown."""
    payload = {"route_id": route_id, "price": price, "reason": reason}
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


def get_monitoring_legs() -> list[dict]:
    """Todas as pernas com status 'monitoring' (ida ou volta) — o filtro de
    weekend expirado é cruzado pelo chamador com get_monitoring_weekends."""
    params = {"status": "eq.monitoring", "select": "*"}
    resp = requests.get(_url("weekend_legs"), headers=_headers(), params=params, timeout=30)
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


def insert_weekend_alert_log(leg_id: str, price: float, reason: str | None = None) -> None:
    """Mesma tabela alert_log das rotas flexíveis (Etapa 3), só que via leg_id."""
    payload = {"leg_id": leg_id, "price": price, "reason": reason}
    resp = requests.post(_url("alert_log"), headers=_headers(), json=payload, timeout=30)
    resp.raise_for_status()


def insert_weekend_leg_run_log(leg_id: str, outcome: str, price: float | None = None,
                               source: str | None = None, detail: str | None = None) -> None:
    """Mesmo padrão do insert_run_log das rotas flexíveis, por perna de fim de semana."""
    payload = {"leg_id": leg_id, "outcome": outcome, "price": price, "source": source, "detail": detail}
    resp = requests.post(_url("weekend_leg_run_log"), headers=_headers(), json=payload, timeout=30)
    resp.raise_for_status()


def get_weekend_leg_counts() -> tuple[int, int]:
    """(total de pernas cadastradas, quantas já compradas) — pro resumo semanal."""
    resp = requests.get(_url("weekend_legs?select=status"), headers=_headers(), timeout=30)
    resp.raise_for_status()
    rows = resp.json()
    return len(rows), sum(1 for r in rows if r["status"] == "purchased")


def get_last_weekend_leg_alert(leg_id: str) -> dict | None:
    params = {
        "leg_id": f"eq.{leg_id}",
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
)


def get_weekend_scrape_state() -> dict:
    """Estado do escalonamento automático de frequência (Parte 10, 28/07/2026)
    — mesmo padrão key-value de weekend_block_streak_days, sem schema fixo
    novo. Defaults: Estágio 0, 0 dias limpos, sem bloqueio hoje."""
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
    }


def set_weekend_scrape_state(**fields) -> None:
    """Grava só as chaves passadas (stage/clean_days/blocked_today/
    last_change_at/last_change_reason) — mesmo padrão merge-duplicates das
    outras funções de bot_state."""
    key_by_field = {
        "stage": "weekend_scrape_stage",
        "clean_days": "weekend_scrape_clean_days",
        "blocked_today": "weekend_scrape_blocked_today",
        "last_change_at": "weekend_scrape_last_change_at",
        "last_change_reason": "weekend_scrape_last_change_reason",
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
