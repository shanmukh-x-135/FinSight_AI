"""Market & admin HTTP routes.

* ``market_router`` → ``/api/v1/market/...`` — read-only market intelligence.
* ``admin_router``  → ``/api/v1/admin/...``  — the manual ingestion trigger
  (auth-protected; the scheduled job is the normal path).

All responses use the standard envelope.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.market.dependencies import get_market_client
from app.market.service import MarketIngestionService, MarketQueryService
from app.shared.clients.market_data import MarketDataClient
from app.shared.database import get_db
from app.shared.response import envelope

market_router = APIRouter(prefix="/market", tags=["market"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])


# --------------------------------------------------------------------------- #
# Market reads                                                                 #
# --------------------------------------------------------------------------- #
@market_router.get("/gainers", summary="Top gaining stocks by daily % change")
async def gainers(
    limit: int = Query(5, ge=1, le=50), db: AsyncSession = Depends(get_db)
) -> dict:
    data = await MarketQueryService(db).get_gainers(limit)
    return envelope(data=data)


@market_router.get("/losers", summary="Top losing stocks by daily % change")
async def losers(
    limit: int = Query(5, ge=1, le=50), db: AsyncSession = Depends(get_db)
) -> dict:
    data = await MarketQueryService(db).get_losers(limit)
    return envelope(data=data)


@market_router.get("/breadth", summary="Market breadth (advancers vs decliners)")
async def breadth(db: AsyncSession = Depends(get_db)) -> dict:
    data = await MarketQueryService(db).get_breadth()
    return envelope(data=data)


@market_router.get("/sectors", summary="Per-sector performance overview (heatmap)")
async def sectors_overview(db: AsyncSession = Depends(get_db)) -> dict:
    data = await MarketQueryService(db).get_sectors_overview()
    return envelope(data=data)


@market_router.get("/sectors/{sector}", summary="Performance of a sector")
async def sector_performance(sector: str, db: AsyncSession = Depends(get_db)) -> dict:
    data = await MarketQueryService(db).get_sector_performance(sector)
    return envelope(data=data)


@market_router.get("/stocks/{symbol}", summary="Latest quote + fundamentals for a stock")
async def stock_detail(symbol: str, db: AsyncSession = Depends(get_db)) -> dict:
    data = await MarketQueryService(db).get_stock_detail(symbol)
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
    "for the given symbols (or the default universe). Auth-protected.",
)
async def run_market_ingestion(
    payload: IngestionTriggerRequest | None = None,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    client: MarketDataClient = Depends(get_market_client),
) -> dict:
    symbols = payload.symbols if payload else None
    result = await MarketIngestionService(db, client).ingest(symbols)
    return envelope(data=result, message="Ingestion complete.")
