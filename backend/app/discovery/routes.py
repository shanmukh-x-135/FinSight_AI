"""Authenticated deterministic discovery endpoints."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.discovery.schemas import SavedScreenCreate, ScreenerQuery
from app.discovery.service import DiscoveryService
from app.shared.database import get_db
from app.shared.response import envelope

discovery_router = APIRouter(prefix="/discovery", tags=["discovery"])


@discovery_router.post(
    "/screen", summary="Parse and execute a deterministic natural-language screen"
)
async def screen(
    payload: ScreenerQuery,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return envelope(data=await DiscoveryService(db).screen(payload))


@discovery_router.post(
    "/screens", status_code=status.HTTP_201_CREATED, summary="Save a validated screen"
)
async def save_screen(
    payload: SavedScreenCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return envelope(
        data=await DiscoveryService(db).save(user.id, payload), message="Screen saved."
    )


@discovery_router.get("/screens", summary="List saved screens")
async def list_screens(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    return envelope(data=await DiscoveryService(db).list_saved(user.id))


@discovery_router.post(
    "/screens/{screen_id}/run", summary="Re-run an immutable saved AST"
)
async def run_screen(
    screen_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return envelope(data=await DiscoveryService(db).run_saved(user.id, screen_id))


@discovery_router.delete("/screens/{screen_id}", summary="Delete a saved screen")
async def delete_screen(
    screen_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await DiscoveryService(db).delete_saved(user.id, screen_id)
    return envelope(message="Saved screen deleted.")
