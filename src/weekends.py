"""Alvo Fins de Semana RIO↔BSB — pernas desacopladas (revisão de 23/07/2026).

Ida e volta são alvos independentes ("pernas"): cada weekend gera uma perna
'outbound' (sexta, GIG/SDU→BSB) e uma perna 'return' (domingo OU segunda,
BSB→GIG/SDU, a mais barata das duas vence), cada uma com seu próprio preço,
histórico, teto e status de compra. Motivo da mudança: exigir ida+volta como
um evento único (o modelo anterior) multiplicava a raridade do cache — nem
o código de cidade RIO (que agrega GIG+SDU) trazia cobertura suficiente.

Busca por MÊS, one-way, GIG e SDU separados (não mais o código de cidade
RIO): cada perna consulta os dois aeroportos individualmente, na direção
certa (ida: aeroporto→BSB; volta: BSB→aeroporto), com departure_at em
granularidade de mês — a mesma lição da rodada anterior (data exata vem
sistematicamente vazia). O match com a data exata da perna é filtrado
localmente, sem tolerância de ±1 dia — bate exato ou fica "sem dado ainda"
(estado normal, não erro).

Agrupamento por (mês, aeroporto, direção): várias pernas compartilham a
mesma chave (todas as pernas 'outbound' de setembro, por exemplo), então
cada chave é buscada uma única vez e reusada — não uma chamada por perna.

Reusa direto as funções de decisão já testadas em produção (rules.py):
is_good_price (teto = meta fixa, oportunidade = % abaixo da média própria),
is_suspicious_price (autocheck anti-preço-fantasma) e cooldown_blocks_alert
(Etapa 3, aqui aplicado por perna via alert_log.leg_id).

Checkpoint da Parte 2 (23/07/2026): resultado real de produção conferido —
só 2 de 132 pernas bateram (cache insuficiente, mesmo padrão do RIO
round-trip). Por isso, desde a Parte 3 (live_check.py), esta busca cache
deixou de ser a fonte primária: o `fast_flights` (Google Flights) passou a
decidir `current_price`/alerta; esta busca continua rodando como conferidor
secundário (barata, ~64 consultas/dia), gravando com `source='cache'` via
a mesma `evaluate_and_record_leg_price` que o live-check usa.
"""
import time
import traceback
from datetime import date, datetime, timedelta, timezone

from rules import cooldown_blocks_alert, is_good_price, is_suspicious_price
from supabase_client import (
    DEFAULT_SETTINGS,
    get_all_weekend_legs,
    get_effective_leg_state,
    get_last_weekend_leg_alert,
    get_monitoring_weekends,
    get_weekend_leg_price_history,
    insert_weekend_leg_price,
    insert_weekend_leg_run_log,
    update_weekend_leg,
)
from travelpayouts_client import get_prices_for_dates

GIG = "GIG"
SDU = "SDU"
AIRPORTS = (GIG, SDU)
BSB = "BSB"
CURRENCY = "BRL"
REQUEST_DELAY_SECONDS = 0.3
MONTH_QUERY_LIMIT = 200  # a API ordena por preço, não por data — limite alto
# aumenta a chance da data exata da perna aparecer entre os resultados do mês.


def cheapest_entry(entries: list[dict]) -> dict | None:
    if not entries:
        return None
    return min(entries, key=lambda e: float(e["price"]))


def relevant_months(leg: dict) -> list[str]:
    """Meses (YYYY-MM) que precisam ser consultados pra essa perna.
    'outbound' tem 1 data só; 'return' pode ter domingo e segunda em meses
    diferentes se o fim de semana cair na virada do mês."""
    if leg["direction"] == "outbound":
        return [leg["outbound_date"][:7]]
    return sorted({leg["return_sunday"][:7], leg["return_monday"][:7]})


def date_candidates(leg: dict) -> list[tuple[str | None, str]]:
    """[(variante, data)] a checar pra essa perna. 'outbound' não tem
    variante (só existe 1 data possível); 'return' tem domingo e segunda."""
    if leg["direction"] == "outbound":
        return [(None, leg["outbound_date"])]
    return [("sunday", leg["return_sunday"]), ("monday", leg["return_monday"])]


def fetch_leg_month_entries(month: str, airport: str, direction: str) -> list[dict]:
    """Uma chamada por (mês, aeroporto, direção) — reusada por todas as
    pernas que compartilham essa combinação."""
    if direction == "outbound":
        origin, destination = airport, BSB
    else:
        origin, destination = BSB, airport
    return get_prices_for_dates(origin, destination, CURRENCY, departure_at=month, one_way=True, limit=MONTH_QUERY_LIMIT)


def match_leg_entries(entries: list[dict], target_date: str) -> dict | None:
    """Entre as entradas do mês, a mais barata cuja data de partida bate
    EXATAMENTE com a perna. Sem tolerância de data — match exato ou nada.
    One-way: a data relevante é sempre departure_at (não há return_at)."""
    matches = [e for e in entries if (e.get("departure_at") or "")[:10] == target_date]
    return cheapest_entry(matches)


def leg_expiry_date(leg: dict) -> str:
    """Última data em que essa perna, especificamente, ainda faz sentido
    monitorar: a própria data de ida, ou (pra volta) `return_monday` — o
    candidato mais tardio entre domingo/segunda, cobrindo os dois mesmo sem
    `current_variant` decidido ainda. Ida e volta expiram de forma
    independente (Parte 9, 28/07/2026) — antes, as duas expiravam junto pela
    data de ida do weekend, cortando a perna de volta 2-3 dias cedo demais."""
    if leg["direction"] == "outbound":
        return leg["outbound_date"]
    return leg["return_monday"]


# Diagnóstico da última carga de pernas, para o aviso único por execução em
# main.py. get_active_legs roda 2x por execução (varredura cache + lote fli) e
# recalcula os mesmos números nas duas — por isso o dict é sobrescrito, nunca
# acumulado: quem lê manda no máximo uma mensagem por condição.
LEG_LOAD_DIAGNOSTICS = {"degraded_no_settings": False, "multi_user_ceiling_legs": 0}


def resolve_effective_leg_state(state_rows: list[dict]) -> tuple[dict[str, float | None], int]:
    """Colapsa as linhas perna × usuário de `weekend_leg_effective` numa
    decisão por perna. Devolve ({leg_id: teto_efetivo}, nº de pernas onde mais
    de um usuário tinha teto).

    Duas regras, ambas já decididas na Etapa 4.2:

    - FILA (pendência 9): a perna fica na fila se PELO MENOS UM usuário ainda
      tem status efetivo 'monitoring'. Sai só quando TODOS decidiram outra
      coisa. Ausência de linha em `weekend_leg_user_state` já chega aqui como
      'monitoring' (a view faz o coalesce) — silêncio segue o padrão, e o
      padrão é continuar monitorando.
    - TETO (pendência 6/10): com mais de um usuário monitorando a mesma perna,
      vale o MENOR teto entre eles — quem tem o teto mais apertado dispara o
      alerta e puxa a perna pra cima na fila.

    ⚠️ REGRA PROVISÓRIA DA ETAPA 4.2. Colapsar N usuários num teto só existe
    porque o Telegram ainda é um canal único, sem fan-out. A Etapa 6 (alerta
    por perna × usuário, com cooldown/dedup e mensagem próprios de cada um)
    substitui este MIN por iteração de verdade — quando ela entrar, esta
    função deixa de fazer sentido. Não construir nada novo em cima dela.

    Usuário que já marcou a perna como comprada não entra no MIN: o teto dele
    não deve mais governar um alerta que só interessa a quem ainda monitora.
    Com um usuário só (cenário de hoje) as duas leituras coincidem."""
    rows_by_leg: dict[str, list[dict]] = {}
    for row in state_rows:
        rows_by_leg.setdefault(row["leg_id"], []).append(row)

    effective: dict[str, float | None] = {}
    multi_user_legs = 0
    for leg_id, rows in rows_by_leg.items():
        monitoring = [r for r in rows if r.get("status") == "monitoring"]
        if not monitoring:
            continue  # todos os usuários já decidiram outra coisa — sai da fila
        ceilings = [float(r["price_ceiling"]) for r in monitoring if r.get("price_ceiling") is not None]
        if len(ceilings) > 1:
            multi_user_legs += 1
        effective[leg_id] = min(ceilings) if ceilings else None
    return effective, multi_user_legs


def get_active_legs() -> list[dict]:
    """Pernas ainda monitoradas por pelo menos um usuário, cuja própria data
    (não a do weekend) ainda não passou de D+1 — expiração independente por
    perna (Parte 9). D+1 é folga de segurança: o robô roda 1x/dia, D0 puro
    arriscaria perder a checagem do próprio dia do voo por atraso de execução
    ou horário do voo já ter passado de manhã. Cada perna volta com as datas
    do weekend anexadas (prontas pro matching local) e com `effective_ceiling`
    — o teto efetivo, única fonte de teto do robô desde a Etapa 4.2.

    Modo degradado: se `weekend_leg_effective` vier vazia (nenhum usuário em
    `settings`), a fila cai no `weekend_legs.status` antigo e as pernas saem
    com `effective_ceiling = None` — grava preço e avalia oportunidade, mas
    sem comparação de teto. Nunca esvazia a fila em silêncio, e nunca inventa
    um teto: main.py avisa no Telegram."""
    cutoff = (date.today() - timedelta(days=1)).isoformat()
    weekends_by_id = {w["id"]: w for w in get_monitoring_weekends()}

    state_rows = get_effective_leg_state()
    effective, multi_user_legs = resolve_effective_leg_state(state_rows)
    degraded = not state_rows
    LEG_LOAD_DIAGNOSTICS["degraded_no_settings"] = degraded
    LEG_LOAD_DIAGNOSTICS["multi_user_ceiling_legs"] = multi_user_legs

    legs = []
    for leg in get_all_weekend_legs():
        weekend = weekends_by_id.get(leg["weekend_id"])
        if weekend is None:
            continue  # weekend já passou (nem a volta é mais válida) ou não existe mais
        if degraded:
            if leg.get("status") != "monitoring":
                continue
            ceiling = None
        else:
            if leg["id"] not in effective:
                continue  # nenhum usuário monitorando essa perna
            ceiling = effective[leg["id"]]
        merged = {
            **leg,
            "outbound_date": weekend["outbound_date"],
            "return_sunday": weekend["return_sunday"],
            "return_monday": weekend["return_monday"],
            "effective_ceiling": ceiling,
        }
        if leg_expiry_date(merged) < cutoff:
            continue  # essa perna específica já passou do D+1 dela
        legs.append(merged)
    return legs


def evaluate_and_record_leg_price(leg: dict, settings: dict, price: float, airport: str | None,
                                  variant: str | None, transfers: int | None, source: str,
                                  airline: str | None = None, departure_time: str | None = None) -> dict:
    """Núcleo compartilhado entre a varredura cache (process_weekend_leg, abaixo)
    e o lote fast-flights (live_check.py, Parte 3): grava o preço, avalia
    teto/oportunidade/suspeita/cooldown, e atualiza a perna. `source` é
    'cache' ou 'live' — desde a Parte 3, 'live' é a fonte primária (decide
    o current_price/alerta); 'cache' virou conferidor secundário, mas grava
    exatamente do mesmo jeito (histórico registra as duas fontes).
    `airline`/`departure_time` (Parte 9, 28/07/2026): só a fonte 'live' (fli)
    devolve esses campos — a Travelpayouts ('cache') não, ficam None ali."""
    leg_id = leg["id"]
    direction = leg["direction"]
    if direction == "outbound":
        leg_date = leg["outbound_date"]
    else:
        leg_date = leg["return_sunday"] if variant == "sunday" else leg["return_monday"]

    insert_weekend_leg_price(leg_id, price, airport, variant, source, transfers, airline, departure_time)

    history = get_weekend_leg_price_history(leg_id, days=90)
    history_prices = [float(h["price"]) for h in history]

    # Teto efetivo vindo de weekend_leg_effective (Etapa 4.2) — sem fallback
    # numérico: teto ausente é erro de dado (nenhum usuário em `settings`), não
    # caso pra mascarar com número inventado. Nesse caso a regra de teto sai de
    # cena (target_price=None) e só a de oportunidade decide; o aviso vai pro
    # Telegram uma vez por execução, em main.py.
    ceiling = leg.get("effective_ceiling")
    ceiling = float(ceiling) if ceiling is not None else None
    opportunity_pct = float(settings.get("weekend_opportunity_pct") or DEFAULT_SETTINGS["weekend_opportunity_pct"])
    good, reason = is_good_price(price, history_prices, ceiling, opportunity_pct)

    suspicious_threshold = float(
        settings.get("suspicious_below_avg_pct") or DEFAULT_SETTINGS["suspicious_below_avg_pct"]
    )
    suspicious = is_suspicious_price(price, history_prices, suspicious_threshold)

    would_alert = good and not suspicious
    cooldown_suppressed = False
    if would_alert:
        last_alert = get_last_weekend_leg_alert(leg_id)
        cooldown_suppressed = cooldown_blocks_alert(last_alert, price, settings)

    lowest_seen = leg.get("lowest_seen")
    is_new_low = lowest_seen is None or price < float(lowest_seen)
    update_fields = {
        "current_price": price,
        "current_airport": airport,
        "current_variant": variant,
        "current_source": source,
        "current_airline": airline,
        "current_departure_time": departure_time,
    }
    if is_new_low:
        update_fields["lowest_seen"] = price
        update_fields["lowest_seen_at"] = datetime.now(timezone.utc).isoformat()
    update_weekend_leg(leg_id, **update_fields)

    insert_weekend_leg_run_log(leg_id, "ok", price=price, source=source)

    variant_label = f", {variant}" if variant else ""
    ceiling_label = f"teto R$ {ceiling:.0f}" if ceiling is not None else "teto indisponível"
    print(f"[perna {direction} {leg['outbound_date']}] R$ {price:.2f} ({airport}{variant_label}, {source}) {ceiling_label}")

    return {
        "leg": leg,
        "status": "ok",
        "direction": direction,
        "weekend_id": leg["weekend_id"],
        "outbound_date": leg["outbound_date"],
        "price": price,
        "date": leg_date,
        "airport": airport,
        "variant": variant,
        "transfers": transfers,
        "source": source,
        "reason": reason,
        "is_ceiling_hit": ceiling is not None and price <= ceiling,
        "suspicious": suspicious,
        "should_alert": would_alert and not cooldown_suppressed,
    }


def process_weekend_leg(leg: dict, settings: dict, month_cache: dict) -> dict:
    """Filtra localmente as entradas já buscadas pra essa perna (1 ou 2 datas
    candidatas × 2 aeroportos) e delega a gravação/avaliação pra
    evaluate_and_record_leg_price (fonte 'cache')."""
    leg_id = leg["id"]
    direction = leg["direction"]
    label = f"perna {direction} {leg['outbound_date']}"

    found = []  # (airport, variant, date, entry)
    for airport in AIRPORTS:
        for month in relevant_months(leg):
            entries = month_cache.get((month, airport, direction))
            if not entries:
                continue
            for variant, target_date in date_candidates(leg):
                if target_date[:7] != month:
                    continue
                best = match_leg_entries(entries, target_date)
                if best is not None:
                    found.append((airport, variant, target_date, best))

    if not found:
        print(f"[{label}] sem dado ainda (nenhum match exato) — estado normal, não é erro")
        insert_weekend_leg_run_log(leg_id, "no_data")
        return {"leg": leg, "status": "no_data"}

    airport, variant, _matched_date, best = min(found, key=lambda f: float(f[3]["price"]))
    price = float(best["price"])
    transfers = best.get("transfers")

    return evaluate_and_record_leg_price(leg, settings, price, airport, variant, transfers, "cache")


def process_all_weekend_legs(settings: dict) -> list[dict]:
    """Varre todas as pernas ativas, agrupando as buscas por (mês, aeroporto,
    direção) — cada chave é buscada 1 vez e reusada pelas pernas que a
    compartilham. Falha ao buscar uma chave só afeta as pernas que dependem
    dela; falha ao processar uma perna não derruba as outras."""
    legs = get_active_legs()
    if not legs:
        return []

    fetch_keys = set()
    for leg in legs:
        for month in relevant_months(leg):
            for airport in AIRPORTS:
                fetch_keys.add((month, airport, leg["direction"]))

    month_cache: dict[tuple[str, str, str], list[dict] | None] = {}
    for i, key in enumerate(sorted(fetch_keys)):
        if i > 0:
            time.sleep(REQUEST_DELAY_SECONDS)
        month, airport, direction = key
        try:
            entries = fetch_leg_month_entries(month, airport, direction)
            month_cache[key] = entries
            print(f"[pernas {direction} {airport} {month}] {len(entries)} entradas")
        except Exception:
            print(f"[pernas {direction} {airport} {month}] ERRO ao buscar:\n{traceback.format_exc()}")
            month_cache[key] = None

    reports = []
    for leg in legs:
        label = f"perna {leg['direction']} {leg['outbound_date']}"
        needed_keys = [(month, airport, leg["direction"]) for month in relevant_months(leg) for airport in AIRPORTS]
        try:
            if all(month_cache.get(k) is None for k in needed_keys):
                raise RuntimeError("todas as buscas necessárias falharam")
            reports.append(process_weekend_leg(leg, settings, month_cache))
        except Exception:
            detail = traceback.format_exc()[-500:]
            print(f"[{label}] ERRO:\n{detail}")
            try:
                insert_weekend_leg_run_log(leg["id"], "error", detail=detail)
            except Exception:
                print(f"[{label}] falha também ao gravar weekend_leg_run_log")
            reports.append({"leg": leg, "status": "error"})
    return reports
