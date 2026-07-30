"""Escalonamento automático da frequência do lote de consulta ao vivo (fli)
— Parte 10 (28/07/2026). Sobe em estágios (mais execuções/dia, não lote
maior por execução) depois de dias consecutivos sem bloqueio; qualquer
bloqueio derruba pro Estágio 0 na hora e reseta a contagem. Teto automático
é o Estágio 2 — não sobe sozinho além disso.

Funções puras (sem I/O) — o estado (`weekend_scrape_stage`,
`weekend_scrape_clean_days`, `weekend_scrape_blocked_today`,
`weekend_scrape_last_primary_run_date`, `weekend_scrape_last_batch_run_date`,
`weekend_scrape_batches_run_today`) é lido/gravado por quem chama
(main.py), via supabase_client.get/set_weekend_scrape_state.

Correção de 30/07/2026 (bug real em produção, runs #41/#42 — ver
HISTORICO.md): a versão original decidia "isso roda agora?" por igualdade
exata de hora BRT (`current_brt_hour() == 8`, `hour in STAGE_HOURS_BRT[stage]`)
contra o agendamento do cron. O cron do GitHub Actions não garante disparo
no minuto/hora exata — um atraso de dezenas de minutos (comum, sobretudo em
horários cheios) bastava pra a execução cair fora de TODOS os "hour buckets"
do dia e zerar rotas, cache, lote fli e gravação de estado inteiros,
silenciosamente, com exit 0. Uma janela de tolerância só adiaria o mesmo
bug pra um atraso maior — a correção troca o critério por ESTADO: "isso já
rodou hoje (data BRT), pra este propósito, ou não?" A execução primária é
sempre a primeira do dia, não importa a que hora chega; o lote fli roda até
completar a cota do estágio atual (1/2/3 execuções por dia), contada por
execuções reais, não por hora fixa — um atraso empurra o lote pra mais
tarde, nunca o cancela.

`daily.yml` tem as janelas de horário como referência de agendamento (cron
estático), mas a decisão de fazer algo ou não em cada execução é toda
daqui, e não depende mais de qual das janelas foi essa. Brasil não usa
horário de verão desde 2019 — BRT = UTC-3 fixo.
"""
from datetime import datetime, timedelta, timezone

STAGE_BATCHES_PER_DAY = {0: 1, 1: 2, 2: 3}
MAX_STAGE = 2
CLEAN_DAYS_TO_ESCALATE = 5


def _brt_now() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=3)


def current_brt_hour() -> int:
    """Só para diagnóstico/log — nenhuma decisão de agendamento depende mais disso."""
    return _brt_now().hour


def current_brt_date() -> str:
    """Data (ISO, BRT) usada como chave de 'já rodou hoje' — insensível a atraso de cron."""
    return _brt_now().date().isoformat()


def _batches_run_today(state: dict, today: str) -> int:
    if state.get("last_batch_run_date") != today:
        return 0
    return int(state.get("batches_run_today") or 0)


def is_primary_run(state: dict, today: str) -> bool:
    """A execução primária é a primeira do dia (BRT), não importa a que hora
    chega — a única que roda rotas flexíveis, cache Travelpayouts e
    notificações de rotas. Execuções extras do mesmo dia só rodam o lote fli,
    pra não triplicar Travelpayouts junto."""
    return state.get("last_primary_run_date") != today


def should_run_live_batch(stage: int, state: dict, today: str) -> bool:
    """Roda o lote fli enquanto não tiver completado a cota do estágio atual
    hoje (1/2/3, conforme Estágio 0/1/2) — contagem por execução, não por
    hora bater com uma lista fixa."""
    return _batches_run_today(state, today) < STAGE_BATCHES_PER_DAY[stage]


def is_last_expected_batch(stage: int, state: dict, today: str) -> bool:
    """True se o lote desta execução (ainda não contabilizado em `state`)
    completa a cota do dia — substitui `is_last_scheduled_hour`; só chamar
    imediatamente antes de rodar o lote (usa a contagem pré-execução)."""
    return _batches_run_today(state, today) + 1 >= STAGE_BATCHES_PER_DAY[stage]


def record_primary_run(state: dict, today: str) -> dict:
    return {**state, "last_primary_run_date": today}


def record_batch_run(state: dict, today: str) -> dict:
    return {
        **state,
        "last_batch_run_date": today,
        "batches_run_today": _batches_run_today(state, today) + 1,
    }


def apply_block_reversion(state: dict) -> dict:
    """Bloqueio detectado — derruba pro Estágio 0 e reseta a contagem de
    dias limpos, de qualquer estágio, a qualquer hora. `blocked_today=True`
    é o que impede `evaluate_stage_transition` de subir de estágio se essa
    mesma execução também for o último lote esperado do dia (o cenário mais
    perigoso: bloqueio bem no lote que decidiria a subida)."""
    return {
        **state,
        "stage": 0,
        "clean_days": 0,
        "blocked_today": True,
        "changed": state.get("stage", 0) != 0,
        "reason": "bloqueio detectado",
    }


def evaluate_stage_transition(state: dict) -> dict:
    """Só chamar depois do último lote esperado do dia
    (`is_last_expected_batch`), e só quando `state['blocked_today']` for
    False — quem decide isso é o chamador (main.py), não esta função. Sobe 1
    estágio ao completar CLEAN_DAYS_TO_ESCALATE dias limpos seguidos; nunca
    passa do MAX_STAGE."""
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
