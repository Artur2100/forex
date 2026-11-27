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
        impact, assets, _ = classify("Monthly retail sales report", "Statistics agency")
        self.assertEqual(impact, "MEDIUM")
        self.assertEqual(assets, [])

    def test_generic_minutes_word_is_not_high(self):
        impact, assets, _ = classify("Japanese Government Bonds Held by the Bank of Japan", "Bank of Japan")
        self.assertEqual(impact, "INFO")
        self.assertEqual(assets, [])

    def test_non_macro_central_bank_agreement_is_not_high(self):
        impact, _, _ = classify("ECB and Sveriges Riksbank conclude agreement for Sweden to join T2", "ECB")
        self.assertEqual(impact, "INFO")

    def test_summary_can_identify_explicit_rate_decision(self):
        impact, assets, _ = classify(
            "Central bank publishes statement",
            "Bank of England",
            "The Monetary Policy Committee announced its interest rate decision today.",
        )
        self.assertEqual(impact, "HIGH")
        self.assertIn("GBP", assets)


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
