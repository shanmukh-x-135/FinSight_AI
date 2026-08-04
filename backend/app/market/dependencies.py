"""Market dependencies.

``get_market_client`` provides the market data provider to the ingestion
endpoint. Isolating it behind a dependency lets tests inject a fake client so no
network call is made during testing.
"""

from __future__ import annotations

from app.shared.clients.economic_calendar import (
    EconomicCalendarClient,
    TradingEconomicsCalendarClient,
)
from app.shared.clients.market_data import MarketDataClient
from app.shared.clients.yfinance_client import build_default_client
from config.settings import settings


def get_market_client() -> MarketDataClient:
    return build_default_client()


def get_economic_calendar_client() -> EconomicCalendarClient | None:
    if not settings.trading_economics_api_key:
        return None
    return TradingEconomicsCalendarClient(
        settings.trading_economics_api_key,
        settings.economic_calendar_timeout_seconds,
    )
