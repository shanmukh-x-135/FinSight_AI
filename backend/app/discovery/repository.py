"""Saved-screen persistence with strict ownership."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.discovery.models import SavedScreen


class DiscoveryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add(self, screen: SavedScreen) -> SavedScreen:
        self.db.add(screen)
        await self.db.flush()
        await self.db.refresh(screen)
        return screen

    async def list(self, user_id: int) -> list[SavedScreen]:
        result = await self.db.execute(
            select(SavedScreen)
            .where(SavedScreen.user_id == user_id)
            .order_by(SavedScreen.updated_at.desc(), SavedScreen.id.desc())
        )
        return list(result.scalars())

    async def get(self, user_id: int, screen_id: int) -> SavedScreen | None:
        return await self.db.scalar(
            select(SavedScreen).where(
                SavedScreen.id == screen_id, SavedScreen.user_id == user_id
            )
        )

    async def delete(self, screen: SavedScreen) -> None:
        await self.db.delete(screen)
