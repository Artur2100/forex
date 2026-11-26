import feedparser
from .config import NEWS_FEEDS

class NewsAgent:
    name = "News Intelligence Agent"

    def analyze(self):
        items = []
        errors = []
        for url in NEWS_FEEDS:
            try:
                feed = feedparser.parse(url)
                if getattr(feed, "bozo", False) and not feed.entries:
                    raise RuntimeError(str(feed.bozo_exception))
                for entry in feed.entries[:10]:
                    items.append({
                        "title": entry.get("title", "Untitled"),
                        "link": entry.get("link", ""),
                        "published": entry.get("published", entry.get("updated", "Unknown time")),
                        "source": feed.feed.get("title", url),
                    })
            except Exception as exc:
                errors.append(f"{url}: {exc}")
        return {
            "ready": bool(NEWS_FEEDS) and not errors,
            "items": items[:30],
            "errors": errors,
            "coverage_note": "RSS headlines are partial coverage; no verified event calendar is connected."
        }
