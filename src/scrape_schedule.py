"""Escalonamento automático da frequência do lote de consulta ao vivo (fli)
— Parte 10 (28/07/2026). Sobe em estágios (mais execuções/dia, não lote
maior por execução) depois de dias consecutivos sem bloqueio; qualquer
bloqueio derruba pro Estágio 0 na hora e reseta a contagem. Teto automático
é o Estágio 2 — não sobe sozinho além disso.

Funções puras (sem I/O) — o estado (`weekend_scrape_stage`,
`weekend_scrape_clean_days`, `weekend_scrape_blocked_today`) é lido/gravado
por quem chama (main.py), via supabase_client.get/set_weekend_scrape_state.

`daily.yml` tem as 3 janelas de horário sempre ativas (cron estático, nunca
reescrito); a decisão de fazer algo ou não em cada execução é toda daqui.
Brasil não usa horário de verão desde 2019 — BRT = UTC-3 fixo.
"""
from datetime import datetime, timezone

STAGE_HOURS_BRT = {0: [8], 1: [8, 20], 2: [8, 14, 20]}
MAX_STAGE = 2
CLEAN_DAYS_TO_ESCALATE = 5
PRIMARY_HOUR_BRT = 8


def current_brt_hour() -> int:
    return (datetime.now(timezone.utc).hour - 3) % 24


def is_primary_run(hour: int) -> bool:
    """A execução primária (08h BRT) é a única que roda rotas flexíveis,
    cache Travelpayouts e notificações de rotas — execuções extras de
    estágio só rodam o lote fli, pra não triplicar Travelpayouts junto."""
    return hour == PRIMARY_HOUR_BRT


def should_run_live_batch(stage: int, hour: int) -> bool:
    return hour in STAGE_HOURS_BRT[stage]


def is_last_scheduled_hour(stage: int, hour: int) -> bool:
    return hour == max(STAGE_HOURS_BRT[stage])


def apply_block_reversion(state: dict) -> dict:
    """Bloqueio detectado — derruba pro Estágio 0 e reseta a contagem de
    dias limpos, de qualquer estágio, a qualquer hora. `blocked_today=True`
    é o que impede `evaluate_stage_transition` de subir de estágio se essa
    mesma execução também for a última hora agendada do dia (o cenário mais
    perigoso: bloqueio bem na hora em que a subida seria avaliada)."""
    return {
        **state,
        "stage": 0,
        "clean_days": 0,
        "blocked_today": True,
        "changed": state.get("stage", 0) != 0,
        "reason": "bloqueio detectado",
    }


def evaluate_stage_transition(state: dict) -> dict:
    """Só chamar na última hora agendada do dia (`is_last_scheduled_hour`),
    e só quando `state['blocked_today']` for False — quem decide isso é o
    chamador (main.py), não esta função. Sobe 1 estágio ao completar
    CLEAN_DAYS_TO_ESCALATE dias limpos seguidos; nunca passa do MAX_STAGE."""
    stage = state["stage"]
    clean_days = state["clean_days"] + 1

    if clean_days >= CLEAN_DAYS_TO_ESCALATE and stage < MAX_STAGE:
        return {
            **state,
            "stage": stage + 1,
            "clean_days": 0,
            "changed": True,
            "reason": f"{CLEAN_DAYS_TO_ESCALATE} dias sem bloqueio",
        }

    return {
        **state,
        "clean_days": min(clean_days, CLEAN_DAYS_TO_ESCALATE) if stage >= MAX_STAGE else clean_days,
        "changed": False,
        "reason": None,
    }
