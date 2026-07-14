import os
import requests

BASE_URL = "https://api.travelpayouts.com"


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

    resp = requests.get(f"{BASE_URL}/v2/prices/month-matrix", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("data", [])


def get_cheapest_prices(origin: str, destination: str, currency: str = "BRL") -> dict:
    """Preços mais baratos encontrados recentemente (endpoint prices/cheap)."""
    token = os.environ["TRAVELPAYOUTS_TOKEN"]
    resp = requests.get(
        f"{BASE_URL}/v1/prices/cheap",
        params={
            "origin": origin,
            "destination": destination,
            "currency": currency,
            "token": token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("data", {})
