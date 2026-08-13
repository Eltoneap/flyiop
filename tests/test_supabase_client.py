"""Etapa 4.2, pendência 13: get_weekend_leg_counts lia weekend_legs.status,
coluna congelada desde as pendências 3/4 (painel escreve status em
weekend_leg_user_state). Passou a ler weekend_leg_effective.

Fatia D1 (12/08/2026): get_weekend_leg_counts ganhou o parâmetro `cutoff` —
só conta pernas de fim de semana >= cutoff, mesma regra do Dashboard
(docs/js/dashboard.js) desde 28/07/2026. Todas as fixtures abaixo passaram a
carregar `outbound_date`.

Uso: python -m unittest tests/test_supabase_client.py -v (a partir da raiz do repo)
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import supabase_client  # noqa: E402

CUTOFF = "2027-01-29"


def state_row(leg_id: str, status: str, user_id: str = "user-a", outbound_date: str = "2027-02-05") -> dict:
    return {
        "leg_id": leg_id, "user_id": user_id, "price_ceiling": 300, "status": status,
        "outbound_date": outbound_date,
    }


class GetWeekendLegCountsTest(unittest.TestCase):
    def test_single_user_none_purchased(self):
        rows = [state_row("leg-1", "monitoring"), state_row("leg-2", "monitoring")]
        with patch("supabase_client.get_effective_leg_state", return_value=rows):
            total, purchased = supabase_client.get_weekend_leg_counts(CUTOFF)
        self.assertEqual((total, purchased), (2, 0))

    def test_single_user_one_purchased(self):
        rows = [state_row("leg-1", "purchased"), state_row("leg-2", "monitoring")]
        with patch("supabase_client.get_effective_leg_state", return_value=rows):
            total, purchased = supabase_client.get_weekend_leg_counts(CUTOFF)
        self.assertEqual((total, purchased), (2, 1))

    def test_leg_counts_purchased_only_when_all_users_agree(self):
        rows = [
            state_row("leg-1", "purchased", user_id="user-a"),
            state_row("leg-1", "monitoring", user_id="user-b"),
        ]
        with patch("supabase_client.get_effective_leg_state", return_value=rows):
            total, purchased = supabase_client.get_weekend_leg_counts(CUTOFF)
        self.assertEqual((total, purchased), (1, 0))

    def test_leg_counts_purchased_when_every_user_purchased(self):
        rows = [
            state_row("leg-1", "purchased", user_id="user-a"),
            state_row("leg-1", "purchased", user_id="user-b"),
        ]
        with patch("supabase_client.get_effective_leg_state", return_value=rows):
            total, purchased = supabase_client.get_weekend_leg_counts(CUTOFF)
        self.assertEqual((total, purchased), (1, 1))

    def test_no_rows_is_zero_zero(self):
        with patch("supabase_client.get_effective_leg_state", return_value=[]):
            self.assertEqual(supabase_client.get_weekend_leg_counts(CUTOFF), (0, 0))

    # --- Fatia D1 (12/08/2026): recorte pela janela de compra -------------

    def test_leg_before_cutoff_is_excluded_from_total(self):
        rows = [
            state_row("leg-1", "monitoring", outbound_date="2026-09-04"),  # antes do corte
            state_row("leg-2", "monitoring", outbound_date="2027-02-05"),  # depois do corte
        ]
        with patch("supabase_client.get_effective_leg_state", return_value=rows):
            total, purchased = supabase_client.get_weekend_leg_counts(CUTOFF)
        self.assertEqual((total, purchased), (1, 0))

    def test_purchased_leg_before_cutoff_does_not_count_as_purchased(self):
        rows = [state_row("leg-1", "purchased", outbound_date="2026-09-04")]
        with patch("supabase_client.get_effective_leg_state", return_value=rows):
            total, purchased = supabase_client.get_weekend_leg_counts(CUTOFF)
        self.assertEqual((total, purchased), (0, 0))

    def test_outbound_date_equal_to_cutoff_counts_as_inside(self):
        rows = [state_row("leg-1", "monitoring", outbound_date=CUTOFF)]
        with patch("supabase_client.get_effective_leg_state", return_value=rows):
            total, purchased = supabase_client.get_weekend_leg_counts(CUTOFF)
        self.assertEqual((total, purchased), (1, 0))


class GetLastWeekendLegAlertTest(unittest.TestCase):
    """Fatia D2 (13/08/2026): get_last_weekend_leg_alert ganhou o parâmetro
    obrigatório `alert_type`, que filtra por is_ceiling_alert/
    is_opportunity_alert além de leg_id — antes o cooldown só filtrava por
    leg_id, deixando um alerta de teto segurar um de oportunidade e
    vice-versa (STATE.md, seção 2)."""

    ENV = {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "fake-key"}

    def call(self, alert_type: str):
        with patch.dict(os.environ, self.ENV), \
             patch("supabase_client.requests.get") as mock_get:
            mock_get.return_value.json.return_value = []
            mock_get.return_value.raise_for_status.return_value = None
            supabase_client.get_last_weekend_leg_alert("leg-1", alert_type)
        return mock_get.call_args.kwargs["params"]

    def test_ceiling_filters_by_is_ceiling_alert_true(self):
        params = self.call("ceiling")
        self.assertEqual(params["leg_id"], "eq.leg-1")
        self.assertEqual(params["is_ceiling_alert"], "is.true")
        self.assertNotIn("is_opportunity_alert", params)

    def test_opportunity_filters_by_is_opportunity_alert_true(self):
        params = self.call("opportunity")
        self.assertEqual(params["leg_id"], "eq.leg-1")
        self.assertEqual(params["is_opportunity_alert"], "is.true")
        self.assertNotIn("is_ceiling_alert", params)

    def test_invalid_alert_type_raises(self):
        with self.assertRaises(ValueError):
            supabase_client.get_last_weekend_leg_alert("leg-1", "both")


if __name__ == "__main__":
    unittest.main()
