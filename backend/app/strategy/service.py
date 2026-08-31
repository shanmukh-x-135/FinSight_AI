"""Strategy ownership, immutable versioning, and deterministic replay orchestration."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.history.models import HistoricalSession
from app.shared.time import utc_now
from app.strategy.data import BacktestDataLoader
from app.strategy.engine import BacktestEngine
from app.strategy.exceptions import (
    BacktestNotFoundError,
    BacktestReplayDriftError,
    StrategyNotFoundError,
)
from app.strategy.models import BacktestRun, Strategy
from app.strategy.repository import StrategyRepository
from app.strategy.robustness import analyze_robustness, regime_contexts
from app.strategy.schemas import (
    BacktestCreate,
    BacktestMetricsOut,
    BacktestOut,
    BacktestSummaryOut,
    BacktestTradeOut,
    EquityPointOut,
    StrategyCreate,
    StrategyDefinition,
    StrategyOut,
    StrategyUpdate,
    StrategyVersionOut,
)


class StrategyService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = StrategyRepository(db)

    async def create(self, user_id: int, payload: StrategyCreate) -> StrategyOut:
        strategy = await self.repo.create_strategy(
            user_id,
            name=payload.name,
            description=payload.description,
            definition=payload.definition.model_dump(mode="json"),
        )
        await self.db.commit()
        return self._strategy_out(strategy)

    async def list(self, user_id: int) -> list[StrategyOut]:
        return [
            self._strategy_out(item) for item in await self.repo.list_strategies(user_id)
        ]

    async def get(self, user_id: int, strategy_id: int) -> StrategyOut:
        return self._strategy_out(await self._owned(user_id, strategy_id))

    async def update(
        self, user_id: int, strategy_id: int, payload: StrategyUpdate
    ) -> StrategyOut:
        strategy = await self._owned(user_id, strategy_id)
        if payload.name is not None:
            strategy.name = payload.name
        strategy.description = payload.description
        await self.repo.add_version(strategy, payload.definition.model_dump(mode="json"))
        await self.db.commit()
        strategy = await self._owned(user_id, strategy_id)
        return self._strategy_out(strategy)

    async def archive(self, user_id: int, strategy_id: int) -> None:
        strategy = await self._owned(user_id, strategy_id)
        strategy.is_active = False
        await self.db.commit()

    async def run_backtest(
        self, user_id: int, strategy_id: int, payload: BacktestCreate
    ) -> BacktestOut:
        strategy = await self._owned(user_id, strategy_id)
        version = strategy.versions[-1]
        definition = StrategyDefinition.model_validate(version.definition)
        data = await BacktestDataLoader(self.db).load(
            start_date=payload.start_date,
            end_date=payload.end_date,
            universe_code=payload.universe_code,
            membership_mode=payload.membership_mode,
            benchmark_symbol=definition.execution.benchmark_symbol,
        )
        run = await self.repo.create_run(
            user_id=user_id,
            version=version,
            start_date=payload.start_date,
            end_date=payload.end_date,
            universe_code=payload.universe_code,
            membership_mode=payload.membership_mode,
            membership_disclaimer=data.membership_disclaimer,
            benchmark_symbol=definition.execution.benchmark_symbol,
        )
        await self.db.commit()
        result = BacktestEngine().run(definition, list(data.bars), list(data.benchmark))
        run = await self.db.get(BacktestRun, run.id)
        assert run is not None
        await self.repo.complete_run(run, result, utc_now())
        await self.db.commit()
        return self._backtest_out(await self._owned_run(user_id, run.id))

    async def get_backtest(self, user_id: int, run_id: int) -> BacktestOut:
        return self._backtest_out(await self._owned_run(user_id, run_id))

    async def analyze_backtest(self, user_id: int, run_id: int) -> dict:
        run = await self._owned_run(user_id, run_id)
        definition = StrategyDefinition.model_validate(run.definition_snapshot)
        data = await BacktestDataLoader(self.db).load(
            start_date=run.start_date,
            end_date=run.end_date,
            universe_code=run.universe_code,
            membership_mode=run.membership_mode,
            benchmark_symbol=run.benchmark_symbol,
        )
        bars, benchmark = list(data.bars), list(data.benchmark)
        baseline = BacktestEngine().run(definition, bars, benchmark)
        if baseline.result_hash != run.result_hash:
            raise BacktestReplayDriftError()
        history_result = await self.db.execute(
            select(HistoricalSession.date, HistoricalSession.feature_vector).where(
                HistoricalSession.date >= run.start_date,
                HistoricalSession.date <= run.end_date,
                HistoricalSession.feature_version == "market_regime_v1",
            )
        )
        history = {day: features for day, features in history_result.all()}
        analysis = analyze_robustness(
            definition, bars, benchmark, baseline, regime_contexts(bars, history)
        )
        await self.repo.save_robustness(run, analysis)
        await self.db.commit()
        return analysis

    async def list_backtests(
        self, user_id: int, strategy_id: int
    ) -> list[BacktestSummaryOut]:
        await self._owned(user_id, strategy_id)
        return [
            BacktestSummaryOut(
                id=run.id,
                strategy_version=run.strategy_version.version,
                status=run.status,
                start_date=run.start_date,
                end_date=run.end_date,
                universe_code=run.universe_code,
                membership_mode=run.membership_mode,
                result_hash=run.result_hash,
                created_at=run.created_at,
                metrics=self._metrics(run),
            )
            for run in await self.repo.list_runs(user_id, strategy_id)
        ]

    async def _owned(self, user_id: int, strategy_id: int) -> Strategy:
        strategy = await self.repo.get_strategy(user_id, strategy_id)
        if strategy is None:
            raise StrategyNotFoundError()
        return strategy

    async def _owned_run(self, user_id: int, run_id: int) -> BacktestRun:
        run = await self.repo.get_run(user_id, run_id)
        if run is None:
            raise BacktestNotFoundError()
        return run

    @staticmethod
    def _strategy_out(strategy: Strategy) -> StrategyOut:
        latest = strategy.versions[-1]
        return StrategyOut(
            id=strategy.id,
            name=strategy.name,
            description=strategy.description,
            is_active=strategy.is_active,
            created_at=strategy.created_at,
            updated_at=strategy.updated_at,
            latest_version=StrategyVersionOut(
                id=latest.id,
                version=latest.version,
                definition=StrategyDefinition.model_validate(latest.definition),
                created_at=latest.created_at,
            ),
        )

    @staticmethod
    def _metrics(run: BacktestRun) -> BacktestMetricsOut | None:
        if run.status != "completed":
            return None
        values = {metric.name: metric.value for metric in run.metrics}
        return BacktestMetricsOut.model_validate(values)

    @classmethod
    def _backtest_out(cls, run: BacktestRun) -> BacktestOut:
        return BacktestOut(
            id=run.id,
            strategy_id=run.strategy_version.strategy_id,
            strategy_version_id=run.strategy_version_id,
            strategy_version=run.strategy_version.version,
            status=run.status,
            start_date=run.start_date,
            end_date=run.end_date,
            universe_code=run.universe_code,
            membership_mode=run.membership_mode,
            membership_disclaimer=run.membership_disclaimer,
            benchmark_symbol=run.benchmark_symbol,
            result_hash=run.result_hash,
            created_at=run.created_at,
            completed_at=run.completed_at,
            metrics=cls._metrics(run),
            equity_curve=[
                EquityPointOut.model_validate(item) for item in run.equity_curve
            ],
            trades=[
                BacktestTradeOut(
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
                for trade in run.trades
            ],
            robustness_analysis=run.robustness_analysis,
        )
