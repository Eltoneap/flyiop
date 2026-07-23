"""Parte 0 do plano "Alvo Fins de Semana": validação empírica do código de
cidade RIO na Travelpayouts, com o 1º alvo real da lista (04/09/2026, volta
06/09 ou 07/09) — perto o bastante pra ter chance real de cache, ao contrário
de testar direto em 2027.

Reusa o cliente v3 já em produção (src/travelpayouts_client.get_prices_for_dates),
não reimplementa a chamada HTTP. Roda sozinho: sem Supabase, sem Telegram.

Duas rodadas: (1) data exata do 1º alvo real — o que o robô vai usar de fato;
(2) mês inteiro (YYYY-MM) — mais permissivo, isola "RIO não é aceito" de
"essa data exata não tem cache ainda" (útil porque a rodada 1 pode vir vazia
até nos controles GIG/SDU sem provar nada sobre o código de cidade).

Uso: python scripts/validate_rio.py
Sai com código 1 só se NENHUMA das 7 consultas retornar preço; qualquer outra
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
DEPARTURE_MONTH = "2026-09"  # mesmo mês, mas em granularidade YYYY-MM

# (label, origin, return_at) — destino é sempre BSB (aeroporto único em Brasília).
# Rodada 1: data exata do 1º alvo real (o que o robô dos alvos vai usar de fato).
CHECKS_EXACT_DATE = [
    ("RIO→BSB, volta domingo (data exata)", "RIO", RETURN_SUNDAY),
    ("RIO→BSB, volta segunda (data exata)", "RIO", RETURN_MONDAY),
    ("GIG→BSB, volta domingo (controle, data exata)", "GIG", RETURN_SUNDAY),
    ("SDU→BSB, volta domingo (controle, data exata)", "SDU", RETURN_SUNDAY),
]

# Rodada 2: mesmo mês em granularidade YYYY-MM (como as rotas flexíveis já
# consultam em produção) — teste mais permissivo, maior chance de achar cache,
# serve pra isolar "RIO não é aceito" de "essa data exata não tem cache ainda".
CHECKS_MONTH = [
    ("RIO→BSB, mês inteiro", "RIO"),
    ("GIG→BSB, mês inteiro (controle)", "GIG"),
    ("SDU→BSB, mês inteiro (controle)", "SDU"),
]


def cheapest(entries: list[dict]) -> dict | None:
    if not entries:
        return None
    return min(entries, key=lambda e: float(e["price"]))


def run_check(label: str, origin: str, return_at: str) -> dict:
    """Rodada 1: data exata (o que o robô dos alvos vai usar de fato)."""
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


def run_check_month(label: str, origin: str) -> dict:
    """Rodada 2: mês inteiro (YYYY-MM) — mais permissivo, maior chance de cache.
    Serve só pra isolar "RIO não é aceito pela API" de "essa data exata não
    tem cache ainda" (o mesmo teste rodado com GIG/SDU em data exata veio
    vazio também, então a rodada 1 sozinha não prova nada sobre o código)."""
    print(f"\n[{label}] origin={origin} destination=BSB departure_at={DEPARTURE_MONTH} (mês, sem return_at)")
    try:
        entries = get_prices_for_dates(
            origin, "BSB", "BRL", departure_at=DEPARTURE_MONTH, one_way=False
        )
    except Exception:
        print(f"[{label}] EXCEÇÃO:\n{traceback.format_exc()}")
        return {"label": label, "status": "erro", "price": None}

    best = cheapest(entries)
    if best is None:
        print(f"[{label}] resposta OK mas vazia (0 entradas no mês inteiro)")
        return {"label": label, "status": "vazio", "price": None}

    print(
        f"[{label}] mais barato do mês: R$ {best['price']} · departure_at={best.get('departure_at')} · "
        f"return_at={best.get('return_at')} · {len(entries)} entradas no total"
    )
    return {"label": label, "status": "ok", "price": float(best["price"])}


def main() -> None:
    print("=== Rodada 1: data exata (04/09/2026) ===")
    results_exact = []
    for i, (label, origin, return_at) in enumerate(CHECKS_EXACT_DATE):
        if i > 0:
            time.sleep(0.3)
        results_exact.append(run_check(label, origin, return_at))

    print("\n=== Rodada 2: mês inteiro (09/2026) ===")
    results_month = []
    for label, origin in CHECKS_MONTH:
        time.sleep(0.3)
        results_month.append(run_check_month(label, origin))

    all_results = results_exact + results_month

    print("\n=== RESUMO ===")
    print(f"{'consulta':<48} | {'status':<6} | preço")
    for r in all_results:
        price = f"R$ {r['price']}" if r["price"] is not None else "—"
        print(f"{r['label']:<48} | {r['status']:<6} | {price}")

    rio_exact_ok = any(r["status"] == "ok" for r in results_exact[:2])
    rio_month_ok = results_month[0]["status"] == "ok"
    print(f"\nRIO respondeu (data exata): {'SIM' if rio_exact_ok else 'NÃO'}")
    print(f"RIO respondeu (mês inteiro): {'SIM' if rio_month_ok else 'NÃO'}")

    if all(r["status"] != "ok" for r in all_results):
        sys.exit(1)


if __name__ == "__main__":
    main()
