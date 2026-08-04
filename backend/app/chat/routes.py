"""Authenticated chat, validated SSE streaming, and user-scoped history."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.chat.constants import (
    DEFAULT_HISTORY_LIMIT,
    MAX_HISTORY_LIMIT,
    STREAM_CHUNK_CHARACTERS,
)
from app.chat.dependencies import get_chat_llm_client
from app.chat.schemas import ChatHistoryDeleteOut, ChatRequest
from app.chat.service import ChatService
from app.intelligence.llm_client import LLMClient
from app.shared.database import get_db
from app.shared.response import envelope

chat_router = APIRouter(prefix="/chat", tags=["chat"])


def _text_chunks(text: str) -> list[str]:
    chunks: list[str] = []
    current = ""
    for word in text.split(" "):
        candidate = word if not current else f"{current} {word}"
        if current and len(candidate) > STREAM_CHUNK_CHARACTERS:
            chunks.append(f"{current} ")
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _sse(event: str, data: dict) -> str:
    payload = json.dumps(data, separators=(",", ":"), default=str)
    return f"event: {event}\ndata: {payload}\n\n"


async def _event_stream(exchange) -> AsyncIterator[str]:
    yield _sse("meta", {"user": exchange.user.model_dump(mode="json")})
    for chunk in _text_chunks(exchange.assistant.content):
        yield _sse("chunk", {"delta": chunk})
        await asyncio.sleep(0)
    yield _sse("complete", {"assistant": exchange.assistant.model_dump(mode="json")})


@chat_router.post("", summary="Ask a grounded financial-research question")
async def ask_chat(
    payload: ChatRequest,
    stream: bool = Query(default=False, description="Return validated SSE chunks"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    llm: LLMClient = Depends(get_chat_llm_client),
):
    exchange = await ChatService(db, llm).ask(user.id, payload.message)
    if not stream:
        return envelope(data=exchange, message="Grounded response generated.")
    return StreamingResponse(
        _event_stream(exchange),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )


@chat_router.get("/history", summary="List your chat history")
async def chat_history(
    limit: int = Query(DEFAULT_HISTORY_LIMIT, ge=1, le=MAX_HISTORY_LIMIT),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return envelope(data=await ChatService(db).history(user.id, limit))


@chat_router.delete("/history", summary="Delete your chat history")
async def delete_chat_history(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    deleted = await ChatService(db).clear_history(user.id)
    return envelope(
        data=ChatHistoryDeleteOut(deleted=deleted), message="Chat history deleted."
    )
