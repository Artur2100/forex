import unittest
from unittest.mock import Mock

from fia.calendar_agent import EconomicCalendarAgent


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.agent = EconomicCalendarAgent(session=Mock())

    def test_high_impact_event_blocks_relevant_usd_pair(self):
        now = 1_800_000_000
        result = {"ready": True, "server_time": now, "events": [{
            "ts": now + 20 * 60, "currency": "USD", "impact": "high",
            "title": "US CPI", "status": "scheduled",
        }]}
        risk = self.agent.risk_for_symbol("EUR/USD", result)
        self.assertTrue(risk["blocked"])
        self.assertEqual(risk["status"], "HIGH RISK")

    def test_unrelated_currency_does_not_block_pair(self):
        now = 1_800_000_000
        result = {"ready": True, "server_time": now, "events": [{
            "ts": now + 10 * 60, "currency": "JPY", "impact": "high",
            "title": "BOJ decision", "status": "scheduled",
        }]}
        self.assertFalse(self.agent.risk_for_symbol("EUR/USD", result)["blocked"])

    def test_medium_event_uses_shorter_window(self):
        now = 1_800_000_000
        result = {"ready": True, "server_time": now, "events": [{
            "ts": now + 10 * 60, "currency": "GBP", "impact": "medium",
            "title": "UK data", "status": "scheduled",
        }]}
        self.assertTrue(self.agent.risk_for_symbol("GBP/USD", result)["blocked"])

    def test_calendar_failure_fails_closed(self):
        risk = self.agent.risk_for_symbol("XAU/USD", {"ready": False, "errors": ["timeout"]})
        self.assertTrue(risk["blocked"])
        self.assertEqual(risk["status"], "UNKNOWN")

    def test_forecast_previous_and_actual_are_shown(self):
        summary = self.agent.upcoming_summary({
            "ready": True, "server_time": 1_800_000_000,
            "events": [{
                "ts": 1_800_003_600, "currency": "USD", "impact": "high",
                "title": "CPI", "forecast": "0.3%", "previous": "0.2%",
                "actual": "", "status": "scheduled",
            }],
        })
        self.assertIn("прогноз 0.3%", summary)
        self.assertIn("пред. 0.2%", summary)


if __name__ == "__main__":
    unittest.main()
