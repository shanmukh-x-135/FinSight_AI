"""Pydantic contracts for conversational intelligence."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.chat.constants import MAX_QUESTION_LENGTH
from app.intelligence.schemas import GenerationMetadataOut


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_QUESTION_LENGTH)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message must not be blank.")
        return value


class ChatSource(BaseModel):
    kind: Literal["portfolio", "watchlist", "market", "history", "news"]
    label: str
    reference: str


class ChatAnswer(BaseModel):
    content: str
    evidence: list[str]
    confidence: int = Field(ge=0, le=100)
    sources: list[ChatSource]
    risks: list[str]
    generation: GenerationMetadataOut | None = None


class ChatMessageOut(ChatAnswer):
    id: int
    role: Literal["assistant"] = "assistant"
    created_at: datetime


class UserChatMessageOut(BaseModel):
    id: int
    role: Literal["user"] = "user"
    content: str
    created_at: datetime


class ChatExchangeOut(BaseModel):
    user: UserChatMessageOut
    assistant: ChatMessageOut


class ChatHistoryMessageOut(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    evidence: list[str] = Field(default_factory=list)
    confidence: int | None = None
    sources: list[ChatSource] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    generation: GenerationMetadataOut | None = None


class ChatHistoryDeleteOut(BaseModel):
    deleted: int
