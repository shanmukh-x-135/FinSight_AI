"""Idempotent NIFTY 50 discovery, validation, and membership synchronization.

Operator usage::

    cd backend
    ./.venv/bin/python -m app.market.universe_sync
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from time import monotonic

from sqlalchemy.ext.asyncio import AsyncSession

from app.market.models import UniverseSyncItem
from app.market.symbol_resolver import (
    ResolvedSymbol,
    SymbolResolutionError,
    YahooNseSymbolResolver,
)
from app.market.universe import (
    SymbolHealthResult,
    SymbolHealthStatus,
    check_configured_universe,
)
from app.market.universe_provider import (
    NIFTY50_INDEX_CODE,
    NseNifty50Provider,
    UniverseConstituent,
    UniverseProvider,
    UniverseProviderError,
    UniverseProviderSnapshot,
)
from app.market.universe_repository import UniverseRepository
from app.scheduler.locks import pipeline_run_lock, pipeline_run_lock_id
from app.shared.clients.market_data import MarketDataClient
from app.shared.clients.yfinance_client import build_default_client
from app.shared.database import SessionFactory
from config.logging import get_logger

logger = get_logger(__name__)


class UniverseSyncError(RuntimeError):
    """Universe synchronization could not safely complete."""


class UniverseSyncInProgressError(UniverseSyncError):
    """Another worker owns the non-blocking universe synchronization lock."""


@dataclass(frozen=True)
class ResolvedCandidate:
    constituent: UniverseConstituent
    resolved: ResolvedSymbol


@dataclass(frozen=True)
class UniverseSyncFailure:
    exchange_symbol: str
    provider_symbol: str | None
    status: str
    error: str | None


@dataclass(frozen=True)
class UniverseSyncResult:
    run_id: int
    index_code: str
    source: str
    snapshot_date: date
    status: str
    fetched_count: int
    normalized_count: int
    added_count: int
    removed_count: int
    unchanged_count: int
    failed_validation_count: int
    active_count: int
    fallback_used: bool
    dry_run: bool
    failures: tuple[UniverseSyncFailure, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "index_code": self.index_code,
            "source": self.source,
            "snapshot_date": self.snapshot_date.isoformat(),
            "status": self.status,
            "fetched_count": self.fetched_count,
            "normalized_count": self.normalized_count,
            "added_count": self.added_count,
            "removed_count": self.removed_count,
            "unchanged_count": self.unchanged_count,
            "failed_validation_count": self.failed_validation_count,
            "active_count": self.active_count,
            "fallback_used": self.fallback_used,
            "dry_run": self.dry_run,
            "failures": [
                {
                    "exchange_symbol": item.exchange_symbol,
                    "provider_symbol": item.provider_symbol,
                    "status": item.status,
                    "error": item.error,
                    "remains_inactive": True,
                }
                for item in self.failures
            ],
        }


class UniverseSyncService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        provider: UniverseProvider | None = None,
        resolver: YahooNseSymbolResolver | None = None,
        market_client: MarketDataClient | None = None,
    ) -> None:
        self.db = db
        self.repo = UniverseRepository(db)
        self.provider = provider or NseNifty50Provider()
        self.resolver = resolver or YahooNseSymbolResolver()
        self.market_client = market_client or build_default_client()

    async def sync(
        self,
        *,
        index_code: str = NIFTY50_INDEX_CODE,
        dry_run: bool = False,
        validate_all: bool = False,
        target_date: date | None = None,
    ) -> UniverseSyncResult:
        index_code = index_code.strip().upper()
        if index_code != NIFTY50_INDEX_CODE:
            raise UniverseSyncError(f"Unsupported universe index: {index_code}")
        lock_id = pipeline_run_lock_id(f"universe-sync:{index_code}", date.min)
        async with pipeline_run_lock(self.db, lock_id) as acquired:
            if not acquired:
                raise UniverseSyncInProgressError(
                    f"A {index_code} universe sync is already running"
                )
            return await self._sync_locked(
                index_code=index_code,
                dry_run=dry_run,
                validate_all=validate_all,
                target_date=target_date,
            )

    async def _sync_locked(
        self,
        *,
        index_code: str,
        dry_run: bool,
        validate_all: bool,
        target_date: date | None,
    ) -> UniverseSyncResult:
        started = monotonic()
        run = await self.repo.create_run(
            index_code=index_code,
            source=self.provider.source,
            dry_run=dry_run,
        )
        await self.db.commit()
        run_id = run.id
        fallback_used = False
        provider_error: str | None = None
        try:
            snapshot = await self.provider.get_constituents(index_code)
        except UniverseProviderError as exc:
            provider_error = str(exc)
            fallback_used = True
            snapshot = await self.repo.latest_snapshot(index_code)
            await self.db.commit()
            if snapshot is None:
                await self._mark_failed(run_id, f"{provider_error}; no cached snapshot")
                raise UniverseSyncError(
                    f"{provider_error}; no last-known-good {index_code} snapshot exists"
                ) from exc

        try:
            candidates, resolution_failures = self._resolve(snapshot)
            if not dry_run and not fallback_used:
                await self.repo.persist_snapshot(snapshot)
                await self.db.commit()

            active = await self.repo.active_memberships(index_code)
            await self.db.commit()
            candidate_symbols = set(candidates)
            protected = {failure.exchange_symbol for failure in resolution_failures}
            unchanged_symbols = candidate_symbols & set(active)
            new_symbols = candidate_symbols - set(active)
            removed_symbols = set(active) - candidate_symbols - protected

            validation_symbols = sorted(
                candidate_symbols if validate_all else new_symbols
            )
            health = await self._validate(
                candidates,
                validation_symbols,
                target_date=target_date or date.today(),
            )
            failures = [*resolution_failures]
            for symbol in validation_symbols:
                result = health[symbol]
                if not result.healthy:
                    candidate = candidates[symbol]
                    failures.append(
                        UniverseSyncFailure(
                            exchange_symbol=symbol,
                            provider_symbol=candidate.resolved.provider_symbol,
                            status=result.status.value,
                            error=f"{result.status.value} for {candidate.resolved.provider_symbol}",
                        )
                    )

            failed_symbols = {item.exchange_symbol for item in failures}
            additions = sorted(new_symbols - failed_symbols)
            removals = [active[symbol] for symbol in sorted(removed_symbols)]
            items: list[UniverseSyncItem] = []
            stock_ids: dict[str, int] = {
                symbol: active[symbol].stock.id for symbol in unchanged_symbols
            }

            if not dry_run:
                for symbol in sorted(unchanged_symbols):
                    candidate = candidates[symbol]
                    stock = await self.repo.refresh_metadata(
                        candidate.constituent, candidate.resolved
                    )
                    stock_ids[symbol] = stock.id
                for symbol in additions:
                    candidate = candidates[symbol]
                    stock = await self.repo.activate(
                        index_code=index_code,
                        source=snapshot.source,
                        snapshot_date=snapshot.snapshot_date,
                        constituent=candidate.constituent,
                        resolved=candidate.resolved,
                    )
                    stock_ids[symbol] = stock.id
                await self.repo.deactivate_removed(
                    removals, snapshot_date=snapshot.snapshot_date
                )

            for symbol in sorted(unchanged_symbols):
                candidate = candidates[symbol]
                result = health.get(symbol)
                items.append(
                    self._item(
                        run_id,
                        candidate,
                        status="unchanged",
                        health=result,
                        stock_id=stock_ids.get(symbol),
                    )
                )
            for symbol in sorted(new_symbols):
                candidate = candidates[symbol]
                result = health[symbol]
                items.append(
                    self._item(
                        run_id,
                        candidate,
                        status="added" if result.healthy else "quarantined",
                        health=result,
                        stock_id=stock_ids.get(symbol),
                    )
                )
            for active_row in removals:
                items.append(
                    UniverseSyncItem(
                        run_id=run_id,
                        stock_id=active_row.stock.id,
                        exchange_symbol=active_row.stock.exchange_symbol
                        or active_row.stock.symbol,
                        provider_symbol=active_row.stock.symbol,
                        company_name=active_row.stock.name or active_row.stock.symbol,
                        status="removed",
                        validation_status="previously_approved",
                    )
                )
            for failure in resolution_failures:
                items.append(
                    UniverseSyncItem(
                        run_id=run_id,
                        exchange_symbol=failure.exchange_symbol,
                        provider_symbol=failure.provider_symbol,
                        company_name=failure.exchange_symbol,
                        status="quarantined",
                        validation_status=failure.status,
                        validation_error=failure.error,
                    )
                )

            final_status = "completed_with_failures" if failures else "completed"
            run = await self.repo.get_run(run_id)
            run.source = snapshot.source
            run.snapshot_date = snapshot.snapshot_date
            run.status = final_status
            run.completed_at = datetime.now(tz=timezone.utc)
            run.fetched_count = len(snapshot.constituents)
            run.normalized_count = len(candidates)
            run.added_count = len(additions)
            run.removed_count = len(removals)
            run.unchanged_count = len(unchanged_symbols)
            run.failed_validation_count = len(failures)
            run.fallback_used = fallback_used
            run.error_summary = provider_error
            await self.repo.add_items(items)
            await self.db.commit()
            active_count = (
                len(active) if dry_run else len(active) - len(removals) + len(additions)
            )
        except Exception as exc:
            await self.db.rollback()
            await self._mark_failed(run_id, f"{type(exc).__name__}: {exc}")
            raise

        duration = monotonic() - started
        result = UniverseSyncResult(
            run_id=run_id,
            index_code=index_code,
            source=snapshot.source,
            snapshot_date=snapshot.snapshot_date,
            status=final_status,
            fetched_count=len(snapshot.constituents),
            normalized_count=len(candidates),
            added_count=len(additions),
            removed_count=len(removals),
            unchanged_count=len(unchanged_symbols),
            failed_validation_count=len(failures),
            active_count=active_count,
            fallback_used=fallback_used,
            dry_run=dry_run,
            failures=tuple(failures),
        )
        logger.info(
            "universe_sync_complete",
            extra={
                **result.to_payload(),
                "duration_seconds": round(duration, 3),
            },
        )
        return result

    def _resolve(
        self, snapshot: UniverseProviderSnapshot
    ) -> tuple[dict[str, ResolvedCandidate], list[UniverseSyncFailure]]:
        candidates: dict[str, ResolvedCandidate] = {}
        failures: list[UniverseSyncFailure] = []
        for constituent in snapshot.constituents:
            try:
                resolved = self.resolver.resolve(constituent.exchange_symbol)
            except SymbolResolutionError as exc:
                failures.append(
                    UniverseSyncFailure(
                        exchange_symbol=constituent.exchange_symbol,
                        provider_symbol=None,
                        status="symbol_resolution_failed",
                        error=str(exc),
                    )
                )
                continue
            normalized = replace(constituent, exchange_symbol=resolved.exchange_symbol)
            if resolved.exchange_symbol in candidates:
                raise UniverseSyncError(
                    f"Multiple source constituents resolve to {resolved.exchange_symbol}"
                )
            candidates[resolved.exchange_symbol] = ResolvedCandidate(
                constituent=normalized, resolved=resolved
            )
        return candidates, failures

    async def _validate(
        self,
        candidates: dict[str, ResolvedCandidate],
        symbols: list[str],
        *,
        target_date: date,
    ) -> dict[str, SymbolHealthResult]:
        if not symbols:
            return {}
        results = await check_configured_universe(
            self.market_client,
            target_date=target_date,
            equity_symbols=tuple(
                candidates[symbol].resolved.provider_symbol for symbol in symbols
            ),
            macro_symbols=(),
        )
        return {symbol: result for symbol, result in zip(symbols, results, strict=True)}

    @staticmethod
    def _item(
        run_id: int,
        candidate: ResolvedCandidate,
        *,
        status: str,
        health: SymbolHealthResult | None,
        stock_id: int | None,
    ) -> UniverseSyncItem:
        validation_status = (
            health.status.value if health is not None else "previously_approved"
        )
        return UniverseSyncItem(
            run_id=run_id,
            stock_id=stock_id,
            exchange_symbol=candidate.resolved.exchange_symbol,
            provider_symbol=candidate.resolved.provider_symbol,
            company_name=candidate.constituent.company_name,
            status=status,
            validation_status=validation_status,
            validation_error=(
                None
                if health is None or health.status == SymbolHealthStatus.HEALTHY
                else f"{health.status.value} for {candidate.resolved.provider_symbol}"
            ),
        )

    async def _mark_failed(self, run_id: int, error: str) -> None:
        await self.repo.fail_run(
            run_id, error=error, completed_at=datetime.now(tz=timezone.utc)
        )
        await self.db.commit()
        logger.error(
            "universe_sync_failed",
            extra={"run_id": run_id, "error": error[:4000]},
        )


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be YYYY-MM-DD") from exc


async def _run_cli(args: argparse.Namespace) -> int:
    async with SessionFactory() as db:
        service = UniverseSyncService(db)
        try:
            result = await service.sync(
                index_code=args.index,
                dry_run=args.dry_run,
                validate_all=args.validate_all,
                target_date=args.target_date,
            )
        except UniverseSyncError as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, indent=2))
            return 2
    print(json.dumps(result.to_payload(), indent=2))
    return 0 if result.failed_validation_count == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Synchronize the approved NIFTY 50 universe from official NSE data."
    )
    parser.add_argument(
        "--index", default=NIFTY50_INDEX_CODE, choices=[NIFTY50_INDEX_CODE]
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch, diff, and validate without changing snapshots or memberships.",
    )
    parser.add_argument(
        "--validate-all",
        action="store_true",
        help="Revalidate unchanged approved constituents as well as new candidates.",
    )
    parser.add_argument(
        "--target-date",
        type=_iso_date,
        help="Validation recency date (defaults to the provider snapshot date).",
    )
    args = parser.parse_args()
    return asyncio.run(_run_cli(args))


if __name__ == "__main__":
    raise SystemExit(main())
