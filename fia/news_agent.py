from datetime import datetime, timezone
import re

import feedparser

from .config import NEWS_FEEDS, NEWS_MAX_AGE_HOURS, NEWS_MAX_ITEMS, NEWS_MAX_ITEMS_PER_FEED


# Only specific monetary-policy decisions and top-tier scheduled macro releases qualify as HIGH.
HIGH_RULES = (
    (r"\b(rate decision|interest rate decision|policy rate decision)\b", {"USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF"}),
    (r"\b(fomc statement|fomc minutes|federal reserve rate decision|federal funds rate)\b", {"USD", "XAU"}),
    (r"\b(ecb rate decision|monetary policy decision|bank of england rate decision|bank of japan rate decision|bank of canada rate decision|rba rate decision|snb rate decision)\b", {"EUR", "GBP", "JPY", "CAD", "AUD", "CHF"}),
    (r"\b(consumer price index|cpi (?:m/?m|y/?y|inflation)|core cpi|inflation rate)\b", {"USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "XAU"}),
    (r"\b(non[- ]farm payrolls|employment situation|unemployment rate|jobs report)\b", {"USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF"}),
    (r"\b(core pce|personal consumption expenditures price index)\b", {"USD", "XAU"}),
    (r"\b(gdp (?:growth|estimate|q/?q|annualized)|gross domestic product)\b", {"USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF"}),
    (r"\b(central bank governor speech|governor .* speech|president .* speech|press conference following .* rate decision)\b", {"USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "XAU"}),
)
MEDIUM_RULES = (
    r"\b(retail sales|industrial production|pmi|purchasing managers index|trade balance|average hourly earnings|wage growth|consumer confidence|business confidence|house prices|jolts job openings)\b",
)
LOW_VALUE_RULES = (
    r"\b(college fed challenge|award|winners|former employee|enforcement action|senior financial officers|survey results|procurement|tender|agreement to join)\b",
)
SOURCE_ASSETS = {
    "federal reserve": {"USD", "XAU"},
    "bank of japan": {"JPY"},
    "bank of england": {"GBP"},
    "bank of canada": {"CAD"},
    "reserve bank of australia": {"AUD"},
    "swiss national bank": {"CHF"},
    "european central bank": {"EUR"},
}


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


def classify(title, source="", summary=""):
    text = re.sub(r"\s+", " ", f"{title} {summary}").strip().lower()
    if any(re.search(pattern, text, re.I) for pattern in LOW_VALUE_RULES):
        return "LOW", [], ["administrative_or_low_market_relevance"]

    for pattern, assets in HIGH_RULES:
        if re.search(pattern, text, re.I):
            matched = [pattern.strip("\\b")]
            return "HIGH", sorted(assets), matched

    if any(re.search(pattern, text, re.I) for pattern in MEDIUM_RULES):
        source_text = source.lower()
        assets = set()
        for institution, currencies in SOURCE_ASSETS.items():
            if institution in source_text:
                assets.update(currencies)
        return "MEDIUM", sorted(assets), ["medium_tier_macro_topic"]

    return "INFO", [], []


class NewsAgent:
    name = "News Intelligence Agent"

    def analyze(self):
        now = datetime.now(timezone.utc)
        items, errors, seen = [], [], set()
        feed_status = []

        for url in NEWS_FEEDS:
            try:
                # feedparser has built-in HTTP timeout; do not let one slow RSS host stall the full scan.
                feed = feedparser.parse(url, request_headers={"User-Agent": "ForexIntelligenceAgent/1.0"})
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
                    published = _published(entry)
                    age_hours = None if published is None else (now - published).total_seconds() / 3600
                    if age_hours is not None and (age_hours < -2 or age_hours > NEWS_MAX_AGE_HOURS):
                        continue
                    seen.add(identity)
                    summary = entry.get("summary", "")
                    impact, assets, matched = classify(title, source, summary)
                    items.append({
                        "title": title,
                        "link": link,
                        "published": published.isoformat() if published else entry.get("published", entry.get("updated", "Unknown time")),
                        "age_hours": round(age_hours, 1) if age_hours is not None else None,
                        "source": source,
                        "impact": impact,
                        "assets": assets,
                        "matched_topics": matched,
                        "summary": re.sub(r"<[^>]+>", " ", summary)[:500],
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
            "ready": any(status.get("ok") for status in feed_status),
            "items": items,
            "errors": errors,
            "feed_status": feed_status,
            "high_impact_count": high,
            "medium_impact_count": medium,
            "coverage_note": "Official RSS monitoring only. RSS headlines are not a complete economic calendar and do not establish a directional trade signal.",
        }
