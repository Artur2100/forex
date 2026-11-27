SYMBOLS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "JPY=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CAD": "CAD=X",
    "USD/CHF": "CHF=X",
    # Spot XAU/USD first; COMEX GC futures are fallback proxy only.
    "XAU/USD": ["XAUUSD=X", "GC=F"],
}

TIMEFRAMES = {
    "D1": {"interval": "1d", "period": "2y"},
    "H1": {"interval": "1h", "period": "60d"},
}

EMA_FAST = 20
EMA_SLOW = 50
RSI_PERIOD = 14
ATR_PERIOD = 14

# Official primary sources. RSS is a news monitor, not an economic calendar.
NEWS_FEEDS = [
    "https://www.federalreserve.gov/feeds/press_all.xml",
    "https://www.ecb.europa.eu/rss/press.html",
    "https://www.bankofcanada.ca/content_type/press-releases/feed/",
    "https://www.rba.gov.au/rss/rss-cb-media-releases.xml",
    "https://www.bankofengland.co.uk/rss/news",
    "https://www.boj.or.jp/en/rss/whatsnew.xml",
    "https://www.bls.gov/feed/news_release/empsit.rss",
    "https://www.bls.gov/feed/news_release/cpi.rss",
]

NEWS_MAX_AGE_HOURS = 96
NEWS_MAX_ITEMS_PER_FEED = 20
NEWS_MAX_ITEMS = 40

# ShowMyTrades public calendar API: no key; documented 15-minute cache.
CALENDAR_URL = "https://showmytrades.com/api/public/calendar/v1"
CALENDAR_FALLBACK_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CALENDAR_CURRENCIES = ("USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF")
CALENDAR_DAYS_AHEAD = 7

# Enable final Telegram signals; each scan still fails closed unless calendar and RSS sources are available.
ECONOMIC_CALENDAR_VALIDATED = True
FINAL_SIGNALS_ENABLED = True
PREALERTS_ENABLED = True
MIN_TREND_ALIGNMENT = 2
ATR_STOP_MULTIPLIER = 1.5
TARGET_R_MULTIPLE = 3.0
RISK_PER_TRADE_PCT = 1.0
