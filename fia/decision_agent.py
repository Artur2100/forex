from .config import ECONOMIC_CALENDAR_VALIDATED, FINAL_SIGNALS_ENABLED, PREALERTS_ENABLED

class ChiefAnalyst:
    name = "Chief Trading Analyst"

    def decide(self, symbol, technical, news, macro, correlation, risk_agent):
        d1 = technical.get("D1")
        h1 = technical.get("H1")
        if not d1 or not h1:
            return {"status": "DATA_INSUFFICIENT", "symbol": symbol}

        aligned = d1["trend"] == h1["trend"] and d1["trend"] in ("BULLISH", "BEARISH")
        direction = "LONG" if d1["trend"] == "BULLISH" else "SHORT" if d1["trend"] == "BEARISH" else None
        if not aligned or not direction:
            return {"status": "NO_SETUP", "symbol": symbol, "reason": "D1/H1 trend not aligned"}

        levels = risk_agent.provisional_levels(direction, h1["close"], h1["atr"])
        if not PREALERTS_ENABLED:
            return {"status": "WATCH_DISABLED", "symbol": symbol}

        gate_open = ECONOMIC_CALENDAR_VALIDATED and FINAL_SIGNALS_ENABLED and news.get("ready", False)
        if not gate_open:
            return {
                "status": "TECHNICAL_PREALERT",
                "symbol": symbol,
                "direction": direction,
                "d1": d1,
                "h1": h1,
                "levels": levels,
                "reason": "D1/H1 trend alignment; news/calendar and strategy validation gates remain closed."
            }

        # Final signals intentionally not implemented in this MVP.
        return {"status": "FINAL_SIGNAL_NOT_IMPLEMENTED", "symbol": symbol}
