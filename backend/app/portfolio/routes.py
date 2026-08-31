"""Portfolio & watchlist HTTP routes (all auth-protected, user-scoped).

* ``portfolio_router`` → ``/api/v1/portfolios/...``
* ``watchlist_router`` → ``/api/v1/watchlist/...``
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.portfolio.schemas import (
    CounterfactualRequest,
    HoldingCreate,
    HoldingUpdate,
    PortfolioCreate,
    PortfolioSummaryOut,
    PortfolioUpdate,
    WatchlistAdd,
    WatchlistUpdate,
)
from app.portfolio.service import PortfolioService
from app.shared.database import get_db
from app.shared.response import envelope

portfolio_router = APIRouter(prefix="/portfolios", tags=["portfolio"])
watchlist_router = APIRouter(prefix="/watchlist", tags=["watchlist"])


# --------------------------------------------------------------------------- #
# Portfolios                                                                   #
# --------------------------------------------------------------------------- #
@portfolio_router.post(
    "", status_code=status.HTTP_201_CREATED, summary="Create a portfolio"
)
async def create_portfolio(
    payload: PortfolioCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    p = await PortfolioService(db).create_portfolio(user.id, payload.name)
    return envelope(
        data=PortfolioSummaryOut(
            id=p.id, name=p.name, created_at=p.created_at, holding_count=0
        ),
        message="Portfolio created.",
    )


@portfolio_router.get("", summary="List your portfolios")
async def list_portfolios(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    return envelope(data=await PortfolioService(db).list_portfolios(user.id))


@portfolio_router.get("/{portfolio_id}", summary="Get a portfolio's holdings")
async def get_portfolio(
    portfolio_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return envelope(
        data=await PortfolioService(db).get_portfolio_detail(user.id, portfolio_id)
    )


@portfolio_router.put("/{portfolio_id}", summary="Rename a portfolio")
async def rename_portfolio(
    portfolio_id: int,
    payload: PortfolioUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    p = await PortfolioService(db).rename_portfolio(user.id, portfolio_id, payload.name)
    return envelope(
        data=PortfolioSummaryOut(
            id=p.id, name=p.name, created_at=p.created_at, holding_count=len(p.items)
        ),
        message="Portfolio renamed.",
    )


@portfolio_router.delete("/{portfolio_id}", summary="Delete a portfolio")
async def delete_portfolio(
    portfolio_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await PortfolioService(db).delete_portfolio(user.id, portfolio_id)
    return envelope(message="Portfolio deleted.")


@portfolio_router.get(
    "/{portfolio_id}/analytics", summary="Portfolio analytics (value, P&L, health)"
)
async def portfolio_analytics(
    portfolio_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return envelope(data=await PortfolioService(db).get_analytics(user.id, portfolio_id))


@portfolio_router.get(
    "/{portfolio_id}/risk", summary="Static-weight portfolio risk diagnostics"
)
async def portfolio_risk(
    portfolio_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return envelope(data=await PortfolioService(db).get_risk(user.id, portfolio_id))


@portfolio_router.post(
    "/{portfolio_id}/counterfactual",
    summary="Estimate risk changes for hypothetical holding adjustments",
)
async def portfolio_counterfactual(
    portfolio_id: int,
    payload: CounterfactualRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return envelope(
        data=await PortfolioService(db).counterfactual(user.id, portfolio_id, payload)
    )


# ----- Holdings ------------------------------------------------------------
@portfolio_router.post(
    "/{portfolio_id}/items", status_code=status.HTTP_201_CREATED, summary="Add a holding"
)
async def add_holding(
    portfolio_id: int,
    payload: HoldingCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    item = await PortfolioService(db).add_holding(user.id, portfolio_id, payload)
    return envelope(
        data={
            "id": item.id,
            "quantity": item.quantity,
            "avg_buy_price": item.avg_buy_price,
        },
        message="Holding added.",
    )


@portfolio_router.put("/{portfolio_id}/items/{item_id}", summary="Update a holding")
async def update_holding(
    portfolio_id: int,
    item_id: int,
    payload: HoldingUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    item = await PortfolioService(db).update_holding(
        user.id, portfolio_id, item_id, payload
    )
    return envelope(
        data={
            "id": item.id,
            "quantity": item.quantity,
            "avg_buy_price": item.avg_buy_price,
        },
        message="Holding updated.",
    )


@portfolio_router.delete("/{portfolio_id}/items/{item_id}", summary="Remove a holding")
async def remove_holding(
    portfolio_id: int,
    item_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await PortfolioService(db).remove_holding(user.id, portfolio_id, item_id)
    return envelope(message="Holding removed.")


# --------------------------------------------------------------------------- #
# Watchlist                                                                    #
# --------------------------------------------------------------------------- #
@watchlist_router.get("", summary="List your watchlist")
async def list_watchlist(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    return envelope(data=await PortfolioService(db).list_watchlist(user.id))


@watchlist_router.post(
    "", status_code=status.HTTP_201_CREATED, summary="Add to watchlist"
)
async def add_watchlist(
    payload: WatchlistAdd,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    item = await PortfolioService(db).add_watchlist_item(
        user.id, payload.symbol, payload.pinned
    )
    return envelope(data={"id": item.id}, message="Added to watchlist.")


@watchlist_router.patch("/{item_id}", summary="Update a watchlist item (pin/sort)")
async def update_watchlist(
    item_id: int,
    payload: WatchlistUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    item = await PortfolioService(db).update_watchlist_item(user.id, item_id, payload)
    return envelope(
        data={"id": item.id, "pinned": item.pinned, "sort_order": item.sort_order},
        message="Watchlist updated.",
    )


@watchlist_router.delete("/{item_id}", summary="Remove from watchlist")
async def remove_watchlist(
    item_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await PortfolioService(db).remove_watchlist_item(user.id, item_id)
    return envelope(message="Removed from watchlist.")
