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
    TATA ADANI BAJAJ BIRLA MAHINDRA JINDAL GODREJ HERO POWER MOTORS STEEL""".split()
    # ^ conglomerate group prefixes span many listed entities (Tata Power, Tata
    # Steel, TCS, …), so matching on the group name over-tags. Match on the
    # company-specific token instead (e.g. CONSULTANCY for TCS).
)
