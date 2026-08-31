"""User-scoped persistence for strategies and immutable replay results."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.shared.time import utc_now
from app.strategy.engine import BacktestResult
from app.strategy.models import (
    BacktestMetric,
    BacktestRun,
    BacktestTrade,
    Strategy,
    StrategyVersion,
)


class StrategyRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_strategy(
        self,
        user_id: int,
        *,
        name: str,
        description: str | None,
        definition: dict,
    ) -> Strategy:
        strategy = Strategy(user_id=user_id, name=name, description=description)
        self.db.add(strategy)
        await self.db.flush()
        self.db.add(
            StrategyVersion(strategy_id=strategy.id, version=1, definition=definition)
        )
        await self.db.flush()
        return await self.get_strategy(user_id, strategy.id, include_inactive=True)  # type: ignore[return-value]

    async def list_strategies(self, user_id: int) -> list[Strategy]:
        result = await self.db.execute(
            select(Strategy)
            .where(Strategy.user_id == user_id, Strategy.is_active.is_(True))
            .options(selectinload(Strategy.versions))
            .order_by(Strategy.updated_at.desc(), Strategy.id.desc())
        )
        return list(result.scalars().unique())

    async def get_strategy(
        self, user_id: int, strategy_id: int, *, include_inactive: bool = False
    ) -> Strategy | None:
        stmt = (
            select(Strategy)
            .where(Strategy.id == strategy_id, Strategy.user_id == user_id)
            .options(selectinload(Strategy.versions))
            .execution_options(populate_existing=True)
        )
        if not include_inactive:
            stmt = stmt.where(Strategy.is_active.is_(True))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def add_version(self, strategy: Strategy, definition: dict) -> StrategyVersion:
        version = StrategyVersion(
            strategy_id=strategy.id,
            version=max(item.version for item in strategy.versions) + 1,
            definition=definition,
        )
        self.db.add(version)
        strategy.updated_at = utc_now()
        await self.db.flush()
        return version

    async def create_run(
        self,
        *,
        user_id: int,
        version: StrategyVersion,
        start_date: date,
        end_date: date,
        universe_code: str,
        membership_mode: str,
        membership_disclaimer: str,
        benchmark_symbol: str,
    ) -> BacktestRun:
        run = BacktestRun(
            user_id=user_id,
            strategy_version_id=version.id,
            status="running",
            start_date=start_date,
            end_date=end_date,
            universe_code=universe_code,
            membership_mode=membership_mode,
            membership_disclaimer=membership_disclaimer,
            benchmark_symbol=benchmark_symbol,
            definition_snapshot=version.definition,
            equity_curve=[],
        )
        self.db.add(run)
        await self.db.flush()
        return run

    async def complete_run(
        self, run: BacktestRun, result: BacktestResult, completed_at: datetime
    ) -> None:
        run.status = "completed"
        run.completed_at = completed_at
        run.result_hash = result.result_hash
        run.equity_curve = [
            {
                "date": point.date.isoformat(),
                "equity": point.equity,
                "benchmark_equity": point.benchmark_equity,
                "drawdown_percent": point.drawdown_percent,
            }
            for point in result.equity_curve
        ]
        self.db.add_all(
            BacktestTrade(
                run_id=run.id,
                stock_id=trade.stock_id,
                symbol=trade.symbol,
                entry_signal_date=trade.entry_signal_date,
                entry_date=trade.entry_date,
                entry_price=trade.entry_price,
                exit_signal_date=trade.exit_signal_date,
                exit_date=trade.exit_date,
                exit_price=trade.exit_price,
                quantity=trade.quantity,
                gross_pnl=trade.gross_pnl,
                net_pnl=trade.net_pnl,
                return_percent=trade.return_percent,
                holding_sessions=trade.holding_sessions,
                exit_reason=trade.exit_reason,
                transaction_cost=trade.transaction_cost,
            )
            for trade in result.trades
        )
        self.db.add_all(
            BacktestMetric(run_id=run.id, name=name, value=value)
            for name, value in asdict(result.metrics).items()
        )

    async def fail_run(self, run_id: int, *, error: str, completed_at: datetime) -> None:
        run = await self.db.get(BacktestRun, run_id)
        if run is not None:
            run.status = "failed"
            run.error_summary = error[:4000]
            run.completed_at = completed_at

    async def save_robustness(self, run: BacktestRun, analysis: dict) -> None:
        run.robustness_analysis = analysis
        await self.db.flush()

    async def get_run(self, user_id: int, run_id: int) -> BacktestRun | None:
        result = await self.db.execute(
            select(BacktestRun)
            .where(BacktestRun.id == run_id, BacktestRun.user_id == user_id)
            .options(
                joinedload(BacktestRun.strategy_version).joinedload(
                    StrategyVersion.strategy
                ),
                selectinload(BacktestRun.trades),
                selectinload(BacktestRun.metrics),
            )
        )
        return result.scalar_one_or_none()

    async def list_runs(self, user_id: int, strategy_id: int) -> list[BacktestRun]:
        result = await self.db.execute(
            select(BacktestRun)
            .join(StrategyVersion, StrategyVersion.id == BacktestRun.strategy_version_id)
            .join(Strategy, Strategy.id == StrategyVersion.strategy_id)
            .where(
                BacktestRun.user_id == user_id,
                Strategy.id == strategy_id,
                Strategy.user_id == user_id,
            )
            .options(
                joinedload(BacktestRun.strategy_version).joinedload(
                    StrategyVersion.strategy
                ),
                selectinload(BacktestRun.trades),
                selectinload(BacktestRun.metrics),
            )
            .order_by(BacktestRun.created_at.desc(), BacktestRun.id.desc())
        )
        return list(result.scalars().unique())
