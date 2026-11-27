import unittest
from fia.risk_agent import RiskAgent
from fia.decision_agent import ChiefAnalyst
from fia.journal import add_alert, summary


class RiskTests(unittest.TestCase):
    def test_long_levels_have_three_to_one_reward_risk(self):
        levels = RiskAgent().provisional_levels("LONG", 100.0, 2.0)
        self.assertAlmostEqual(100.0 - levels["stop_loss"], 3.0)
        self.assertAlmostEqual(levels["take_profit"] - 100.0, 9.0)

    def test_short_levels_have_three_to_one_reward_risk(self):
        levels = RiskAgent().provisional_levels("SHORT", 100.0, 2.0)
        self.assertAlmostEqual(levels["stop_loss"] - 100.0, 3.0)
        self.assertAlmostEqual(100.0 - levels["take_profit"], 9.0)

    def test_missing_data_never_creates_prealert(self):
        result = ChiefAnalyst().decide("TEST", {}, {}, {}, None, RiskAgent())
        self.assertEqual(result["status"], "DATA_INSUFFICIENT")

    def test_stale_data_never_creates_prealert(self):
        candle = {
            "valid": True, "fresh": False, "trend": "BEARISH",
            "ema_slope": "DOWN", "rsi": 40.0, "adx": 20.0,
            "close": 100.0, "atr": 2.0,
        }
        result = ChiefAnalyst().decide(
            "TEST", {"D1": candle, "H4": candle, "H1": candle},
            {}, {}, None, RiskAgent(),
        )
        self.assertEqual(result["status"], "DATA_STALE")

    def test_weak_adx_never_creates_prealert(self):
        base = {
            "valid": True, "fresh": True, "trend": "BEARISH",
            "ema_slope": "DOWN",
        }
        d1 = dict(base, rsi=40.0, adx=20.0, close=100.0, atr=2.0)
        h4 = dict(base, rsi=40.0, adx=20.0, close=100.0, atr=2.0)
        h1 = dict(base, rsi=40.0, adx=10.0, close=100.0, atr=2.0)
        result = ChiefAnalyst().decide(
            "TEST", {"D1": d1, "H4": h4, "H1": h1},
            {}, {}, None, RiskAgent(),
        )
        self.assertEqual(result["status"], "FILTERED")

    def test_journal_adds_unique_hypothetical_alert(self):
        d = {
            "symbol": "TEST", "direction": "LONG",
            "h1": {"bar_time": "2026-01-01T00:00:00+00:00"},
            "levels": {"entry_reference": 100, "stop_loss": 99, "take_profit": 103},
        }
        rows = []
        self.assertTrue(add_alert(rows, d))
        self.assertFalse(add_alert(rows, d))
        self.assertEqual(summary(rows)["total_alerts"], 1)

    def test_aligned_setup_emits_final_signal_when_guards_are_ready(self):
        from fia.config import ECONOMIC_CALENDAR_VALIDATED, FINAL_SIGNALS_ENABLED
        self.assertTrue(ECONOMIC_CALENDAR_VALIDATED)
        self.assertTrue(FINAL_SIGNALS_ENABLED)
        base = {"valid": True, "fresh": True, "trend": "BULLISH", "ema_slope": "UP",
                "rsi": 60.0, "adx": 25.0, "close": 100.0, "atr": 2.0}
        result = ChiefAnalyst().decide(
            "TEST", {"D1": dict(base), "H4": dict(base), "H1": dict(base)},
            {"ready": True}, {}, None, RiskAgent(),
            {"blocked": False, "status": "NORMAL"},
        )
        self.assertEqual(result["status"], "FINAL_SIGNAL")
        self.assertEqual(result["direction"], "LONG")
        self.assertAlmostEqual(result["levels"]["rr_target"], 3.0)

    def test_calendar_block_prevents_final_signal(self):
        base = {"valid": True, "fresh": True, "trend": "BULLISH", "ema_slope": "UP",
                "rsi": 60.0, "adx": 25.0, "close": 100.0, "atr": 2.0}
        result = ChiefAnalyst().decide(
            "TEST", {"D1": dict(base), "H4": dict(base), "H1": dict(base)},
            {"ready": True}, {}, None, RiskAgent(),
            {"blocked": True, "reason": "High impact event"},
        )
        self.assertEqual(result["status"], "EVENT_RISK_BLOCK")


if __name__ == "__main__":
    unittest.main()
