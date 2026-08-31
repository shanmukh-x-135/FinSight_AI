"""Market & admin HTTP routes.

* ``market_router`` → ``/api/v1/market/...`` — read-only market intelligence.
* ``admin_router``  → ``/api/v1/admin/...``  — the manual ingestion trigger
  (auth-protected; the scheduled job is the normal path).

All responses use the standard envelope.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_admin_user
from app.auth.models import User
from app.market.dependencies import get_economic_calendar_client, get_market_client
from app.market.service import (
    EconomicCalendarService,
    MarketIngestionService,
    MarketQueryService,
)
from app.shared.clients.economic_calendar import EconomicCalendarClient
from app.shared.clients.market_data import MarketDataClient
from app.shared.database import get_db
from app.shared.response import envelope

market_router = APIRouter(prefix="/market", tags=["market"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])
UniverseCode = Literal["NIFTY50", "NIFTYNEXT50", "NIFTY100"]


# --------------------------------------------------------------------------- #
# Market reads                                                                 #
# --------------------------------------------------------------------------- #
@market_router.get("/gainers", summary="Top gaining stocks by daily % change")
async def gainers(
    limit: int = Query(5, ge=1, le=50),
    universe: UniverseCode | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    data = await MarketQueryService(db).get_gainers(limit, universe)
    return envelope(data=data)


@market_router.get("/losers", summary="Top losing stocks by daily % change")
async def losers(
    limit: int = Query(5, ge=1, le=50),
    universe: UniverseCode | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    data = await MarketQueryService(db).get_losers(limit, universe)
    return envelope(data=data)


@market_router.get("/breadth", summary="Market breadth (advancers vs decliners)")
async def breadth(
    universe: UniverseCode | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    data = await MarketQueryService(db).get_breadth(universe)
    return envelope(data=data)


@market_router.get("/technical-summary", summary="Market-wide technical summary")
async def technical_summary(
    universe: UniverseCode | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    data = await MarketQueryService(db).get_technical_summary(universe)
    return envelope(data=data)


@market_router.get("/economic-events", summary="Upcoming India economic events")
async def economic_events(
    days: int = Query(14, ge=1, le=60),
    client: EconomicCalendarClient | None = Depends(get_economic_calendar_client),
) -> dict:
    start_date = date.today()
    data = await EconomicCalendarService(client).upcoming(
        start_date, start_date + timedelta(days=days)
    )
    return envelope(data=data)


@market_router.get("/sectors", summary="Per-sector performance overview (heatmap)")
async def sectors_overview(
    universe: UniverseCode | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    data = await MarketQueryService(db).get_sectors_overview(universe)
    return envelope(data=data)


@market_router.get("/sectors/{sector}", summary="Performance of a sector")
async def sector_performance(
    sector: str,
    universe: UniverseCode | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    data = await MarketQueryService(db).get_sector_performance(sector, universe)
    return envelope(data=data)


@market_router.get("/stocks", summary="Dense snapshots for the active stock universe")
async def market_stocks(
    universe: UniverseCode | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    data = await MarketQueryService(db).list_market_stocks(universe)
    return envelope(data=data)


@market_router.get("/universes", summary="Supported research universes and status")
async def universes(db: AsyncSession = Depends(get_db)) -> dict:
    return envelope(data=await MarketQueryService(db).list_universes())


@market_router.get("/workspace", summary="Batched market research workspace")
async def market_workspace(
    universe: UniverseCode = Query("NIFTY100"),
    days: int = Query(14, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
    client: EconomicCalendarClient | None = Depends(get_economic_calendar_client),
) -> dict:
    start_date = date.today()
    calendar = await EconomicCalendarService(client).upcoming(
        start_date, start_date + timedelta(days=days)
    )
    data = await MarketQueryService(db).get_workspace(universe, calendar)
    return envelope(data=data)


@market_router.get("/heatmap", summary="Compact stock heatmap for one universe")
async def market_heatmap(
    universe: UniverseCode = Query("NIFTY100"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return envelope(data=await MarketQueryService(db).get_heatmap(universe))


@market_router.get(
    "/sector-rotation", summary="Sector 1D, 5D, and 20D momentum regimes"
)
async def sector_rotation(
    universe: UniverseCode = Query("NIFTY100"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return envelope(data=await MarketQueryService(db).get_sector_rotation(universe))


@market_router.get(
    "/stocks/{symbol}/attribution",
    summary="Deterministic likely contributors to a stock's latest move",
)
async def stock_movement_attribution(
    symbol: str, db: AsyncSession = Depends(get_db)
) -> dict:
    data = await MarketQueryService(db).get_movement_attribution(symbol)
    return envelope(data=data)


@market_router.get("/stocks/{symbol}", summary="Latest quote + fundamentals for a stock")
async def stock_detail(symbol: str, db: AsyncSession = Depends(get_db)) -> dict:
    data = await MarketQueryService(db).get_stock_detail(symbol)
    return envelope(data=data)


@market_router.get("/stocks/{symbol}/prices", summary="Recent daily OHLCV history")
async def stock_prices(
    symbol: str,
    limit: int = Query(260, ge=2, le=365),
    db: AsyncSession = Depends(get_db),
) -> dict:
    data = await MarketQueryService(db).get_price_history(symbol, limit)
    return envelope(data=data)


@market_router.get(
    "/stocks/{symbol}/indicators", summary="Technical indicator history for a stock"
)
async def stock_indicators(
    symbol: str,
    limit: int = Query(60, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> dict:
    data = await MarketQueryService(db).get_indicator_history(symbol, limit)
    return envelope(data=data)


# --------------------------------------------------------------------------- #
# Admin: manual ingestion trigger                                             #
# --------------------------------------------------------------------------- #
class IngestionTriggerRequest(BaseModel):
    symbols: list[str] | None = None


@admin_router.post(
    "/jobs/market-ingestion/run",
    summary="Manually trigger market data ingestion (dev/ops)",
    description="Runs the fetch→validate→store→indicators pipeline synchronously "
    "for the given symbols (or the configured DB-approved research universe plus macros). "
    "Auth-protected.",
)
async def run_market_ingestion(
    payload: IngestionTriggerRequest | None = None,
    _user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    client: MarketDataClient = Depends(get_market_client),
) -> dict:
    symbols = payload.symbols if payload else None
    result = await MarketIngestionService(db, client).ingest(symbols)
    return envelope(data=result, message="Ingestion complete.")
