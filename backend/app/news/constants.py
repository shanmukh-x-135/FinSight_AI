"""News-domain constants: default RSS feeds and company-tagging config."""

from __future__ import annotations

# Free Indian financial-news RSS feeds (no API key). Configurable per deployment.
DEFAULT_FEEDS: tuple[str, ...] = (
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "https://www.moneycontrol.com/rss/business.xml",
    "https://www.business-standard.com/rss/markets-106.rss",
    "https://www.livemint.com/rss/markets",
)

# Minimum alias length — avoids short tickers colliding with common words.
MIN_ALIAS_LEN = 3

# Generic tokens excluded from company aliases to reduce false-positive tags
# (e.g. tagging every "bank" story to one bank).
ALIAS_STOPWORDS = frozenset(
    """LTD LIMITED INC CORP CORPORATION CO COMPANY INDIA INDIAN THE AND FOR OF NEW
    SERV SERVICE SERVICES INDUSTRIES INDUSTRY ENTERPRISE ENTERPRISES GROUP HOLDING
    HOLDINGS BANK FINANCE FINANCIAL INTERNATIONAL GLOBAL
    TATA ADANI BAJAJ BIRLA MAHINDRA JINDAL GODREJ HERO POWER MOTORS STEEL
    RELIANCE""".split()
    # ^ conglomerate group prefixes span many listed entities (Tata Power, Tata
    # Steel, TCS, …), so matching on the group name over-tags. Match on the
    # company-specific token instead (e.g. CONSULTANCY for TCS).
)

# Reviewed public-facing names used by financial publishers for current NIFTY 50
# constituents.  The ticker/full-name fallback in ``build_aliases`` keeps the
# linker dynamic when membership changes; these aliases cover common shortened
# names without falling back to unsafe generic tokens such as ``LIFE``, ``OIL``
# or ``TECH``.
COMPANY_ALIASES: dict[str, tuple[str, ...]] = {
    "ADANIENT": ("ADANI ENTERPRISES",),
    "ADANIPORTS": ("ADANI PORTS", "ADANI PORTS AND SPECIAL ECONOMIC ZONE"),
    "APOLLOHOSP": ("APOLLO HOSPITALS",),
    "ASIANPAINT": ("ASIAN PAINTS",),
    "AXISBANK": ("AXIS BANK",),
    "BAJAJ-AUTO": ("BAJAJ AUTO",),
    "BAJAJFINSV": ("BAJAJ FINSERV",),
    "BAJFINANCE": ("BAJAJ FINANCE",),
    "BEL": ("BHARAT ELECTRONICS",),
    "BHARTIARTL": ("BHARTI AIRTEL", "AIRTEL"),
    "CIPLA": ("CIPLA",),
    "COALINDIA": ("COAL INDIA",),
    "DRREDDY": ("DR REDDY", "DR REDDYS", "DR REDDYS LABORATORIES"),
    "EICHERMOT": ("EICHER MOTORS",),
    "ETERNAL": ("ETERNAL", "ZOMATO"),
    "GRASIM": ("GRASIM",),
    "HCLTECH": ("HCL TECH", "HCL TECHNOLOGIES"),
    "HDFCBANK": ("HDFC BANK",),
    "HDFCLIFE": ("HDFC LIFE",),
    "HINDALCO": ("HINDALCO",),
    "HINDUNILVR": ("HINDUSTAN UNILEVER", "HUL"),
    "ICICIBANK": ("ICICI BANK",),
    "INDIGO": ("INTERGLOBE AVIATION", "INDIGO AIRLINES"),
    "INFY": ("INFOSYS",),
    "ITC": ("ITC",),
    "JIOFIN": ("JIO FINANCIAL", "JIO FINANCIAL SERVICES"),
    "JSWSTEEL": ("JSW STEEL",),
    "KOTAKBANK": ("KOTAK BANK", "KOTAK MAHINDRA BANK"),
    "LT": ("LARSEN AND TOUBRO", "LARSEN TOUBRO"),
    "M&M": ("MAHINDRA AND MAHINDRA",),
    "MARUTI": ("MARUTI", "MARUTI SUZUKI"),
    "MAXHEALTH": ("MAX HEALTHCARE",),
    "NESTLEIND": ("NESTLE INDIA",),
    "NTPC": ("NTPC",),
    "ONGC": ("ONGC", "OIL AND NATURAL GAS CORPORATION"),
    "POWERGRID": ("POWER GRID", "POWERGRID"),
    "RELIANCE": ("RELIANCE INDUSTRIES",),
    "SBILIFE": ("SBI LIFE",),
    "SBIN": ("SBI", "STATE BANK OF INDIA"),
    "SHRIRAMFIN": ("SHRIRAM FINANCE",),
    "SUNPHARMA": ("SUN PHARMA", "SUN PHARMACEUTICAL"),
    "TATACONSUM": ("TATA CONSUMER", "TATA CONSUMER PRODUCTS"),
    "TATASTEEL": ("TATA STEEL",),
    "TCS": ("TCS", "TATA CONSULTANCY SERVICES"),
    "TECHM": ("TECH MAHINDRA",),
    "TITAN": ("TITAN", "TITAN COMPANY"),
    "TMPV": ("TMPV", "TATA MOTORS", "TATA MOTORS PASSENGER VEHICLES"),
    "TRENT": ("TRENT",),
    "ULTRACEMCO": ("ULTRATECH CEMENT",),
    "WIPRO": ("WIPRO",),
}
