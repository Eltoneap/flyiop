"""Teste local do cliente v3 (get_prices_for_dates).

Nota: as classes que testavam a comparação paralela v2×v3 (v3_comparison_detail
e safe_v3_comparison) foram removidas no corte da Etapa 6 — essas funções
deixaram de existir quando o v3 virou a fonte oficial. O cliente v3 em si
continua em uso e coberto aqui.

Roda 100% com mocks — nenhuma chamada à API da Travelpayouts nem ao Supabase.
Uso: python -m unittest tests/test_etapa1_v3.py -v  (a partir da raiz do repo)
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

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


if __name__ == "__main__":
    unittest.main()
