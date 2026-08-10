"""make PostgreSQL authoritative for historical index reconstruction

Revision ID: 0012_history_index_state
Revises: 0011_incremental_ingestion
Create Date: 2026-08-11
"""

from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_history_index_state"
down_revision: str | None = "0011_incremental_ingestion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ARTIFACT_SCHEMA_VERSION = 1
_FEATURE_NAMES = (
    "avg_return",
    "median_return",
    "pct_advancers",
    "advance_decline_ratio",
    "avg_rsi",
    "avg_ema20_distance",
    "avg_ema50_distance",
    "avg_bollinger_position",
    "avg_atr_pct",
    "avg_macd_hist_pct",
    "avg_sentiment",
    "usd_inr_return",
    "crude_oil_return",
    "gold_return",
    "us_10y_yield_return",
)


def _corpus_hash(rows: list[sa.Row]) -> str:
    digest = hashlib.sha256()
    digest.update(struct.pack(">I", _ARTIFACT_SCHEMA_VERSION))
    for name in _FEATURE_NAMES:
        encoded = name.encode("utf-8")
        digest.update(struct.pack(">H", len(encoded)))
        digest.update(encoded)
    for row in rows:
        if row.session_id != row.faiss_id or row.dim != len(_FEATURE_NAMES):
            raise RuntimeError("Existing historical embedding metadata is inconsistent")
        try:
            vector = [float(row.feature_vector[name]) for name in _FEATURE_NAMES]
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                "Existing historical feature vector is incompatible"
            ) from exc
        if not all(math.isfinite(value) for value in vector):
            raise RuntimeError("Existing historical feature vector is non-finite")
        digest.update(struct.pack(">q", row.session_id))
        for value in vector:
            digest.update(struct.pack(">d", value))
    return digest.hexdigest()


def upgrade() -> None:
    op.create_table(
        "historical_index_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("corpus_hash", sa.String(length=64), nullable=False),
        sa.Column("session_count", sa.Integer(), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("artifact_schema_version", sa.Integer(), nullable=False),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_history_index_state_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )

    connection = op.get_bind()
    sessions = sa.table(
        "historical_sessions",
        sa.column("id", sa.Integer()),
        sa.column("feature_vector", sa.JSON()),
    )
    embeddings = sa.table(
        "historical_embeddings",
        sa.column("session_id", sa.Integer()),
        sa.column("faiss_id", sa.Integer()),
        sa.column("dim", sa.Integer()),
    )
    rows = list(
        connection.execute(
            sa.select(
                sessions.c.id.label("session_id"),
                embeddings.c.faiss_id,
                embeddings.c.dim,
                sessions.c.feature_vector,
            )
            .select_from(
                embeddings.join(sessions, sessions.c.id == embeddings.c.session_id)
            )
            .order_by(sessions.c.id)
        )
    )
    if rows:
        state = sa.table(
            "historical_index_state",
            sa.column("id", sa.Integer()),
            sa.column("corpus_hash", sa.String()),
            sa.column("session_count", sa.Integer()),
            sa.column("dimension", sa.Integer()),
            sa.column("artifact_schema_version", sa.Integer()),
            sa.column("built_at", sa.DateTime(timezone=True)),
        )
        connection.execute(
            state.insert().values(
                id=1,
                corpus_hash=_corpus_hash(rows),
                session_count=len(rows),
                dimension=len(_FEATURE_NAMES),
                artifact_schema_version=_ARTIFACT_SCHEMA_VERSION,
                built_at=sa.func.now(),
            )
        )


def downgrade() -> None:
    op.drop_table("historical_index_state")
