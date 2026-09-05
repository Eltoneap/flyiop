"""Teste local do radar de calendário (radar_check.py) — grade via
`fli.search.dates.SearchDates`, validada em produção real na Etapa 0
(24/08/2026, ver HISTORICO.md item 24).

Roda 100% com mocks — nenhuma chamada real ao fli nem ao Supabase.
Uso: python -m unittest tests/test_radar_check.py -v  (a partir da raiz do repo)
"""
import os
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import call, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import live_check  # noqa: E402
import radar_check  # noqa: E402


def days_from_today(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def fake_date_price(flight_date: str, price: float, currency: str = "BRL"):
    return SimpleNamespace(date=(datetime.fromisoformat(flight_date),), price=price, currency=currency)


OUTBOUND_LEG = {
    "id": "leg-out-1", "direction": "outbound",
    "outbound_date": days_from_today(30), "return_sunday": days_from_today(32),
    "return_monday": days_from_today(33), "ceilings_by_user": {"user-a": 300.0},
    "lowest_seen": None,
}


class ConstantSyncTest(unittest.TestCase):
    def test_radar_coverage_window_matches_across_modules(self):
        """live_check.RADAR_COVERAGE_WINDOW_DAYS e radar_check.RADAR_WINDOW_DAYS
        são o MESMO valor duplicado de propósito (radar_check.py já importa
        leg_travel_date de live_check.py — um import de volta criaria ciclo).
        Os dois precisam ficar em sincronia; sem este teste, um dos dois
        podia mudar sozinho e nada acusaria a divergência."""
        self.assertEqual(live_check.RADAR_COVERAGE_WINDOW_DAYS, radar_check.RADAR_WINDOW_DAYS)


class DateBlocksTest(unittest.TestCase):
    def test_no_block_exceeds_max_days(self):
        """Invariante que impede o particionamento paralelo interno da lib
        (SearchDates.search só aciona ThreadPoolExecutor quando o intervalo
        PEDIDO numa única chamada passa de MAX_DAYS_PER_SEARCH)."""
        blocks = radar_check.date_blocks(date.today(), date.today() + timedelta(days=305))
        for start, end in blocks:
            self.assertLessEqual((end - start).days + 1, radar_check.RADAR_BLOCK_DAYS)

    def test_covers_full_range_without_gaps_or_overlap(self):
        start, end = date.today(), date.today() + timedelta(days=305)
        blocks = radar_check.date_blocks(start, end)
        expected_day = start
        for block_start, block_end in blocks:
            self.assertEqual(block_start, expected_day)
            expected_day = block_end + timedelta(days=1)
        self.assertEqual(expected_day, end + timedelta(days=1))

    def test_single_day_range_is_one_block(self):
        today = date.today()
        blocks = radar_check.date_blocks(today, today)
        self.assertEqual(blocks, [(today, today)])

    def test_exactly_max_days_is_one_block(self):
        start = date.today()
        end = start + timedelta(days=radar_check.RADAR_BLOCK_DAYS - 1)
        blocks = radar_check.date_blocks(start, end)
        self.assertEqual(len(blocks), 1)

    def test_one_day_over_max_is_two_blocks(self):
        start = date.today()
        end = start + timedelta(days=radar_check.RADAR_BLOCK_DAYS)
        blocks = radar_check.date_blocks(start, end)
        self.assertEqual(len(blocks), 2)


class DetectBlockAnomalyTest(unittest.TestCase):
    def test_below_minimum_sample_never_opines(self):
        self.assertFalse(radar_check.detect_block_anomaly(today_count=0, known_count=4))

    def test_always_empty_with_no_history_is_not_anomalous(self):
        # known_count=0 é o caso normal de "essa data ainda não abriu pra
        # venda" — nunca teve dado, não é anomalia.
        self.assertFalse(radar_check.detect_block_anomaly(today_count=0, known_count=0))

    def test_went_from_known_to_empty_is_anomalous(self):
        self.assertTrue(radar_check.detect_block_anomaly(today_count=0, known_count=20))

    def test_dropped_below_half_is_anomalous(self):
        self.assertTrue(radar_check.detect_block_anomaly(today_count=9, known_count=20))

    def test_at_exactly_half_is_not_anomalous(self):
        self.assertFalse(radar_check.detect_block_anomaly(today_count=10, known_count=20))

    def test_stable_volume_is_not_anomalous(self):
        self.assertFalse(radar_check.detect_block_anomaly(today_count=19, known_count=20))


class SelectPrecisionCandidatesTest(unittest.TestCase):
    TODAY = date.today()

    def grid_row(self, origin, destination, flight_date, price):
        return {"origin": origin, "destination": destination, "flight_date": flight_date, "price": price}

    def test_uses_max_ceiling_not_min(self):
        """A precisão precisa disparar pro usuário de teto MAIS ALTO — usar o
        menor (queue_ceiling, heurística de fila) faria isso nunca acontecer
        em silêncio."""
        leg = {**OUTBOUND_LEG, "ceilings_by_user": {"user-a": 200.0, "user-b": 400.0}}
        grid = [self.grid_row("GIG", "BSB", leg["outbound_date"], 350.0)]
        candidates = radar_check.select_precision_candidates([leg], grid, self.TODAY, 10)
        self.assertEqual(len(candidates), 1)  # 350 <= 400 (max), mesmo acima de 200 (min)
        self.assertEqual(candidates[0]["max_ceiling"], 400.0)

    def test_no_ceiling_can_still_trigger_via_lowest_seen(self):
        leg = {**OUTBOUND_LEG, "ceilings_by_user": {}, "lowest_seen": 500.0}
        grid = [self.grid_row("GIG", "BSB", leg["outbound_date"], 450.0)]
        candidates = radar_check.select_precision_candidates([leg], grid, self.TODAY, 10)
        self.assertEqual(len(candidates), 1)
        self.assertIsNone(candidates[0]["max_ceiling"])

    def test_price_above_ceiling_and_not_a_new_low_is_not_a_candidate(self):
        leg = {**OUTBOUND_LEG, "ceilings_by_user": {"user-a": 300.0}, "lowest_seen": 280.0}
        grid = [self.grid_row("GIG", "BSB", leg["outbound_date"], 310.0)]
        candidates = radar_check.select_precision_candidates([leg], grid, self.TODAY, 10)
        self.assertEqual(candidates, [])

    def test_orders_by_biggest_gap_first(self):
        near_ceiling = {**OUTBOUND_LEG, "id": "near", "outbound_date": days_from_today(31),
                        "ceilings_by_user": {"user-a": 300.0}}
        big_discount = {**OUTBOUND_LEG, "id": "cheap", "outbound_date": days_from_today(32),
                        "ceilings_by_user": {"user-a": 300.0}}
        grid = [
            self.grid_row("GIG", "BSB", near_ceiling["outbound_date"], 295.0),
            self.grid_row("GIG", "BSB", big_discount["outbound_date"], 150.0),
        ]
        candidates = radar_check.select_precision_candidates([near_ceiling, big_discount], grid, self.TODAY, 10)
        self.assertEqual([c["leg"]["id"] for c in candidates], ["cheap", "near"])

    def test_lowest_seen_only_candidate_sorts_last(self):
        """Sem teto, gap = +inf — desempata por último, mesmo padrão de
        price_gap em live_check.select_batch."""
        with_ceiling = {**OUTBOUND_LEG, "id": "with-ceiling", "outbound_date": days_from_today(31),
                       "ceilings_by_user": {"user-a": 300.0}}
        only_low = {**OUTBOUND_LEG, "id": "only-low", "outbound_date": days_from_today(32),
                   "ceilings_by_user": {}, "lowest_seen": 500.0}
        grid = [
            self.grid_row("GIG", "BSB", with_ceiling["outbound_date"], 295.0),
            self.grid_row("GIG", "BSB", only_low["outbound_date"], 450.0),
        ]
        candidates = radar_check.select_precision_candidates([with_ceiling, only_low], grid, self.TODAY, 10)
        self.assertEqual([c["leg"]["id"] for c in candidates], ["with-ceiling", "only-low"])

    def test_cut_at_max_per_run(self):
        legs = [{**OUTBOUND_LEG, "id": f"leg-{i}", "ceilings_by_user": {"user-a": 300.0}} for i in range(15)]
        grid = [self.grid_row("GIG", "BSB", leg["outbound_date"], 250.0) for leg in legs]
        candidates = radar_check.select_precision_candidates(legs, grid, self.TODAY, 10)
        self.assertEqual(len(candidates), 10)

    def test_leg_outside_radar_window_is_ignored(self):
        far = {**OUTBOUND_LEG, "outbound_date": days_from_today(320), "ceilings_by_user": {"user-a": 300.0}}
        grid = [self.grid_row("GIG", "BSB", far["outbound_date"], 200.0)]
        candidates = radar_check.select_precision_candidates([far], grid, self.TODAY, 10)
        self.assertEqual(candidates, [])

    def test_leg_without_grid_data_is_ignored(self):
        candidates = radar_check.select_precision_candidates([OUTBOUND_LEG], [], self.TODAY, 10)
        self.assertEqual(candidates, [])

    def test_picks_cheapest_between_gig_and_sdu(self):
        leg = {**OUTBOUND_LEG, "ceilings_by_user": {"user-a": 300.0}}
        grid = [
            self.grid_row("GIG", "BSB", leg["outbound_date"], 280.0),
            self.grid_row("SDU", "BSB", leg["outbound_date"], 250.0),
        ]
        candidates = radar_check.select_precision_candidates([leg], grid, self.TODAY, 10)
        self.assertEqual(candidates[0]["radar_price"], 250.0)
        self.assertEqual(candidates[0]["radar_destination"], "BSB")
        self.assertEqual(candidates[0]["radar_origin"], "SDU")

    def test_return_leg_queries_bsb_to_airport(self):
        leg = {**OUTBOUND_LEG, "id": "ret-1", "direction": "return", "ceilings_by_user": {"user-a": 300.0}}
        grid = [self.grid_row("BSB", "GIG", leg["return_sunday"], 250.0)]
        candidates = radar_check.select_precision_candidates([leg], grid, self.TODAY, 10)
        self.assertEqual(len(candidates), 1)


class RunSweepTest(unittest.TestCase):
    def setUp(self):
        patcher = patch("radar_check.current_brt_date", return_value=date.today().isoformat())
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_kill_switch_makes_zero_calls(self):
        with patch("radar_check.get_radar_sweep_state") as mock_state, \
             patch("radar_check.search_dates_block") as mock_search, \
             patch("radar_check.upsert_weekend_radar_grid") as mock_upsert:
            result = radar_check.run_sweep({"radar_enabled": False})
        self.assertEqual(result, {"ran": False, "reason": "kill_switch_off"})
        mock_state.assert_not_called()
        mock_search.assert_not_called()
        mock_upsert.assert_not_called()

    def test_quota_already_reached_today_skips(self):
        today = date.today().isoformat()
        with patch("radar_check.get_radar_sweep_state",
                   return_value={"last_sweep_date": today, "sweeps_today": 2}), \
             patch("radar_check.search_dates_block") as mock_search:
            result = radar_check.run_sweep({"radar_enabled": True, "radar_sweeps_per_day": 2})
        self.assertEqual(result, {"ran": False, "reason": "quota_reached"})
        mock_search.assert_not_called()

    def test_quota_from_a_previous_day_does_not_count(self):
        with patch("radar_check.get_radar_sweep_state",
                   return_value={"last_sweep_date": "2020-01-01", "sweeps_today": 99}), \
             patch("radar_check.get_weekend_radar_grid_known_count", return_value=0), \
             patch("radar_check.search_dates_block", return_value=[]), \
             patch("radar_check.upsert_weekend_radar_grid"), \
             patch("radar_check.set_radar_sweep_state") as mock_set, \
             patch("radar_check.time.sleep"), \
             patch("radar_check.RADAR_DIRECTIONS", (("GIG", "BSB"),)), \
             patch("radar_check.RADAR_WINDOW_DAYS", 5):
            result = radar_check.run_sweep({"radar_enabled": True, "radar_sweeps_per_day": 2})
        self.assertTrue(result["ran"])
        mock_set.assert_called_once_with(last_sweep_date=date.today().isoformat(), sweeps_today=1)

    @patch("radar_check.RADAR_DIRECTIONS", (("GIG", "BSB"),))
    @patch("radar_check.RADAR_WINDOW_DAYS", 5)  # 1 bloco só
    def test_known_count_is_measured_before_upsert_for_the_same_block(self):
        """Ordem obrigatória por bloco (revisão desta sessão): contar ANTES
        de gravar. Invertido, a contagem mediria a varredura de hoje contra
        ela mesma e o detector de anomalia nunca dispararia."""
        call_order = []
        with patch("radar_check.get_radar_sweep_state",
                   return_value={"last_sweep_date": None, "sweeps_today": 0}), \
             patch("radar_check.get_weekend_radar_grid_known_count",
                   side_effect=lambda *a: call_order.append("known_count") or 0), \
             patch("radar_check.search_dates_block", return_value=[fake_date_price(days_from_today(1), 300.0)]), \
             patch("radar_check.upsert_weekend_radar_grid",
                   side_effect=lambda *a: call_order.append("upsert")), \
             patch("radar_check.set_radar_sweep_state"), \
             patch("radar_check.time.sleep"):
            radar_check.run_sweep({"radar_enabled": True})
        self.assertEqual(call_order, ["known_count", "upsert"])

    @patch("radar_check.RADAR_DIRECTIONS", (("GIG", "BSB"),))
    @patch("radar_check.RADAR_WINDOW_DAYS", 5)
    def test_sleep_called_between_blocks_not_before_first(self):
        with patch("radar_check.get_radar_sweep_state",
                   return_value={"last_sweep_date": None, "sweeps_today": 0}), \
             patch("radar_check.get_weekend_radar_grid_known_count", return_value=0), \
             patch("radar_check.search_dates_block", return_value=[]), \
             patch("radar_check.upsert_weekend_radar_grid"), \
             patch("radar_check.set_radar_sweep_state"), \
             patch("radar_check.time.sleep") as mock_sleep:
            radar_check.run_sweep({"radar_enabled": True})
        mock_sleep.assert_not_called()  # 1 bloco só — nada pra espaçar

    @patch("radar_check.RADAR_DIRECTIONS", (("GIG", "BSB"), ("SDU", "BSB")))
    @patch("radar_check.RADAR_WINDOW_DAYS", 182)  # 3 blocos por direção (61+61+60)
    def test_total_anomaly_interrupts_before_completing_and_alerts(self):
        """100% dos blocos com histórico suficiente vieram anômalos —
        interrompe ANTES de completar todos os blocos disponíveis e avisa no
        Telegram. Blocos gravados antes da interrupção não são desfeitos
        (upsert é por bloco, não transação única) — aqui nenhum bloco tinha
        sido gravado ainda, então 0 upserts é o resultado esperado."""
        with patch("radar_check.get_radar_sweep_state",
                   return_value={"last_sweep_date": None, "sweeps_today": 0}), \
             patch("radar_check.get_weekend_radar_grid_known_count", return_value=20), \
             patch("radar_check.search_dates_block", return_value=[]), \
             patch("radar_check.upsert_weekend_radar_grid") as mock_upsert, \
             patch("radar_check.set_radar_sweep_state"), \
             patch("radar_check.time.sleep"), \
             patch("radar_check.send_message") as mock_send:
            result = radar_check.run_sweep({"radar_enabled": True})
        self.assertTrue(result["blocked"])
        self.assertEqual(result["blocks_checked"], 3)  # havia 6 blocos no total (2 direções x 3)
        mock_upsert.assert_not_called()
        mock_send.assert_called_once()

    @patch("radar_check.RADAR_DIRECTIONS", (("GIG", "BSB"),))
    @patch("radar_check.RADAR_WINDOW_DAYS", 5)
    def test_isolated_anomalous_block_does_not_overwrite_grid(self):
        with patch("radar_check.get_radar_sweep_state",
                   return_value={"last_sweep_date": None, "sweeps_today": 0}), \
             patch("radar_check.get_weekend_radar_grid_known_count", return_value=20), \
             patch("radar_check.search_dates_block", return_value=[]), \
             patch("radar_check.upsert_weekend_radar_grid") as mock_upsert, \
             patch("radar_check.set_radar_sweep_state"), \
             patch("radar_check.time.sleep"), \
             patch("radar_check.send_message") as mock_send:
            result = radar_check.run_sweep({"radar_enabled": True})
        self.assertFalse(result["blocked"])  # só 1 bloco com histórico -- abaixo do mínimo de 3
        mock_upsert.assert_not_called()
        mock_send.assert_not_called()


class ResolveRadarLegPricesTest(unittest.TestCase):
    """Fatia 2 (04/09/2026) — preço do radar pra TODA perna dentro do
    alcance, não só as candidatas de precisão (select_precision_candidates
    continua existindo, com seu próprio filtro de teto/lowest_seen).
    resolve_radar_leg_prices não filtra por teto nenhum: é descoberta pra
    tela, não seleção."""

    TODAY = date.today()
    DEFAULT_SWEPT_AT = "2026-09-04T08:00:00+00:00"

    def grid_row(self, origin, destination, flight_date, price, swept_at=DEFAULT_SWEPT_AT):
        return {
            "origin": origin, "destination": destination, "flight_date": flight_date,
            "price": price, "swept_at": swept_at,
        }

    def test_returns_price_for_leg_far_from_any_ceiling(self):
        """A perna NUNCA seria candidata de precisão (preço muito acima do
        teto, sem lowest_seen pra disparar new_low) — e ainda assim
        resolve_radar_leg_prices devolve o preço, porque aqui não há
        filtro de teto."""
        leg = {**OUTBOUND_LEG, "ceilings_by_user": {"user-a": 100.0}, "lowest_seen": None}
        grid = [self.grid_row("GIG", "BSB", leg["outbound_date"], 900.0)]
        rows = radar_check.resolve_radar_leg_prices([leg], grid, self.TODAY)
        self.assertEqual(rows, [{
            "leg_id": "leg-out-1", "radar_price": 900.0, "radar_airport": "GIG",
            "radar_price_at": self.DEFAULT_SWEPT_AT,
        }])

    def test_picks_cheapest_between_gig_and_sdu(self):
        leg = OUTBOUND_LEG
        grid = [
            self.grid_row("GIG", "BSB", leg["outbound_date"], 280.0),
            self.grid_row("SDU", "BSB", leg["outbound_date"], 250.0),
        ]
        rows = radar_check.resolve_radar_leg_prices([leg], grid, self.TODAY)
        self.assertEqual(rows, [{
            "leg_id": "leg-out-1", "radar_price": 250.0, "radar_airport": "SDU",
            "radar_price_at": self.DEFAULT_SWEPT_AT,
        }])

    def test_radar_price_at_is_the_grid_rows_swept_at_not_now(self):
        """O bug corrigido na revisão de 04/09/2026: a primeira versão desta
        função ignorava o swept_at por linha da grade e main.py carimbava
        datetime.now() (a hora do RUN) em radar_price_at pra toda perna —
        um preço com até RADAR_GRID_MAX_AGE_HOURS de idade virava "agora".
        Aqui a linha da grade tem um swept_at claramente no passado, e o
        resultado tem que carregar ESSE valor, não o momento do teste."""
        leg = OUTBOUND_LEG
        old_swept_at = "2020-01-01T00:00:00+00:00"
        grid = [self.grid_row("GIG", "BSB", leg["outbound_date"], 300.0, swept_at=old_swept_at)]
        rows = radar_check.resolve_radar_leg_prices([leg], grid, self.TODAY)
        self.assertEqual(rows[0]["radar_price_at"], old_swept_at)

    def test_swept_at_follows_the_winning_cheapest_row(self):
        """GIG e SDU podem ter sido varridos em blocos diferentes, com
        swept_at diferentes — o swept_at devolvido tem que ser o da linha
        que de fato venceu (o menor preço), não o de qualquer uma das duas."""
        leg = OUTBOUND_LEG
        grid = [
            self.grid_row("GIG", "BSB", leg["outbound_date"], 280.0, swept_at="2026-09-04T06:00:00+00:00"),
            self.grid_row("SDU", "BSB", leg["outbound_date"], 250.0, swept_at="2026-09-04T09:00:00+00:00"),
        ]
        rows = radar_check.resolve_radar_leg_prices([leg], grid, self.TODAY)
        self.assertEqual(rows[0]["radar_price"], 250.0)
        self.assertEqual(rows[0]["radar_price_at"], "2026-09-04T09:00:00+00:00")

    def test_outbound_leg_airport_is_the_origin(self):
        leg = OUTBOUND_LEG
        grid = [self.grid_row("GIG", "BSB", leg["outbound_date"], 300.0)]
        rows = radar_check.resolve_radar_leg_prices([leg], grid, self.TODAY)
        self.assertEqual(rows[0]["radar_airport"], "GIG")

    def test_return_leg_airport_is_the_destination(self):
        leg = {**OUTBOUND_LEG, "id": "ret-1", "direction": "return"}
        grid = [self.grid_row("BSB", "SDU", leg["return_sunday"], 300.0)]
        rows = radar_check.resolve_radar_leg_prices([leg], grid, self.TODAY)
        self.assertEqual(rows, [{
            "leg_id": "ret-1", "radar_price": 300.0, "radar_airport": "SDU",
            "radar_price_at": self.DEFAULT_SWEPT_AT,
        }])

    def test_leg_outside_radar_window_is_skipped(self):
        far = {**OUTBOUND_LEG, "outbound_date": days_from_today(320)}
        grid = [self.grid_row("GIG", "BSB", far["outbound_date"], 200.0)]
        rows = radar_check.resolve_radar_leg_prices([far], grid, self.TODAY)
        self.assertEqual(rows, [])

    def test_leg_without_grid_data_is_skipped(self):
        rows = radar_check.resolve_radar_leg_prices([OUTBOUND_LEG], [], self.TODAY)
        self.assertEqual(rows, [])

    def test_multiple_legs_each_get_their_own_row(self):
        leg_a = {**OUTBOUND_LEG, "id": "leg-a", "outbound_date": days_from_today(10)}
        leg_b = {**OUTBOUND_LEG, "id": "leg-b", "outbound_date": days_from_today(20)}
        grid = [
            self.grid_row("GIG", "BSB", leg_a["outbound_date"], 200.0),
            self.grid_row("GIG", "BSB", leg_b["outbound_date"], 300.0),
        ]
        rows = radar_check.resolve_radar_leg_prices([leg_a, leg_b], grid, self.TODAY)
        self.assertEqual({r["leg_id"]: r["radar_price"] for r in rows}, {"leg-a": 200.0, "leg-b": 300.0})


class LoadRadarGridForLegsTest(unittest.TestCase):
    """Extraído de load_radar_candidates (Fatia 2) — main.py reusa a MESMA
    leitura pra gravar radar_price em toda perna E selecionar candidatas de
    precisão, uma única consulta à grade por execução."""

    def test_queries_grid_with_leg_dates_and_freshness_window(self):
        leg = OUTBOUND_LEG
        with patch("radar_check.current_brt_date", return_value=date.today().isoformat()), \
             patch("radar_check.get_weekend_radar_grid_for_dates", return_value=[]) as mock_get:
            today, grid = radar_check.load_radar_grid_for_legs([leg])
        self.assertEqual(today, date.today())
        self.assertEqual(grid, [])
        called_dates, since_iso = mock_get.call_args.args
        self.assertEqual(called_dates, [leg["outbound_date"]])
        since_dt = datetime.fromisoformat(since_iso)
        age = datetime.now(timezone.utc) - since_dt
        self.assertAlmostEqual(age.total_seconds(), radar_check.RADAR_GRID_MAX_AGE_HOURS * 3600, delta=5)


class LoadRadarCandidatesReusesGridTest(unittest.TestCase):
    """load_radar_candidates aceita today/grid já carregados (main.py) pra
    não duplicar a consulta feita por load_radar_grid_for_legs pra gravar
    radar_price em todas as pernas; sem eles, carrega do zero (chamador
    antigo, se algum dia existir, continua funcionando sem mudança)."""

    def test_reuses_provided_grid_without_querying_again(self):
        leg = {**OUTBOUND_LEG, "ceilings_by_user": {"user-a": 300.0}}
        grid = [{"origin": "GIG", "destination": "BSB", "flight_date": leg["outbound_date"], "price": 250.0}]
        with patch("radar_check.get_weekend_radar_grid_for_dates") as mock_get:
            candidates = radar_check.load_radar_candidates(
                {"radar_precision_max_per_run": 10}, [leg], today=date.today(), grid=grid,
            )
        mock_get.assert_not_called()
        self.assertEqual(len(candidates), 1)

    def test_falls_back_to_loading_grid_when_not_provided(self):
        leg = {**OUTBOUND_LEG, "ceilings_by_user": {"user-a": 300.0}}
        with patch("radar_check.current_brt_date", return_value=date.today().isoformat()), \
             patch("radar_check.get_weekend_radar_grid_for_dates", return_value=[]) as mock_get:
            candidates = radar_check.load_radar_candidates({"radar_precision_max_per_run": 10}, [leg])
        mock_get.assert_called_once()
        self.assertEqual(candidates, [])


class BuildPrecisionComparisonRowTest(unittest.TestCase):
    """Fatia 2, item 7 — persistência da comparação radar×precisão que
    log_precision_divergence já calcula e só imprime (log do Actions
    expira). Mesma aritmética de diff_pct, em formato de linha de banco."""

    def candidate(self, direction="outbound", radar_price=300.0):
        leg = {**OUTBOUND_LEG, "id": "leg-1", "direction": direction}
        # Par (origem, destino) na direção REAL — ida é aeroporto→BSB, volta
        # é BSB→aeroporto (nit da revisão de 04/09/2026: a fixture antiga
        # usava GIG/BSB fixos pras duas direções, invertendo a volta; o
        # teste passava mesmo assim porque só depende de qual EXTREMO
        # _leg_airport escolhe, não de qual aeroporto é qual — mas confundia
        # quem lesse).
        radar_origin, radar_destination = ("GIG", "BSB") if direction == "outbound" else ("BSB", "GIG")
        return {
            "leg": leg, "travel_date": leg["outbound_date"], "radar_price": radar_price,
            "radar_origin": radar_origin, "radar_destination": radar_destination,
            "max_ceiling": 350.0, "gap": 50.0,
        }

    def test_ok_report_computes_diff_pct_and_carries_precision_fields(self):
        report = {"status": "ok", "price": 330.0, "airport": "GIG", "transfers": 0}
        row = radar_check.build_precision_comparison_row(self.candidate(), report, "2026-09-04T12:00:00+00:00")
        self.assertEqual(row["leg_id"], "leg-1")
        self.assertEqual(row["radar_price"], 300.0)
        self.assertEqual(row["precision_price"], 330.0)
        self.assertEqual(row["precision_status"], "ok")
        self.assertEqual(row["precision_airport"], "GIG")
        self.assertEqual(row["precision_transfers"], 0)
        self.assertAlmostEqual(row["diff_pct"], 10.0)
        self.assertEqual(row["checked_at"], "2026-09-04T12:00:00+00:00")

    def test_ok_report_with_a_connection_carries_the_transfer_count(self):
        """Item 3 da revisão de 04/09/2026: sem esta coluna, o checkpoint de
        01/12/2026 não tinha como distinguir voo direto de voo com escala —
        precision_airport sozinho só diz GIG/SDU."""
        report = {"status": "ok", "price": 330.0, "airport": "GIG", "transfers": 1}
        row = radar_check.build_precision_comparison_row(self.candidate(), report, "x")
        self.assertEqual(row["precision_transfers"], 1)

    def test_no_data_report_has_null_precision_fields(self):
        report = {"status": "no_data"}
        row = radar_check.build_precision_comparison_row(self.candidate(), report, "2026-09-04T12:00:00+00:00")
        self.assertIsNone(row["precision_price"])
        self.assertIsNone(row["precision_airport"])
        self.assertIsNone(row["precision_transfers"])
        self.assertIsNone(row["diff_pct"])
        self.assertEqual(row["precision_status"], "no_data")

    def test_radar_airport_is_origin_for_outbound(self):
        report = {"status": "no_data"}
        row = radar_check.build_precision_comparison_row(self.candidate(direction="outbound"), report, "x")
        self.assertEqual(row["radar_airport"], "GIG")

    def test_radar_airport_is_destination_for_return(self):
        report = {"status": "no_data"}
        row = radar_check.build_precision_comparison_row(self.candidate(direction="return"), report, "x")
        self.assertEqual(row["radar_airport"], "GIG")


if __name__ == "__main__":
    unittest.main()
