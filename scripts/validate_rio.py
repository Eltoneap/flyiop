"""Parte 0 do plano "Alvo Fins de Semana": validação empírica do código de
cidade RIO na Travelpayouts, com o 1º alvo real da lista (04/09/2026, volta
06/09 ou 07/09) — perto o bastante pra ter chance real de cache, ao contrário
de testar direto em 2027.

Reusa o cliente v3 já em produção (src/travelpayouts_client.get_prices_for_dates),
não reimplementa a chamada HTTP. Roda sozinho: sem Supabase, sem Telegram.

Uso: python scripts/validate_rio.py
Sai com código 1 só se NENHUMA das 4 consultas retornar preço; qualquer outra
combinação sai com 0 — a decisão (RIO vs fallback GIG+SDU) é lida na tabela.
"""
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from travelpayouts_client import get_prices_for_dates  # noqa: E402

DEPARTURE_AT = "2026-09-04"  # sexta, 1º alvo real da lista de 66
RETURN_SUNDAY = "2026-09-06"
RETURN_MONDAY = "2026-09-07"

# (label, origin, return_at) — destino é sempre BSB (aeroporto único em Brasília).
CHECKS = [
    ("RIO→BSB, volta domingo", "RIO", RETURN_SUNDAY),
    ("RIO→BSB, volta segunda", "RIO", RETURN_MONDAY),
    ("GIG→BSB, volta domingo (controle)", "GIG", RETURN_SUNDAY),
    ("SDU→BSB, volta domingo (controle)", "SDU", RETURN_SUNDAY),
]


def cheapest(entries: list[dict]) -> dict | None:
    if not entries:
        return None
    return min(entries, key=lambda e: float(e["price"]))


def run_check(label: str, origin: str, return_at: str) -> dict:
    print(f"\n[{label}] origin={origin} destination=BSB departure_at={DEPARTURE_AT} return_at={return_at}")
    try:
        entries = get_prices_for_dates(
            origin, "BSB", "BRL", departure_at=DEPARTURE_AT, one_way=False
        )
    except Exception:
        print(f"[{label}] EXCEÇÃO:\n{traceback.format_exc()}")
        return {"label": label, "status": "erro", "price": None}

    # A API não filtra por return_at exato numa única chamada por variante
    # aqui — filtramos no cliente pra achar a entrada da variante testada.
    same_return = [e for e in entries if (e.get("return_at") or "")[:10] == return_at]
    best = cheapest(same_return) or cheapest(entries)

    if best is None:
        print(f"[{label}] resposta OK mas vazia ({len(entries)} entradas no total, nenhuma bate a data)")
        return {"label": label, "status": "vazio", "price": None}

    print(
        f"[{label}] mais barato: R$ {best['price']} · origin_airport={best.get('origin_airport')} · "
        f"destination_airport={best.get('destination_airport')} · departure_at={best.get('departure_at')} · "
        f"return_at={best.get('return_at')} · transfers={best.get('transfers')}"
    )
    print(f"[{label}] resposta bruta da entrada mais barata: {best}")
    return {"label": label, "status": "ok", "price": float(best["price"])}


def main() -> None:
    results = []
    for i, (label, origin, return_at) in enumerate(CHECKS):
        if i > 0:
            time.sleep(0.3)
        results.append(run_check(label, origin, return_at))

    print("\n=== RESUMO ===")
    print(f"{'consulta':<38} | {'status':<6} | preço")
    for r in results:
        price = f"R$ {r['price']}" if r["price"] is not None else "—"
        print(f"{r['label']:<38} | {r['status']:<6} | {price}")

    rio_ok = any(r["status"] == "ok" for r in results[:2])
    print(f"\nRIO respondeu: {'SIM' if rio_ok else 'NÃO'}")

    if all(r["status"] != "ok" for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
