"""Persistence operations for effective-dated universe synchronization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.models import (
    IndexMembership,
    Stock,
    StockSymbolAlias,
    UniverseSnapshot,
    UniverseSyncItem,
    UniverseSyncRun,
)
from app.market.repository import MarketRepository
from app.market.symbol_resolver import ResolvedSymbol
from app.market.universe_provider import (
    UniverseConstituent,
    UniverseProviderSnapshot,
)
from app.shared.upsert import conflict_insert


@dataclass(frozen=True)
class ActiveMembership:
    membership: IndexMembership
    stock: Stock


class UniverseRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.market = MarketRepository(db)

    async def create_run(
        self, *, index_code: str, source: str, dry_run: bool
    ) -> UniverseSyncRun:
        run = UniverseSyncRun(
            index_code=index_code,
            source=source,
            status="running",
            dry_run=dry_run,
            fetched_count=0,
            normalized_count=0,
            added_count=0,
            removed_count=0,
            unchanged_count=0,
            failed_validation_count=0,
            fallback_used=False,
        )
        self.db.add(run)
        await self.db.flush()
        return run

    async def get_run(self, run_id: int) -> UniverseSyncRun:
        result = await self.db.execute(
            select(UniverseSyncRun).where(UniverseSyncRun.id == run_id)
        )
        return result.scalar_one()

    async def latest_snapshot(self, index_code: str) -> UniverseProviderSnapshot | None:
        result = await self.db.execute(
            select(UniverseSnapshot)
            .where(UniverseSnapshot.index_code == index_code)
            .order_by(UniverseSnapshot.fetched_at.desc(), UniverseSnapshot.id.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return UniverseProviderSnapshot(
            index_code=row.index_code,
            source=row.source,
            source_url=row.source_url,
            snapshot_date=row.snapshot_date,
            fetched_at=row.fetched_at,
            constituents=tuple(
                UniverseConstituent.from_payload(item) for item in row.constituents
            ),
        )

    async def persist_snapshot(self, snapshot: UniverseProviderSnapshot) -> None:
        values = {
            "index_code": snapshot.index_code,
            "source": snapshot.source,
            "source_url": snapshot.source_url,
            "snapshot_date": snapshot.snapshot_date,
            "fetched_at": snapshot.fetched_at,
            "checksum": snapshot.checksum,
            "constituent_count": len(snapshot.constituents),
            "constituents": [row.to_payload() for row in snapshot.constituents],
        }
        stmt = conflict_insert(self.db, UniverseSnapshot).values(**values)
        await self.db.execute(
            stmt.on_conflict_do_nothing(
                index_elements=[
                    UniverseSnapshot.index_code,
                    UniverseSnapshot.source,
                    UniverseSnapshot.snapshot_date,
                    UniverseSnapshot.checksum,
                ]
            )
        )

    async def active_memberships(self, index_code: str) -> dict[str, ActiveMembership]:
        result = await self.db.execute(
            select(IndexMembership, Stock)
            .join(Stock, Stock.id == IndexMembership.stock_id)
            .where(
                IndexMembership.index_code == index_code,
                IndexMembership.valid_to.is_(None),
            )
            .order_by(Stock.exchange_symbol, Stock.symbol)
        )
        active: dict[str, ActiveMembership] = {}
        for membership, stock in result.all():
            if not stock.exchange_symbol:
                raise RuntimeError(
                    f"Active {index_code} stock {stock.symbol} has no exchange symbol"
                )
            if stock.exchange_symbol in active:
                raise RuntimeError(
                    f"Duplicate active {index_code} membership for {stock.exchange_symbol}"
                )
            active[stock.exchange_symbol] = ActiveMembership(membership, stock)
        return active

    async def activate(
        self,
        *,
        index_code: str,
        source: str,
        snapshot_date: date,
        constituent: UniverseConstituent,
        resolved: ResolvedSymbol,
    ) -> Stock:
        existing = await self.market.get_stock_by_symbol(resolved.provider_symbol)
        stock = await self.market.upsert_stock(
            resolved.provider_symbol,
            exchange_symbol=resolved.exchange_symbol,
            data_provider="yahoo",
            name=constituent.company_name,
            sector=constituent.industry,
            industry=constituent.industry,
            exchange="NSE",
            is_active=True,
        )
        if existing is None:
            stock.history_eligible = False
        latest_result = await self.db.execute(
            select(IndexMembership)
            .where(
                IndexMembership.stock_id == stock.id,
                IndexMembership.index_code == index_code,
            )
            .order_by(IndexMembership.valid_from.desc(), IndexMembership.id.desc())
            .limit(1)
        )
        latest = latest_result.scalar_one_or_none()
        if latest is None:
            self.db.add(
                IndexMembership(
                    stock_id=stock.id,
                    index_code=index_code,
                    valid_from=snapshot_date,
                    source=source,
                    source_snapshot_date=snapshot_date,
                )
            )
        elif latest.valid_to is not None:
            if latest.valid_from == snapshot_date:
                latest.valid_to = None
                latest.source = source
                latest.source_snapshot_date = snapshot_date
            else:
                self.db.add(
                    IndexMembership(
                        stock_id=stock.id,
                        index_code=index_code,
                        valid_from=snapshot_date,
                        source=source,
                        source_snapshot_date=snapshot_date,
                    )
                )
        await self._persist_alias(stock, resolved, snapshot_date)
        return stock

    async def refresh_metadata(
        self, constituent: UniverseConstituent, resolved: ResolvedSymbol
    ) -> Stock:
        return await self.market.upsert_stock(
            resolved.provider_symbol,
            exchange_symbol=resolved.exchange_symbol,
            data_provider="yahoo",
            name=constituent.company_name,
            sector=constituent.industry,
            industry=constituent.industry,
            exchange="NSE",
            is_active=True,
        )

    async def _persist_alias(
        self, stock: Stock, resolved: ResolvedSymbol, snapshot_date: date
    ) -> None:
        if resolved.alias_exchange_symbol is None:
            return
        retired = None
        if resolved.alias_provider_symbol:
            retired = await self.market.get_stock_by_symbol(
                resolved.alias_provider_symbol
            )
        values = {
            "stock_id": stock.id,
            "retired_stock_id": retired.id if retired else None,
            "exchange": "NSE",
            "alias_exchange_symbol": resolved.alias_exchange_symbol,
            "alias_provider_symbol": resolved.alias_provider_symbol,
            "alias_type": resolved.alias_type or "alias",
            "effective_to": snapshot_date,
        }
        stmt = conflict_insert(self.db, StockSymbolAlias).values(**values)
        await self.db.execute(
            stmt.on_conflict_do_update(
                index_elements=[
                    StockSymbolAlias.exchange,
                    StockSymbolAlias.alias_exchange_symbol,
                ],
                set_={
                    key: getattr(stmt.excluded, key)
                    for key in values
                    if key != "exchange"
                },
            )
        )
        if retired is not None:
            retired.is_active = False

    async def deactivate_removed(
        self,
        memberships: list[ActiveMembership],
        *,
        snapshot_date: date,
    ) -> None:
        for active in memberships:
            active.membership.valid_to = snapshot_date
        await self.db.flush()
        for active in memberships:
            has_other = await self.db.scalar(
                select(
                    exists().where(
                        IndexMembership.stock_id == active.stock.id,
                        IndexMembership.valid_to.is_(None),
                    )
                )
            )
            if not has_other:
                active.stock.is_active = False

    async def add_items(self, items: list[UniverseSyncItem]) -> None:
        self.db.add_all(items)

    async def fail_run(self, run_id: int, *, error: str, completed_at: datetime) -> None:
        await self.db.execute(
            update(UniverseSyncRun)
            .where(UniverseSyncRun.id == run_id)
            .values(
                status="failed", error_summary=error[:4000], completed_at=completed_at
            )
        )
