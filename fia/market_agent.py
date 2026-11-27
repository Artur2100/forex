from datetime import datetime, timezone
import yfinance as yf
import pandas as pd
from .config import TIMEFRAMES


class MarketAgent:
    name = "Market Data Agent"

    @staticmethod
    def _utc_index(frame):
        index = pd.DatetimeIndex(frame.index)
        if index.tz is None:
            return index.tz_localize("UTC")
        return index.tz_convert("UTC")

    def _freshness(self, frame, timeframe):
        if frame.empty:
            return False
        now = pd.Timestamp(datetime.now(timezone.utc))
        index = self._utc_index(frame)

        if timeframe == "H1":
            cutoff = now.floor("h") - pd.Timedelta(hours=1)
            completed = index[index <= cutoff]
            if len(completed) == 0:
                return False
            age_hours = (now - completed[-1]).total_seconds() / 3600
            return -0.1 <= age_hours <= 3.5

        if timeframe == "H4":
            cutoff = now.floor("4h") - pd.Timedelta(hours=4)
            completed = index[index <= cutoff]
            if len(completed) == 0:
                return False
            age_hours = (now - completed[-1]).total_seconds() / 3600
            return -0.1 <= age_hours <= 8.5

        if len(index) < 2:
            return False
        age_hours = (now - index[-2]).total_seconds() / 3600
        return -24 <= age_hours <= 96

    @staticmethod
    def build_h4(hourly, now=None):
        """Build only fully closed 4-hour candles from hourly OHLC data."""
        if hourly is None or hourly.empty:
            return pd.DataFrame()
        now = pd.Timestamp(now or datetime.now(timezone.utc))
        if now.tzinfo is None:
            now = now.tz_localize("UTC")
        else:
            now = now.tz_convert("UTC")

        frame = hourly.copy().sort_index()
        frame.index = MarketAgent._utc_index(frame)
        frame = frame[~frame.index.duplicated(keep="last")]
        columns = {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
        }
        if "volume" in frame.columns:
            columns["volume"] = "sum"

        grouped = frame.resample("4h", origin="epoch", label="left", closed="left")
        result = grouped.agg(columns)
        counts = grouped["close"].count()
        result = result[counts >= 4].dropna(subset=["open", "high", "low", "close"])

        # A bar labelled 08:00 is complete only at 12:00 UTC.
        latest_completed_start = now.floor("4h") - pd.Timedelta(hours=4)
        result = result[result.index <= latest_completed_start]
        result.attrs["source_symbol"] = hourly.attrs.get("source_symbol", "unknown")
        result.attrs["is_fresh"] = bool(
            not result.empty
            and (now - result.index[-1]).total_seconds() / 3600 <= 8.5
            and (now - result.index[-1]).total_seconds() >= 0
        )
        return result

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
            chosen = selected if selected is not None else stale_candidate
            if chosen is not None:
                result[tf] = chosen
                if not chosen.attrs.get("is_fresh", False):
                    errors.append(f"{tf}/{chosen.attrs.get('source_symbol')}: latest completed candle is stale")

        # H4 is derived from the same H1 source to avoid an unsupported 4h vendor interval.
        if "H1" in result:
            h4 = self.build_h4(result["H1"])
            if not h4.empty:
                result["H4"] = h4
                if not h4.attrs.get("is_fresh", False):
                    errors.append(f"H4/{h4.attrs.get('source_symbol')}: latest completed 4h candle is stale")
            else:
                errors.append("H4: unable to build complete 4-hour candles from H1 data")
        else:
            errors.append("H4: unavailable because H1 data is missing")
        return result, errors
