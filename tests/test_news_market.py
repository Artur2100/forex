import unittest
from datetime import datetime, timedelta, timezone

import pandas as pd

from fia.market_agent import MarketAgent
from fia.news_agent import classify


class NewsClassificationTests(unittest.TestCase):
    def test_us_inflation_news_is_high_impact(self):
        impact, assets, topics = classify("Consumer Price Index increases more than expected", "BLS")
        self.assertEqual(impact, "HIGH")
        self.assertIn("USD", assets)
        self.assertIn("XAU", assets)

    def test_irrelevant_press_release_is_low_priority(self):
        impact, assets, _ = classify("Federal Reserve announces College Fed Challenge winners", "Federal Reserve")
        self.assertEqual(impact, "LOW")
        self.assertEqual(assets, [])

    def test_medium_macro_release(self):
        impact, _, _ = classify("Monthly retail sales report", "Statistics agency")
        self.assertEqual(impact, "MEDIUM")


class GoldDataFreshnessTests(unittest.TestCase):
    def test_recent_completed_hourly_candle_is_fresh(self):
        now = datetime.now(timezone.utc)
        stamp = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        frame = pd.DataFrame({"close": [1.0]}, index=pd.DatetimeIndex([stamp]))
        self.assertTrue(MarketAgent()._freshness(frame, "H1"))

    def test_old_hourly_candle_is_stale(self):
        stamp = datetime.now(timezone.utc) - timedelta(hours=8)
        frame = pd.DataFrame({"close": [1.0]}, index=pd.DatetimeIndex([stamp]))
        self.assertFalse(MarketAgent()._freshness(frame, "H1"))


if __name__ == "__main__":
    unittest.main()
