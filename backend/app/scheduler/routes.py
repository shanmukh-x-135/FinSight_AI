"""Protected operational reads for the external EOD control plane."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_admin_user
from app.auth.models import User
from app.scheduler.constants import EOD_PIPELINE_NAME, PipelineRunStatus
from app.scheduler.repository import PipelineRunRepository
from app.scheduler.schemas import EODStatusOut, PipelineRunOut
from app.shared.database import get_db
from app.shared.response import envelope

scheduler_admin_router = APIRouter(prefix="/admin/jobs/eod", tags=["admin"])


@scheduler_admin_router.get(
    "/status",
    summary="Inspect the latest or selected EOD pipeline run",
    description=(
        "Read-only operational status. Failed, partial, pending, or absent runs "
        "can be safely retried through the external one-shot runner."
    ),
)
async def eod_status(
    target_trading_date: date | None = Query(default=None),
    _user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    repository = PipelineRunRepository(db)
    run = (
        await repository.get_run(EOD_PIPELINE_NAME, target_trading_date)
        if target_trading_date is not None
        else await repository.get_latest_run(EOD_PIPELINE_NAME)
    )
    rerun_recommended = run is None or run.status in {
        PipelineRunStatus.PENDING,
        PipelineRunStatus.PARTIAL,
        PipelineRunStatus.FAILED,
    }
    status = EODStatusOut(
        pipeline_name=EOD_PIPELINE_NAME,
        requested_trading_date=target_trading_date,
        run=PipelineRunOut.model_validate(run) if run is not None else None,
        rerun_recommended=rerun_recommended,
    )
    message = "No matching EOD run exists." if run is None else "EOD status loaded."
    return envelope(data=status.model_dump(mode="json"), message=message)
