"""Etapa 0 do PLAN-VALIDACAO-CRUZADA.md: validação do fast-flights.

Prova que a consulta ao Google Flights via `fast-flights` funciona (a) na máquina
local e (b) no IP do runner do GitHub Actions, para as rotas reais monitoradas.
Roda sozinho: sem Supabase, sem Telegram, sem token da Travelpayouts.

Uso: python scripts/validate_fastflights.py
Sai com código 1 apenas se NENHUMA rota retornar preço (bloqueio sistemático
fica vermelho no Actions); qualquer outra combinação sai com 0 — a avaliação
fina (critério ≥2 de 3 rotas) é feita lendo a tabela impressa no final.
"""
import sys
import time
import traceback
from datetime import date, timedelta

from fast_flights import FlightQuery, create_query, get_flights

# Rotas ativas em produção (confirmadas com o usuário em 18/07/2026).
# RIA→BSB é a mais interessante: sem cobertura na Aviasales — o Google
# Flights tendo dado ali é sinal genuíno de fonte independente.
ROUTES = [
    ("BSB", "GIG"),
    ("GIG", "BSB"),
    ("RIA", "BSB"),
]

DAYS_AHEAD_DEPART = 90  # ~90 dias à frente, como especifica a Etapa 0
TRIP_LENGTH_DAYS = 7


def cheapest_result(results) -> dict | None:
    """Menor preço válido entre os itinerários retornados (preço 0 = indisponível)."""
    best = None
    for entry in results:
        price = getattr(entry, "price", 0)
        if not price:
            continue
        if best is None or price < best["price"]:
            legs = getattr(entry, "flights", []) or []
            best = {
                "price": price,
                "airlines": ", ".join(getattr(entry, "airlines", []) or []) or "?",
                "legs": len(legs),
            }
    return best


def check_route(origin: str, destination: str) -> dict:
    depart = (date.today() + timedelta(days=DAYS_AHEAD_DEPART)).isoformat()
    ret = (date.today() + timedelta(days=DAYS_AHEAD_DEPART + TRIP_LENGTH_DAYS)).isoformat()
    label = f"{origin} → {destination}"
    print(f"\n[{label}] ida {depart}, volta {ret} (ida e volta, 1 adulto, econômica, BRL)")

    query = create_query(
        flights=[
            FlightQuery(date=depart, from_airport=origin, to_airport=destination),
            FlightQuery(date=ret, from_airport=destination, to_airport=origin),
        ],
        trip="round-trip",
        seat="economy",
        currency="BRL",
        language="pt-BR",
    )

    started = time.monotonic()
    try:
        results = get_flights(query)
    except Exception:
        elapsed = time.monotonic() - started
        print(f"[{label}] EXCEÇÃO após {elapsed:.1f}s:\n{traceback.format_exc()}")
        return {"route": label, "status": "erro", "price": None, "latency": elapsed}

    elapsed = time.monotonic() - started
    best = cheapest_result(results)
    if best is None:
        print(f"[{label}] resposta OK mas sem nenhum preço ({elapsed:.1f}s, {len(list(results))} itinerários)")
        return {"route": label, "status": "vazio", "price": None, "latency": elapsed}

    print(
        f"[{label}] mais barato: R$ {best['price']} · {best['airlines']} · "
        f"{best['legs']} trecho(s) · {elapsed:.1f}s"
    )
    return {"route": label, "status": "ok", "price": best["price"], "latency": elapsed}


def main() -> None:
    print(f"Validação fast-flights — {date.today().isoformat()}")
    reports = [check_route(o, d) for o, d in ROUTES]

    print("\n=== RESUMO ===")
    print(f"{'rota':<12} | {'status':<6} | {'preço':<10} | latência")
    for r in reports:
        price = f"R$ {r['price']}" if r["price"] is not None else "—"
        print(f"{r['route']:<12} | {r['status']:<6} | {price:<10} | {r['latency']:.1f}s")

    ok_count = sum(1 for r in reports if r["status"] == "ok")
    print(f"\nRotas com preço: {ok_count}/{len(reports)}")
    if ok_count == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
