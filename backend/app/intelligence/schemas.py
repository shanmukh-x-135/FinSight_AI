"""Pydantic schemas for the intelligence endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GenerationUsageOut(BaseModel):
    prompt_tokens: int | None = Field(default=None, ge=0)
    candidate_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)
    thoughts_tokens: int | None = Field(default=None, ge=0)


class GenerationMetadataOut(BaseModel):
    configured_backend: str
    backend: str
    requested_model: str | None = None
    model_version: str | None = None
    response_id: str | None = None
    finish_reason: str | None = None
    provider_created_at: str | None = None
    attempt_count: int = Field(ge=0)
    provider_response_count: int = Field(ge=0)
    fallback_used: bool
    latency_ms: int = Field(ge=0)
    usage: GenerationUsageOut


class GenerationItemOut(GenerationMetadataOut):
    purpose: str


class GenerationSummaryOut(BaseModel):
    schema_version: int = 1
    configured_backend: str
    actual_backends: list[str]
    requested_models: list[str]
    model_versions: list[str]
    generation_count: int = Field(ge=0)
    provider_attempt_count: int = Field(ge=0)
    provider_response_count: int = Field(ge=0)
    fallback_count: int = Field(ge=0)
    usage: GenerationUsageOut
    items: list[GenerationItemOut]


class ReportSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_type: str
    created_at: datetime


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    report_type: str
    sections: dict
    created_at: datetime


class RecommendationsOut(BaseModel):
    watchlist: list[dict]
    risk_alerts: list[dict]
    generation: GenerationSummaryOut
