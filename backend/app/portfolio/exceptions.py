"""Portfolio-domain exceptions.

Not-found and not-owned both surface as 404 (never another user's data, and no
existence leak) — ownership is enforced by scoping every query to the user.
"""

from __future__ import annotations

from fastapi import status

from app.shared.exceptions import AppException, BusinessException


class PortfolioNotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    error_type = "portfolio_not_found"

    def __init__(self) -> None:
        super().__init__("Portfolio not found.")


class HoldingNotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    error_type = "holding_not_found"

    def __init__(self) -> None:
        super().__init__("Holding not found.")


class WatchlistItemNotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    error_type = "watchlist_item_not_found"

    def __init__(self) -> None:
        super().__init__("Watchlist item not found.")


class StockNotTrackedError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    error_type = "stock_not_tracked"

    def __init__(self, symbol: str) -> None:
        super().__init__(
            f"Stock '{symbol}' is not tracked. Ingest it via the market module first."
        )


class DuplicateHoldingError(BusinessException):
    error_type = "duplicate_holding"

    def __init__(self, symbol: str) -> None:
        super().__init__(f"Holding for '{symbol}' already exists in this portfolio.")


class DuplicateWatchlistItemError(BusinessException):
    error_type = "duplicate_watchlist_item"

    def __init__(self, symbol: str) -> None:
        super().__init__(f"'{symbol}' is already in your watchlist.")
