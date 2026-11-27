import unittest

from fia.day_agent import DayChiefAnalyst, DayRiskAgent


class DayTradingTests(unittest.TestCase):
    def setUp(self):
        self.context = {
            "H4": {"valid": True, "fresh": True, "trend": "BULLISH", "ema_slope": "UP"},
            "H1": {"valid": True, "fresh": True, "trend": "BULLISH", "ema_slope": "UP"},
        }
        self.m15 = {
            "bar_time": "2026-11-28T10:15:00+00:00",
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
            "ema20": 100.2, "ema50": 99.8,
            "previous_close": 99.8, "previous_ema20": 100.1,
            "rsi": 60.0, "atr": 1.0, "adx": 24.0,
            "fresh": True, "source": "EURUSD=X",
        }

    def test_valid_long_pullback_creates_day_signal(self):
        result = DayChiefAnalyst().decide(
            "EUR/USD", self.context, self.m15,
            {"blocked": False}, {"ready": True}, DayRiskAgent(),
        )
        self.assertEqual(result["status"], "DAY_FINAL_SIGNAL")
        self.assertEqual(result["direction"], "LONG")
        self.assertEqual(result["levels"]["risk_pct_reference"], 0.5)
        self.assertEqual(result["levels"]["rr_target"], 2.0)

    def test_calendar_blocks_day_signal(self):
        result = DayChiefAnalyst().decide(
            "EUR/USD", self.context, self.m15,
            {"blocked": True, "reason": "High impact event"},
            {"ready": True}, DayRiskAgent(),
        )
        self.assertEqual(result["status"], "DAY_EVENT_BLOCK")

    def test_missing_news_blocks_day_signal(self):
        result = DayChiefAnalyst().decide(
            "EUR/USD", self.context, self.m15,
            {"blocked": False}, {"ready": False}, DayRiskAgent(),
        )
        self.assertEqual(result["status"], "DAY_NEWS_BLOCK")

    def test_unaligned_higher_timeframes_do_not_signal(self):
        context = dict(self.context)
        context["H1"] = dict(context["H1"], trend="BEARISH")
        result = DayChiefAnalyst().decide(
            "EUR/USD", context, self.m15,
            {"blocked": False}, {"ready": True}, DayRiskAgent(),
        )
        self.assertEqual(result["status"], "DAY_NO_SETUP")

    def test_short_levels_have_two_to_one_reward_risk(self):
        levels = DayRiskAgent().levels("SHORT", 100.0, 2.0)
        self.assertAlmostEqual(levels["stop_loss"] - 100.0, 3.0)
        self.assertAlmostEqual(100.0 - levels["take_profit"], 6.0)


if __name__ == "__main__":
    unittest.main()
