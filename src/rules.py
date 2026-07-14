from statistics import mean


def is_good_price(current_price: float, history_prices: list[float], target_price: float | None,
                   target_percent_below_avg: float | None) -> tuple[bool, str]:
    """Verifica se o preço atual bate a meta configurada (valor fixo e/ou % abaixo da média)."""
    reasons = []

    if target_price is not None and current_price <= target_price:
        reasons.append(f"abaixo da meta fixa (R$ {target_price})")

    if target_percent_below_avg is not None and history_prices:
        avg = mean(history_prices)
        threshold = avg * (1 - target_percent_below_avg / 100)
        if current_price <= threshold:
            pct_below = (1 - current_price / avg) * 100
            reasons.append(f"{pct_below:.1f}% abaixo da média histórica (R$ {avg:.2f})")

    return (len(reasons) > 0, "; ".join(reasons))


def detect_trend(history: list[tuple[str, float]], window_3d_pct: float, window_7d_pct: float) -> tuple[bool, str]:
    """Recebe histórico ordenado [(checked_at, price), ...] e detecta alta OU queda preocupante.

    Usa o mesmo limite percentual configurado para os dois sentidos: uma variação
    de X% pra cima é "tendência de alta", de X% pra baixo é "tendência de queda".
    """
    if len(history) < 2:
        return False, ""

    current_price = history[-1][1]
    reasons = []

    for days, threshold_pct in ((3, window_3d_pct), (7, window_7d_pct)):
        past_prices = [p for _, p in history[:-1]]
        if not past_prices:
            continue
        reference_price = past_prices[max(0, len(past_prices) - days)]
        if reference_price <= 0:
            continue
        change_pct = (current_price - reference_price) / reference_price * 100
        if abs(change_pct) >= threshold_pct:
            direction = "alta" if change_pct > 0 else "queda"
            reasons.append(f"{change_pct:+.1f}% em {days} dias (tendência de {direction})")

    return (len(reasons) > 0, "; ".join(reasons))
