"""Teste local da orquestração de main() — Parte 10 (28/07/2026), escalonamento
automático de frequência de scraping. Cobre especificamente o cenário mais
perigoso apontado na revisão do plano: bloqueio detectado exatamente na
última hora agendada do estágio atual (o mesmo instante em que a subida de
estágio seria avaliada) — o resultado final tem que ser sempre Estágio 0,
nunca uma subida no mesmo ciclo em que acabou de cair.

Usa as funções REAIS de scrape_schedule.py (não mockadas) — só I/O
(Supabase, fli, Telegram) é mockado — pra exercitar a ordem de verdade do
main.py, não uma reimplementação da lógica no teste.

Uso: python -m unittest tests/test_main.py -v  (a partir da raiz do repo)
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main  # noqa: E402


class BlockAtLastScheduledHourTest(unittest.TestCase):
    def test_block_at_last_scheduled_hour_never_escalates_same_cycle(self):
        # Estágio 2 já no teto automático, última hora agendada = 20h BRT,
        # 4 dias limpos acumulados (1 a menos pro degrau seguinte — mas
        # Estágio 2 já é o teto, então não subiria de qualquer forma; o
        # ponto do teste é a ORDEM, não o número de estágios disponíveis).
        # Reforça com Estágio 1 -> repetir a mesma asserção também cobre
        # "não sobe pro 2 na mesma execução em que caiu pro 0".
        scrape_state = {
            "stage": 1, "clean_days": 4, "blocked_today": False,
            "last_change_at": None, "last_change_reason": None,
        }

        with patch("main.get_routes", return_value=[]), \
             patch("main.process_all_weekend_legs", return_value=[]), \
             patch("main.run_daily_batch", return_value=([], True)), \
             patch("main.current_brt_hour", return_value=20), \
             patch("main.get_weekend_scrape_state", return_value=scrape_state), \
             patch("main.set_weekend_scrape_state") as mock_set_state, \
             patch("main.date") as mock_date, \
             patch("main.send_message") as mock_send, \
             patch("main.build_stage_change_message", side_effect=lambda stage, reason: f"stage={stage}"):
            mock_date.today.return_value.weekday.return_value = 2  # quarta — sem resumo semanal
            main.main()

        # A ÚLTIMA gravação de estágio tem que ser 0 — nunca uma subida
        # depois da queda na mesma execução.
        stage_calls = [c.kwargs["stage"] for c in mock_set_state.call_args_list if "stage" in c.kwargs]
        self.assertTrue(stage_calls, "esperava pelo menos 1 gravação de estágio")
        self.assertEqual(stage_calls[-1], 0)
        self.assertNotIn(2, stage_calls)  # nunca chegou a considerar subir pro 2

        # Só 1 alerta de mudança de estágio (a queda) — nunca queda + subida.
        stage_change_sends = [c.args[0] for c in mock_send.call_args_list if c.args[0].startswith("stage=")]
        self.assertEqual(stage_change_sends, ["stage=0"])

    def test_no_block_at_last_scheduled_hour_does_escalate(self):
        # Controle: sem bloqueio, mesmo cenário (Estágio 1, 4 dias limpos,
        # última hora agendada) tem que subir pro Estágio 2 normalmente —
        # confirma que o teste acima falha por causa do bloqueio, não por
        # algum outro bug que sempre impede a subida.
        scrape_state = {
            "stage": 1, "clean_days": 4, "blocked_today": False,
            "last_change_at": None, "last_change_reason": None,
        }

        with patch("main.get_routes", return_value=[]), \
             patch("main.process_all_weekend_legs", return_value=[]), \
             patch("main.run_daily_batch", return_value=([], False)), \
             patch("main.current_brt_hour", return_value=20), \
             patch("main.get_weekend_scrape_state", return_value=scrape_state), \
             patch("main.set_weekend_scrape_state") as mock_set_state, \
             patch("main.date") as mock_date, \
             patch("main.send_message") as mock_send, \
             patch("main.build_stage_change_message", side_effect=lambda stage, reason: f"stage={stage}"):
            mock_date.today.return_value.weekday.return_value = 2
            main.main()

        stage_calls = [c.kwargs["stage"] for c in mock_set_state.call_args_list if "stage" in c.kwargs]
        self.assertEqual(stage_calls[-1], 2)
        stage_change_sends = [c.args[0] for c in mock_send.call_args_list if c.args[0].startswith("stage=")]
        self.assertEqual(stage_change_sends, ["stage=2"])


if __name__ == "__main__":
    unittest.main()
