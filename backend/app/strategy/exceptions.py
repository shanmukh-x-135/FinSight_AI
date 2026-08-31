"""Stable strategy/backtest application errors."""

from fastapi import status

from app.shared.exceptions import AppException


class StrategyNotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    error_type = "strategy_not_found"

    def __init__(self) -> None:
        super().__init__("Strategy not found.")


class BacktestNotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    error_type = "backtest_not_found"

    def __init__(self) -> None:
        super().__init__("Backtest run not found.")


class BacktestDataError(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_type = "backtest_data_unavailable"

    def __init__(self, message: str) -> None:
        super().__init__(message)


class BacktestReplayDriftError(AppException):
    status_code = status.HTTP_409_CONFLICT
    error_type = "backtest_replay_drift"

    def __init__(self) -> None:
        super().__init__(
            "The source data or current membership has changed since this replay. "
            "Run a new backtest before robustness analysis."
        )
