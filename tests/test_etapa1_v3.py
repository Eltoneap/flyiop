"""Teste local da Etapa 1 (PLAN-FASE-A.md): cliente v3 + comparação paralela v2×v3.

Roda 100% com mocks — nenhuma chamada à API da Travelpayouts nem ao Supabase.
Uso: python -m unittest tests/test_etapa1_v3.py -v  (a partir da raiz do repo)
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main  # noqa: E402
import travelpayouts_client  # noqa: E402

FAKE_TOKEN_ENV = {"TRAVELPAYOUTS_TOKEN": "fake-token-para-teste"}

# Formato documentado do v3 prices_for_dates.
SAMPLE_V3_ENTRY = {
    "origin": "BSB",
    "destination": "GIG",
    "price": 1180.0,
    "airline": "G3",
    "flight_number": 1234,
    "departure_at": "2026-08-15T07:00:00Z",
    "return_at": "2026-08-22T20:00:00Z",
    "transfers": 0,
    "return_transfers": 0,
    "found_at": "2026-07-16T10:00:00Z",
    "link": "/search/BSB1508GIG2208",
}


class GetPricesForDatesTest(unittest.TestCase):
    """Cobre o parse e o mapeamento de campos do cliente v3."""

    @patch("travelpayouts_client.requests.get")
    def test_parses_response_and_sends_expected_params(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [SAMPLE_V3_ENTRY]}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        with patch.dict(os.environ, FAKE_TOKEN_ENV):
            result = travelpayouts_client.get_prices_for_dates(
                "BSB", "GIG", "BRL", departure_at="2026-08", one_way=False
            )

        self.assertEqual(result, [SAMPLE_V3_ENTRY])
        called_url, called_kwargs = mock_get.call_args
        self.assertIn("/aviasales/v3/prices_for_dates", called_url[0])
        params = called_kwargs["params"]
        self.assertEqual(params["origin"], "BSB")
        self.assertEqual(params["destination"], "GIG")
        self.assertEqual(params["departure_at"], "2026-08")
        self.assertEqual(params["one_way"], "false")
        self.assertEqual(params["sorting"], "price")
        self.assertEqual(params["token"], "fake-token-para-teste")

    @patch("travelpayouts_client.requests.get")
    def test_empty_data_returns_empty_list(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": []}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        with patch.dict(os.environ, FAKE_TOKEN_ENV):
            result = travelpayouts_client.get_prices_for_dates("RIA", "BSB", "BRL", departure_at="2026-08")

        self.assertEqual(result, [])


class V3ComparisonDetailTest(unittest.TestCase):
    """Cobre a lógica de comparação em main.py — sem tocar a rede ou o Supabase."""

    @patch("main.time.sleep", return_value=None)
    @patch("main.get_prices_for_dates")
    def test_cheapest_v3_entry_wins_and_reports_found_at(self, mock_v3, _mock_sleep):
        cheap_entry = {**SAMPLE_V3_ENTRY, "price": 1180.0, "departure_at": "2026-08-15T07:00:00Z"}
        pricier_entry = {**SAMPLE_V3_ENTRY, "price": 1400.0, "departure_at": "2026-09-01T07:00:00Z"}
        # 6 meses varridos (MONTHS_AHEAD): só 2 têm dados, os demais vazios.
        mock_v3.side_effect = [[cheap_entry], [pricier_entry], [], [], [], []]

        detail = main.v3_comparison_detail("BSB", "GIG", "BRL", v2_price=1250.0)

        self.assertIn("v3: 1180.00", detail)
        self.assertIn("2/6 meses", detail)
        self.assertIn("2026-08-15", detail)
        self.assertIn("com found_at", detail)
        self.assertIn("v2: 1250.00", detail)

    @patch("main.time.sleep", return_value=None)
    @patch("main.get_prices_for_dates")
    def test_missing_found_at_is_reported_honestly(self, mock_v3, _mock_sleep):
        entry_without_found_at = {k: v for k, v in SAMPLE_V3_ENTRY.items() if k != "found_at"}
        mock_v3.side_effect = [[entry_without_found_at], [], [], [], [], []]

        detail = main.v3_comparison_detail("BSB", "GIG", "BRL", v2_price=1250.0)

        self.assertIn("sem found_at", detail)

    @patch("main.time.sleep", return_value=None)
    @patch("main.get_prices_for_dates")
    def test_no_v3_data_and_no_v2_price(self, mock_v3, _mock_sleep):
        mock_v3.side_effect = [[] for _ in range(6)]

        detail = main.v3_comparison_detail("RIA", "BSB", "BRL", v2_price=None)

        self.assertIn("v3: sem dados", detail)
        self.assertIn("v2: sem dados", detail)


class SafeV3ComparisonTest(unittest.TestCase):
    """A comparação é observacional: uma falha no v3 nunca pode derrubar a rota."""

    @patch("main.v3_comparison_detail", side_effect=RuntimeError("timeout simulado"))
    def test_exception_is_caught_and_summarized(self, _mock_detail):
        detail = main.safe_v3_comparison("BSB → GIG", "BSB", "GIG", "BRL", v2_price=1250.0)

        self.assertIn("v3: erro na comparação", detail)
        self.assertIn("RuntimeError", detail)

    @patch("main.v3_comparison_detail", return_value="v3: 1180.00 (2/6 meses) | v2: 1250.00")
    def test_success_passthrough(self, _mock_detail):
        detail = main.safe_v3_comparison("BSB → GIG", "BSB", "GIG", "BRL", v2_price=1250.0)

        self.assertEqual(detail, "v3: 1180.00 (2/6 meses) | v2: 1250.00")


if __name__ == "__main__":
    unittest.main()
