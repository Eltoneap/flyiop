from datetime import datetime, timezone
from statistics import mean

from supabase_client import DEFAULT_SETTINGS
from telegram_notifier import hours_since_found


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


def staleness(found_at: str | None, freshness_hours_limit: float) -> tuple[bool, float | None]:
    """Portão de frescor (Etapa 2): (is_stale, idade_em_horas).

    found_at ausente/ilegível = idade desconhecida → tratado como velho
    (nunca como fresco). Com a fonte v3 (que não devolve found_at, mas garante
    cache ≤48h) a ausência é esperada — a mensagem vira informativa (cache_48h)
    e a política 'suppress' não se aplica (ver should_suppress_alert)."""
    age_hours = hours_since_found(found_at)
    return (age_hours is None or age_hours > freshness_hours_limit), age_hours


def should_suppress_alert(is_stale: bool, age_hours: float | None, settings: dict) -> bool:
    """Política 'suppress' segura o alerta de dado velho. Só vale no modo alerta —
    o resumo diário nunca é suprimido.

    Salvaguarda (Etapa 6): idade DESCONHECIDA não suprime — a fonte v3 nunca
    informa found_at, e suprimir nesse caso seguraria 100% dos alertas em
    silêncio. Só suprime quando a idade foi medida e passou do limite."""
    return (
        is_stale
        and age_hours is not None
        and settings.get("stale_alert_policy") == "suppress"
        and settings.get("notification_mode") != "daily_summary"
    )


def cooldown_blocks_alert(last_alert: dict | None, current_price: float, settings: dict) -> bool:
    """Etapa 3: não repetir o mesmo bom preço todo dia. True = segurar o alerta.

    Resumo diário nunca é afetado (sempre mostra tudo, não é alerta repetido).
    Sem alerta anterior → nunca segura (é o primeiro). Com alerta anterior →
    só segura se o preço NÃO caiu o suficiente E NÃO passou tempo suficiente
    desde o último envio. Reusada pelos alvos de fim de semana (weekends.py),
    não só pelas rotas flexíveis."""
    if settings.get("notification_mode") == "daily_summary":
        return False
    if last_alert is None:
        return False

    drop_pct = float(settings.get("realert_drop_pct") or DEFAULT_SETTINGS["realert_drop_pct"])
    cooldown_days = float(settings.get("realert_days") or DEFAULT_SETTINGS["realert_days"])

    last_price = float(last_alert["price"])
    threshold = last_price * (1 - drop_pct / 100)
    price_dropped_enough = current_price <= threshold

    sent_at = datetime.fromisoformat(last_alert["sent_at"])
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=timezone.utc)
    days_since = (datetime.now(timezone.utc) - sent_at).total_seconds() / 86400
    enough_time_passed = days_since >= cooldown_days

    return not (price_dropped_enough or enough_time_passed)


def is_suspicious_price(current_price: float, history_prices: list[float], threshold_pct: float) -> bool:
    """Autocheck anti-preço-fantasma (Etapa 4): preço absurdamente abaixo da
    média provavelmente é erro de dado, não achado real. Precisa de histórico
    mínimo (5 registros) pra ter uma média confiável — sem isso, não classifica
    (evita marcar as primeiras buscas de uma rota nova como suspeitas)."""
    if len(history_prices) < 5:
        return False
    avg = mean(history_prices)
    if avg <= 0:
        return False
    pct_below = (1 - current_price / avg) * 100
    return pct_below > threshold_pct


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
