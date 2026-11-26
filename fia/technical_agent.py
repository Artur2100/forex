import numpy as np
import pandas as pd
from .config import EMA_FAST, EMA_SLOW, RSI_PERIOD, ATR_PERIOD

class TechnicalAgent:
    name = "Technical Analysis Agent"

    def analyze_frame(self, df):
        x = df.copy()
        close = x["close"].astype(float)
        high = x["high"].astype(float)
        low = x["low"].astype(float)
        x["ema_fast"] = close.ewm(span=EMA_FAST, adjust=False).mean()
        x["ema_slow"] = close.ewm(span=EMA_SLOW, adjust=False).mean()
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1/RSI_PERIOD, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1/RSI_PERIOD, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        x["rsi"] = 100 - 100 / (1 + rs)
        prev = close.shift(1)
        tr = pd.concat([(high-low), (high-prev).abs(), (low-prev).abs()], axis=1).max(axis=1)
        x["atr"] = tr.ewm(alpha=1/ATR_PERIOD, adjust=False).mean()
        row = x.iloc[-2]  # last completed candle
        trend = "BULLISH" if row.ema_fast > row.ema_slow else "BEARISH" if row.ema_fast < row.ema_slow else "NEUTRAL"
        return {
            "trend": trend,
            "close": float(row.close),
            "ema_fast": float(row.ema_fast),
            "ema_slow": float(row.ema_slow),
            "rsi": float(row.rsi) if pd.notna(row.rsi) else None,
            "atr": float(row.atr) if pd.notna(row.atr) else None,
            "bar_time": str(x.index[-2]),
        }

    def analyze(self, frames):
        return {tf: self.analyze_frame(df) for tf, df in frames.items() if len(df) > 60}
