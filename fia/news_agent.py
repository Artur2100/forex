from datetime import datetime, timezone
import feedparser

from .config import NEWS_FEEDS, NEWS_MAX_AGE_HOURS, NEWS_MAX_ITEMS, NEWS_MAX_ITEMS_PER_FEED


HIGH_IMPACT = {
    "rate decision": ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "NZD", "XAU"],
    "interest rate": ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "NZD", "XAU"],
    "monetary policy": ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "NZD", "XAU"],
    "fomc": ["USD", "XAU"],
    "federal reserve": ["USD", "XAU"],
    "ecb": ["EUR"],
    "bank of england": ["GBP"],
    "bank of japan": ["JPY"],
    "bank of canada": ["CAD"],
    "reserve bank of australia": ["AUD"],
    "inflation": ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "NZD", "XAU"],
    "consumer price": ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "NZD", "XAU"],
    "cpi": ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "NZD", "XAU"],
    "pce": ["USD", "XAU"],
    "employment situation": ["USD"],
    "nonfarm": ["USD"],
    "payroll": ["USD"],
    "unemployment": ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "NZD"],
    "gdp": ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "NZD"],
    "gross domestic product": ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "NZD"],
    "minutes": ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "NZD", "XAU"],
    "press conference": ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "NZD", "XAU"],
}
MEDIUM_TERMS = (
    "retail sales", "industrial production", "pmi", "purchasing managers",
    "trade balance", "wages", "house prices", "consumer confidence",
    "business confidence", "financial stability", "bank lending",
)
LOW_VALUE_TERMS = (
    "college fed challenge", "award", "winners", "former employee",
    "enforcement action", "senior financial officers", "survey",
)


def _published(entry):
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(field)
        if value:
            try:
                from calendar import timegm
                return datetime.fromtimestamp(timegm(value), tz=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                pass
    return None


def classify(title, source=""):
    title_text = title.lower()
    assets = set()
    matched = []
    if any(term in title_text for term in LOW_VALUE_TERMS):
        return "LOW", [], []
    text = title_text
    for phrase, affected in HIGH_IMPACT.items():
        if phrase in text:
            matched.append(phrase)
            assets.update(affected)
    if matched:
        return "HIGH", sorted(assets), matched
    if any(term in text for term in MEDIUM_TERMS):
        return "MEDIUM", [], []
    if any(term in text for term in LOW_VALUE_TERMS):
        return "LOW", [], []
    return "INFO", [], []


class NewsAgent:
    name = "News Intelligence Agent"

    def analyze(self):
        now = datetime.now(timezone.utc)
        items, errors, seen = [], [], set()
        feed_status = []

        for url in NEWS_FEEDS:
            try:
                feed = feedparser.parse(url)
                if getattr(feed, "bozo", False) and not feed.entries:
                    raise RuntimeError(str(feed.bozo_exception))
                source = feed.feed.get("title", url)
                accepted = 0
                for entry in feed.entries[:NEWS_MAX_ITEMS_PER_FEED]:
                    title = entry.get("title", "").strip()
                    link = entry.get("link", "")
                    if not title:
                        continue
                    identity = link or title.lower()
                    if identity in seen:
                        continue
                    seen.add(identity)
                    published = _published(entry)
                    age_hours = None if published is None else (now - published).total_seconds() / 3600
                    if age_hours is not None and (age_hours < -2 or age_hours > NEWS_MAX_AGE_HOURS):
                        continue
                    impact, assets, matched = classify(title, source)
                    items.append({
                        "title": title,
                        "link": link,
                        "published": published.isoformat() if published else entry.get("published", entry.get("updated", "Unknown time")),
                        "age_hours": round(age_hours, 1) if age_hours is not None else None,
                        "source": source,
                        "impact": impact,
                        "assets": assets,
                        "matched_topics": matched,
                    })
                    accepted += 1
                feed_status.append({"source": source, "accepted": accepted, "ok": True})
            except Exception as exc:
                errors.append(f"{url}: {exc}")
                feed_status.append({"source": url, "accepted": 0, "ok": False})

        rank = {"HIGH": 0, "MEDIUM": 1, "INFO": 2, "LOW": 3}
        items.sort(key=lambda item: (
            rank[item["impact"]],
            item["age_hours"] if item["age_hours"] is not None else 99999,
        ))
        items = items[:NEWS_MAX_ITEMS]
        high = sum(item["impact"] == "HIGH" for item in items)
        medium = sum(item["impact"] == "MEDIUM" for item in items)
        return {
            "ready": bool(items) and not errors,
            "items": items,
            "errors": errors,
            "feed_status": feed_status,
            "high_impact_count": high,
            "medium_impact_count": medium,
            "coverage_note": "Official RSS monitoring only. It is not a complete economic calendar; missing RSS events must never be interpreted as no scheduled risk.",
        }
