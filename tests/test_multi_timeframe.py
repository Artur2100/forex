import unittest
from datetime import datetime, timezone

import pandas as pd

from fia.market_agent import MarketAgent
from fia.technical_agent import TechnicalAgent
from fia.decision_agent import ChiefAnalyst
from fia.risk_agent import RiskAgent


class H4AggregationTests(unittest.TestCase):
    def test_h4_aggregates_four_completed_hourly_bars(self):
        now = pd.Timestamp("2026-11-27T12:30:00Z")
        idx = pd.date_range("2026-11-27T04:00:00Z", periods=9, freq="h")
        hourly = pd.DataFrame({
            "open": range(100, 109),
            "high": range(101, 110),
            "low": range(99, 108),
            "close": range(100, 109),
            "volume": [10] * 9,
        }, index=idx)
        hourly.attrs["source_symbol"] = "TEST"
        h4 = MarketAgent.build_h4(hourly, now=now)
        self.assertEqual(list(h4.index), [pd.Timestamp("2026-11-27T04:00:00Z")])
        self.assertEqual(h4.iloc[0]["open"], 100)
        self.assertEqual(h4.iloc[0]["high"], 104)
        self.assertEqual(h4.iloc[0]["low"], 99)
        self.assertEqual(h4.iloc[0]["close"], 103)
        self.assertEqual(h4.iloc[0]["volume"], 40)
        self.assertEqual(h4.attrs["source_symbol"], "TEST")

    def test_incomplete_h4_interval_is_excluded(self):
        now = pd.Timestamp("2026-11-27T12:30:00Z")
        idx = pd.date_range("2026-11-27T08:00:00Z", periods=3, freq="h")
        hourly = pd.DataFrame({
            "open": [1, 2, 3], "high": [2, 3, 4],
            "low": [0, 1, 2], "close": [1, 2, 3],
        }, index=idx)
        self.assertTrue(MarketAgent.build_h4(hourly, now=now).empty)


class DecisionTimeframeTests(unittest.TestCase):
    def setUp(self):
        self.frame = {
            "trend": "BULLISH", "ema_slope": "UP", "valid": True,
            "fresh": True, "rsi": 60, "adx": 25, "close": 1.1, "atr": 0.01,
        }

    def test_h4_is_required(self):
        result = ChiefAnalyst().decide(
            "EUR/USD", {"D1": self.frame, "H1": self.frame},
            {"ready": False}, {}, None, RiskAgent(), {},
        )
        self.assertEqual(result["status"], "DATA_INSUFFICIENT")

    def test_all_three_timeframes_must_align(self):
        h4 = dict(self.frame, trend="BEARISH", ema_slope="DOWN")
        result = ChiefAnalyst().decide(
            "EUR/USD", {"D1": self.frame, "H4": h4, "H1": self.frame},
            {"ready": False}, {}, None, RiskAgent(), {},
        )
        self.assertEqual(result["status"], "NO_SETUP")

    def test_aligned_three_timeframes_create_only_prealert(self):
        result = ChiefAnalyst().decide(
            "EUR/USD", {"D1": self.frame, "H4": self.frame, "H1": self.frame},
            {"ready": False}, {}, None, RiskAgent(), {},
        )
        self.assertEqual(result["status"], "TECHNICAL_PREALERT")
        self.assertIn("h4", result)
        self.assertEqual(result["levels"]["rr_target"], 3.0)


if __name__ == "__main__":
    unittest.main()
