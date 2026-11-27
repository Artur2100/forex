from datetime import datetime, timedelta, timezone
import requests

from .config import CALENDAR_URL, CALENDAR_CURRENCIES, CALENDAR_DAYS_AHEAD


SYMBOL_CURRENCIES = {
    "EUR/USD": {"EUR", "USD"},
    "GBP/USD": {"GBP", "USD"},
    "USD/JPY": {"USD", "JPY"},
    "AUD/USD": {"AUD", "USD"},
    "USD/CAD": {"USD", "CAD"},
    "USD/CHF": {"USD", "CHF"},
    "XAU/USD": {"USD"},
}

WINDOWS_MINUTES = {
    "high": (45, 30),
    "medium": (20, 15),
}


class EconomicCalendarAgent:
    """Fetches scheduled macro events and applies conservative entry blackout windows."""

    name = "Economic Calendar Agent"

    def __init__(self, session=None):
        self.session = session or requests.Session()

    def analyze(self):
        params = {
            "currency": ",".join(CALENDAR_CURRENCIES),
            "impact": "high,medium",
            "days": CALENDAR_DAYS_AHEAD,
            "format": "json",
        }
        try:
            response = self.session.get(CALENDAR_URL, params=params, timeout=20)
            response.raise_for_status()
            payload = response.json()
            server_time = int(payload["server_time"])
            generated_at = datetime.fromisoformat(
                payload.get("generated_at", payload["server_time_iso"]).replace("Z", "+00:00")
            )
            if generated_at.tzinfo is None:
                generated_at = generated_at.replace(tzinfo=timezone.utc)
            age_seconds = (datetime.now(timezone.utc) - generated_at.astimezone(timezone.utc)).total_seconds()
            if age_seconds > 30 * 60 or age_seconds < -5 * 60:
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
                        "ts": ts,
                        "time": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
                        "currency": currency,
                        "impact": impact,
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
            return {
                "ready": True,
                "server_time": server_time,
                "generated_at": generated_at.astimezone(timezone.utc).isoformat(),
                "events": normalized,
                "errors": [],
            }
        except Exception as exc:
            return {
                "ready": False,
                "server_time": int(datetime.now(timezone.utc).timestamp()),
                "generated_at": None,
                "events": [],
                "errors": [f"{type(exc).__name__}: {exc}"],
            }

    @staticmethod
    def risk_for_symbol(symbol, calendar_result):
        if not calendar_result.get("ready"):
            return {
                "blocked": True,
                "status": "UNKNOWN",
                "reason": "Экономический календарь недоступен: новые предупреждения приостановлены",
                "events": [],
            }

        currencies = SYMBOL_CURRENCIES.get(symbol, set())
        now_ts = int(calendar_result["server_time"])
        relevant = [
            event for event in calendar_result.get("events", [])
            if event["currency"] in currencies
        ]
        active = []
        for event in relevant:
            before, after = WINDOWS_MINUTES[event["impact"]]
            delta = event["ts"] - now_ts
            if -after * 60 <= delta <= before * 60:
                active.append((event, delta))

        if active:
            event, delta = min(active, key=lambda pair: abs(pair[1]))
            if delta > 0:
                timing = f"через {max(1, int(delta // 60))} мин"
            elif delta < 0:
                timing = f"{max(1, int(abs(delta) // 60))} мин после публикации"
            else:
                timing = "публикация сейчас"
            return {
                "blocked": True,
                "status": "HIGH RISK" if event["impact"] == "high" else "CAUTION",
                "reason": f"{event['currency']} {event['title']} — {timing}",
                "events": [item[0] for item in active],
            }

        upcoming = [
            event for event in relevant
            if event["ts"] >= now_ts
        ]
        return {
            "blocked": False,
            "status": "NORMAL",
            "reason": "Нет событий HIGH/MEDIUM в защитном временном окне",
            "events": upcoming,
        }

    @staticmethod
    def upcoming_summary(calendar_result, limit=8):
        if not calendar_result.get("ready"):
            errors = "; ".join(calendar_result.get("errors", []))
            return f"ЭКОНОМКАЛЕНДАРЬ: НЕДОСТУПЕН — {errors}"
        now_ts = int(calendar_result["server_time"])
        upcoming = [
            event for event in calendar_result.get("events", [])
            if event["ts"] >= now_ts
        ][:limit]
        if not upcoming:
            return "Экономкалендарь: ближайшие HIGH/MEDIUM события не найдены."
        lines = ["Экономкалендарь (время UTC):"]
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
            status = f" | {event['status']}" if event["status"] not in ("scheduled", "") else ""
            lines.append(
                f"• [{event['impact'].upper()}] {when} UTC · {event['currency']} · {event['title']}{suffix}{status}"
            )
        return "\n".join(lines)
