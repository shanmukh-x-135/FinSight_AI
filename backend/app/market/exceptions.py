"""Market-domain exceptions, rendered by the global handlers."""

from __future__ import annotations

from fastapi import status

from app.shared.exceptions import AppException


class StockNotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    error_type = "stock_not_found"

    def __init__(self, symbol: str) -> None:
        super().__init__(f"No stock found for symbol '{symbol}'.")


class SectorNotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    error_type = "sector_not_found"

    def __init__(self, sector: str) -> None:
        super().__init__(f"No stocks found for sector '{sector}'.")


class UniverseNotInitializedError(AppException):
    status_code = status.HTTP_409_CONFLICT
    error_type = "market_universe_not_initialized"

    def __init__(self) -> None:
        super().__init__(
            "The approved NIFTY50 universe is empty. Run "
            "'python -m app.market.universe_sync' before EOD ingestion."
        )
