from urllib.parse import quote


def _ddmm(iso_date: str) -> str:
    # "2026-07-31" -> "3107"
    return f"{iso_date[8:10]}{iso_date[5:7]}"


def aviasales_link(origin: str, destination: str, depart_date: str, return_date: str | None = None,
                   passengers: int = 1) -> str:
    """Deep-link de busca da Aviasales com as datas exatas (fonte real dos preços do robô)."""
    leg = f"{origin}{_ddmm(depart_date)}{destination}"
    if return_date:
        leg += _ddmm(return_date)
    return f"https://www.aviasales.com/search/{leg}{passengers}"


def google_flights_link(origin: str, destination: str, depart_date: str,
                        return_date: str | None = None) -> str:
    """Busca do Google Flights pré-preenchida; com return_date vira ida e volta."""
    query = f"Flights from {origin} to {destination} on {depart_date}"
    if return_date:
        query += f" through {return_date}"
    return f"https://www.google.com/travel/flights?q={quote(query)}"
