import yfinance as yf
import pandas as pd
from .config import TIMEFRAMES

class MarketAgent:
    name = "Market Data Agent"

    def fetch(self, ticker):
        result = {}
        errors = []
        for tf, params in TIMEFRAMES.items():
            try:
                frame = yf.download(
                    ticker, period=params["period"], interval=params["interval"],
                    auto_adjust=False, progress=False, threads=False
                )
                if frame is None or frame.empty:
                    raise RuntimeError("empty response")
                if isinstance(frame.columns, pd.MultiIndex):
                    frame.columns = frame.columns.get_level_values(0)
                frame = frame.rename(columns=str.lower)
                required = {"open", "high", "low", "close"}
                if not required.issubset(set(frame.columns)):
                    raise RuntimeError(f"missing OHLC columns: {list(frame.columns)}")
                frame = frame.dropna(subset=["open", "high", "low", "close"])
                result[tf] = frame
            except Exception as exc:
                errors.append(f"{tf}: {exc}")
        return result, errors
