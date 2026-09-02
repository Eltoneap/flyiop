"""Teste local do lote de consulta ao vivo (live_check.py) — Parte 3
(23/07/2026), migrado de fast_flights pra fli na Parte 7 (24/07/2026).

Roda 100% com mocks — nenhuma chamada real ao fli nem ao Supabase.
Uso: python -m unittest tests/test_live_check.py -v  (a partir da raiz do repo)
"""
import os
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import live_check  # noqa: E402
import main  # noqa: E402
from telegram_notifier import (  # noqa: E402
    build_block_alert_message,
    build_block_recovered_message,
    build_weekend_alert_message,
    user_label,
)


def fake_result(price, stops: int = 0, airline: str = "LATAM", legs=None):
    if legs is None:
        legs = [SimpleNamespace(departure_datetime=datetime(2026, 9, 4, 8, 30))]
    return SimpleNamespace(price=price, stops=stops, primary_airline_name=airline, legs=legs)


def days_from_today(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


USER_A = "user-a"

OUTBOUND_LEG = {
    "id": "leg-out-1", "weekend_id": "wknd-1", "direction": "outbound",
    "outbound_date": days_from_today(10), "return_sunday": days_from_today(12),
    "return_monday": days_from_today(13), "ceilings_by_user": {USER_A: 200},
    "queue_ceiling": 200, "current_price": None,
    "lowest_seen": None, "last_live_check_at": None,
}

RETURN_LEG = {
    "id": "leg-ret-1", "weekend_id": "wknd-1", "direction": "return",
    "outbound_date": days_from_today(10), "return_sunday": days_from_today(12),
    "return_monday": days_from_today(13), "ceilings_by_user": {USER_A: 200},
    "queue_ceiling": 200, "current_price": None,
    "lowest_seen": None, "last_live_check_at": None,
}

# Fatia D4 (15/08/2026): o lote lê SÓ configuração de sistema. `SETTINGS_BY_USER`
# é carga opaca que run_daily_batch transporta até a avaliação e nunca inspeciona.
SYSTEM_SETTINGS = {
    "fast_flights_enabled": True,
    "fast_flights_daily_batch_size": 20,
    "suspicious_below_avg_pct": 50,
}

SETTINGS_BY_USER = {USER_A: {"notification_mode": "alert_only", "weekend_opportunity_pct": 15}}


class CheckLivePriceTest(unittest.TestCase):
    @patch("live_check.SearchFlights")
    def test_success_returns_cheapest(self, mock_cls):
        mock_cls.return_value.search.return_value = [fake_result(500.0, stops=2), fake_result(350.0, stops=0)]
        result = live_check.check_live_price("GIG", "BSB", "2026-09-04")
        self.assertEqual(result["price"], 350.0)
        self.assertEqual(result["transfers"], 0)
        self.assertEqual(result["airline"], "LATAM")
        self.assertEqual(result["departure_time"], "2026-09-04T08:30:00")

    @patch("live_check.SearchFlights")
    def test_no_legs_means_no_departure_time(self, mock_cls):
        # defensivo: se a fli algum dia devolver um resultado sem legs,
        # não deve quebrar a extração — só fica sem horário.
        mock_cls.return_value.search.return_value = [fake_result(350.0, legs=[])]
        result = live_check.check_live_price("GIG", "BSB", "2026-09-04")
        self.assertIsNone(result["departure_time"])

    @patch("live_check.SearchFlights")
    def test_none_price_entries_are_ignored(self, mock_cls):
        # fli deixa price=None quando o Google não expõe tarifa agregada
        # pra aquela linha (comum em cabines premium) — não deve quebrar
        # a escolha do mínimo nem ser tratado como "mais barato".
        mock_cls.return_value.search.return_value = [fake_result(None), fake_result(350.0, stops=1)]
        result = live_check.check_live_price("GIG", "BSB", "2026-09-04")
        self.assertEqual(result["price"], 350.0)
        self.assertEqual(result["transfers"], 1)

    @patch("live_check.SearchFlights")
    def test_all_prices_none_is_none(self, mock_cls):
        mock_cls.return_value.search.return_value = [fake_result(None)]
        result = live_check.check_live_price("GIG", "BSB", "2026-09-04")
        self.assertIsNone(result)

    @patch("live_check.SearchFlights")
    def test_empty_results_is_none(self, mock_cls):
        mock_cls.return_value.search.return_value = []
        result = live_check.check_live_price("GIG", "BSB", "2026-09-04")
        self.assertIsNone(result)

    @patch("live_check.SearchFlights")
    def test_none_results_is_none(self, mock_cls):
        mock_cls.return_value.search.return_value = None
        result = live_check.check_live_price("GIG", "BSB", "2026-09-04")
        self.assertIsNone(result)

    @patch("live_check.SearchFlights", side_effect=RuntimeError("bloqueado"))
    def test_exception_is_caught_as_none(self, mock_cls):
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
            batch = live_check.select_batch(SYSTEM_SETTINGS)
        ids = [leg["id"] for leg in batch]
        self.assertIn("near", ids)
        self.assertNotIn("far", ids)

    def test_never_checked_legs_come_first(self):
        checked = {**OUTBOUND_LEG, "id": "checked", "last_live_check_at": "2026-07-20T10:00:00Z"}
        never_checked = {**OUTBOUND_LEG, "id": "never", "last_live_check_at": None}
        with patch("live_check.get_active_legs", return_value=[checked, never_checked]):
            batch = live_check.select_batch(SYSTEM_SETTINGS)
        self.assertEqual(batch[0]["id"], "never")

    def test_batch_size_respected(self):
        legs = [{**OUTBOUND_LEG, "id": f"leg-{i}", "outbound_date": days_from_today(10 + i)} for i in range(5)]
        settings = {**SYSTEM_SETTINGS, "fast_flights_daily_batch_size": 3}
        with patch("live_check.get_active_legs", return_value=legs):
            batch = live_check.select_batch(settings)
        self.assertEqual(len(batch), 3)

    def test_queue_order_uses_queue_ceiling_not_a_per_user_decision(self):
        """Fatia D4: `sort_key` passou a ler `queue_ceiling` (menor teto entre
        os usuários) — heurística de PRIORIDADE de fila. Mesmo dia e mesmo
        last_check: quem está mais perto de bater meta pra alguém vem antes."""
        far_from_target = {**OUTBOUND_LEG, "id": "longe", "current_price": 900.0, "queue_ceiling": 200}
        near_target = {**OUTBOUND_LEG, "id": "perto", "current_price": 210.0, "queue_ceiling": 200}
        with patch("live_check.get_active_legs", return_value=[far_from_target, near_target]):
            batch = live_check.select_batch(SYSTEM_SETTINGS)
        self.assertEqual([leg["id"] for leg in batch], ["perto", "longe"])

    def test_leg_without_queue_ceiling_sorts_last_without_crashing(self):
        # Modo degradado (ninguém monitorando): sem teto não há "perto de bater
        # meta" pra medir — desempata por último, como perna sem preço.
        no_owner = {**OUTBOUND_LEG, "id": "sem-dono", "current_price": 210.0,
                    "ceilings_by_user": {}, "queue_ceiling": None}
        with_owner = {**OUTBOUND_LEG, "id": "com-dono", "current_price": 210.0, "queue_ceiling": 200}
        with patch("live_check.get_active_legs", return_value=[no_owner, with_owner]):
            batch = live_check.select_batch(SYSTEM_SETTINGS)
        self.assertEqual([leg["id"] for leg in batch], ["com-dono", "sem-dono"])

    def test_select_batch_never_receives_per_user_settings(self):
        """A seleção do lote é sobre QUANTO o robô consulta, não sobre quem
        alerta — `settings_by_user` não entra nesta função."""
        import inspect
        params = list(inspect.signature(live_check.select_batch).parameters)
        self.assertEqual(params, ["system_settings"])

    def test_tie_break_prefers_nearest_date(self):
        far = {**OUTBOUND_LEG, "id": "far", "outbound_date": days_from_today(60)}
        near = {**OUTBOUND_LEG, "id": "near", "outbound_date": days_from_today(15)}
        with patch("live_check.get_active_legs", return_value=[far, near]):
            batch = live_check.select_batch(SYSTEM_SETTINGS)
        self.assertEqual(batch[0]["id"], "near")

    # --- Radar de calendário: regime='price' quando radar_enabled ausente --
    # (trava de regressão) — SYSTEM_SETTINGS não tem a chave 'radar_enabled'
    # (código subiu antes do SQL, ou coluna ainda default false): toda perna
    # elegível continua regime 'price', igual a antes desta fatia.

    def test_radar_key_absent_is_same_as_radar_off(self):
        leg = {**OUTBOUND_LEG, "id": "leg-1"}
        with patch("live_check.get_active_legs", return_value=[leg]):
            batch = live_check.select_batch(SYSTEM_SETTINGS)
        self.assertEqual(batch[0]["_batch_regime"], "price")

    def test_radar_off_leg_beyond_183_days_is_excluded(self):
        """Trava de regressão do bug corrigido nesta revisão: sem radar, o
        cutoff de 183 dias continua valendo exatamente como sempre."""
        far = {**OUTBOUND_LEG, "id": "far", "outbound_date": days_from_today(400)}
        with patch("live_check.get_active_legs", return_value=[far]):
            batch = live_check.select_batch(SYSTEM_SETTINGS)
        self.assertEqual(batch, [])

    def test_radar_on_leg_beyond_source_horizon_is_excluded_from_batch(self):
        """Opção A (01/09/2026): perna além de RADAR_COVERAGE_WINDOW_DAYS não
        entra em consulta ao vivo nenhuma. Até esta data ela entrava com
        regime 'price', ordenava PRIMEIRO (regime_rank=0) e enchia o batch
        com consultas que a fonte não sabe responder — as respostas vazias
        disparavam o detector de bloqueio todo dia."""
        far = {**OUTBOUND_LEG, "id": "far", "outbound_date": days_from_today(400)}
        settings = {**SYSTEM_SETTINGS, "radar_enabled": True}
        with patch("live_check.get_active_legs", return_value=[far]):
            batch = live_check.select_batch(settings)
        self.assertEqual(batch, [])

    def test_radar_on_batch_keeps_only_legs_within_source_horizon(self):
        """Mistura: só a de dentro do alcance entra, e nunca com regime
        'price' (com radar ligado o lote é só refresh de metadado)."""
        inside = {**OUTBOUND_LEG, "id": "dentro", "outbound_date": days_from_today(200)}
        outside = {**OUTBOUND_LEG, "id": "fora", "outbound_date": days_from_today(400)}
        settings = {**SYSTEM_SETTINGS, "radar_enabled": True}
        with patch("live_check.get_active_legs", return_value=[inside, outside]):
            batch = live_check.select_batch(settings)
        self.assertEqual([leg["id"] for leg in batch], ["dentro"])
        self.assertEqual(batch[0]["_batch_regime"], "metadata")

    def test_radar_on_leg_checked_recently_is_excluded_from_batch(self):
        recent = {**OUTBOUND_LEG, "id": "recent", "outbound_date": days_from_today(30),
                  "last_live_check_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()}
        settings = {**SYSTEM_SETTINGS, "radar_enabled": True}
        with patch("live_check.get_active_legs", return_value=[recent]):
            batch = live_check.select_batch(settings)
        self.assertEqual(batch, [])

    def test_radar_on_leg_checked_long_ago_enters_as_metadata(self):
        stale = {**OUTBOUND_LEG, "id": "stale", "outbound_date": days_from_today(30),
                 "last_live_check_at": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()}
        settings = {**SYSTEM_SETTINGS, "radar_enabled": True}
        with patch("live_check.get_active_legs", return_value=[stale]):
            batch = live_check.select_batch(settings)
        self.assertEqual(len(batch), 1)
        self.assertEqual(batch[0]["_batch_regime"], "metadata")

class BatchRegimeTest(unittest.TestCase):
    """Pura — decisão 1 do radar de calendário."""

    TODAY = date.today()

    def test_radar_off_is_always_price(self):
        """Trava de regressão do caminho SEM radar: a checagem de distância
        nem é alcançada (o `return 'price'` vem antes), e quem corta perna
        distante continua sendo o cutoff de 183 dias em select_batch."""
        leg = {**OUTBOUND_LEG, "outbound_date": days_from_today(400)}
        self.assertEqual(live_check.batch_regime(leg, self.TODAY, radar_on=False), "price")

    def test_beyond_source_horizon_is_none(self):
        """Opção A (01/09/2026): além do teto real da fonte (~305 dias) a
        resposta vem VAZIA, não com erro — e o detector de bloqueio conta
        vazio como falha. Mandar essas pernas pro lote (o que este ramo fazia
        até esta data, devolvendo 'price') gerava falso bloqueio diário."""
        leg = {**OUTBOUND_LEG, "outbound_date": days_from_today(320)}
        self.assertIsNone(live_check.batch_regime(leg, self.TODAY, radar_on=True))

    def test_exactly_at_source_horizon_is_still_inside(self):
        """O corte é estrito (`>`): hoje+305 está DENTRO do alcance."""
        leg = {**OUTBOUND_LEG,
               "outbound_date": days_from_today(live_check.RADAR_COVERAGE_WINDOW_DAYS),
               "last_live_check_at": None}
        self.assertEqual(live_check.batch_regime(leg, self.TODAY, radar_on=True), "metadata")

    def test_one_day_beyond_source_horizon_is_none(self):
        leg = {**OUTBOUND_LEG,
               "outbound_date": days_from_today(live_check.RADAR_COVERAGE_WINDOW_DAYS + 1),
               "last_live_check_at": None}
        self.assertIsNone(live_check.batch_regime(leg, self.TODAY, radar_on=True))

    def test_within_window_never_checked_is_metadata(self):
        leg = {**OUTBOUND_LEG, "outbound_date": days_from_today(30), "last_live_check_at": None}
        self.assertEqual(live_check.batch_regime(leg, self.TODAY, radar_on=True), "metadata")

    def test_within_window_checked_recently_is_none(self):
        leg = {**OUTBOUND_LEG, "outbound_date": days_from_today(30),
               "last_live_check_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()}
        self.assertIsNone(live_check.batch_regime(leg, self.TODAY, radar_on=True))

    def test_within_window_checked_exactly_at_threshold_is_metadata(self):
        leg = {**OUTBOUND_LEG, "outbound_date": days_from_today(30),
               "last_live_check_at": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()}
        self.assertEqual(live_check.batch_regime(leg, self.TODAY, radar_on=True), "metadata")


class CheckAndEvaluateLegTest(unittest.TestCase):
    @patch("live_check.update_weekend_leg")
    @patch("live_check.evaluate_and_record_leg_price")
    @patch("live_check.check_live_price")
    def test_gig_success_never_tries_sdu(self, mock_check, mock_evaluate, mock_update):
        mock_check.return_value = {"price": 300.0, "transfers": 0, "airline": "GOL", "departure_time": "2026-09-04T07:00:00"}
        mock_evaluate.return_value = {"leg": OUTBOUND_LEG, "status": "ok", "should_alert": False}
        report, ok = live_check.check_and_evaluate_leg(OUTBOUND_LEG, SYSTEM_SETTINGS, SETTINGS_BY_USER)
        self.assertTrue(ok)
        mock_check.assert_called_once_with("GIG", "BSB", OUTBOUND_LEG["outbound_date"])
        mock_evaluate.assert_called_once_with(
            OUTBOUND_LEG, SYSTEM_SETTINGS, SETTINGS_BY_USER, 300.0, "GIG", None, 0, "live",
            "GOL", "2026-09-04T07:00:00"
        )

    @patch("live_check.time.sleep", return_value=None)
    @patch("live_check.update_weekend_leg")
    @patch("live_check.evaluate_and_record_leg_price")
    @patch("live_check.check_live_price")
    def test_falls_back_to_sdu_when_gig_empty(self, mock_check, mock_evaluate, mock_update, _sleep):
        mock_check.side_effect = [None, {"price": 280.0, "transfers": 1, "airline": "Azul", "departure_time": None}]
        mock_evaluate.return_value = {"leg": OUTBOUND_LEG, "status": "ok", "should_alert": False}
        report, ok = live_check.check_and_evaluate_leg(OUTBOUND_LEG, SYSTEM_SETTINGS, SETTINGS_BY_USER)
        self.assertTrue(ok)
        self.assertEqual(mock_check.call_args_list[0].args, ("GIG", "BSB", OUTBOUND_LEG["outbound_date"]))
        self.assertEqual(mock_check.call_args_list[1].args, ("SDU", "BSB", OUTBOUND_LEG["outbound_date"]))
        mock_evaluate.assert_called_once_with(
            OUTBOUND_LEG, SYSTEM_SETTINGS, SETTINGS_BY_USER, 280.0, "SDU", None, 1, "live",
            "Azul", None
        )

    @patch("live_check.time.sleep", return_value=None)
    @patch("live_check.insert_weekend_leg_run_log")
    @patch("live_check.update_weekend_leg")
    @patch("live_check.check_live_price", return_value=None)
    def test_both_airports_empty_is_no_data(self, mock_check, mock_update, mock_run_log, _sleep):
        report, ok = live_check.check_and_evaluate_leg(OUTBOUND_LEG, SYSTEM_SETTINGS, SETTINGS_BY_USER)
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
        live_check.check_and_evaluate_leg(RETURN_LEG, SYSTEM_SETTINGS, SETTINGS_BY_USER)
        mock_check.assert_called_once_with("BSB", "GIG", RETURN_LEG["return_sunday"])


class RunDailyBatchTest(unittest.TestCase):
    def make_legs(self, n: int) -> list[dict]:
        return [{**OUTBOUND_LEG, "id": f"leg-{i}", "outbound_date": days_from_today(10 + i)} for i in range(n)]

    def test_kill_switch_skips_entirely(self):
        settings = {**SYSTEM_SETTINGS, "fast_flights_enabled": False}
        with patch("live_check.select_batch") as mock_select, \
             patch("live_check.check_and_evaluate_leg") as mock_check:
            reports, blocked = live_check.run_daily_batch(settings, SETTINGS_BY_USER)
        self.assertEqual(reports, [])
        self.assertFalse(blocked)
        mock_select.assert_not_called()
        mock_check.assert_not_called()

    def test_empty_batch_returns_empty(self):
        with patch("live_check.select_batch", return_value=[]):
            reports, blocked = live_check.run_daily_batch(SYSTEM_SETTINGS, SETTINGS_BY_USER)
        self.assertEqual(reports, [])
        self.assertFalse(blocked)

    @patch("live_check.time.sleep", return_value=None)
    def test_radar_on_universe_beyond_horizon_never_queries_nor_blocks(self, _sleep):
        """Reprodução do falso bloqueio diário (29/08–01/09/2026): com o radar
        ligado e o universo de pernas todo além do alcance da fonte, o lote
        enchia de consultas que voltavam vazias e disparava o detector de
        bloqueio. Agora nenhuma consulta sai, nada bloqueia, nada é enviado ao
        Telegram — passa pelo select_batch REAL de propósito (é ele o corte)."""
        far = [{**OUTBOUND_LEG, "id": f"far-{i}", "outbound_date": days_from_today(400 + i)}
               for i in range(10)]
        settings = {**SYSTEM_SETTINGS, "radar_enabled": True}
        with patch("live_check.get_active_legs", return_value=far), \
             patch("live_check.check_live_price") as mock_price, \
             patch("live_check.get_weekend_block_streak", return_value=(0, None)), \
             patch("live_check.send_message") as mock_send:
            reports, blocked = live_check.run_daily_batch(settings, SETTINGS_BY_USER)
        self.assertEqual(reports, [])
        self.assertFalse(blocked)
        mock_price.assert_not_called()
        mock_send.assert_not_called()

    @patch("live_check.time.sleep", return_value=None)
    def test_all_success_processes_whole_batch_no_alert(self, _sleep):
        legs = self.make_legs(10)
        ok_report = {"leg": None, "status": "ok"}
        with patch("live_check.select_batch", return_value=legs), \
             patch("live_check.check_and_evaluate_leg", return_value=(ok_report, True)), \
             patch("live_check.get_weekend_block_streak", return_value=(0, None)), \
             patch("live_check.send_message") as mock_send:
            reports, blocked = live_check.run_daily_batch(SYSTEM_SETTINGS, SETTINGS_BY_USER)
        self.assertEqual(len(reports), 10)
        self.assertFalse(blocked)
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
             patch("live_check.get_last_successful_live_check", return_value=None), \
             patch("live_check.get_weekend_block_streak", return_value=(0, None)), \
             patch("live_check.set_weekend_block_streak") as mock_set_streak, \
             patch("live_check.build_block_alert_message", return_value="sentinel-message") as mock_build, \
             patch("live_check.send_message") as mock_send, \
             patch("live_check.set_weekend_batch_blocked_at") as mock_blocked_at:
            reports, blocked = live_check.run_daily_batch(SYSTEM_SETTINGS, SETTINGS_BY_USER)
        self.assertEqual(len(reports), 9)  # parou antes do 10º
        self.assertTrue(blocked)
        mock_send.assert_called_once_with("sentinel-message")
        mock_blocked_at.assert_called_once()
        mock_set_streak.assert_called_once_with(1, date.today().isoformat())
        diag = mock_build.call_args.args[0]
        self.assertEqual(diag["checked"], 9)
        self.assertEqual(diag["failures"], 5)
        self.assertEqual(diag["reason"], "falhas seguidas")
        self.assertEqual(diag["streak_days"], 1)
        self.assertIsNone(diag["seconds_since_last_success"])
        self.assertEqual(diag["config_url"], live_check.WEEKEND_CONFIG_URL)

    @patch("live_check.time.sleep", return_value=None)
    def test_no_block_never_persists_blocked_at(self, _sleep):
        legs = self.make_legs(3)
        ok_report = {"leg": None, "status": "ok"}
        with patch("live_check.select_batch", return_value=legs), \
             patch("live_check.check_and_evaluate_leg", return_value=(ok_report, True)), \
             patch("live_check.get_weekend_block_streak", return_value=(0, None)), \
             patch("live_check.send_message") as mock_send, \
             patch("live_check.set_weekend_batch_blocked_at") as mock_blocked_at:
            _, blocked = live_check.run_daily_batch(SYSTEM_SETTINGS, SETTINGS_BY_USER)
        self.assertFalse(blocked)
        mock_send.assert_not_called()
        mock_blocked_at.assert_not_called()

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
             patch("live_check.get_last_successful_live_check", return_value=None), \
             patch("live_check.get_weekend_block_streak", return_value=(0, None)), \
             patch("live_check.set_weekend_block_streak") as mock_set_streak, \
             patch("live_check.build_block_alert_message", return_value="sentinel-message") as mock_build, \
             patch("live_check.send_message") as mock_send, \
             patch("live_check.set_weekend_batch_blocked_at") as mock_blocked_at:
            reports, blocked = live_check.run_daily_batch(SYSTEM_SETTINGS, SETTINGS_BY_USER)
        self.assertEqual(len(reports), 8)
        self.assertTrue(blocked)
        mock_send.assert_called_once_with("sentinel-message")
        mock_blocked_at.assert_called_once()
        mock_set_streak.assert_called_once_with(1, date.today().isoformat())
        diag = mock_build.call_args.args[0]
        self.assertEqual(diag["reason"], "taxa de sucesso")

    @patch("live_check.time.sleep", return_value=None)
    def test_low_success_rate_with_small_sample_does_not_stop(self, _sleep):
        legs = self.make_legs(3)
        ok_report = {"leg": None, "status": "ok"}
        fail_report = {"leg": None, "status": "no_data"}
        # 1 sucesso, 2 falhas -> taxa 33%, mas amostra (3) < mínimo (8) -> não bloqueia
        results = [(ok_report, True), (fail_report, False), (fail_report, False)]
        with patch("live_check.select_batch", return_value=legs), \
             patch("live_check.check_and_evaluate_leg", side_effect=results), \
             patch("live_check.get_weekend_block_streak", return_value=(0, None)), \
             patch("live_check.send_message") as mock_send:
            reports, blocked = live_check.run_daily_batch(SYSTEM_SETTINGS, SETTINGS_BY_USER)
        self.assertEqual(len(reports), 3)
        self.assertFalse(blocked)
        mock_send.assert_not_called()

    @patch("live_check.time.sleep", return_value=None)
    def test_second_block_day_increments_streak_keeps_start_date(self, _sleep):
        legs = self.make_legs(5)
        fail_report = {"leg": None, "status": "no_data"}
        with patch("live_check.select_batch", return_value=legs), \
             patch("live_check.check_and_evaluate_leg", return_value=(fail_report, False)), \
             patch("live_check.get_last_successful_live_check", return_value=None), \
             patch("live_check.get_weekend_block_streak", return_value=(1, "2026-07-24")), \
             patch("live_check.set_weekend_block_streak") as mock_set_streak, \
             patch("live_check.build_block_alert_message", return_value="msg"), \
             patch("live_check.send_message"), \
             patch("live_check.set_weekend_batch_blocked_at"):
            live_check.run_daily_batch(SYSTEM_SETTINGS, SETTINGS_BY_USER)
        mock_set_streak.assert_called_once_with(2, "2026-07-24")

    @patch("live_check.time.sleep", return_value=None)
    def test_recovery_after_streak_sends_message_and_resets(self, _sleep):
        legs = self.make_legs(3)
        ok_report = {"leg": None, "status": "ok"}
        with patch("live_check.select_batch", return_value=legs), \
             patch("live_check.check_and_evaluate_leg", return_value=(ok_report, True)), \
             patch("live_check.get_weekend_block_streak", return_value=(3, "2026-07-22")), \
             patch("live_check.set_weekend_block_streak") as mock_set_streak, \
             patch("live_check.build_block_recovered_message", return_value="recovered-message") as mock_build, \
             patch("live_check.send_message") as mock_send:
            live_check.run_daily_batch(SYSTEM_SETTINGS, SETTINGS_BY_USER)
        mock_build.assert_called_once_with(3)
        mock_send.assert_called_once_with("recovered-message")
        mock_set_streak.assert_called_once_with(0, None)

    @patch("live_check.time.sleep", return_value=None)
    def test_no_recovery_message_when_streak_already_zero(self, _sleep):
        legs = self.make_legs(3)
        ok_report = {"leg": None, "status": "ok"}
        with patch("live_check.select_batch", return_value=legs), \
             patch("live_check.check_and_evaluate_leg", return_value=(ok_report, True)), \
             patch("live_check.get_weekend_block_streak", return_value=(0, None)), \
             patch("live_check.set_weekend_block_streak") as mock_set_streak, \
             patch("live_check.send_message") as mock_send:
            live_check.run_daily_batch(SYSTEM_SETTINGS, SETTINGS_BY_USER)
        mock_send.assert_not_called()
        mock_set_streak.assert_not_called()


class BuildPackageComparisonTest(unittest.TestCase):
    """Suspensa em 24/07/2026 (Parte 7) — ver docstring de
    build_package_comparison. Sempre None, independente do input."""

    OUTBOUND_REPORT = {
        "leg": {"id": "leg-out-1"}, "weekend_id": "wknd-1", "direction": "outbound",
        "outbound_date": "2026-09-04", "date": "2026-09-04", "price": 300.0, "airport": "GIG",
    }

    def test_always_returns_none(self):
        result = live_check.build_package_comparison(self.OUTBOUND_REPORT, {"fast_flights_enabled": True})
        self.assertIsNone(result)

    def test_always_returns_none_regardless_of_kill_switch(self):
        result = live_check.build_package_comparison(self.OUTBOUND_REPORT, {"fast_flights_enabled": False})
        self.assertIsNone(result)


class BuildWeekendAlertMessageComparisonTest(unittest.TestCase):
    REPORT = {
        "leg": {"id": "leg-out-1"}, "status": "ok", "direction": "outbound",
        "outbound_date": "2026-09-04", "date": "2026-09-04", "price": 150.0, "airport": "GIG",
        "variant": None, "transfers": 0, "source": "live",
    }
    # Fatia D4: a decisão de UM usuário — o que a mensagem diz depende de quem
    # está olhando, então teto/razão/tipo vêm daqui, não do topo do report.
    DECISION = {
        "user_id": USER_A, "ceiling": 200, "reason": "abaixo da meta fixa (R$ 200)",
        "is_ceiling_hit": True, "is_opportunity_hit": False, "should_alert": True,
    }

    def build(self, comparison):
        return build_weekend_alert_message(self.REPORT, self.DECISION, "Elton", comparison)

    def test_no_comparison_omits_line(self):
        self.assertNotIn("Avulso", self.build(None))

    def test_comparison_with_both_values(self):
        message = self.build({"avulso": 430.0, "pacote": 380.0})
        self.assertIn("💰 Avulso (2 pernas): R$ 430.00 · Pacote (ida+volta): R$ 380.00", message)

    def test_comparison_with_only_avulso(self):
        message = self.build({"avulso": 430.0, "pacote": None})
        self.assertIn("Avulso (2 pernas): R$ 430.00 — pacote indisponível agora", message)
        self.assertNotIn("Pacote (ida+volta)", message)

    def test_comparison_dict_without_avulso_is_ignored(self):
        message = self.build({"pacote": 380.0})
        self.assertNotIn("Avulso", message)
        self.assertNotIn("Pacote", message)


class WeekendAlertMessagePerUserTest(unittest.TestCase):
    """Fatia D4 (15/08/2026): a mensagem passa a dizer DE QUEM é o alerta e a
    mostrar o teto de quem disparou — não mais um teto colapsado por MIN."""

    REPORT = BuildWeekendAlertMessageComparisonTest.REPORT

    def test_shows_the_name_and_ceiling_of_whoever_triggered(self):
        decision = {"ceiling": 300, "reason": "abaixo da meta fixa (R$ 300)", "is_ceiling_hit": True}
        message = build_weekend_alert_message(self.REPORT, decision, "Elton")
        self.assertIn("👤 Elton", message)
        self.assertIn("teto R$ 300", message)

    def test_two_users_get_different_ceilings_in_their_own_messages(self):
        a = build_weekend_alert_message(
            self.REPORT, {"ceiling": 300, "reason": "r", "is_ceiling_hit": True}, "Elton")
        b = build_weekend_alert_message(
            self.REPORT, {"ceiling": 180, "reason": "r", "is_ceiling_hit": True}, "user-b12")
        self.assertIn("teto R$ 300", a)
        self.assertIn("teto R$ 180", b)

    def test_degraded_branch_has_no_name_line_and_no_ceiling_number(self):
        # Ramo degradado: user_label=None e ceiling=None — a mensagem sai como
        # antes da D4, sem nome e dizendo "indisponível" em vez de inventar.
        degraded = {"ceiling": None, "reason": "20% abaixo da média histórica (R$ 400.00)",
                    "is_ceiling_hit": False, "is_opportunity_hit": True}
        message = build_weekend_alert_message(self.REPORT, degraded, None)
        self.assertNotIn("👤", message)
        self.assertIn("teto indisponível", message)
        self.assertIn("Oportunidade", message)

    def test_user_without_ceiling_gets_an_opportunity_message_without_a_number(self):
        decision = {"ceiling": None, "reason": "20% abaixo da média histórica (R$ 400.00)",
                    "is_ceiling_hit": False, "is_opportunity_hit": True}
        message = build_weekend_alert_message(self.REPORT, decision, "Elton")
        self.assertIn("👤 Elton", message)
        self.assertIn("teto indisponível", message)


class UserLabelTest(unittest.TestCase):
    """Fatia D4 (15/08/2026): `settings.display_name` quando houver, senão os 8
    primeiros caracteres do uuid. A mensagem nunca quebra por falta de nome."""

    UUID = "c72bf50e-16f7-48fd-9c86-7b49dea1551e"

    def test_display_name_wins_when_present(self):
        self.assertEqual(user_label(self.UUID, {self.UUID: {"display_name": "Elton"}}), "Elton")

    def test_missing_key_falls_back_to_first_8_chars(self):
        self.assertEqual(user_label(self.UUID, {self.UUID: {}}), "c72bf50e")

    def test_null_value_falls_back_to_first_8_chars(self):
        # É o caso real de uma linha de settings antes de alguém preencher o
        # nome — e o de rodar o código novo antes do SQL da fatia.
        self.assertEqual(user_label(self.UUID, {self.UUID: {"display_name": None}}), "c72bf50e")

    def test_blank_display_name_falls_back(self):
        self.assertEqual(user_label(self.UUID, {self.UUID: {"display_name": "   "}}), "c72bf50e")

    def test_user_absent_from_the_cache_falls_back(self):
        self.assertEqual(user_label(self.UUID, {}), "c72bf50e")


class WeekendReportPriorityTest(unittest.TestCase):
    """Radar de calendário: uma perna pode cair no mesmo run como refresh de
    metadado do lote (suppress_alert=True, nunca avalia teto) E como
    candidata de precisão do radar (avalia teto de verdade) — as duas batem
    source == 'live'. O report suprimido nunca pode vencer um alertável."""

    def leg(self, leg_id="leg-1"):
        return {"id": leg_id}

    def test_live_alertable_beats_live_suppressed(self):
        suppressed = {"leg": self.leg(), "status": "ok", "source": "live", "alert_suppressed": True}
        alertable = {"leg": self.leg(), "status": "ok", "source": "live", "alert_suppressed": False}
        result = main.dedupe_weekend_reports([suppressed, alertable])
        self.assertFalse(result[0]["alert_suppressed"])

    def test_order_of_appearance_does_not_matter_for_suppressed_vs_alertable(self):
        suppressed = {"leg": self.leg(), "status": "ok", "source": "live", "alert_suppressed": True}
        alertable = {"leg": self.leg(), "status": "ok", "source": "live", "alert_suppressed": False}
        result = main.dedupe_weekend_reports([alertable, suppressed])
        self.assertFalse(result[0]["alert_suppressed"])

    def test_live_suppressed_still_beats_no_data(self):
        suppressed = {"leg": self.leg(), "status": "ok", "source": "live", "alert_suppressed": True}
        no_data = {"leg": self.leg(), "status": "no_data"}
        result = main.dedupe_weekend_reports([no_data, suppressed])
        self.assertEqual(result[0]["status"], "ok")

    def test_cache_ok_beats_live_suppressed(self):
        """Cache é conferidor secundário, mas ainda avalia teto de verdade —
        vence um live suprimido (que não avaliou nada)."""
        suppressed = {"leg": self.leg(), "status": "ok", "source": "live", "alert_suppressed": True}
        cache = {"leg": self.leg(), "status": "ok", "source": "cache"}
        result = main.dedupe_weekend_reports([suppressed, cache])
        self.assertEqual(result[0]["source"], "cache")


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


class BuildBlockAlertMessageTest(unittest.TestCase):
    """Conteúdo do alerta de bloqueio escalonado por dias consecutivos —
    pedido do usuário (24/07): diagnóstico com números reais, nunca repetir
    texto idêntico dia após dia, nunca sugerir proxy/IP/evasão."""

    BASE_DIAG = {
        "checked": 9, "failures": 5, "reason": "falhas seguidas",
        "seconds_since_last_success": None, "streak_days": 1,
        "streak_started_at": None, "config_url": "https://eltoneap.github.io/flyiop/config.html",
    }

    def test_day_one_is_informative_only(self):
        message = build_block_alert_message(self.BASE_DIAG)
        self.assertIn("Nenhuma ação necessária", message)
        self.assertNotIn("reduzir", message)
        self.assertNotIn("desligar", message)

    def test_day_two_and_three_suggest_reducing_batch(self):
        for day in (2, 3):
            diag = {**self.BASE_DIAG, "streak_days": day}
            message = build_block_alert_message(diag)
            self.assertIn("reduzir", message)
            self.assertIn(f"{day}º dia", message)
            self.assertNotIn("desligar", message)

    def test_day_four_plus_suggests_kill_switch_and_frozen_date(self):
        diag = {**self.BASE_DIAG, "streak_days": 4, "streak_started_at": "2026-07-21"}
        message = build_block_alert_message(diag)
        self.assertIn("desligar", message)
        self.assertIn("2026-07-21", message)

    def test_missing_last_success_omits_line(self):
        message = build_block_alert_message(self.BASE_DIAG)
        self.assertNotIn("Última consulta bem-sucedida", message)

    def test_present_last_success_shows_elapsed(self):
        diag = {**self.BASE_DIAG, "seconds_since_last_success": 7200}
        message = build_block_alert_message(diag)
        self.assertIn("Última consulta bem-sucedida", message)
        self.assertIn("2h", message)

    def test_always_includes_config_link(self):
        message = build_block_alert_message(self.BASE_DIAG)
        self.assertIn(self.BASE_DIAG["config_url"], message)

    def test_never_suggests_evasion(self):
        for day in (1, 2, 4):
            message = build_block_alert_message({**self.BASE_DIAG, "streak_days": day, "streak_started_at": "2026-07-20"})
            lowered = message.lower()
            for banned in ("proxy", "ip", "user-agent", "fingerprint", "evas"):
                self.assertNotIn(banned, lowered)

    def test_recovered_message_singular_plural(self):
        self.assertIn("1 dia ", build_block_recovered_message(1) + " ")
        self.assertIn("3 dias", build_block_recovered_message(3))


if __name__ == "__main__":
    unittest.main()
