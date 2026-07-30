"""Teste local do escalonamento automático de frequência (Parte 10,
28/07/2026) — funções puras, sem I/O nem mocks de rede.

Correção de 30/07/2026: a decisão de "isso roda agora?" deixou de ser por
igualdade exata de hora BRT contra o cron (bug real em produção — atraso de
disparo do GitHub Actions zerava a execução inteira) e passou a ser por
estado gravado (data da última execução primária, contagem de lotes fli já
rodados hoje). As classes abaixo cobrem especificamente essa mudança,
incluindo os três cenários de risco: disparo atrasado ainda executa 1x/dia,
disparo atrasado não roda lote extra além da cota do estágio, e disparo
duplicado da mesma janela não roda em dobro.

Uso: python -m unittest tests/test_scrape_schedule.py -v  (a partir da raiz do repo)
"""
import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import scrape_schedule as sched  # noqa: E402

TODAY = "2026-07-30"
YESTERDAY = "2026-07-29"


class CurrentBrtHourTest(unittest.TestCase):
    def test_maps_utc_to_brt(self):
        with patch("scrape_schedule.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 28, 11, 0, tzinfo=timezone.utc)
            self.assertEqual(sched.current_brt_hour(), 8)

    def test_wraps_around_midnight(self):
        with patch("scrape_schedule.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 28, 1, 0, tzinfo=timezone.utc)
            self.assertEqual(sched.current_brt_hour(), 22)  # 01h UTC = 22h BRT do dia anterior


class CurrentBrtDateTest(unittest.TestCase):
    def test_same_calendar_day(self):
        with patch("scrape_schedule.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 30, 12, 21, tzinfo=timezone.utc)
            self.assertEqual(sched.current_brt_date(), "2026-07-30")

    def test_rolls_back_a_day_just_after_utc_midnight(self):
        # 02h UTC = 23h BRT do dia anterior — data BRT tem que refletir isso,
        # não a data UTC.
        with patch("scrape_schedule.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 30, 2, 0, tzinfo=timezone.utc)
            self.assertEqual(sched.current_brt_date(), "2026-07-29")


class IsPrimaryRunTest(unittest.TestCase):
    def test_no_record_yet_is_primary(self):
        self.assertTrue(sched.is_primary_run({}, TODAY))

    def test_already_ran_today_is_not_primary(self):
        state = {"last_primary_run_date": TODAY}
        self.assertFalse(sched.is_primary_run(state, TODAY))

    def test_ran_on_a_different_date_is_primary_again(self):
        state = {"last_primary_run_date": YESTERDAY}
        self.assertTrue(sched.is_primary_run(state, TODAY))

    def test_scenario_a_delayed_run_still_executes_once_per_day(self):
        # A execução "primária" pode chegar a qualquer hora (atraso de cron
        # do GitHub Actions) — o que importa é ser a primeira do dia.
        state = {}
        self.assertTrue(sched.is_primary_run(state, TODAY))
        state = sched.record_primary_run(state, TODAY)
        # Uma segunda execução no mesmo dia (ex.: janela extra do estágio,
        # também atrasada) não deve rodar de novo como primária.
        self.assertFalse(sched.is_primary_run(state, TODAY))


class ShouldRunLiveBatchTest(unittest.TestCase):
    def test_stage_0_runs_once_then_stops(self):
        state = {}
        self.assertTrue(sched.should_run_live_batch(0, state, TODAY))
        state = sched.record_batch_run(state, TODAY)
        self.assertFalse(sched.should_run_live_batch(0, state, TODAY))

    def test_scenario_b_stage_1_runs_exactly_twice_even_if_delayed(self):
        # Simula 3 execuções no mesmo dia (ex.: janelas atrasadas que
        # colidem) — só as 2 primeiras devem rodar o lote, a 3ª não, mesmo
        # que a hora real de cada uma não bata com nenhum horário "esperado".
        state = {}
        results = []
        for _ in range(3):
            should_run = sched.should_run_live_batch(1, state, TODAY)
            results.append(should_run)
            if should_run:
                state = sched.record_batch_run(state, TODAY)
        self.assertEqual(results, [True, True, False])

    def test_stage_2_runs_exactly_three_times(self):
        state = {}
        results = []
        for _ in range(4):
            should_run = sched.should_run_live_batch(2, state, TODAY)
            results.append(should_run)
            if should_run:
                state = sched.record_batch_run(state, TODAY)
        self.assertEqual(results, [True, True, True, False])

    def test_quota_resets_on_a_new_day(self):
        state = {}
        state = sched.record_batch_run(state, TODAY)
        self.assertFalse(sched.should_run_live_batch(0, state, TODAY))
        tomorrow = "2026-07-31"
        self.assertTrue(sched.should_run_live_batch(0, state, tomorrow))

    def test_scenario_c_duplicate_fire_of_same_window_does_not_run_twice(self):
        # GitHub Actions dispara a mesma janela agendada duas vezes (retry,
        # falha transitória seguida de novo disparo, etc.) — a segunda
        # chamada com o mesmo estado pós-gravação não deve rodar de novo.
        state = {}
        self.assertTrue(sched.should_run_live_batch(0, state, TODAY))
        state = sched.record_batch_run(state, TODAY)
        self.assertFalse(sched.should_run_live_batch(0, state, TODAY))


class IsLastExpectedBatchTest(unittest.TestCase):
    def test_stage_0_first_batch_is_always_last(self):
        self.assertTrue(sched.is_last_expected_batch(0, {}, TODAY))

    def test_stage_1_first_of_two_is_not_last(self):
        self.assertFalse(sched.is_last_expected_batch(1, {}, TODAY))

    def test_stage_1_second_of_two_is_last(self):
        state = sched.record_batch_run({}, TODAY)
        self.assertTrue(sched.is_last_expected_batch(1, state, TODAY))

    def test_stage_2_only_third_batch_is_last(self):
        state = {}
        self.assertFalse(sched.is_last_expected_batch(2, state, TODAY))
        state = sched.record_batch_run(state, TODAY)
        self.assertFalse(sched.is_last_expected_batch(2, state, TODAY))
        state = sched.record_batch_run(state, TODAY)
        self.assertTrue(sched.is_last_expected_batch(2, state, TODAY))


class RecordPrimaryRunTest(unittest.TestCase):
    def test_sets_last_primary_run_date_without_touching_other_fields(self):
        state = {"stage": 1, "clean_days": 3}
        result = sched.record_primary_run(state, TODAY)
        self.assertEqual(result["last_primary_run_date"], TODAY)
        self.assertEqual(result["stage"], 1)
        self.assertEqual(result["clean_days"], 3)


class RecordBatchRunTest(unittest.TestCase):
    def test_first_call_today_sets_count_to_1(self):
        result = sched.record_batch_run({}, TODAY)
        self.assertEqual(result["last_batch_run_date"], TODAY)
        self.assertEqual(result["batches_run_today"], 1)

    def test_second_call_same_day_increments(self):
        state = sched.record_batch_run({}, TODAY)
        state = sched.record_batch_run(state, TODAY)
        self.assertEqual(state["batches_run_today"], 2)

    def test_stale_count_from_a_previous_day_is_ignored(self):
        state = {"last_batch_run_date": YESTERDAY, "batches_run_today": 3}
        result = sched.record_batch_run(state, TODAY)
        self.assertEqual(result["batches_run_today"], 1)


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

    def test_preserves_unrelated_fields(self):
        state = {
            "stage": 1, "clean_days": 2, "blocked_today": False,
            "last_primary_run_date": TODAY, "batches_run_today": 1,
        }
        result = sched.apply_block_reversion(state)
        self.assertEqual(result["last_primary_run_date"], TODAY)
        self.assertEqual(result["batches_run_today"], 1)


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
