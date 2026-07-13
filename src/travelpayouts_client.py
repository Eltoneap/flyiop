import os
import requests

BASE_URL = "https://api.travelpayouts.com"


def get_month_matrix(origin: str, destination: str, currency: str = "BRL") -> list[dict]:
    """Preço mais barato por dia do mês (endpoint month-matrix)."""
    token = os.environ["TRAVELPAYOUTS_TOKEN"]
    resp = requests.get(
        f"{BASE_URL}/v2/prices/month-matrix",
        params={
            "origin": origin,
            "destination": destination,
            "currency": currency,
            "token": token,
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
