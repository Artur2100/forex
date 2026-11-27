from datetime import datetime, timezone, timedelta
from pathlib import Path
import csv

import numpy as np
import pandas as pd
import yfinance as yf

from .notifier import send_telegram


DAY_RISK_PCT = 0.5
DAY_RR = 2.0
DAY_ATR_MULTIPLIER = 1.5
DAY_MAX_HOLD_HOURS = 24


class DayMarketAgent:
    """Separate M15 data fetcher; H1/H4 context is shared with the Swing scan."""

    def fetch(self, ticker):
        candidates = ticker if isinstance(ticker, (list, tuple)) else [ticker]
        errors = []
        for candidate in candidates:
            try:
                frame = yf.download(
                    candidate, period="60d", interval="15m",
                    auto_adjust=False, progress=False, threads=False,
                )
                if frame is None or frame.empty:
                    raise RuntimeError("empty M15 response")
                if isinstance(frame.columns, pd.MultiIndex):
                    frame.columns = frame.columns.get_level_values(0)
                frame = frame.rename(columns=str.lower)
                required = {"open", "high", "low", "close"}
                if not required.issubset(frame.columns):
                    raise RuntimeError(f"missing OHLC columns: {list(frame.columns)}")
                frame = frame.dropna(subset=list(required)).sort_index()
                if frame.empty:
                    raise RuntimeError("no valid M15 candles")
                index = pd.DatetimeIndex(frame.index)
                if index.tz is None:
                    index = index.tz_localize("UTC")
                else:
                    index = index.tz_convert("UTC")
                frame.index = index
                frame = frame[~frame.index.duplicated(keep="last")]
                now = pd.Timestamp(datetime.now(timezone.utc))
                last_closed = now.floor("15min") - pd.Timedelta(minutes=15)
                closed = frame[frame.index <= last_closed]
                if len(closed) < 100:
                    raise RuntimeError("not enough completed M15 candles")
                age = (now - closed.index[-1]).total_seconds() / 60
                if age < -1 or age > 45:
                    raise RuntimeError(f"latest completed M15 candle is stale ({age:.0f} min)")
                closed.attrs["source_symbol"] = candidate
                closed.attrs["is_fresh"] = True
                return closed, errors
            except Exception as exc:
                errors.append(f"M15/{candidate}: {exc}")
        return None, errors


class DayTechnicalAgent:
    """Indicators calculated only on completed M15 candles."""

    def analyze(self, frame):
        if frame is None or frame.empty or len(frame) < 100:
            raise ValueError("insufficient M15 data")
        x = frame.copy().sort_index()
        for col in ("open", "high", "low", "close"):
            x[col] = pd.to_numeric(x[col], errors="coerce")
        x = x.dropna(subset=["open", "high", "low", "close"])
        close, high, low = x["close"], x["high"], x["low"]
        x["ema20"] = close.ewm(span=20, adjust=False).mean()
        x["ema50"] = close.ewm(span=50, adjust=False).mean()
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        x["rsi"] = 100 - 100 / (1 + rs)
        prev = close.shift(1)
        tr = pd.concat([(high - low), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
        x["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
        up, down = high.diff(), -low.diff()
        plus_dm = up.where((up > down) & (up > 0), 0.0)
        minus_dm = down.where((down > up) & (down > 0), 0.0)
        atr_smooth = tr.ewm(alpha=1 / 14, adjust=False).mean().replace(0, np.nan)
        plus_di = 100 * plus_dm.ewm(alpha=1 / 14, adjust=False).mean() / atr_smooth
        minus_di = 100 * minus_dm.ewm(alpha=1 / 14, adjust=False).mean() / atr_smooth
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        x["adx"] = dx.ewm(alpha=1 / 14, adjust=False).mean()
        row, prior = x.iloc[-1], x.iloc[-2]
        stamp = pd.Timestamp(x.index[-1])
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        else:
            stamp = stamp.tz_convert("UTC")
        values = [row.close, row.ema20, row.ema50, row.rsi, row.atr, row.adx]
        if not all(pd.notna(v) and np.isfinite(float(v)) for v in values) or row.atr <= 0:
            raise ValueError("invalid M15 indicators")
        return {
            "bar_time": stamp.isoformat(),
            "open": float(row.open), "high": float(row.high),
            "low": float(row.low), "close": float(row.close),
            "ema20": float(row.ema20), "ema50": float(row.ema50),
            "previous_close": float(prior.close),
            "previous_ema20": float(prior.ema20),
            "rsi": float(row.rsi), "atr": float(row.atr), "adx": float(row.adx),
            "fresh": bool(frame.attrs.get("is_fresh", False)),
            "source": frame.attrs.get("source_symbol", "unknown"),
        }


class DayRiskAgent:
    def levels(self, direction, price, atr):
        if not atr or atr <= 0:
            return None
        distance = atr * DAY_ATR_MULTIPLIER
        if direction == "LONG":
            sl, tp = price - distance, price + distance * DAY_RR
        else:
            sl, tp = price + distance, price - distance * DAY_RR
        return {
            "entry_reference": price, "stop_loss": sl, "take_profit": tp,
            "risk_pct_reference": DAY_RISK_PCT, "rr_target": DAY_RR,
        }


class DayChiefAnalyst:
    """H4/H1 trend filter plus a completed-M15 pullback/rejection trigger."""

    def decide(self, symbol, context, m15, event_risk, news, risk_agent):
        h4, h1 = context.get("H4"), context.get("H1")
        if not h4 or not h1 or not m15:
            return {"status": "DAY_DATA_INSUFFICIENT", "symbol": symbol}
        if not all(x.get("valid") and x.get("fresh") for x in (h4, h1)):
            return {"status": "DAY_CONTEXT_STALE", "symbol": symbol}
        if not m15.get("fresh"):
            return {"status": "DAY_M15_STALE", "symbol": symbol}
        trend = h4.get("trend")
        if trend not in ("BULLISH", "BEARISH") or h1.get("trend") != trend:
            return {"status": "DAY_NO_SETUP", "symbol": symbol, "reason": "H4/H1 trend is not aligned"}
        direction = "LONG" if trend == "BULLISH" else "SHORT"
        expected_slope = "UP" if direction == "LONG" else "DOWN"
        if h4.get("ema_slope") != expected_slope or h1.get("ema_slope") != expected_slope:
            return {"status": "DAY_FILTERED", "symbol": symbol, "reason": "H4/H1 EMA slope does not confirm trend"}

        bullish_rejection = (
            m15["low"] <= m15["ema20"] and m15["close"] > m15["ema20"]
            and m15["close"] > m15["open"]
        )
        bearish_rejection = (
            m15["high"] >= m15["ema20"] and m15["close"] < m15["ema20"]
            and m15["close"] < m15["open"]
        )
        if direction == "LONG":
            trigger = bullish_rejection and 52 <= m15["rsi"] <= 72
        else:
            trigger = bearish_rejection and 28 <= m15["rsi"] <= 48
        if not trigger or m15["adx"] < 18 or m15["close"] <= 0:
            return {"status": "DAY_NO_SETUP", "symbol": symbol, "reason": "M15 pullback, RSI or ADX trigger not confirmed"}
        if event_risk and event_risk.get("blocked"):
            return {"status": "DAY_EVENT_BLOCK", "symbol": symbol, "reason": event_risk.get("reason", "Calendar risk")}
        if not news.get("ready"):
            return {"status": "DAY_NEWS_BLOCK", "symbol": symbol, "reason": "Official RSS news gate is unavailable"}
        levels = risk_agent.levels(direction, m15["close"], m15["atr"])
        if not levels:
            return {"status": "DAY_LEVELS_INVALID", "symbol": symbol}
        return {
            "status": "DAY_FINAL_SIGNAL", "symbol": symbol, "direction": direction,
            "m15": m15, "levels": levels,
            "reason": "H4/H1 trend aligned; completed M15 rejection, RSI/ADX and calendar/news gates passed.",
        }


DAY_JOURNAL_PATH = Path("day_journal.csv")
DAY_STATE_PATH = Path("day_state.json")
DAY_FIELDS = ["id", "created_utc", "symbol", "direction", "entry", "sl", "tp",
              "status", "outcome_r", "resolved_utc", "notes"]


def load_day_journal():
    if not DAY_JOURNAL_PATH.exists():
        return []
    with DAY_JOURNAL_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_day_journal(rows):
    with DAY_JOURNAL_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=DAY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def add_day_alert(rows, decision):
    m15, levels = decision["m15"], decision["levels"]
    key = f"{decision['symbol']}|{decision['direction']}|{m15['bar_time']}"
    if any(row["id"] == key for row in rows):
        return False
    rows.append({
        "id": key, "created_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": decision["symbol"], "direction": decision["direction"],
        "entry": f"{levels['entry_reference']:.10g}",
        "sl": f"{levels['stop_loss']:.10g}", "tp": f"{levels['take_profit']:.10g}",
        "status": "OPEN", "outcome_r": "", "resolved_utc": "",
        "notes": "Hypothetical Day alert; not an executed trade.",
    })
    return True


def update_day_outcomes(rows, frames_by_symbol):
    now = datetime.now(timezone.utc)
    for row in rows:
        if row["status"] != "OPEN":
            continue
        frame = frames_by_symbol.get(row["symbol"])
        if frame is None or frame.empty:
            continue
        entry_time = datetime.fromisoformat(row["id"].rsplit("|", 1)[-1])
        if entry_time.tzinfo is None:
            entry_time = entry_time.replace(tzinfo=timezone.utc)
        bars = frame.copy()
        if bars.index.tz is None:
            bars.index = bars.index.tz_localize("UTC")
        else:
            bars.index = bars.index.tz_convert("UTC")
        bars = bars[bars.index > entry_time]
        sl, tp = float(row["sl"]), float(row["tp"])
        for stamp, candle in bars.iterrows():
            high, low = float(candle["high"]), float(candle["low"])
            if row["direction"] == "LONG":
                sl_hit, tp_hit = low <= sl, high >= tp
            else:
                sl_hit, tp_hit = high >= sl, low <= tp
            if sl_hit and tp_hit:
                row["status"], row["outcome_r"] = "AMBIGUOUS_SAME_CANDLE", ""
            elif tp_hit:
                row["status"], row["outcome_r"] = "TP_HIT", f"{DAY_RR:.1f}"
            elif sl_hit:
                row["status"], row["outcome_r"] = "SL_HIT", "-1.0"
            else:
                continue
            row["resolved_utc"] = stamp.to_pydatetime().isoformat()
            break
        if row["status"] == "OPEN" and now - entry_time > timedelta(hours=DAY_MAX_HOLD_HOURS):
            row["status"] = "EXPIRED_24H"
            row["resolved_utc"] = now.isoformat()
    return rows


def day_journal_summary(rows):
    closed = [r for r in rows if r["status"] in ("TP_HIT", "SL_HIT")]
    wins = sum(r["status"] == "TP_HIT" for r in closed)
    losses = sum(r["status"] == "SL_HIT" for r in closed)
    return {
        "total": len(rows), "open": sum(r["status"] == "OPEN" for r in rows),
        "wins": wins, "losses": losses,
        "wr": wins / len(closed) * 100 if closed else None,
        "net_r": sum(float(r["outcome_r"]) for r in closed),
    }


def run_day_agent(symbols, context_by_symbol, calendar_agent, calendar, news):
    risk_agent, analyst, market_agent, technical_agent = (
        DayRiskAgent(), DayChiefAnalyst(), DayMarketAgent(), DayTechnicalAgent()
    )
    state = {"sent": []}
    if DAY_STATE_PATH.exists():
        try:
            import json
            state = json.loads(DAY_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    journal = load_day_journal()
    frames_by_symbol, decisions, messages = {}, [], []
    errors = []
    for symbol, ticker in symbols.items():
        frame, fetch_errors = market_agent.fetch(ticker)
        errors.extend(f"{symbol}: {error}" for error in fetch_errors)
        if frame is None:
            continue
        frames_by_symbol[symbol] = frame
        try:
            m15 = technical_agent.analyze(frame)
        except Exception as exc:
            errors.append(f"{symbol}: M15 analysis: {exc}")
            continue
        event_risk = calendar_agent.risk_for_symbol(symbol, calendar)
        decision = analyst.decide(symbol, context_by_symbol.get(symbol, {}), m15,
                                  event_risk, news, risk_agent)
        decisions.append(decision)
        if decision["status"] != "DAY_FINAL_SIGNAL":
            continue
        key = f"{symbol}|{decision['direction']}|{m15['bar_time']}"
        if key in state.get("sent", []):
            continue
        state.setdefault("sent", []).append(key)
        levels = decision["levels"]
        side = "BUY" if decision["direction"] == "LONG" else "SELL"
        price_fmt = lambda value: f"{value:.5f}" if abs(value) < 100 else f"{value:.2f}"
        messages.append(
            "⚡ DAY TRADING — ФИНАЛЬНЫЙ СИГНАЛ\n"
            f"{symbol} · {side}\n"
            f"Вход-ориентир: {price_fmt(levels['entry_reference'])}\n"
            f"Stop Loss: {price_fmt(levels['stop_loss'])}\n"
            f"Take Profit: {price_fmt(levels['take_profit'])}\n"
            f"R:R 1:{levels['rr_target']:.0f} · риск до {levels['risk_pct_reference']:.1f}%\n"
            f"M15: RSI {m15['rsi']:.1f} · ADX {m15['adx']:.1f}\n"
            "Котировка Yahoo Finance, не MT5. Проверь цену и спред у брокера; объём рассчитай так, чтобы риск по SL не превышал 0,5% депозита. Исполнение вручную."
        )
        add_day_alert(journal, decision)
    journal = update_day_outcomes(journal, frames_by_symbol)
    save_day_journal(journal)
    state["sent"] = state.get("sent", [])[-500:]
    import json
    for message in messages:
        send_telegram(message[:3900])
    DAY_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return decisions
