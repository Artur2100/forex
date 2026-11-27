from .config import ECONOMIC_CALENDAR_VALIDATED, FINAL_SIGNALS_ENABLED, PREALERTS_ENABLED


class ChiefAnalyst:
    name = "Chief Trading Analyst"

    def decide(self, symbol, technical, news, macro, correlation, risk_agent, event_risk=None):
        d1, h4, h1 = technical.get("D1"), technical.get("H4"), technical.get("H1")
        if not d1 or not h4 or not h1:
            return {"status": "DATA_INSUFFICIENT", "symbol": symbol, "reason": "D1, H4 or H1 data unavailable"}
        if not all(frame.get("valid") for frame in (d1, h4, h1)):
            return {"status": "DATA_INVALID", "symbol": symbol, "reason": "Indicator validation failed"}
        if not all(frame.get("fresh") for frame in (d1, h4, h1)):
            return {"status": "DATA_STALE", "symbol": symbol, "reason": "Latest completed D1/H4/H1 candle is stale"}

        trends = [d1["trend"], h4["trend"], h1["trend"]]
        if trends[0] not in ("BULLISH", "BEARISH") or len(set(trends)) != 1:
            return {
                "status": "NO_SETUP", "symbol": symbol,
                "reason": "D1/H4/H1 trend alignment is absent",
            }
        direction = "LONG" if d1["trend"] == "BULLISH" else "SHORT"
        expected_slope = "UP" if direction == "LONG" else "DOWN"
        if any(frame.get("ema_slope") != expected_slope for frame in (d1, h4, h1)):
            return {"status": "FILTERED", "symbol": symbol, "reason": "EMA slope does not confirm D1/H4/H1 trend"}

        rsi = h1.get("rsi")
        adx = h1.get("adx")
        if rsi is None or adx is None or adx < 15:
            return {"status": "FILTERED", "symbol": symbol, "reason": "Momentum/ADX confirmation unavailable or weak"}
        if direction == "LONG" and not (50 <= rsi <= 75):
            return {"status": "FILTERED", "symbol": symbol, "reason": "H1 RSI outside long confirmation range"}
        if direction == "SHORT" and not (25 <= rsi <= 50):
            return {"status": "FILTERED", "symbol": symbol, "reason": "H1 RSI outside short confirmation range"}

        if event_risk and event_risk.get("blocked"):
            return {
                "status": "EVENT_RISK_BLOCK", "symbol": symbol, "direction": direction,
                "reason": event_risk.get("reason", "Calendar risk window active"),
            }

        levels = risk_agent.provisional_levels(direction, h1["close"], h1["atr"])
        if not PREALERTS_ENABLED or not levels:
            return {"status": "WATCH_DISABLED", "symbol": symbol}
        gate_open = ECONOMIC_CALENDAR_VALIDATED and FINAL_SIGNALS_ENABLED and news.get("ready", False)
        if not gate_open:
            return {
                "status": "TECHNICAL_PREALERT", "symbol": symbol, "direction": direction,
                "d1": d1, "h4": h4, "h1": h1, "levels": levels,
                "reason": "Технические условия совпали, но защитный шлюз данных/новостей закрыт.",
            }
        return {
            "status": "FINAL_SIGNAL", "symbol": symbol, "direction": direction,
            "d1": d1, "h4": h4, "h1": h1, "levels": levels,
            "reason": "D1/H4/H1 alignment, EMA slope, RSI/ADX and calendar/news checks passed.",
        }
