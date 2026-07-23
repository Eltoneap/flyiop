"""Teste local do lote fast-flights (live_check.py) — Parte 3 (23/07/2026).

Roda 100% com mocks — nenhuma chamada real ao fast-flights nem ao Supabase.
Uso: python -m unittest tests/test_live_check.py -v  (a partir da raiz do repo)
"""
import os
import sys
import unittest
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import live_check  # noqa: E402
import main  # noqa: E402


def fake_result(price: float, num_legs: int = 1):
    return SimpleNamespace(price=price, flights=[None] * num_legs)


def days_from_today(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


OUTBOUND_LEG = {
    "id": "leg-out-1", "weekend_id": "wknd-1", "direction": "outbound",
    "outbound_date": days_from_today(10), "return_sunday": days_from_today(12),
    "return_monday": days_from_today(13), "price_ceiling": 200, "current_price": None,
    "lowest_seen": None, "last_live_check_at": None,
}

RETURN_LEG = {
    "id": "leg-ret-1", "weekend_id": "wknd-1", "direction": "return",
    "outbound_date": days_from_today(10), "return_sunday": days_from_today(12),
    "return_monday": days_from_today(13), "price_ceiling": 200, "current_price": None,
    "lowest_seen": None, "last_live_check_at": None,
}

SETTINGS = {
    "notification_mode": "alert_only",
    "fast_flights_enabled": True,
    "fast_flights_daily_batch_size": 20,
    "weekend_opportunity_pct": 15,
    "suspicious_below_avg_pct": 50,
}


class CheckLivePriceTest(unittest.TestCase):
    @patch("live_check.get_flights")
    @patch("live_check.create_query")
    def test_success_returns_cheapest(self, mock_create, mock_get_flights):
        mock_get_flights.return_value = [fake_result(500.0, 2), fake_result(350.0, 1)]
        result = live_check.check_live_price("GIG", "BSB", "2026-09-04")
        self.assertEqual(result["price"], 350.0)
        self.assertEqual(result["transfers"], 0)

    @patch("live_check.get_flights")
    @patch("live_check.create_query")
    def test_zero_price_entries_are_ignored(self, mock_create, mock_get_flights):
        mock_get_flights.return_value = [fake_result(0)]
        result = live_check.check_live_price("GIG", "BSB", "2026-09-04")
        self.assertIsNone(result)

    @patch("live_check.get_flights")
    @patch("live_check.create_query")
    def test_empty_results_is_none(self, mock_create, mock_get_flights):
        mock_get_flights.return_value = []
        result = live_check.check_live_price("GIG", "BSB", "2026-09-04")
        self.assertIsNone(result)

    @patch("live_check.get_flights", side_effect=RuntimeError("bloqueado"))
    @patch("live_check.create_query")
    def test_exception_is_caught_as_none(self, mock_create, mock_get_flights):
        result = live_check.check_live_price("GIG", "BSB", "2026-09-04")
        self.assertIsNone(result)


class LegTravelDateTest(unittest.TestCase):
    def test_outbound_uses_outbound_date(self):
        self.assertEqual(live_check.leg_travel_date(OUTBOUND_LEG), OUTBOUND_LEG["outbound_date"])

    def test_return_defaults_to_sunday_when_no_variant_known(self):
        self.assertEqual(live_check.leg_travel_date(RETURN_LEG), RETURN_LEG["return_sunday"])

    def test_return_uses_known_variant(self):
        leg = {**RETURN_LEG, "current_variant": "monday"}
        self.assertEqual(live_check.leg_travel_date(leg), RETURN_LEG["return_monday"])


class SelectBatchTest(unittest.TestCase):
    def test_legs_beyond_window_are_excluded(self):
        near = {**OUTBOUND_LEG, "id": "near", "outbound_date": days_from_today(30)}
        far = {**OUTBOUND_LEG, "id": "far", "outbound_date": days_from_today(300)}
        with patch("live_check.get_active_legs", return_value=[near, far]):
            batch = live_check.select_batch(SETTINGS)
        ids = [leg["id"] for leg in batch]
        self.assertIn("near", ids)
        self.assertNotIn("far", ids)

    def test_never_checked_legs_come_first(self):
        checked = {**OUTBOUND_LEG, "id": "checked", "last_live_check_at": "2026-07-20T10:00:00Z"}
        never_checked = {**OUTBOUND_LEG, "id": "never", "last_live_check_at": None}
        with patch("live_check.get_active_legs", return_value=[checked, never_checked]):
            batch = live_check.select_batch(SETTINGS)
        self.assertEqual(batch[0]["id"], "never")

    def test_batch_size_respected(self):
        legs = [{**OUTBOUND_LEG, "id": f"leg-{i}", "outbound_date": days_from_today(10 + i)} for i in range(5)]
        settings = {**SETTINGS, "fast_flights_daily_batch_size": 3}
        with patch("live_check.get_active_legs", return_value=legs):
            batch = live_check.select_batch(settings)
        self.assertEqual(len(batch), 3)

    def test_tie_break_prefers_nearest_date(self):
        far = {**OUTBOUND_LEG, "id": "far", "outbound_date": days_from_today(60)}
        near = {**OUTBOUND_LEG, "id": "near", "outbound_date": days_from_today(15)}
        with patch("live_check.get_active_legs", return_value=[far, near]):
            batch = live_check.select_batch(SETTINGS)
        self.assertEqual(batch[0]["id"], "near")


class CheckAndEvaluateLegTest(unittest.TestCase):
    @patch("live_check.update_weekend_leg")
    @patch("live_check.evaluate_and_record_leg_price")
    @patch("live_check.check_live_price")
    def test_gig_success_never_tries_sdu(self, mock_check, mock_evaluate, mock_update):
        mock_check.return_value = {"price": 300.0, "transfers": 0}
        mock_evaluate.return_value = {"leg": OUTBOUND_LEG, "status": "ok", "should_alert": False}
        report, ok = live_check.check_and_evaluate_leg(OUTBOUND_LEG, SETTINGS)
        self.assertTrue(ok)
        mock_check.assert_called_once_with("GIG", "BSB", OUTBOUND_LEG["outbound_date"])
        mock_evaluate.assert_called_once_with(
            OUTBOUND_LEG, SETTINGS, 300.0, "GIG", None, 0, "live"
        )

    @patch("live_check.time.sleep", return_value=None)
    @patch("live_check.update_weekend_leg")
    @patch("live_check.evaluate_and_record_leg_price")
    @patch("live_check.check_live_price")
    def test_falls_back_to_sdu_when_gig_empty(self, mock_check, mock_evaluate, mock_update, _sleep):
        mock_check.side_effect = [None, {"price": 280.0, "transfers": 1}]
        mock_evaluate.return_value = {"leg": OUTBOUND_LEG, "status": "ok", "should_alert": False}
        report, ok = live_check.check_and_evaluate_leg(OUTBOUND_LEG, SETTINGS)
        self.assertTrue(ok)
        self.assertEqual(mock_check.call_args_list[0].args, ("GIG", "BSB", OUTBOUND_LEG["outbound_date"]))
        self.assertEqual(mock_check.call_args_list[1].args, ("SDU", "BSB", OUTBOUND_LEG["outbound_date"]))
        mock_evaluate.assert_called_once_with(
            OUTBOUND_LEG, SETTINGS, 280.0, "SDU", None, 1, "live"
        )

    @patch("live_check.time.sleep", return_value=None)
    @patch("live_check.insert_weekend_leg_run_log")
    @patch("live_check.update_weekend_leg")
    @patch("live_check.check_live_price", return_value=None)
    def test_both_airports_empty_is_no_data(self, mock_check, mock_update, mock_run_log, _sleep):
        report, ok = live_check.check_and_evaluate_leg(OUTBOUND_LEG, SETTINGS)
        self.assertFalse(ok)
        self.assertEqual(report["status"], "no_data")
        mock_update.assert_called_once()
        self.assertIn("last_live_check_at", mock_update.call_args[1])
        mock_run_log.assert_called_once_with("leg-out-1", "no_data", source="live")

    @patch("live_check.update_weekend_leg")
    @patch("live_check.evaluate_and_record_leg_price")
    @patch("live_check.check_live_price", return_value={"price": 300.0, "transfers": 0})
    def test_return_leg_queries_bsb_to_airport(self, mock_check, mock_evaluate, mock_update):
        mock_evaluate.return_value = {"leg": RETURN_LEG, "status": "ok", "should_alert": False}
        live_check.check_and_evaluate_leg(RETURN_LEG, SETTINGS)
        mock_check.assert_called_once_with("BSB", "GIG", RETURN_LEG["return_sunday"])


class RunDailyBatchTest(unittest.TestCase):
    def make_legs(self, n: int) -> list[dict]:
        return [{**OUTBOUND_LEG, "id": f"leg-{i}", "outbound_date": days_from_today(10 + i)} for i in range(n)]

    def test_kill_switch_skips_entirely(self):
        settings = {**SETTINGS, "fast_flights_enabled": False}
        with patch("live_check.select_batch") as mock_select, \
             patch("live_check.check_and_evaluate_leg") as mock_check:
            reports = live_check.run_daily_batch(settings)
        self.assertEqual(reports, [])
        mock_select.assert_not_called()
        mock_check.assert_not_called()

    def test_empty_batch_returns_empty(self):
        with patch("live_check.select_batch", return_value=[]):
            reports = live_check.run_daily_batch(SETTINGS)
        self.assertEqual(reports, [])

    @patch("live_check.time.sleep", return_value=None)
    def test_all_success_processes_whole_batch_no_alert(self, _sleep):
        legs = self.make_legs(10)
        ok_report = {"leg": None, "status": "ok"}
        with patch("live_check.select_batch", return_value=legs), \
             patch("live_check.check_and_evaluate_leg", return_value=(ok_report, True)), \
             patch("live_check.send_message") as mock_send:
            reports = live_check.run_daily_batch(SETTINGS)
        self.assertEqual(len(reports), 10)
        mock_send.assert_not_called()

    @patch("live_check.time.sleep", return_value=None)
    def test_five_consecutive_failures_stops_batch_and_alerts(self, _sleep):
        legs = self.make_legs(10)
        ok_report = {"leg": None, "status": "ok"}
        fail_report = {"leg": None, "status": "no_data"}
        # 4 sucessos, depois 5 falhas seguidas -> deve parar aos 9 processados
        results = [(ok_report, True)] * 4 + [(fail_report, False)] * 5 + [(ok_report, True)] * 1
        with patch("live_check.select_batch", return_value=legs), \
             patch("live_check.check_and_evaluate_leg", side_effect=results), \
             patch("live_check.send_message") as mock_send:
            reports = live_check.run_daily_batch(SETTINGS)
        self.assertEqual(len(reports), 9)  # parou antes do 10º
        mock_send.assert_called_once_with(live_check.BLOCK_ALERT_MESSAGE)

    @patch("live_check.time.sleep", return_value=None)
    def test_low_success_rate_with_enough_sample_stops_batch(self, _sleep):
        legs = self.make_legs(10)
        ok_report = {"leg": None, "status": "ok"}
        fail_report = {"leg": None, "status": "no_data"}
        # O,F,F,O,F,F,O,F -> nunca 5 falhas seguidas (máximo 2), mas taxa cai
        # pra 3/8=37.5% no 8º item -> deve bloquear ali, via taxa, não sequência
        results = [
            (ok_report, True), (fail_report, False), (fail_report, False),
            (ok_report, True), (fail_report, False), (fail_report, False),
            (ok_report, True), (fail_report, False),
        ]
        with patch("live_check.select_batch", return_value=legs), \
             patch("live_check.check_and_evaluate_leg", side_effect=results), \
             patch("live_check.send_message") as mock_send:
            reports = live_check.run_daily_batch(SETTINGS)
        self.assertEqual(len(reports), 8)
        mock_send.assert_called_once_with(live_check.BLOCK_ALERT_MESSAGE)

    @patch("live_check.time.sleep", return_value=None)
    def test_low_success_rate_with_small_sample_does_not_stop(self, _sleep):
        legs = self.make_legs(3)
        ok_report = {"leg": None, "status": "ok"}
        fail_report = {"leg": None, "status": "no_data"}
        # 1 sucesso, 2 falhas -> taxa 33%, mas amostra (3) < mínimo (8) -> não bloqueia
        results = [(ok_report, True), (fail_report, False), (fail_report, False)]
        with patch("live_check.select_batch", return_value=legs), \
             patch("live_check.check_and_evaluate_leg", side_effect=results), \
             patch("live_check.send_message") as mock_send:
            reports = live_check.run_daily_batch(SETTINGS)
        self.assertEqual(len(reports), 3)
        mock_send.assert_not_called()


class DedupeWeekendReportsTest(unittest.TestCase):
    """Cache e live podem achar a mesma perna no mesmo run — sem dedupe,
    o alerta sairia duplicado (alert_log só é gravado depois, no laço de
    envio, então o cooldown não veria a duplicata a tempo)."""

    def leg(self, leg_id="leg-1"):
        return {"id": leg_id}

    def test_live_ok_wins_over_cache_ok_for_same_leg(self):
        cache_r = {"leg": self.leg(), "status": "ok", "source": "cache", "price": 400.0}
        live_r = {"leg": self.leg(), "status": "ok", "source": "live", "price": 350.0}
        result = main.dedupe_weekend_reports([cache_r, live_r])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source"], "live")

    def test_order_of_appearance_does_not_matter(self):
        cache_r = {"leg": self.leg(), "status": "ok", "source": "cache", "price": 400.0}
        live_r = {"leg": self.leg(), "status": "ok", "source": "live", "price": 350.0}
        result = main.dedupe_weekend_reports([live_r, cache_r])
        self.assertEqual(result[0]["source"], "live")

    def test_cache_ok_wins_over_live_no_data(self):
        cache_r = {"leg": self.leg(), "status": "ok", "source": "cache", "price": 400.0}
        live_r = {"leg": self.leg(), "status": "no_data"}
        result = main.dedupe_weekend_reports([cache_r, live_r])
        self.assertEqual(result[0]["status"], "ok")

    def test_no_data_wins_over_error(self):
        error_r = {"leg": self.leg(), "status": "error"}
        no_data_r = {"leg": self.leg(), "status": "no_data"}
        result = main.dedupe_weekend_reports([error_r, no_data_r])
        self.assertEqual(result[0]["status"], "no_data")

    def test_different_legs_are_not_merged(self):
        r1 = {"leg": self.leg("leg-1"), "status": "ok", "source": "live", "price": 300.0}
        r2 = {"leg": self.leg("leg-2"), "status": "ok", "source": "live", "price": 400.0}
        result = main.dedupe_weekend_reports([r1, r2])
        self.assertEqual(len(result), 2)

    def test_preserves_first_seen_order(self):
        r1 = {"leg": self.leg("leg-1"), "status": "ok", "source": "live"}
        r2 = {"leg": self.leg("leg-2"), "status": "ok", "source": "live"}
        r1_dup = {"leg": self.leg("leg-1"), "status": "no_data"}
        result = main.dedupe_weekend_reports([r1, r2, r1_dup])
        self.assertEqual([r["leg"]["id"] for r in result], ["leg-1", "leg-2"])


if __name__ == "__main__":
    unittest.main()
