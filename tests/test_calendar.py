import unittest
from unittest.mock import Mock

import requests

from fia.calendar_agent import EconomicCalendarAgent


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.sleep = Mock()
        self.agent = EconomicCalendarAgent(session=self.session, sleep=self.sleep)

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

    def test_retries_temporary_timeout(self):
        response = Mock(status_code=200)
        response.json.return_value = {"ok": True}
        self.session.get.side_effect = [requests.Timeout("slow"), response]
        payload = self.agent._fetch_payload({})
        self.assertEqual(payload, {"ok": True})
        self.assertEqual(self.session.get.call_count, 2)
        self.sleep.assert_called_once_with(1)

    def test_generated_at_does_not_require_server_time_iso(self):
        from datetime import datetime, timezone
        now = int(datetime.now(timezone.utc).timestamp())
        response = Mock(status_code=200)
        response.json.return_value = {
            "server_time": now,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "events": [],
        }
        self.session.get.return_value = response
        result = self.agent.analyze()
        self.assertTrue(result["ready"])
        self.assertEqual(result["events"], [])

    def test_forecast_previous_and_actual_are_shown(self):
        summary = self.agent.upcoming_summary({
            "ready": True, "server_time": 1_800_000_000,
            "events": [{
                "ts": 1_800_003_600, "currency": "USD", "impact": "high",
                "title": "CPI", "forecast": "0.3%", "previous": "0.2%",
                "actual": "", "status": "scheduled", "confidence": "official",
            }],
        })
        self.assertIn("прогноз 0.3%", summary)
        self.assertIn("пред. 0.2%", summary)
        self.assertIn("official", summary)


if __name__ == "__main__":
    unittest.main()
