from .config import ATR_STOP_MULTIPLIER, TARGET_R_MULTIPLE, RISK_PER_TRADE_PCT

class RiskAgent:
    name = "Risk Manager"

    def provisional_levels(self, direction, price, atr):
        if not atr or atr <= 0:
            return None
        distance = atr * ATR_STOP_MULTIPLIER
        if direction == "LONG":
            entry, sl, tp = price, price-distance, price+distance*TARGET_R_MULTIPLE
        else:
            entry, sl, tp = price, price+distance, price-distance*TARGET_R_MULTIPLE
        return {
            "entry_reference": entry,
            "stop_loss": sl,
            "take_profit": tp,
            "risk_pct_reference": RISK_PER_TRADE_PCT,
            "rr_target": TARGET_R_MULTIPLE,
            "note": "Illustrative levels only; excludes broker spread, commission, slippage and contract specifications."
        }
