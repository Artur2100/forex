from datetime import datetime, timezone
import yfinance as yf
import pandas as pd
from .config import TIMEFRAMES


class MarketAgent:
    name = "Market Data Agent"

    @staticmethod
    def _stamp(value):
        stamp = pd.Timestamp(value)
        if stamp.tzinfo is None:
            return stamp.tz_localize("UTC")
        return stamp.tz_convert("UTC")

    def _freshness(self, frame, timeframe):
        if frame.empty:
            return False
        now = pd.Timestamp(datetime.now(timezone.utc))
        index = pd.DatetimeIndex(frame.index)
        if index.tz is None:
            index = index.tz_localize("UTC")
        else:
            index = index.tz_convert("UTC")

        if timeframe == "H1":
            # Yahoo's newest hourly bar may still be forming. Use the latest bar
            # whose opening time is at least one full hour behind current UTC time.
            cutoff = now.floor("h") - pd.Timedelta(hours=1)
            completed = index[index <= cutoff]
            if len(completed) == 0:
                return False
            age_hours = (now - completed[-1]).total_seconds() / 3600
            return -0.1 <= age_hours <= 3.5

        # For D1, conservatively ignore the current daily bar.
        if len(index) < 2:
            return False
        age_hours = (now - index[-2]).total_seconds() / 3600
        return -24 <= age_hours <= 96

    def fetch(self, ticker):
        candidates = ticker if isinstance(ticker, (list, tuple)) else [ticker]
        result, errors = {}, []
        for tf, params in TIMEFRAMES.items():
            selected = None
            stale_candidate = None
            for candidate in candidates:
                try:
                    frame = yf.download(
                        candidate, period=params["period"], interval=params["interval"],
                        auto_adjust=False, progress=False, threads=False,
                    )
                    if frame is None or frame.empty:
                        raise RuntimeError("empty response")
                    if isinstance(frame.columns, pd.MultiIndex):
                        frame.columns = frame.columns.get_level_values(0)
                    frame = frame.rename(columns=str.lower)
                    required = {"open", "high", "low", "close"}
                    if not required.issubset(set(frame.columns)):
                        raise RuntimeError(f"missing OHLC columns: {list(frame.columns)}")
                    frame = frame.dropna(subset=["open", "high", "low", "close"]).sort_index()
                    if frame.empty:
                        raise RuntimeError("no valid OHLC candles")
                    frame.attrs["source_symbol"] = candidate
                    frame.attrs["is_fresh"] = self._freshness(frame, tf)
                    if frame.attrs["is_fresh"]:
                        selected = frame
                        break
                    stale_candidate = frame
                except Exception as exc:
                    errors.append(f"{tf}/{candidate}: {exc}")
            # Keep stale data only so the analysis layer can explicitly reject it;
            # never silently relabel a futures proxy as spot gold.
            chosen = selected or stale_candidate
            if chosen is not None:
                result[tf] = chosen
                if not chosen.attrs.get("is_fresh", False):
                    errors.append(f"{tf}/{chosen.attrs.get('source_symbol')}: latest completed candle is stale")
        return result, errors
