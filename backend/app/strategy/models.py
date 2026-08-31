"""ORM persistence for versioned strategies and reproducible backtest results."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.database import Base
from app.shared.time import utc_now


class Strategy(Base):
    __tablename__ = "strategies"
    __table_args__ = (Index("ix_strategies_user_updated", "user_id", "updated_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    versions: Mapped[list["StrategyVersion"]] = relationship(
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by="StrategyVersion.version",
    )


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"
    __table_args__ = (
        UniqueConstraint("strategy_id", "version", name="uq_strategy_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    strategy: Mapped[Strategy] = relationship(back_populates="versions")
    backtest_runs: Mapped[list["BacktestRun"]] = relationship(
        back_populates="strategy_version", cascade="all, delete-orphan"
    )


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    __table_args__ = (
        Index("ix_backtest_runs_user_created", "user_id", "created_at"),
        Index("ix_backtest_runs_result_hash", "result_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    strategy_version_id: Mapped[int] = mapped_column(
        ForeignKey("strategy_versions.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    universe_code: Mapped[str] = mapped_column(String(32), nullable=False)
    membership_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    membership_disclaimer: Mapped[str] = mapped_column(String(500), nullable=False)
    benchmark_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    definition_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    equity_curve: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    robustness_analysis: Mapped[dict | None] = mapped_column(JSON)
    result_hash: Mapped[str | None] = mapped_column(String(64))
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    strategy_version: Mapped[StrategyVersion] = relationship(
        back_populates="backtest_runs"
    )
    trades: Mapped[list["BacktestTrade"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="BacktestTrade.id"
    )
    metrics: Mapped[list["BacktestMetric"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"
    __table_args__ = (Index("ix_backtest_trades_run_entry", "run_id", "entry_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False
    )
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="RESTRICT"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    entry_signal_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_signal_date: Mapped[date | None] = mapped_column(Date)
    exit_date: Mapped[date] = mapped_column(Date, nullable=False)
    exit_price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    gross_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    net_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    return_percent: Mapped[float] = mapped_column(Float, nullable=False)
    holding_sessions: Mapped[int] = mapped_column(Integer, nullable=False)
    exit_reason: Mapped[str] = mapped_column(String(40), nullable=False)
    transaction_cost: Mapped[float] = mapped_column(Float, nullable=False)
    run: Mapped[BacktestRun] = relationship(back_populates="trades")


class BacktestMetric(Base):
    __tablename__ = "backtest_metrics"
    __table_args__ = (
        UniqueConstraint("run_id", "name", name="uq_backtest_metric_run_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("backtest_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float | None] = mapped_column(Float)
    run: Mapped[BacktestRun] = relationship(back_populates="metrics")
