from datetime import datetime, timezone
import numpy as np
import pandas as pd
from .config import EMA_FAST, EMA_SLOW, RSI_PERIOD, ATR_PERIOD


class TechnicalAgent:
    name = "Technical Analysis Agent"

    def analyze_frame(self, df, timeframe):
        x = df.copy().sort_index()
        for col in ("open", "high", "low", "close"):
            x[col] = pd.to_numeric(x[col], errors="coerce")
        x = x.dropna(subset=["open", "high", "low", "close"])
        if len(x) < max(EMA_SLOW + 5, 70):
            raise ValueError("not enough valid candles")

        close, high, low = x["close"], x["high"], x["low"]
        x["ema_fast"] = close.ewm(span=EMA_FAST, adjust=False).mean()
        x["ema_slow"] = close.ewm(span=EMA_SLOW, adjust=False).mean()

        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / RSI_PERIOD, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / RSI_PERIOD, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        x["rsi"] = 100 - 100 / (1 + rs)

        prev = close.shift(1)
        tr = pd.concat([(high - low), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
        x["atr"] = tr.ewm(alpha=1 / ATR_PERIOD, adjust=False).mean()

        up = high.diff()
        down = -low.diff()
        plus_dm = up.where((up > down) & (up > 0), 0.0)
        minus_dm = down.where((down > up) & (down > 0), 0.0)
        atr_smooth = tr.ewm(alpha=1 / ATR_PERIOD, adjust=False).mean().replace(0, np.nan)
        plus_di = 100 * plus_dm.ewm(alpha=1 / ATR_PERIOD, adjust=False).mean() / atr_smooth
        minus_di = 100 * minus_dm.ewm(alpha=1 / ATR_PERIOD, adjust=False).mean() / atr_smooth
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        x["adx"] = dx.ewm(alpha=1 / ATR_PERIOD, adjust=False).mean()

        now = pd.Timestamp(datetime.now(timezone.utc))
        idx = pd.DatetimeIndex(x.index)
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        else:
            idx = idx.tz_convert("UTC")

        if timeframe == "D1":
            row_pos = len(x) - 2
            max_age = 96
        elif timeframe == "H4":
            cutoff = now.floor("4h") - pd.Timedelta(hours=4)
            eligible = np.flatnonzero(idx <= cutoff)
            if len(eligible) == 0:
                raise ValueError("no completed H4 candle available")
            row_pos = int(eligible[-1])
            max_age = 8.5
        elif timeframe == "H1":
            cutoff = now.floor("h") - pd.Timedelta(hours=1)
            eligible = np.flatnonzero(idx <= cutoff)
            if len(eligible) == 0:
                raise ValueError("no completed H1 candle available")
            row_pos = int(eligible[-1])
            max_age = 3.5
        else:
            raise ValueError(f"unsupported timeframe: {timeframe}")

        if row_pos < 5:
            raise ValueError("not enough completed candles")
        row = x.iloc[row_pos]
        prior = x.iloc[max(0, row_pos - 3)]
        stamp = pd.Timestamp(x.index[row_pos])
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        else:
            stamp = stamp.tz_convert("UTC")
        age_hours = (datetime.now(timezone.utc) - stamp.to_pydatetime()).total_seconds() / 3600

        trend = "BULLISH" if row.ema_fast > row.ema_slow else "BEARISH" if row.ema_fast < row.ema_slow else "NEUTRAL"
        slope = "UP" if row.ema_fast > prior.ema_fast else "DOWN" if row.ema_fast < prior.ema_fast else "FLAT"
        values = [row.close, row.ema_fast, row.ema_slow, row.atr, row.rsi, row.adx]
        valid = all(pd.notna(v) and np.isfinite(float(v)) for v in values) and float(row.close) > 0 and float(row.atr) > 0

        return {
            "trend": trend, "ema_slope": slope, "close": float(row.close),
            "ema_fast": float(row.ema_fast), "ema_slow": float(row.ema_slow),
            "rsi": float(row.rsi) if pd.notna(row.rsi) else None,
            "atr": float(row.atr) if pd.notna(row.atr) else None,
            "adx": float(row.adx) if pd.notna(row.adx) else None,
            "bar_time": stamp.isoformat(), "age_hours": round(age_hours, 2),
            "fresh": age_hours >= -1 and age_hours <= max_age, "valid": valid,
        }

    def analyze(self, frames):
        results, errors = {}, {}
        for tf, df in frames.items():
            try:
                results[tf] = self.analyze_frame(df, tf)
                if df.attrs.get("is_fresh") is False:
                    results[tf]["fresh"] = False
            except Exception as exc:
                errors[tf] = str(exc)
        return results, errors
