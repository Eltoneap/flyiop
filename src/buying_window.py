import json
import os

# Mesmas faixas usadas em docs/js/buying-window.js — pesquisa consolidada em jul/2026
# (Viaje na Viagem, Melhores Destinos, Exame). Mantenha os dois arquivos em sincronia.
DOMESTIC_WINDOW_DAYS = (30, 60)
INTERNATIONAL_WINDOW_DAYS = (60, 120)

_AIRPORTS_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "data", "airports.json")
_airports_by_iata: dict | None = None


def _load_airports() -> dict:
    global _airports_by_iata
    if _airports_by_iata is None:
        with open(_AIRPORTS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        _airports_by_iata = {a["iata"]: a for a in data}
    return _airports_by_iata


def is_domestic(origin: str, destination: str) -> bool:
    airports = _load_airports()
    o = airports.get(origin)
    d = airports.get(destination)
    return bool(o and d and o["country"] == "Brazil" and d["country"] == "Brazil")


def buying_window_days(origin: str, destination: str) -> tuple[int, int]:
    return DOMESTIC_WINDOW_DAYS if is_domestic(origin, destination) else INTERNATIONAL_WINDOW_DAYS
