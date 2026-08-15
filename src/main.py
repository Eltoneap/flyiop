import sys
import time
import traceback
from datetime import date

from rules import (
    cooldown_blocks_alert,
    detect_trend,
    evaluate_good_price,
    is_suspicious_price,
    should_suppress_alert,
    staleness,
)
from supabase_client import (
    DEFAULT_SETTINGS,
    DEFAULT_SYSTEM_CONFIG,
    get_all_settings,
    get_last_alert,
    get_price_history,
    get_recent_run_outcomes,
    get_routes,
    get_settings,
    get_system_config,
    get_weekend_leg_counts,
    get_weekend_scrape_state,
    insert_alert_log,
    insert_price,
    insert_run_log,
    insert_weekend_alert_log,
    set_weekend_scrape_state,
)
from telegram_notifier import (
    build_alert_message,
    build_buying_cutoff_fallback_message,
    build_multi_user_ceiling_message,
    build_no_effective_ceiling_message,
    build_route_block,
    build_shared_settings_message,
    build_stage_change_message,
    build_summary_message,
    build_weekend_alert_message,
    build_weekly_weekend_summary,
    send_message,
)
from live_check import build_package_comparison, run_daily_batch
from scrape_schedule import (
    apply_block_reversion,
    current_brt_date,
    evaluate_stage_transition,
    is_last_expected_batch,
    is_primary_run,
    record_batch_run,
    record_primary_run,
    should_run_live_batch,
)
from travelpayouts_client import get_prices_for_dates
from weekends import LEG_LOAD_DIAGNOSTICS, process_all_weekend_legs, resolve_buying_cutoff

MONTHS_AHEAD = 6  # varre de "em cima da hora" até ~6 meses à frente; o histórico aprende sozinho qual faixa é mais barata
REQUEST_DELAY_SECONDS = 0.3  # precaução contra possível limite de requisições da Travelpayouts
NO_COVERAGE_SUGGESTION_EVERY = 7  # sugere arquivar a cada N dias consecutivos sem cobertura


def _target_months(count: int = MONTHS_AHEAD) -> list[str]:
    today = date.today()
    months = []
    year, month = today.year, today.month
    for _ in range(count):
        months.append(date(year, month, 1).isoformat())
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def _to_float(value) -> float | None:
    return float(value) if value is not None else None


def entry_price(entry: dict) -> float:
    # month-matrix (v2) devolve o preço em "value"; prices/cheap (v1) em "price"
    value = entry.get("value", entry.get("price"))
    if value is None:
        raise KeyError(f"entrada sem preço reconhecível: {entry}")
    return float(value)


def cheapest_entry(month_matrix: list[dict]) -> dict | None:
    if not month_matrix:
        return None
    return min(month_matrix, key=entry_price)


def _days_ahead(depart_date: str | None) -> int | None:
    if not depart_date:
        return None
    try:
        return (date.fromisoformat(depart_date) - date.today()).days
    except ValueError:
        return None


def _no_coverage_streak(route_id: str) -> int:
    """Dias consecutivos (mais recentes) em que a rota ficou sem dados na fonte."""
    outcomes = get_recent_run_outcomes(route_id)
    streak = 0
    for outcome in outcomes:
        if outcome != "no_data":
            break
        streak += 1
    return streak


def process_route(route: dict, settings: dict) -> dict:
    """Busca, grava e avalia uma rota. Retorna um report para a camada de notificação.

    Fonte: v3 prices_for_dates (corte da Etapa 6, 21/07/2026 — 5 dias de
    comparação paralela com 100% de paridade de preço com o v2).
    Nota: o v3 não tem filtro de duração da estadia; trip_duration_weeks da
    rota deixou de ter efeito na busca (a UI de Configurações avisa)."""
    origin, destination, currency = route["origin"], route["destination"], route["currency"]
    route_label = f"{origin} → {destination}"

    matrix = []
    for i, month in enumerate(_target_months()):
        if i > 0:
            time.sleep(REQUEST_DELAY_SECONDS)
        month_entries = get_prices_for_dates(origin, destination, currency, departure_at=month[:7], one_way=False)
        print(f"[{route_label}] mês {month[:7]}: {len(month_entries)} entradas")
        matrix.extend(month_entries)

    cheapest = cheapest_entry(matrix)
    if cheapest is None:
        print(f"[{route_label}] sem dados de ida e volta retornados em nenhum dos {MONTHS_AHEAD} meses varridos")
        insert_run_log(route["id"], "no_data", detail="fonte: v3")
        return {"route": route, "status": "no_data", "streak": _no_coverage_streak(route["id"])}

    price = entry_price(cheapest)
    depart_date = (cheapest.get("departure_at") or "")[:10] or None
    return_date = (cheapest.get("return_at") or "")[:10] or None
    stops = cheapest.get("transfers")
    found_at = cheapest.get("found_at") or None
    days_ahead = _days_ahead(depart_date)

    insert_price(
        route["id"], depart_date or "", price, currency,
        return_date=return_date, found_at=found_at, stops=stops, days_ahead=days_ahead,
    )

    freshness_limit = float(settings.get("freshness_hours") or DEFAULT_SETTINGS["freshness_hours"])
    is_stale, age_hours = staleness(found_at, freshness_limit)
    cache_48h = is_stale and age_hours is None  # ausência esperada na fonte v3
    if age_hours is None:
        freshness_note = "frescor: n/d (cache ≤48h)"
    else:
        freshness_note = f"frescor: {age_hours:.0f}h"
        if is_stale:
            freshness_note += " (velho)"

    history_30d = get_price_history(route["id"], days=30)
    history_prices = [float(h["price"]) for h in history_30d]
    avg_30d = sum(history_prices) / len(history_prices) if history_prices else None

    suspicious_threshold = float(
        settings.get("suspicious_below_avg_pct") or DEFAULT_SETTINGS["suspicious_below_avg_pct"]
    )
    suspicious = is_suspicious_price(price, history_prices, suspicious_threshold)
    if suspicious and avg_30d:
        pct_below_avg = (1 - price / avg_30d) * 100
        freshness_note += f" | suspeito: {pct_below_avg:.0f}% abaixo da média 30d"
        print(f"[{route_label}] preço suspeito: {pct_below_avg:.0f}% abaixo da média 30d — alerta não dispara hoje")

    target_price = _to_float(route.get("target_price"))
    target_percent = _to_float(route.get("target_percent_below_avg"))
    good, good_reason, ceiling_hit, opportunity_hit = evaluate_good_price(
        price, history_prices, target_price, target_percent
    )

    history_7d = get_price_history(route["id"], days=7)
    recent = [(h["checked_at"], float(h["price"])) for h in history_7d]
    trending, trend_reason = detect_trend(
        recent, float(settings["window_3d_pct"]), float(settings["window_7d_pct"])
    )

    would_alert = (good or trending) and not suspicious
    stale_suppressed = would_alert and should_suppress_alert(is_stale, age_hours, settings)
    if stale_suppressed:
        freshness_note += " — alerta segurado"
        print(f"[{route_label}] alerta segurado: dado velho e política 'suppress'")
    elif would_alert and cache_48h and settings.get("stale_alert_policy") == "suppress":
        freshness_note += " — política suppress não aplicada (idade desconhecida, fonte v3)"

    cooldown_suppressed = False
    if would_alert and not stale_suppressed:
        last_alert = get_last_alert(route["id"])
        cooldown_suppressed = cooldown_blocks_alert(last_alert, price, settings)
        if cooldown_suppressed:
            freshness_note += " — alerta segurado (cooldown)"
            print(f"[{route_label}] alerta segurado: cooldown ativo (sem queda nem tempo suficiente)")

    insert_run_log(route["id"], "ok", price=price, detail=f"fonte: v3 | {freshness_note}")

    print(f"[{route_label}] R$ {price:.2f} ida {depart_date} volta {return_date} ({stops} escalas)")

    return {
        "route": route,
        "status": "ok",
        "origin": origin,
        "destination": destination,
        "currency": currency,
        "price": price,
        "depart_date": depart_date,
        "return_date": return_date,
        "stops": stops,
        "found_at": found_at,
        "days_ahead": days_ahead,
        "target_price": target_price,
        "avg_30d": avg_30d,
        "is_stale": is_stale,
        "age_hours": age_hours,
        "cache_48h": cache_48h,
        "suspicious": suspicious,
        "should_alert": would_alert and not stale_suppressed and not cooldown_suppressed,
        "reason": good_reason if good else (trend_reason if trending else None),
        # Fatia D2 (13/08/2026): false/false quando o alerta saiu só por
        # tendência (detect_trend) — órfã LEGÍTIMA na classificação
        # teto/oportunidade, o cooldown de rota não usa essas colunas ainda
        # (fora de escopo da D2, get_last_alert continua só por route_id).
        "is_ceiling_alert": ceiling_hit,
        "is_opportunity_alert": opportunity_hit,
    }


def _weekend_report_priority(r: dict) -> int:
    """Prioridade pra dedupe_weekend_reports: 'ok' com fonte live > 'ok' com
    cache > 'no_data' > 'error'. Live é a fonte primária desde a Parte 3."""
    if r.get("status") == "ok" and r.get("source") == "live":
        return 3
    if r.get("status") == "ok":
        return 2
    if r.get("status") == "no_data":
        return 1
    return 0


def dedupe_weekend_reports(reports: list[dict]) -> list[dict]:
    """Uma perna pode aparecer em cache_reports E live_reports no mesmo run
    (cache achou hoje e a perna também caiu no lote fast-flights). Sem isso,
    o alerta sairia duplicado — o insert em alert_log só acontece depois
    deste ponto (no laço de envio), então o cooldown não veria a duplicata
    a tempo. Fica só 1 report por perna, o de maior prioridade."""
    by_leg_id: dict[str, dict] = {}
    order: list[str] = []
    for r in reports:
        leg = r.get("leg")
        if leg is None:
            continue
        leg_id = leg["id"]
        if leg_id not in by_leg_id:
            order.append(leg_id)
            by_leg_id[leg_id] = r
        elif _weekend_report_priority(r) > _weekend_report_priority(by_leg_id[leg_id]):
            by_leg_id[leg_id] = r
    return [by_leg_id[lid] for lid in order]


def build_notes(reports: list[dict]) -> list[str]:
    """Notas extras: rotas sem cobertura persistente (sugestão de arquivar) e erros."""
    notes = []
    for r in reports:
        label = f"{r['route']['origin']} → {r['route']['destination']}"
        if r["status"] == "no_data":
            streak = r.get("streak", 0)
            if streak >= NO_COVERAGE_SUGGESTION_EVERY and streak % NO_COVERAGE_SUGGESTION_EVERY == 0:
                notes.append(
                    f"⚠️ {label}: {streak} dias seguidos sem cobertura de dados na fonte. "
                    f"Considere arquivar a rota nas Configurações (o histórico é preservado)."
                )
        elif r["status"] == "error":
            notes.append(f"❌ {label}: erro na busca de hoje — será tentada de novo amanhã.")
        elif r["status"] == "ok" and r.get("suspicious"):
            notes.append(
                f"🔍 {label}: preço de hoje (R$ {r['price']:.2f}) muito abaixo da média — marcado como "
                f"suspeito, alerta não disparado. Será reavaliado amanhã (se persistir 2 dias, deixa de ser suspeito)."
            )
    return notes


def main() -> None:
    # Parte 10 (28/07/2026): daily.yml roda até 3x/dia (janelas fixas em
    # cron), mas só a execução primária faz rotas flexíveis + cache
    # Travelpayouts das pernas de fim de semana + notificações de rotas —
    # as execuções extras do estágio de frequência automática só rodam o
    # lote fli. Sem isso, subir o estágio triplicaria consumo da
    # Travelpayouts sem necessidade (ela não tem detector de bloqueio nem
    # é o gargalo que motivou o escalonamento).
    #
    # Correção de 30/07/2026 (bug real em produção — ver scrape_schedule.py):
    # "primária" e "lote fli esperado hoje" não são mais decididos por
    # igualdade exata de hora BRT contra o cron (um atraso de disparo do
    # GitHub Actions bastava pra zerar a execução inteira, silenciosamente).
    # Agora é por estado gravado em bot_state: a primeira execução do dia,
    # não importa a que hora chega, é a primária; o lote fli roda até
    # completar a cota do estágio atual, contada por execuções reais.
    today = current_brt_date()
    scrape_state = get_weekend_scrape_state()
    initial_stage = scrape_state["stage"]  # decide a cota do dia — não muda com bloqueio nesta execução
    primary_run = is_primary_run(scrape_state, today)

    routes = get_routes()
    raw_system_config = get_system_config()  # None = tabela sem linha (kill-switch etc. também degradam aqui)
    system_config = raw_system_config or DEFAULT_SYSTEM_CONFIG

    # `settings` é o registro de usuários (mesma tabela do cross join da view
    # weekend_leg_effective) — carregada inteira, ordenada por user_id. NÃO
    # derivar de `routes`: usuário sem rota flexível continua sendo usuário, e
    # antes da Etapa 4.2 era exatamente esse o furo — a escolha de settings
    # nascia de `routes` e ignorava quem só tem pernas de fim de semana.
    settings_cache: dict[str, dict] = {
        row["user_id"]: {**row, **system_config} for row in get_all_settings()
    }
    for route in routes:  # usuário com rota mas sem linha em settings: cai no default
        user_id = route["user_id"]
        if user_id not in settings_cache:
            settings_cache[user_id] = {**(get_settings(user_id) or DEFAULT_SETTINGS), **system_config}

    reports: list[dict] = []
    had_error = False

    if primary_run:
        for route in routes:
            try:
                reports.append(process_route(route, settings_cache[route["user_id"]]))
            except Exception:
                had_error = True
                label = f"{route['origin']} → {route['destination']}"
                print(f"[{label}] ERRO:\n{traceback.format_exc()}")
                try:
                    insert_run_log(route["id"], "error", detail=traceback.format_exc()[-500:])
                except Exception:
                    print(f"[{label}] falha também ao gravar run_log")
                reports.append({"route": route, "status": "error"})
    else:
        print(f"[main] execução extra do dia ({today}) — pulando rotas flexíveis e cache Travelpayouts")

    # Escolha ÚNICA e determinística de quem dita os limiares gerais (%
    # oportunidade, cooldown/re-alerta, modo de notificação): o menor user_id.
    # Antes era `next(iter(settings_cache.values()))` — o primeiro usuário que a
    # ordem do dicionário devolvesse, escolha implícita e instável.
    #
    # ⚠️ PROVISÓRIO até a Etapa 6, que troca isto por um loop de verdade por
    # usuário. O TETO já não passa por aqui: desde a Etapa 4.2 cada perna carrega
    # seu próprio teto efetivo (weekends.get_active_legs). O que ainda é de um
    # usuário só são os limiares gerais — e, quando há mais de um, o Telegram
    # avisa em vez de escolher em silêncio.
    settings_user_id = sorted(settings_cache)[0] if settings_cache else None
    weekend_settings = (
        settings_cache[settings_user_id] if settings_user_id
        else {**DEFAULT_SETTINGS, **system_config}
    )
    if settings_user_id:
        print(f"[main] limiares gerais: settings de {settings_user_id} ({len(settings_cache)} usuário(s))")

    # Janela de compra (Fatia D1, 12/08/2026): resolvida uma única vez por
    # execução, a partir de `raw_system_config` (a resposta CRUA do banco, não
    # o `system_config` já mesclado com DEFAULT_SYSTEM_CONFIG acima) — se
    # calculássemos a partir de `weekend_settings`, o caso "system_config sem
    # linha" ficaria indistinguível de um corte real configurado igual ao
    # fallback, e o aviso nunca dispararia. Resultado normalizado de volta em
    # weekend_settings — é a mesma cópia que evaluate_and_record_leg_price
    # (weekends.py) vai ler para cada perna, então o valor usado no alerta e
    # o usado no resumo/contagem abaixo são garantidamente o mesmo.
    # Degradação nunca remove o filtro — cai no fallback embutido e avisa.
    buying_cutoff, buying_cutoff_degraded = resolve_buying_cutoff(raw_system_config or {})
    weekend_settings["weekend_buying_cutoff_date"] = buying_cutoff

    if primary_run:
        # Novo dia de contagem começando — sempre reseta (idempotente se já
        # estava False). Persistido na hora: cada execução é um processo
        # novo, não dá pra confiar em estado só em memória entre execuções.
        scrape_state["blocked_today"] = False
        scrape_state = record_primary_run(scrape_state, today)
        set_weekend_scrape_state(blocked_today=False, last_primary_run_date=today)
        # Cache (Travelpayouts) — conferidor secundário desde a Parte 3
        # (23/07/2026: só 2/132 pernas bateram, insuficiente pra decidir sozinho).
        cache_reports = process_all_weekend_legs(weekend_settings)
    else:
        cache_reports = []

    if should_run_live_batch(initial_stage, scrape_state, today):
        # Calculado ANTES de rodar o lote (usa a contagem pré-execução) —
        # "esse lote, se rodar, completa a cota do dia?".
        is_last_batch_of_day = is_last_expected_batch(initial_stage, scrape_state, today)
        # Live (fli) — fonte primária: quando encontra preço, sobrescreve
        # current_price/current_source da perna naquele dia.
        live_reports, blocked = run_daily_batch(weekend_settings)
        scrape_state = record_batch_run(scrape_state, today)
        set_weekend_scrape_state(
            last_batch_run_date=today, batches_run_today=scrape_state["batches_run_today"],
        )
    else:
        print(
            f"[main] Estágio {initial_stage} já rodou os lotes fli esperados hoje ({today}) "
            "— pulado nesta execução"
        )
        live_reports, blocked = [], False
        is_last_batch_of_day = False

    if blocked:
        scrape_state = apply_block_reversion(scrape_state)
        set_weekend_scrape_state(
            stage=scrape_state["stage"], clean_days=scrape_state["clean_days"],
            blocked_today=scrape_state["blocked_today"],
        )
        if scrape_state["changed"]:
            send_message(build_stage_change_message(scrape_state["stage"], scrape_state["reason"]))

    # Avaliação de subida só depois do último lote esperado do dia pro
    # estágio do INÍCIO do dia (initial_stage — não o estágio pós-bloqueio) e
    # só se não bloqueou em nenhum momento hoje, inclusive agora mesmo
    # (scrape_state já reflete o apply_block_reversion acima, se aconteceu
    # nesta mesma execução) — sem isso, um bloqueio bem no lote que decidiria
    # a subida subiria e cairia no mesmo ciclo.
    if is_last_batch_of_day and not scrape_state["blocked_today"]:
        scrape_state = evaluate_stage_transition(scrape_state)
        set_weekend_scrape_state(stage=scrape_state["stage"], clean_days=scrape_state["clean_days"])
        if scrape_state["changed"]:
            send_message(build_stage_change_message(scrape_state["stage"], scrape_state["reason"]))

    # Avisos de estado provisório da Etapa 4.2 — no máximo um de cada por
    # execução, mesmo que get_active_legs tenha rodado 2x (cache + lote fli):
    # LEG_LOAD_DIAGNOSTICS é sobrescrito a cada carga, nunca acumulado.
    if LEG_LOAD_DIAGNOSTICS["degraded_no_settings"]:
        send_message(build_no_effective_ceiling_message())
    if LEG_LOAD_DIAGNOSTICS["multi_user_ceiling_legs"]:
        send_message(build_multi_user_ceiling_message(LEG_LOAD_DIAGNOSTICS["multi_user_ceiling_legs"]))
    if len(settings_cache) > 1:
        send_message(build_shared_settings_message(settings_user_id, len(settings_cache)))
    if buying_cutoff_degraded:
        send_message(build_buying_cutoff_fallback_message(buying_cutoff))

    weekend_reports = dedupe_weekend_reports(cache_reports + live_reports)
    if any(wr["status"] == "error" for wr in weekend_reports):
        had_error = True

    if not routes and not weekend_reports:
        print("Nenhuma rota nem perna de fim de semana cadastrada.")
        return

    notes = build_notes(reports)

    if primary_run:
        if routes:
            mode = weekend_settings["notification_mode"]  # mesma escolha determinística acima
            if mode == "daily_summary":
                blocks = [build_route_block(r) for r in reports if r["status"] == "ok"]
                for r in reports:
                    if r["status"] == "no_data":
                        blocks.append(
                            f"✈️ <b>{r['route']['origin']} → {r['route']['destination']}</b> — sem dados na fonte hoje"
                        )
                send_message(build_summary_message(blocks, notes))
            else:
                for r in reports:
                    if r["status"] == "ok" and r["should_alert"]:
                        send_message(build_alert_message(r))
                        # Fatia D3 (14/08/2026): a gravação do log de alerta é
                        # protegida porque acontece DEPOIS de a mensagem já ter
                        # saído — falhar aqui derrubava a execução inteira com o
                        # usuário já avisado, e (neste laço) cancelava os alertas
                        # das rotas seguintes. Degradação preferível: registra,
                        # marca had_error (exit 1 no fim, visível no Actions) e
                        # segue. Consequência aceita e registrada: sem a linha em
                        # alert_log o cooldown não é alimentado, então o mesmo
                        # alerta pode sair de novo amanhã.
                        try:
                            insert_alert_log(
                                r["route"]["id"], r["price"], r.get("reason"),
                                is_ceiling_alert=r["is_ceiling_alert"],
                                is_opportunity_alert=r["is_opportunity_alert"],
                                user_id=r["route"]["user_id"],
                            )
                        except Exception:
                            had_error = True
                            print(
                                f"[alert_log] FALHA AO GRAVAR (rota {r['route']['id']}) — "
                                f"mensagem já enviada, cooldown não alimentado:\n{traceback.format_exc()}"
                            )
                if notes:
                    send_message("\n".join(notes))
        elif notes:
            send_message("\n".join(notes))

    # Pernas de fim de semana: notificação sempre imediata quando bate teto ou
    # oportunidade, em toda execução (é o próprio ponto de rodar mais vezes
    # por dia) — independe do notification_mode das rotas flexíveis e de
    # primary_run. Resumo semanal curado só às segundas-feiras, só na
    # execução primária (senão mandaria 3x no mesmo dia).
    for wr in weekend_reports:
        if wr["status"] == "ok" and wr["should_alert"]:
            comparison = build_package_comparison(wr, weekend_settings)
            send_message(build_weekend_alert_message(wr, comparison))
            # Fatia D3 (14/08/2026): mesma proteção do insert de rota acima, e
            # aqui ela pesa mais — este insert está DENTRO do laço de pernas,
            # então uma exceção não tratada cancelava os alertas das pernas
            # seguintes, o resumo semanal de segunda e o exit code correto.
            # A linha nasce com user_id NULL por desenho (ver
            # supabase_client.insert_weekend_alert_log).
            try:
                insert_weekend_alert_log(
                    wr["leg"]["id"], wr["price"], wr.get("reason"),
                    is_ceiling_alert=wr["is_ceiling_hit"], is_opportunity_alert=wr["is_opportunity_hit"],
                )
            except Exception:
                had_error = True
                print(
                    f"[alert_log] FALHA AO GRAVAR (perna {wr['leg']['id']}) — "
                    f"mensagem já enviada, cooldown não alimentado:\n{traceback.format_exc()}"
                )

    if primary_run and date.today().weekday() == 0:  # segunda-feira
        total, purchased = get_weekend_leg_counts(buying_cutoff)
        send_message(build_weekly_weekend_summary(weekend_reports, total, purchased, buying_cutoff))

    if had_error:
        sys.exit(1)


if __name__ == "__main__":
    main()
