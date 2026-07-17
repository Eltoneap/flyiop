import os
import time

import requests

BASE_URL = "https://api.travelpayouts.com"
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1.5, 3.0)  # espera antes da 2a e da 3a tentativa


def _get_with_retry(url: str, params: dict) -> requests.Response:
    """GET com retry/backoff em 429 (rate limit) e 5xx (instabilidade do servidor)."""
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
            resp.raise_for_status()
            return resp
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            retryable = status is None or status == 429 or status >= 500
            if not retryable or attempt == MAX_ATTEMPTS - 1:
                raise
            last_error = error
            time.sleep(BACKOFF_SECONDS[attempt])
    raise last_error  # inalcançável, mas satisfaz o type checker


def get_month_matrix(
    origin: str,
    destination: str,
    currency: str = "BRL",
    month: str | None = None,
    trip_duration_weeks: int | None = None,
    one_way: bool = False,
) -> list[dict]:
    """Preço por dia de um mês específico (endpoint month-matrix).

    `month` é documentado como obrigatório pela Travelpayouts (formato YYYY-MM-DD,
    primeiro dia do mês) — sem ele, o comportamento depende de um default não
    documentado da API. one_way=false pede preço de ida+volta; trip_duration
    define a duração da estadia em semanas (opcional — pedir uma duração exata
    reduz bastante a cobertura de dados em cache).
    """
    token = os.environ["TRAVELPAYOUTS_TOKEN"]
    params = {
        "origin": origin,
        "destination": destination,
        "currency": currency,
        "token": token,
        "one_way": "true" if one_way else "false",
    }
    if month is not None:
        params["month"] = month
    if trip_duration_weeks is not None:
        params["trip_duration"] = trip_duration_weeks

    resp = _get_with_retry(f"{BASE_URL}/v2/prices/month-matrix", params)
    return resp.json().get("data", [])


def get_prices_for_dates(
    origin: str,
    destination: str,
    currency: str = "BRL",
    departure_at: str | None = None,
    one_way: bool = False,
    limit: int = 30,
) -> list[dict]:
    """Preços mais baratos (endpoint v3 prices_for_dates, cache de até 48h).

    `departure_at` aceita YYYY-MM (mês flexível) ou YYYY-MM-DD (data exata) —
    o mesmo endpoint cobre a Fase 1 (sem data fixa) e a Fase 2 (data fixa).
    Com sorting=price o primeiro resultado já é o mais barato. Campos por
    entrada: price, departure_at, return_at, transfers, return_transfers, link.
    """
    token = os.environ["TRAVELPAYOUTS_TOKEN"]
    params = {
        "origin": origin,
        "destination": destination,
        "currency": currency,
        "token": token,
        "one_way": "true" if one_way else "false",
        "sorting": "price",
        "limit": limit,
    }
    if departure_at is not None:
        params["departure_at"] = departure_at

    resp = _get_with_retry(f"{BASE_URL}/aviasales/v3/prices_for_dates", params)
    return resp.json().get("data", [])
