def compare_cash_vs_miles(cash_price: float, miles_required: int | None, cost_per_thousand_brl: float) -> str:
    """Compara pagar em dinheiro vs. usar milhas, com base no custo real do usuário por milheiro."""
    if not miles_required:
        return "sem opção em milhas para comparar"

    miles_cost_equivalent = miles_required / 1000 * cost_per_thousand_brl

    if miles_cost_equivalent < cash_price:
        savings = cash_price - miles_cost_equivalent
        return f"compensa usar milhas (equivale a R$ {miles_cost_equivalent:.2f}, economiza R$ {savings:.2f})"

    extra = miles_cost_equivalent - cash_price
    return f"compensa pagar em dinheiro (milhas equivaleriam a R$ {miles_cost_equivalent:.2f}, R$ {extra:.2f} a mais)"
