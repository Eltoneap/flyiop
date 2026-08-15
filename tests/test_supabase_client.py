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


class AlertLogUserIdPayloadTest(unittest.TestCase):
    """Fatia D3 (14/08/2026): `alert_log` ganhou `user_id`, preenchido de forma
    ASSIMÉTRICA por desenho — linha de rota leva o dono (`routes.user_id`),
    linha de perna nasce NULL porque não há dono derivável (weekend_legs não
    tem user_id e weekend_leg_effective resolve por cross join com settings, ou
    seja N usuários, não um).

    Estes testes batem na função REAL, não em mock: os testes de
    tests/test_etapa3_cooldown.py usam `patch(...)` sem autospec, então
    validam o call site, não a assinatura de verdade."""

    ENV = {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "fake-key"}

    def post_payload(self, fn, *args, **kwargs) -> dict:
        with patch.dict(os.environ, self.ENV), \
             patch("supabase_client.requests.post") as mock_post:
            mock_post.return_value.raise_for_status.return_value = None
            fn(*args, **kwargs)
        return mock_post.call_args.kwargs["json"]

    def test_route_insert_sends_user_id(self):
        payload = self.post_payload(
            supabase_client.insert_alert_log, "rota-1", 520.0, "abaixo da meta",
            is_ceiling_alert=True, is_opportunity_alert=False, user_id="user-1",
        )
        self.assertEqual(payload["user_id"], "user-1")
        self.assertEqual(payload["route_id"], "rota-1")

    def test_route_insert_accepts_none_user_id(self):
        """A coluna é nullable e sem CHECK de propósito: o insert acontece
        depois de a mensagem do Telegram já ter saído, então nada aqui pode
        ser rejeitável pelo banco."""
        payload = self.post_payload(
            supabase_client.insert_alert_log, "rota-1", 520.0, None,
            is_ceiling_alert=False, is_opportunity_alert=True, user_id=None,
        )
        self.assertIsNone(payload["user_id"])

    def test_route_insert_requires_user_id_keyword(self):
        """Keyword-only e sem default — mesmo padrão das flags da D2: um
        caminho de gravação novo não pode esquecer o dono em silêncio."""
        with self.assertRaises(TypeError):
            supabase_client.insert_alert_log(
                "rota-1", 520.0, "abaixo da meta",
                is_ceiling_alert=True, is_opportunity_alert=False,
            )

    def test_leg_insert_omits_user_id_key_entirely(self):
        """Não é esquecimento: a chave nem entra no payload, e a linha nasce
        NULL. Quem escreve dono em linha de perna é a D4."""
        payload = self.post_payload(
            supabase_client.insert_weekend_alert_log, "leg-1", 150.0, "abaixo da meta fixa (R$ 200)",
            is_ceiling_alert=True, is_opportunity_alert=False,
        )
        self.assertNotIn("user_id", payload)
        self.assertEqual(payload["leg_id"], "leg-1")

    def test_leg_insert_rejects_user_id_kwarg(self):
        """Trava de desenho: enquanto a D4 não chegar, passar dono para uma
        linha de perna é erro, não opção silenciosa."""
        with self.assertRaises(TypeError):
            supabase_client.insert_weekend_alert_log(
                "leg-1", 150.0, "abaixo da meta fixa (R$ 200)",
                is_ceiling_alert=True, is_opportunity_alert=False, user_id="user-1",
            )


if __name__ == "__main__":
    unittest.main()
