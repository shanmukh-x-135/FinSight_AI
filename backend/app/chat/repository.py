"""User-scoped persistence for chat messages."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.models import ChatHistory


class ChatRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add_message(self, user_id: int, role: str, message: str) -> ChatHistory:
        row = ChatHistory(user_id=user_id, role=role, message=message)
        self.db.add(row)
        await self.db.flush()
        return row

    async def list_history(self, user_id: int, limit: int) -> list[ChatHistory]:
        result = await self.db.execute(
            select(ChatHistory)
            .where(ChatHistory.user_id == user_id)
            .order_by(ChatHistory.created_at.desc(), ChatHistory.id.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def delete_history(self, user_id: int) -> int:
        result = await self.db.execute(
            delete(ChatHistory).where(ChatHistory.user_id == user_id)
        )
        await self.db.flush()
        return int(result.rowcount or 0)
