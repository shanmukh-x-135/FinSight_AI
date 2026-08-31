"""Authenticated strategy versioning and deterministic backtest APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.shared.database import get_db
from app.shared.response import envelope
from app.strategy.schemas import BacktestCreate, StrategyCreate, StrategyUpdate
from app.strategy.service import StrategyService

strategy_router = APIRouter(prefix="/strategies", tags=["strategies"])
backtest_router = APIRouter(prefix="/backtests", tags=["backtests"])


@strategy_router.post("", status_code=status.HTTP_201_CREATED, summary="Create strategy")
async def create_strategy(
    payload: StrategyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return envelope(
        data=await StrategyService(db).create(user.id, payload),
        message="Strategy created.",
    )


@strategy_router.get("", summary="List active strategies")
async def list_strategies(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return envelope(data=await StrategyService(db).list(user.id))


@strategy_router.get("/{strategy_id}", summary="Get latest strategy version")
async def get_strategy(
    strategy_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return envelope(data=await StrategyService(db).get(user.id, strategy_id))


@strategy_router.put("/{strategy_id}", summary="Create a new immutable version")
async def update_strategy(
    strategy_id: int,
    payload: StrategyUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return envelope(
        data=await StrategyService(db).update(user.id, strategy_id, payload),
        message="Strategy version created.",
    )


@strategy_router.delete("/{strategy_id}", summary="Archive a strategy")
async def archive_strategy(
    strategy_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await StrategyService(db).archive(user.id, strategy_id)
    return envelope(message="Strategy archived.")


@strategy_router.post(
    "/{strategy_id}/backtests",
    status_code=status.HTTP_201_CREATED,
    summary="Run deterministic close-signal/next-session replay",
)
async def run_backtest(
    strategy_id: int,
    payload: BacktestCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return envelope(
        data=await StrategyService(db).run_backtest(user.id, strategy_id, payload),
        message="Backtest completed.",
    )


@strategy_router.get("/{strategy_id}/backtests", summary="List strategy backtests")
async def list_backtests(
    strategy_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return envelope(data=await StrategyService(db).list_backtests(user.id, strategy_id))


@backtest_router.get("/{run_id}", summary="Get reproducible backtest results")
async def get_backtest(
    run_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return envelope(data=await StrategyService(db).get_backtest(user.id, run_id))


@backtest_router.post(
    "/{run_id}/robustness",
    summary="Analyze regimes, signal outcomes, OOS, and sensitivity",
)
async def analyze_backtest(
    run_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return envelope(
        data=await StrategyService(db).analyze_backtest(user.id, run_id),
        message="Robustness analysis completed.",
    )
