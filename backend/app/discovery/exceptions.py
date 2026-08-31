"""Stable discovery errors."""

from fastapi import status

from app.shared.exceptions import AppException


class UnsupportedScreenerQueryError(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_type = "unsupported_screener_query"

    def __init__(self, detail: list[str] | None = None) -> None:
        super().__init__(
            "The screener query contains unsupported or unrecognized fields.",
            detail={
                "unsupported": detail or [],
                "supported_fields": [
                    "universe",
                    "sector",
                    "price change",
                    "RSI",
                    "EMA20/EMA50",
                    "MACD",
                    "volume",
                    "P/E",
                    "profitability (EPS)",
                    "news sentiment",
                    "signal state",
                    "regime fit",
                ],
            },
        )


class SavedScreenNotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    error_type = "saved_screen_not_found"

    def __init__(self) -> None:
        super().__init__("Saved screen not found.")
