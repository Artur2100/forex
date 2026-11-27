from datetime import datetime, timezone
import time

import requests

from .config import (
    CALENDAR_URL, CALENDAR_CURRENCIES, CALENDAR_DAYS_AHEAD,
    CALENDAR_FALLBACK_URL,
)


SYMBOL_CURRENCIES = {
    "EUR/USD": {"EUR", "USD"},
    "GBP/USD": {"GBP", "USD"},
    "USD/JPY": {"USD", "JPY"},
    "AUD/USD": {"AUD", "USD"},
    "USD/CAD": {"USD", "CAD"},
    "USD/CHF": {"USD", "CHF"},
    "XAU/USD": {"USD"},
}

WINDOWS_MINUTES = {"high": (45, 30), "medium": (20, 15)}
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
FF_IMPACT = {"high": "high", "medium": "medium"}


class EconomicCalendarAgent:
    """Primary structured calendar with an independent weekly Forex Factory fallback."""

    name = "Economic Calendar Agent"

    def __init__(self, session=None, sleep=time.sleep):
        self.session = session or requests.Session()
        self.sleep = sleep

    def _get_json(self, url, params=None):
        last_error = None
        for attempt in range(3):
            try:
                response = self.session.get(
                    url, params=params, timeout=(5, 12),
                    headers={"User-Agent": "ForexIntelligenceAgent/1.0"},
                )
                if response.status_code in RETRYABLE_STATUS and attempt < 2:
                    retry_after = response.headers.get("Retry-After", "")
                    try:
                        delay = min(8, max(1, int(retry_after)))
                    except (TypeError, ValueError):
                        delay = 1 + attempt * 2
                    self.sleep(delay)
                    continue
                response.raise_for_status()
                return response.json()
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                if attempt < 2:
                    self.sleep(1 + attempt * 2)
                    continue
                raise
        if last_error:
            raise last_error
        raise RuntimeError("calendar request failed after retries")

    @staticmethod
    def _normalize_primary(payload):
        server_time = int(payload["server_time"])
        generated_value = payload.get("generated_at") or payload.get("server_time_iso")
        if not generated_value:
            raise ValueError("calendar response has no generated_at/server_time_iso")
        generated_at = datetime.fromisoformat(str(generated_value).replace("Z", "+00:00"))
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - generated_at.astimezone(timezone.utc)).total_seconds()
        if age_seconds > 25 * 60 or age_seconds < -5 * 60:
            raise ValueError(f"calendar payload is stale or clock-skewed ({age_seconds:.0f}s)")
        events = payload.get("events")
        if not isinstance(events, list):
            raise ValueError("calendar response has no valid events list")
        normalized = []
        for event in events:
            try:
                ts = int(event["ts"])
                currency = str(event["currency"]).upper()
                impact = str(event["impact"]).lower()
                if currency not in CALENDAR_CURRENCIES or impact not in WINDOWS_MINUTES:
                    continue
                normalized.append({
                    "ts": ts, "time": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
                    "currency": currency, "impact": impact,
                    "title": str(event.get("title", "Untitled event")),
                    "forecast": str(event.get("forecast", "")),
                    "previous": str(event.get("previous", "")),
                    "actual": str(event.get("actual", "")),
                    "status": str(event.get("status", "unknown")),
                    "moved_from": str(event.get("moved_from", "")),
                    "confidence": str(event.get("confidence", "unknown")),
                    "id": str(event.get("id", "")),
                })
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        normalized.sort(key=lambda item: item["ts"])
        return normalized, server_time, generated_at.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _normalize_forex_factory(payload):
        if not isinstance(payload, list) or not payload:
            raise ValueError("Forex Factory feed is empty or not a JSON array")
        normalized = []
        for index, event in enumerate(payload):
            try:
                currency = str(event.get("country", "")).upper()
                impact = str(event.get("impact", "")).lower()
                if currency not in CALENDAR_CURRENCIES or impact not in FF_IMPACT:
                    continue
                event_time = datetime.fromisoformat(str(event["date"]).replace("Z", "+00:00"))
                if event_time.tzinfo is None:
                    raise ValueError("event date has no timezone offset")
                ts = int(event_time.astimezone(timezone.utc).timestamp())
                normalized.append({
                    "ts": ts, "time": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
                    "currency": currency, "impact": FF_IMPACT[impact],
                    "title": str(event.get("title", "Untitled event")),
                    "forecast": str(event.get("forecast", "")),
                    "previous": str(event.get("previous", "")),
                    "actual": str(event.get("actual", "")),
                    "status": "scheduled", "moved_from": "",
                    "confidence": "Forex Factory weekly feed",
                    "id": str(event.get("id", f"ff-{currency}-{ts}-{index}")),
                })
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        if not normalized:
            raise ValueError("Forex Factory feed contained no supported HIGH/MEDIUM events")
        normalized.sort(key=lambda item: item["ts"])
        return normalized

    def analyze(self):
        params = {
            "currency": ",".join(CALENDAR_CURRENCIES),
            "impact": "high,medium",
            "days": CALENDAR_DAYS_AHEAD,
            "format": "json",
        }
        errors = []
        try:
            payload = self._get_json(CALENDAR_URL, params=params)
            events, server_time, generated_at = self._normalize_primary(payload)
            return {
                "ready": True, "provider": "ShowMyTrades", "fallback_used": False,
                "server_time": server_time, "generated_at": generated_at,
                "events": events, "errors": [],
            }
        except Exception as exc:
            errors.append(f"ShowMyTrades: {type(exc).__name__}: {exc}")

        try:
            payload = self._get_json(CALENDAR_FALLBACK_URL)
            events = self._normalize_forex_factory(payload)
            now = int(datetime.now(timezone.utc).timestamp())
            return {
                "ready": True, "provider": "Forex Factory (weekly fallback)",
                "fallback_used": True, "server_time": now,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "events": events, "errors": errors,
                "coverage_warning": "Резервный источник покрывает только текущую неделю; actual может отсутствовать.",
            }
        except Exception as exc:
            errors.append(f"Forex Factory fallback: {type(exc).__name__}: {exc}")
            return {
                "ready": False, "provider": None, "fallback_used": False,
                "server_time": int(datetime.now(timezone.utc).timestamp()),
                "generated_at": None, "events": [], "errors": errors,
            }

    @staticmethod
    def risk_for_symbol(symbol, calendar_result):
        if not calendar_result.get("ready"):
            return {
                "blocked": True, "status": "UNKNOWN",
                "reason": "Экономический календарь недоступен: новые предупреждения приостановлены",
                "events": [],
            }
        currencies = SYMBOL_CURRENCIES.get(symbol, set())
        now_ts = int(calendar_result["server_time"])
        relevant = [event for event in calendar_result.get("events", []) if event["currency"] in currencies]
        active = []
        for event in relevant:
            before, after = WINDOWS_MINUTES[event["impact"]]
            delta = event["ts"] - now_ts
            if -after * 60 <= delta <= before * 60:
                active.append((event, delta))
        if active:
            event, delta = min(active, key=lambda pair: abs(pair[1]))
            timing = f"через {max(1, int(delta // 60))} мин" if delta > 0 else (
                f"{max(1, int(abs(delta) // 60))} мин после публикации" if delta < 0 else "публикация сейчас"
            )
            return {
                "blocked": True,
                "status": "HIGH RISK" if event["impact"] == "high" else "CAUTION",
                "reason": f"{event['currency']} {event['title']} — {timing}",
                "events": [item[0] for item in active],
            }
        upcoming = [event for event in relevant if event["ts"] >= now_ts]
        return {
            "blocked": False, "status": "NORMAL",
            "reason": "Нет событий HIGH/MEDIUM в защитном временном окне",
            "events": upcoming,
        }

    @staticmethod
    def upcoming_summary(calendar_result, limit=8):
        if not calendar_result.get("ready"):
            errors = "; ".join(calendar_result.get("errors", []))
            return f"ЭКОНОМКАЛЕНДАРЬ: НЕДОСТУПЕН — {errors}"
        now_ts = int(calendar_result["server_time"])
        upcoming = [event for event in calendar_result.get("events", []) if event["ts"] >= now_ts][:limit]
        if not upcoming:
            return "Экономкалендарь: ближайшие HIGH/MEDIUM события не найдены."
        provider = calendar_result.get("provider", "unknown")
        lines = [f"Экономкалендарь ({provider}; время UTC):"]
        if calendar_result.get("coverage_warning"):
            lines.append(f"⚠️ {calendar_result['coverage_warning']}")
        for event in upcoming:
            when = datetime.fromtimestamp(event["ts"], timezone.utc).strftime("%d.%m %H:%M")
            values = []
            if event["forecast"]:
                values.append(f"прогноз {event['forecast']}")
            if event["previous"]:
                values.append(f"пред. {event['previous']}")
            if event["actual"]:
                values.append(f"факт {event['actual']}")
            suffix = f" | {', '.join(values)}" if values else ""
            confidence = f" | дата: {event['confidence']}" if event.get("confidence") else ""
            lines.append(f"• [{event['impact'].upper()}] {when} UTC · {event['currency']} · {event['title']}{suffix}{confidence}")
        return "\n".join(lines)
