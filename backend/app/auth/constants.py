"""Auth/user domain constants.

Preference vocabularies live here (not in the DB as native enums) so they are
portable across Postgres and the SQLite test database and easy to extend. The
Pydantic schemas validate against these; the columns are plain strings.
"""

from __future__ import annotations

from enum import Enum


class RiskTolerance(str, Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class InvestmentHorizon(str, Enum):
    SHORT = "short"      # < 1 year
    MEDIUM = "medium"    # 1–3 years
    LONG = "long"        # > 3 years


class Market(str, Enum):
    IN = "IN"            # India (NSE/BSE) — default target market
    US = "US"


# Defaults applied to a new user's preferences at registration.
DEFAULT_RISK_TOLERANCE = RiskTolerance.MODERATE
DEFAULT_INVESTMENT_HORIZON = InvestmentHorizon.MEDIUM
DEFAULT_MARKET = Market.IN

# Token type surfaced to clients.
BEARER_TOKEN_TYPE = "bearer"
