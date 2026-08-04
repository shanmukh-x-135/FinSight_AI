"""Market-domain constants: the default stock universe and indicator periods."""

from __future__ import annotations

# Default universe: a spread of large-cap NSE names across sectors, so the
# sector/breadth endpoints are meaningful. yfinance uses the ``.NS`` suffix for
# NSE listings. Configurable — the ingestion job accepts an explicit list too.
DEFAULT_UNIVERSE: tuple[str, ...] = (
    "RELIANCE.NS",
    "TCS.NS",
    "INFY.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "SBIN.NS",
    "ITC.NS",
    "LT.NS",
    "HINDUNILVR.NS",
    "BHARTIARTL.NS",
    "KOTAKBANK.NS",
    "AXISBANK.NS",
    "MARUTI.NS",
    "SUNPHARMA.NS",
    "TATAMOTORS.NS",
)

DEFAULT_EXCHANGE = "NSE"

# Cross-asset macro proxies persisted as inactive ``Stock`` rows so the existing
# validated OHLC pipeline can be reused without including them in stock breadth,
# sectors, portfolios, or watchlists. Values are converted to daily returns by
# the historical feature-engineering pipeline.
MACRO_PROXIES: dict[str, tuple[str, str]] = {
    "INR=X": ("USD/INR", "Currency"),
    "CL=F": ("WTI Crude Oil", "Commodity"),
    "GC=F": ("Gold", "Commodity"),
    "^TNX": ("US 10-Year Treasury Yield", "Rates"),
}

MACRO_FEATURE_SYMBOLS: dict[str, str] = {
    "usd_inr_return": "INR=X",
    "crude_oil_return": "CL=F",
    "gold_return": "GC=F",
    "us_10y_yield_return": "^TNX",
}

# How much daily history to pull per ingestion (enough to warm up EMA-50 / BB-20).
HISTORY_PERIOD = "1y"

# Indicator periods (design doc §5.6 / §4.3).
RSI_PERIOD = 14
EMA_SHORT_PERIOD = 20
EMA_LONG_PERIOD = 50
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_NUM_STD = 2.0
ATR_PERIOD = 14
