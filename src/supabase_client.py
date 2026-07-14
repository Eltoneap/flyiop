import os
from datetime import datetime, timedelta, timezone

import requests


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
    resp = requests.get(_url("routes?select=*"), headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_settings(user_id: str) -> dict | None:
    resp = requests.get(_url(f"settings?user_id=eq.{user_id}&select=*"), headers=_headers(), timeout=30)
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None


def insert_price(route_id: str, flight_date: str, price: float, currency: str) -> None:
    payload = {"route_id": route_id, "flight_date": flight_date, "price": price, "currency": currency}
    resp = requests.post(_url("price_history"), headers=_headers(), json=payload, timeout=30)
    resp.raise_for_status()


def get_price_history(route_id: str, days: int | None = None) -> list[dict]:
    path = f"price_history?route_id=eq.{route_id}&select=checked_at,price&order=checked_at.asc"
    if days is not None:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        path += f"&checked_at=gte.{since}"
    resp = requests.get(_url(path), headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()
