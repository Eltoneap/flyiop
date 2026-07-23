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
    """Weekends cuja ida não passou — auto-expiração é este filtro
    (outbound_date >= hoje), não um status separado gravado por cron."""
    params = {
        "outbound_date": f"gte.{date.today().isoformat()}",
        "select": "id,outbound_date,return_sunday,return_monday",
        "order": "outbound_date.asc",
    }
    resp = requests.get(_url("weekends"), headers=_headers(), params=params, timeout=30)
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
                             source: str, transfers: int | None) -> None:
    payload = {
        "leg_id": leg_id, "price": price, "airport": airport, "variant": variant,
        "source": source, "transfers": transfers,
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
