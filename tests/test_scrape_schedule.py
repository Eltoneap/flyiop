"""Teste local do escalonamento automático de frequência (Parte 10,
28/07/2026) — funções puras, sem I/O nem mocks de rede.

Uso: python -m unittest tests/test_scrape_schedule.py -v  (a partir da raiz do repo)
"""
import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import scrape_schedule as sched  # noqa: E402


class CurrentBrtHourTest(unittest.TestCase):
    def test_maps_utc_to_brt(self):
        with patch("scrape_schedule.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 28, 11, 0, tzinfo=timezone.utc)
            self.assertEqual(sched.current_brt_hour(), 8)

    def test_wraps_around_midnight(self):
        with patch("scrape_schedule.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 28, 1, 0, tzinfo=timezone.utc)
            self.assertEqual(sched.current_brt_hour(), 22)  # 01h UTC = 22h BRT do dia anterior


class IsPrimaryRunTest(unittest.TestCase):
    def test_8h_is_primary(self):
        self.assertTrue(sched.is_primary_run(8))

    def test_14h_and_20h_are_not_primary(self):
        self.assertFalse(sched.is_primary_run(14))
        self.assertFalse(sched.is_primary_run(20))


class ShouldRunLiveBatchTest(unittest.TestCase):
    def test_stage_0_only_8h(self):
        self.assertTrue(sched.should_run_live_batch(0, 8))
        self.assertFalse(sched.should_run_live_batch(0, 14))
        self.assertFalse(sched.should_run_live_batch(0, 20))

    def test_stage_1_8h_and_20h(self):
        self.assertTrue(sched.should_run_live_batch(1, 8))
        self.assertFalse(sched.should_run_live_batch(1, 14))
        self.assertTrue(sched.should_run_live_batch(1, 20))

    def test_stage_2_all_three(self):
        for hour in (8, 14, 20):
            self.assertTrue(sched.should_run_live_batch(2, hour))


class IsLastScheduledHourTest(unittest.TestCase):
    def test_stage_0_last_hour_is_8h(self):
        self.assertTrue(sched.is_last_scheduled_hour(0, 8))
        self.assertFalse(sched.is_last_scheduled_hour(0, 14))

    def test_stage_1_last_hour_is_20h(self):
        self.assertFalse(sched.is_last_scheduled_hour(1, 8))
        self.assertTrue(sched.is_last_scheduled_hour(1, 20))

    def test_stage_2_last_hour_is_20h(self):
        self.assertFalse(sched.is_last_scheduled_hour(2, 14))
        self.assertTrue(sched.is_last_scheduled_hour(2, 20))


class ApplyBlockReversionTest(unittest.TestCase):
    def test_reverts_from_any_stage(self):
        state = {"stage": 2, "clean_days": 3, "blocked_today": False}
        result = sched.apply_block_reversion(state)
        self.assertEqual(result["stage"], 0)
        self.assertEqual(result["clean_days"], 0)
        self.assertTrue(result["blocked_today"])
        self.assertTrue(result["changed"])

    def test_no_change_flag_when_already_stage_0(self):
        state = {"stage": 0, "clean_days": 0, "blocked_today": False}
        result = sched.apply_block_reversion(state)
        self.assertFalse(result["changed"])


class EvaluateStageTransitionTest(unittest.TestCase):
    def test_increments_without_escalating_below_threshold(self):
        state = {"stage": 0, "clean_days": 2, "blocked_today": False}
        result = sched.evaluate_stage_transition(state)
        self.assertEqual(result["stage"], 0)
        self.assertEqual(result["clean_days"], 3)
        self.assertFalse(result["changed"])

    def test_escalates_exactly_on_5th_clean_day(self):
        state = {"stage": 0, "clean_days": 4, "blocked_today": False}
        result = sched.evaluate_stage_transition(state)
        self.assertEqual(result["stage"], 1)
        self.assertEqual(result["clean_days"], 0)
        self.assertTrue(result["changed"])

    def test_escalates_stage_1_to_2(self):
        state = {"stage": 1, "clean_days": 4, "blocked_today": False}
        result = sched.evaluate_stage_transition(state)
        self.assertEqual(result["stage"], 2)
        self.assertTrue(result["changed"])

    def test_never_escalates_past_stage_2(self):
        state = {"stage": 2, "clean_days": 4, "blocked_today": False}
        result = sched.evaluate_stage_transition(state)
        self.assertEqual(result["stage"], 2)
        self.assertFalse(result["changed"])


if __name__ == "__main__":
    unittest.main()
