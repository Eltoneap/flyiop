"""Teste local da Etapa 3 (PLAN-FASE-A.md): deduplicação/cooldown de alertas.

Roda 100% com mocks — nenhuma chamada à API da Travelpayouts nem ao Supabase.
Uso: python -m unittest tests/test_etapa3_cooldown.py -v  (a partir da raiz)
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main  # noqa: E402


def iso_days_ago(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


# Parte 10 (28/07/2026): estado padrão do escalonamento automático de
# frequência pra testes que não são sobre isso — Estágio 0, sem bloqueio,
# nada rodado ainda hoje (primária e lote fli rodam normalmente).
SCRAPE_STATE_STAGE_0 = {
    "stage": 0, "clean_days": 0, "blocked_today": False,
    "last_change_at": None, "last_change_reason": None,
    "last_primary_run_date": None,
    "last_batch_run_date": None, "batches_run_today": 0,
}

TODAY = "2026-07-30"

# Fatia D1 (12/08/2026): ver mesma constante/motivo em tests/test_main.py —
# `None` para get_system_config passou a disparar o aviso de fallback da
# janela de compra, que quebraria as asserções estritas destes testes.
SYSTEM_CONFIG = {
    "suspicious_below_avg_pct": 50, "fast_flights_enabled": True,
    "fast_flights_daily_batch_size": 20, "weekend_buying_cutoff_date": "2026-01-01",
}


class CooldownBlocksAlertTest(unittest.TestCase):
    BASE_SETTINGS = {"notification_mode": "alert_only", "realert_drop_pct": 5, "realert_days": 3}

    def test_no_previous_alert_never_blocks(self):
        self.assertFalse(main.cooldown_blocks_alert(None, 1000.0, self.BASE_SETTINGS))

    def test_price_equal_and_recent_blocks(self):
        last_alert = {"price": 1000.0, "sent_at": iso_days_ago(1)}
        self.assertTrue(main.cooldown_blocks_alert(last_alert, 1000.0, self.BASE_SETTINGS))

    def test_price_dropped_enough_does_not_block(self):
        last_alert = {"price": 1000.0, "sent_at": iso_days_ago(1)}
        # queda de 6%, limite configurado é 5% -> não bloqueia
        self.assertFalse(main.cooldown_blocks_alert(last_alert, 940.0, self.BASE_SETTINGS))

    def test_price_dropped_not_enough_but_recent_blocks(self):
        last_alert = {"price": 1000.0, "sent_at": iso_days_ago(1)}
        # queda de só 2%, abaixo do limite de 5% -> ainda bloqueia (recente)
        self.assertTrue(main.cooldown_blocks_alert(last_alert, 980.0, self.BASE_SETTINGS))

    def test_enough_days_passed_does_not_block_even_same_price(self):
        last_alert = {"price": 1000.0, "sent_at": iso_days_ago(4)}
        self.assertFalse(main.cooldown_blocks_alert(last_alert, 1000.0, self.BASE_SETTINGS))

    def test_exactly_at_day_threshold_does_not_block(self):
        last_alert = {"price": 1000.0, "sent_at": iso_days_ago(3)}
        self.assertFalse(main.cooldown_blocks_alert(last_alert, 1000.0, self.BASE_SETTINGS))

    def test_daily_summary_never_blocks(self):
        settings = {**self.BASE_SETTINGS, "notification_mode": "daily_summary"}
        last_alert = {"price": 1000.0, "sent_at": iso_days_ago(0.1)}
        self.assertFalse(main.cooldown_blocks_alert(last_alert, 1000.0, settings))

    def test_custom_thresholds_respected(self):
        settings = {"notification_mode": "alert_only", "realert_drop_pct": 10, "realert_days": 7}
        last_alert = {"price": 1000.0, "sent_at": iso_days_ago(5)}
        # 5 dias < 7 configurado, e queda de 6% < 10% configurado -> bloqueia
        self.assertTrue(main.cooldown_blocks_alert(last_alert, 940.0, settings))


class ProcessRouteCooldownIntegrationTest(unittest.TestCase):
    ROUTE = {
        "id": "rota-1",
        "user_id": "user-1",
        "origin": "BSB",
        "destination": "GIG",
        "currency": "BRL",
        "target_price": 600,
        "target_percent_below_avg": None,
        "trip_duration_weeks": None,
    }

    def run_process_route(self, price: float, last_alert: dict | None) -> dict:
        settings = {
            "window_3d_pct": 10, "window_7d_pct": 15, "notification_mode": "alert_only",
            "freshness_hours": 24, "stale_alert_policy": "warn",
            "realert_drop_pct": 5, "realert_days": 3, "suspicious_below_avg_pct": 50,
        }
        v3_entry = {
            "price": price, "departure_at": "2026-11-27T00:00:00Z", "return_at": "2026-11-30T00:00:00Z",
            "transfers": 1,
        }
        with patch("main.get_prices_for_dates", side_effect=[[v3_entry], [], [], [], [], []]), \
             patch("main.insert_price"), \
             patch("main.insert_run_log"), \
             patch("main.get_price_history", return_value=[]), \
             patch("main.get_last_alert", return_value=last_alert), \
             patch("main.time.sleep", return_value=None):
            return main.process_route(self.ROUTE, settings)

    def test_first_alert_never_blocked_by_cooldown(self):
        report = self.run_process_route(500.0, last_alert=None)
        self.assertTrue(report["should_alert"])

    def test_repeat_same_price_recent_is_blocked(self):
        last_alert = {"price": 500.0, "sent_at": iso_days_ago(1)}
        report = self.run_process_route(500.0, last_alert=last_alert)
        self.assertFalse(report["should_alert"])

    def test_big_drop_overrides_cooldown(self):
        last_alert = {"price": 600.0, "sent_at": iso_days_ago(1)}
        report = self.run_process_route(500.0, last_alert=last_alert)  # ~16.7% de queda
        self.assertTrue(report["should_alert"])


class AlertLogWiringTest(unittest.TestCase):
    """Confirma que o alerta enviado é gravado em alert_log, e o resumo diário não grava."""

    def test_alert_only_mode_inserts_alert_log_on_send(self):
        route = {"id": "rota-1", "user_id": "user-1", "origin": "BSB", "destination": "GIG"}
        report = {
            "route": route, "status": "ok", "should_alert": True, "price": 520.0, "reason": "abaixo da meta",
            # Fatia D2 (13/08/2026): main.py lê essas flags do report pra
            # gravar em alert_log — sem elas o dict simulado não representa
            # mais o formato real de process_route.
            "is_ceiling_alert": True, "is_opportunity_alert": False,
        }
        with patch("main.get_routes", return_value=[route]), \
             patch("main.get_all_settings", return_value=[{"user_id": "user-1", "notification_mode": "alert_only"}]), \
             patch("main.get_settings", return_value={"notification_mode": "alert_only"}), \
             patch("main.get_system_config", return_value=SYSTEM_CONFIG), \
             patch("main.process_route", return_value=report), \
             patch("main.process_all_weekend_legs", return_value=[]), \
             patch("main.run_daily_batch", return_value=([], False)), \
             patch("main.current_brt_date", return_value=TODAY), \
             patch("main.get_weekend_scrape_state", return_value=SCRAPE_STATE_STAGE_0), \
             patch("main.set_weekend_scrape_state"), \
             patch("main.date") as mock_date, \
             patch("main.send_message") as mock_send, \
             patch("main.insert_alert_log") as mock_insert_alert, \
             patch("main.build_alert_message", return_value="msg"):
            mock_date.today.return_value.weekday.return_value = 2  # quarta — sem resumo semanal
            main.main()

        mock_send.assert_called_once_with("msg")
        mock_insert_alert.assert_called_once_with(
            "rota-1", 520.0, "abaixo da meta", is_ceiling_alert=True, is_opportunity_alert=False
        )

    def test_daily_summary_mode_never_inserts_alert_log(self):
        route = {"id": "rota-1", "user_id": "user-1", "origin": "BSB", "destination": "GIG"}
        report = {
            "route": route, "status": "ok", "should_alert": True, "price": 520.0, "reason": "abaixo da meta",
            "currency": "BRL", "depart_date": "2026-11-27",
        }
        with patch("main.get_routes", return_value=[route]), \
             patch("main.get_all_settings", return_value=[{"user_id": "user-1", "notification_mode": "daily_summary"}]), \
             patch("main.get_settings", return_value={"notification_mode": "daily_summary"}), \
             patch("main.get_system_config", return_value=SYSTEM_CONFIG), \
             patch("main.process_route", return_value=report), \
             patch("main.process_all_weekend_legs", return_value=[]), \
             patch("main.run_daily_batch", return_value=([], False)), \
             patch("main.current_brt_date", return_value=TODAY), \
             patch("main.get_weekend_scrape_state", return_value=SCRAPE_STATE_STAGE_0), \
             patch("main.set_weekend_scrape_state"), \
             patch("main.date") as mock_date, \
             patch("main.send_message"), \
             patch("main.insert_alert_log") as mock_insert_alert, \
             patch("main.build_route_block", return_value="bloco"), \
             patch("main.build_summary_message", return_value="resumo"):
            mock_date.today.return_value.weekday.return_value = 2
            main.main()

        mock_insert_alert.assert_not_called()

    def test_weekend_targets_processed_even_without_flexible_routes(self):
        """main() não pode ficar refém de existir alguma rota flexível cadastrada."""
        weekend_report = {
            "leg": {"id": "leg-1", "effective_ceiling": 200}, "status": "ok", "price": 150.0,
            "should_alert": True, "reason": "abaixo da meta fixa (R$ 200)",
            "is_ceiling_hit": True, "is_opportunity_hit": False,
        }
        with patch("main.get_routes", return_value=[]), \
             patch("main.get_all_settings", return_value=[]), \
             patch("main.get_system_config", return_value=SYSTEM_CONFIG), \
             patch("main.process_all_weekend_legs", return_value=[weekend_report]), \
             patch("main.run_daily_batch", return_value=([], False)), \
             patch("main.current_brt_date", return_value=TODAY), \
             patch("main.get_weekend_scrape_state", return_value=SCRAPE_STATE_STAGE_0), \
             patch("main.set_weekend_scrape_state"), \
             patch("main.date") as mock_date, \
             patch("main.send_message") as mock_send, \
             patch("main.insert_weekend_alert_log") as mock_insert_weekend_alert, \
             patch("main.build_package_comparison", return_value=None), \
             patch("main.build_weekend_alert_message", return_value="msg-fds"):
            mock_date.today.return_value.weekday.return_value = 2
            main.main()

        mock_send.assert_called_once_with("msg-fds")
        mock_insert_weekend_alert.assert_called_once_with(
            "leg-1", 150.0, "abaixo da meta fixa (R$ 200)",
            is_ceiling_alert=True, is_opportunity_alert=False,
        )

    def test_weekend_composite_alert_grava_as_duas_flags_true(self):
        """Fatia D2 (13/08/2026): quando a mesma perna dispara teto E
        oportunidade na mesma avaliação, evaluate_and_record_leg_price já
        compõe uma única mensagem com as duas razões concatenadas por `;`
        (não duas linhas separadas) — a linha gravada em alert_log leva as
        duas flags true."""
        weekend_report = {
            "leg": {"id": "leg-1", "effective_ceiling": 300}, "status": "ok", "price": 150.0,
            "should_alert": True,
            "reason": "abaixo da meta fixa (R$ 300); 23.1% abaixo da média histórica (R$ 232.62)",
            "is_ceiling_hit": True, "is_opportunity_hit": True,
        }
        with patch("main.get_routes", return_value=[]), \
             patch("main.get_all_settings", return_value=[]), \
             patch("main.get_system_config", return_value=SYSTEM_CONFIG), \
             patch("main.process_all_weekend_legs", return_value=[weekend_report]), \
             patch("main.run_daily_batch", return_value=([], False)), \
             patch("main.current_brt_date", return_value=TODAY), \
             patch("main.get_weekend_scrape_state", return_value=SCRAPE_STATE_STAGE_0), \
             patch("main.set_weekend_scrape_state"), \
             patch("main.date") as mock_date, \
             patch("main.send_message"), \
             patch("main.insert_weekend_alert_log") as mock_insert_weekend_alert, \
             patch("main.build_package_comparison", return_value=None), \
             patch("main.build_weekend_alert_message", return_value="msg-fds"):
            mock_date.today.return_value.weekday.return_value = 2
            main.main()

        mock_insert_weekend_alert.assert_called_once_with(
            "leg-1", 150.0, "abaixo da meta fixa (R$ 300); 23.1% abaixo da média histórica (R$ 232.62)",
            is_ceiling_alert=True, is_opportunity_alert=True,
        )


if __name__ == "__main__":
    unittest.main()
