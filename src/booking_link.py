def google_flights_link(origin: str, destination: str, flight_date: str) -> str:
    """Link do Google Flights pré-filtrado (rota + data), ida e volta, 1 adulto econômica."""
    query = f"Flights to {destination} from {origin} on {flight_date}"
    return f"https://www.google.com/travel/flights?q={query.replace(' ', '%20')}"
