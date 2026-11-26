import unittest
from fia.risk_agent import RiskAgent
from fia.decision_agent import ChiefAnalyst

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
        candle = {"valid": True, "fresh": False, "trend": "BEARISH"}
        result = ChiefAnalyst().decide("TEST", {"D1": candle, "H1": candle}, {}, {}, None, RiskAgent())
        self.assertEqual(result["status"], "DATA_STALE")

    def test_weak_adx_never_creates_prealert(self):
        base = {"valid": True, "fresh": True, "trend": "BEARISH", "ema_slope": "DOWN"}
        d1 = dict(base, rsi=40.0, adx=20.0, close=100.0, atr=2.0)
        h1 = dict(base, rsi=40.0, adx=10.0, close=100.0, atr=2.0)
        result = ChiefAnalyst().decide("TEST", {"D1": d1, "H1": h1}, {}, {}, None, RiskAgent())
        self.assertEqual(result["status"], "FILTERED")

if __name__ == "__main__":
    unittest.main()
