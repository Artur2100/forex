SYMBOLS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "JPY=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CAD": "CAD=X",
    "USD/CHF": "CHF=X",
    # Yahoo ticker is COMEX gold futures, not spot XAU/USD.
    "XAU/USD (GC futures proxy)": "GC=F",
}

TIMEFRAMES = {
    "D1": {"interval": "1d", "period": "2y"},
    # Yahoo Finance limits intraday history; 60 days is a safer H1 request.
    "H1": {"interval": "1h", "period": "60d"},
}

EMA_FAST = 20
EMA_SLOW = 50
RSI_PERIOD = 14
ATR_PERIOD = 14

NEWS_FEEDS = [
    "https://www.federalreserve.gov/feeds/press_all.xml",
    "https://www.ecb.europa.eu/rss/press.html",
    "https://www.bankofcanada.ca/content_type/press-releases/feed/",
    "https://www.rba.gov.au/rss/rss-cb-media-releases.xml",
]

# Final signal gate stays closed until calendar provider, backtest and forward-test are approved.
ECONOMIC_CALENDAR_VALIDATED = False
FINAL_SIGNALS_ENABLED = False
PREALERTS_ENABLED = True
MIN_TREND_ALIGNMENT = 2
ATR_STOP_MULTIPLIER = 1.5
TARGET_R_MULTIPLE = 3.0
RISK_PER_TRADE_PCT = 1.0
