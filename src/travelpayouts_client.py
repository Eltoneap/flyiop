import os
import requests

BASE_URL = "https://api.travelpayouts.com"


def get_month_matrix(
    origin: str, destination: str, currency: str = "BRL", trip_duration_weeks: int = 1
) -> list[dict]:
    """Preço de ida e volta por dia do mês (endpoint month-matrix).

    one_way=false pede preço de ida+volta; trip_duration define a duração
    da estadia em semanas. Sem isso a API devolve preço só de ida (default).
    """
    token = os.environ["TRAVELPAYOUTS_TOKEN"]
    resp = requests.get(
        f"{BASE_URL}/v2/prices/month-matrix",
        params={
            "origin": origin,
            "destination": destination,
            "currency": currency,
            "token": token,
            "one_way": "false",
            "trip_duration": trip_duration_weeks,
        },
        timeout=30,
    )
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
