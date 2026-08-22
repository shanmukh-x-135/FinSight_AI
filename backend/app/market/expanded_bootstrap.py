"""Safe, resumable Phase 10D production-data bootstrap.

Run a read-only preflight by default::

    ./.venv/bin/python -m app.market.expanded_bootstrap

Execute locally or in staging only after reviewing the preflight::

    ./.venv/bin/python -m app.market.expanded_bootstrap --execute

Production additionally requires the exact confirmation token printed by the
preflight. The workflow never deletes market or user data; all constituent,
price, indicator, historical-session, and index writes are idempotent upserts.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import date
from time import monotonic

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.history.feature_engineering import FEATURE_VERSION
from app.history.models import HistoricalSession
from app.history.service import HistoryService
from app.market.constants import MACRO_PROXIES
from app.market.models import DailyPrice, Indicator, Stock
from app.market.repository import MarketRepository
from app.market.service import MarketIngestionService
from app.market.universe_provider import EXPECTED_NIFTY50_COUNT, NIFTY50_INDEX_CODE
from app.market.universe_sync import UniverseSyncService
from app.shared.database import SessionFactory
from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)

EXPECTED_DATABASE_REVISION = "0015_market_regime_history"
PRODUCTION_CONFIRMATION = "RUN_PRODUCTION_PHASE_10D_BOOTSTRAP"


class BootstrapSafetyError(RuntimeError):
    """The bootstrap cannot continue without risking partial production data."""


@dataclass(frozen=True)
class BootstrapCounts:
    active_constituents: int
    equities_with_prices: int
    equity_price_rows: int
    indicator_rows: int
    macros_with_prices: int
    historical_sessions: int


@dataclass(frozen=True)
class BootstrapResult:
    status: str
    environment: str
    database_revision: str
    target_date: date
    before: BootstrapCounts
    after: BootstrapCounts
    universe: dict[str, object] | None
    ingestion: dict[str, object] | None
    history: dict[str, object] | None
    duration_seconds: float
    production_confirmation_required: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload["target_date"] = self.target_date.isoformat()
        return payload


class ExpandedBootstrapService:
    """Orchestrate the existing universe, ingestion, and history services."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        universe_service: UniverseSyncService | None = None,
        ingestion_service: MarketIngestionService | None = None,
        history_service: HistoryService | None = None,
    ) -> None:
        self.db = db
        self.universe_service = universe_service or UniverseSyncService(db)
        self.ingestion_service = ingestion_service or MarketIngestionService(db)
        self.history_service = history_service or HistoryService(db)

    async def run(
        self,
        *,
        execute: bool,
        target_date: date,
        production_confirmation: str | None = None,
    ) -> BootstrapResult:
        started = monotonic()
        revision = await self._verify_database_revision()
        before = await self._counts()
        self._verify_execution_authority(execute, production_confirmation)

        if not execute:
            return BootstrapResult(
                status="preflight_ready",
                environment=settings.app_env,
                database_revision=revision,
                target_date=target_date,
                before=before,
                after=before,
                universe=None,
                ingestion=None,
                history=None,
                duration_seconds=monotonic() - started,
                production_confirmation_required=(
                    PRODUCTION_CONFIRMATION if settings.is_production else None
                ),
            )

        universe = await self.universe_service.sync(
            index_code=NIFTY50_INDEX_CODE,
            validate_all=True,
            target_date=target_date,
        )
        if universe.fallback_used:
            raise BootstrapSafetyError(
                "Universe sync used a cached snapshot; rerun when the official source is available"
            )
        if universe.failed_validation_count:
            raise BootstrapSafetyError(
                "Universe validation failed for "
                f"{universe.failed_validation_count} constituent(s); ingestion was not run"
            )
        if universe.active_count != EXPECTED_NIFTY50_COUNT:
            raise BootstrapSafetyError(
                f"Expected {EXPECTED_NIFTY50_COUNT} active constituents after sync; "
                f"found {universe.active_count}"
            )

        ingestion = await self.ingestion_service.ingest(target_trading_date=target_date)
        if ingestion.failed:
            raise BootstrapSafetyError(
                "Market ingestion was incomplete; rerun after resolving: "
                + ", ".join(sorted(ingestion.failed))
            )
        expected_symbols = EXPECTED_NIFTY50_COUNT + len(MACRO_PROXIES)
        if ingestion.requested != expected_symbols:
            raise BootstrapSafetyError(
                f"Expected ingestion of {expected_symbols} equity/macro symbols; "
                f"requested {ingestion.requested}"
            )

        history = await self.history_service.build_index()
        if history.feature_version != FEATURE_VERSION:
            raise BootstrapSafetyError("History rebuild produced an unexpected version")
        after = await self._counts()
        if after.active_constituents != EXPECTED_NIFTY50_COUNT:
            raise BootstrapSafetyError("Post-bootstrap constituent count is incomplete")
        if after.macros_with_prices != len(MACRO_PROXIES):
            raise BootstrapSafetyError("Post-bootstrap macro coverage is incomplete")

        duration = monotonic() - started
        result = BootstrapResult(
            status="completed",
            environment=settings.app_env,
            database_revision=revision,
            target_date=target_date,
            before=before,
            after=after,
            universe=universe.to_payload(),
            ingestion=ingestion.model_dump(mode="json"),
            history=history.model_dump(mode="json"),
            duration_seconds=duration,
        )
        logger.info("expanded_bootstrap_complete", extra=result.to_payload())
        return result

    @staticmethod
    def _verify_execution_authority(
        execute: bool, production_confirmation: str | None
    ) -> None:
        if not execute:
            return
        if settings.is_production and production_confirmation != PRODUCTION_CONFIRMATION:
            raise BootstrapSafetyError(
                "Production execution requires --confirm-production "
                f"{PRODUCTION_CONFIRMATION}"
            )

    async def _verify_database_revision(self) -> str:
        try:
            revisions = list(
                (
                    await self.db.execute(text("SELECT version_num FROM alembic_version"))
                ).scalars()
            )
        except Exception as exc:
            await self.db.rollback()
            raise BootstrapSafetyError(
                "Cannot verify Alembic revision; apply migrations before bootstrap"
            ) from exc
        await self.db.commit()
        if revisions != [EXPECTED_DATABASE_REVISION]:
            raise BootstrapSafetyError(
                f"Database revision must be {EXPECTED_DATABASE_REVISION}; "
                f"found {revisions or ['unversioned']}"
            )
        return revisions[0]

    async def _counts(self) -> BootstrapCounts:
        approved = await MarketRepository(self.db).list_approved_equities(
            NIFTY50_INDEX_CODE
        )
        approved_ids = [stock.id for stock in approved]
        equity_price_rows = 0
        equities_with_prices = 0
        indicator_rows = 0
        if approved_ids:
            equity_price_rows = int(
                await self.db.scalar(
                    select(func.count(DailyPrice.id)).where(
                        DailyPrice.stock_id.in_(approved_ids)
                    )
                )
                or 0
            )
            equities_with_prices = int(
                await self.db.scalar(
                    select(func.count(func.distinct(DailyPrice.stock_id))).where(
                        DailyPrice.stock_id.in_(approved_ids)
                    )
                )
                or 0
            )
            indicator_rows = int(
                await self.db.scalar(
                    select(func.count(Indicator.id)).where(
                        Indicator.stock_id.in_(approved_ids)
                    )
                )
                or 0
            )
        macros_with_prices = int(
            await self.db.scalar(
                select(func.count(func.distinct(DailyPrice.stock_id)))
                .join(Stock, Stock.id == DailyPrice.stock_id)
                .where(Stock.symbol.in_(tuple(MACRO_PROXIES)))
            )
            or 0
        )
        historical_sessions = int(
            await self.db.scalar(
                select(func.count(HistoricalSession.id)).where(
                    HistoricalSession.feature_version == FEATURE_VERSION
                )
            )
            or 0
        )
        # Force all read transactions to close before services that own commits run.
        await self.db.commit()
        return BootstrapCounts(
            active_constituents=len(approved),
            equities_with_prices=equities_with_prices,
            equity_price_rows=equity_price_rows,
            indicator_rows=indicator_rows,
            macros_with_prices=macros_with_prices,
            historical_sessions=historical_sessions,
        )


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be YYYY-MM-DD") from exc


async def _run_cli(args: argparse.Namespace) -> int:
    async with SessionFactory() as db:
        try:
            result = await ExpandedBootstrapService(db).run(
                execute=args.execute,
                target_date=args.target_date or date.today(),
                production_confirmation=args.confirm_production,
            )
        except BootstrapSafetyError as exc:
            print(json.dumps({"status": "blocked", "error": str(exc)}, indent=2))
            return 2
    print(json.dumps(result.to_payload(), indent=2, default=str))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safely bootstrap NIFTY50 market data and regime similarity."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform writes. Without this flag, only preflight checks run.",
    )
    parser.add_argument("--target-date", type=_iso_date)
    parser.add_argument(
        "--confirm-production",
        help="Exact production confirmation token shown by the preflight.",
    )
    return asyncio.run(_run_cli(parser.parse_args()))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
