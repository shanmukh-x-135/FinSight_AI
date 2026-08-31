"""ORM models for the market domain: Stock, DailyPrice, Fundamentals, Indicator.

Design doc §6.3 (Market domain). ``daily_prices`` is indexed on
``(stock_id, date)`` because it is queried by date range constantly. Column
types are portable across Postgres and the SQLite test DB (``Date`` for trading
dates avoids timezone ambiguity).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
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
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.database import Base
from app.shared.time import utc_now


class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, nullable=False
    )
    # ``symbol`` remains the price-provider ticker for backward compatibility.
    # ``exchange_symbol`` is the canonical constituent identifier supplied by NSE.
    exchange_symbol: Mapped[str | None] = mapped_column(String(32), index=True)
    data_provider: Mapped[str] = mapped_column(
        String(32), default="yahoo", server_default="yahoo", nullable=False
    )
    name: Mapped[str | None] = mapped_column(String(128))
    sector: Mapped[str | None] = mapped_column(String(64), index=True)
    industry: Mapped[str | None] = mapped_column(String(128))
    exchange: Mapped[str | None] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    # Frozen Phase-10C compatibility boundary. Universe sync does not expand
    # historical feature reconstruction until membership-aware Phase 10D work.
    history_eligible: Mapped[bool] = mapped_column(
        default=False, server_default=false(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    # Watermark for periodic full-window reconciliation of adjusted provider data.
    last_full_price_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    daily_prices: Mapped[list["DailyPrice"]] = relationship(
        back_populates="stock", cascade="all, delete-orphan"
    )
    indicators: Mapped[list["Indicator"]] = relationship(
        back_populates="stock", cascade="all, delete-orphan"
    )
    fundamentals: Mapped["Fundamentals | None"] = relationship(
        back_populates="stock", uselist=False, cascade="all, delete-orphan"
    )
    index_memberships: Mapped[list["IndexMembership"]] = relationship(
        back_populates="stock", cascade="all, delete-orphan"
    )
    symbol_aliases: Mapped[list["StockSymbolAlias"]] = relationship(
        back_populates="stock",
        cascade="all, delete-orphan",
        foreign_keys="StockSymbolAlias.stock_id",
    )


class IndexMembership(Base):
    """Effective-dated membership; an open interval is currently approved."""

    __tablename__ = "index_memberships"
    __table_args__ = (
        UniqueConstraint(
            "stock_id", "index_code", "valid_from", name="uq_membership_stock_index_from"
        ),
        Index("ix_membership_active", "index_code", "valid_to"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="RESTRICT"), nullable=False
    )
    index_code: Mapped[str] = mapped_column(String(32), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    stock: Mapped[Stock] = relationship(back_populates="index_memberships")


class UniverseSnapshot(Base):
    """Validated last-known-good provider payload used for explicit fallback."""

    __tablename__ = "universe_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "index_code",
            "source",
            "snapshot_date",
            "checksum",
            name="uq_universe_snapshot_identity",
        ),
        Index("ix_universe_snapshot_latest", "index_code", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    index_code: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(512))
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    constituent_count: Mapped[int] = mapped_column(Integer, nullable=False)
    constituents: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)


class UniverseSyncRun(Base):
    """One observable synchronization attempt."""

    __tablename__ = "universe_sync_runs"
    __table_args__ = (
        Index("ix_universe_sync_runs_index_started", "index_code", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    index_code: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    normalized_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    added_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    removed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unchanged_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_validation_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text)

    items: Mapped[list["UniverseSyncItem"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class UniverseSyncItem(Base):
    """Per-candidate resolution/validation audit, including quarantine failures."""

    __tablename__ = "universe_sync_items"
    __table_args__ = (
        UniqueConstraint("run_id", "exchange_symbol", name="uq_sync_item_run_symbol"),
        Index("ix_sync_item_run_status", "run_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("universe_sync_runs.id", ondelete="CASCADE"), nullable=False
    )
    stock_id: Mapped[int | None] = mapped_column(
        ForeignKey("stocks.id", ondelete="SET NULL")
    )
    exchange_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_symbol: Mapped[str | None] = mapped_column(String(32))
    company_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    validation_status: Mapped[str | None] = mapped_column(String(32))
    validation_error: Mapped[str | None] = mapped_column(Text)

    run: Mapped[UniverseSyncRun] = relationship(back_populates="items")


class StockSymbolAlias(Base):
    """Explicit historical alias/replacement metadata for a current stock."""

    __tablename__ = "stock_symbol_aliases"
    __table_args__ = (
        UniqueConstraint(
            "exchange", "alias_exchange_symbol", name="uq_stock_alias_exchange_symbol"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )
    retired_stock_id: Mapped[int | None] = mapped_column(
        ForeignKey("stocks.id", ondelete="SET NULL")
    )
    exchange: Mapped[str] = mapped_column(String(16), nullable=False)
    alias_exchange_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    alias_provider_symbol: Mapped[str | None] = mapped_column(String(32))
    alias_type: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    stock: Mapped[Stock] = relationship(
        back_populates="symbol_aliases", foreign_keys=[stock_id]
    )


class DailyPrice(Base):
    __tablename__ = "daily_prices"
    __table_args__ = (
        UniqueConstraint("stock_id", "date", name="uq_daily_prices_stock_date"),
        Index("ix_daily_prices_stock_date", "stock_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    stock: Mapped["Stock"] = relationship(back_populates="daily_prices")


class Indicator(Base):
    __tablename__ = "indicators"
    __table_args__ = (
        UniqueConstraint("stock_id", "date", name="uq_indicators_stock_date"),
        Index("ix_indicators_stock_date", "stock_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)

    rsi_14: Mapped[float | None] = mapped_column(Float)
    ema_20: Mapped[float | None] = mapped_column(Float)
    ema_50: Mapped[float | None] = mapped_column(Float)
    macd: Mapped[float | None] = mapped_column(Float)
    macd_signal: Mapped[float | None] = mapped_column(Float)
    macd_histogram: Mapped[float | None] = mapped_column(Float)
    bb_upper: Mapped[float | None] = mapped_column(Float)
    bb_middle: Mapped[float | None] = mapped_column(Float)
    bb_lower: Mapped[float | None] = mapped_column(Float)
    atr_14: Mapped[float | None] = mapped_column(Float)

    stock: Mapped["Stock"] = relationship(back_populates="indicators")


class Fundamentals(Base):
    __tablename__ = "fundamentals"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    market_cap: Mapped[int | None] = mapped_column(BigInteger)
    pe_ratio: Mapped[float | None] = mapped_column(Float)
    eps: Mapped[float | None] = mapped_column(Float)
    dividend_yield: Mapped[float | None] = mapped_column(Float)
    week52_high: Mapped[float | None] = mapped_column(Float)
    week52_low: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    stock: Mapped["Stock"] = relationship(back_populates="fundamentals")
