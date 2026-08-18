import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api.auth import get_configured_api_token, require_api_token
from api.job_store import JOB_STORE
from api.service import (
    ActiveJobError,
    RetryJobError,
    recover_interrupted_work,
    retry_job,
    start_daily_operations,
    start_job,
)
from operations.approval_store import APPROVAL_STORE, ApprovalStoreError
from operations.run_store import RUN_STORE


class JobRequest(BaseModel):
    command: str = Field(min_length=1, max_length=500)


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["APPROVED", "DEFERRED", "REJECTED", "ACKNOWLEDGED"]
    note: str | None = Field(default=None, max_length=1000)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Fail closed: never serve portfolio or approval data without a strong token.
    get_configured_api_token()
    recover_interrupted_work()
    yield


app = FastAPI(
    title="Asset Management HQ API",
    description=(
        "Read-only brokerage bridge and CEO operating API for the Python "
        "investment-agent company. Approval decisions are recorded but never "
        "place, modify, or cancel brokerage orders."
    ),
    version="0.6.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

protected_api = APIRouter(dependencies=[Depends(require_api_token)])


allowed_origins = [
    origin.strip()
    for origin in os.getenv("ASSET_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "asset-management-hq-api",
        "mode": os.getenv("ASSET_ENV", "UNKNOWN"),
        "branch": os.getenv("ASSET_BRANCH", "unknown"),
    }


@protected_api.get("/api/v1/auth/check")
def check_authentication() -> dict[str, bool]:
    return {"authenticated": True}


@protected_api.post("/api/v1/jobs", status_code=status.HTTP_202_ACCEPTED)
def create_job(request: JobRequest) -> dict[str, object]:
    command = request.command.strip()
    if not command:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="command must not be blank",
        )

    try:
        job = start_job(command)
    except ActiveJobError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Another job is already running.",
                "active_job_id": exc.job_id,
            },
        ) from exc

    return {
        **job,
        "poll_path": f"/api/v1/jobs/{job['job_id']}",
        "hq_state_path": "/api/v1/hq/state",
    }


@protected_api.post("/api/v1/operations/daily", status_code=status.HTTP_202_ACCEPTED)
def create_daily_operations_job() -> dict[str, object]:
    """Manually start one SYSTEM Daily Operations cycle for validation."""
    try:
        job = start_daily_operations()
    except ActiveJobError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Another job is already running.",
                "active_job_id": exc.job_id,
            },
        ) from exc

    return {
        **job,
        "poll_path": f"/api/v1/jobs/{job['job_id']}",
        "latest_daily_path": "/api/v1/operations/daily/latest",
        "hq_state_path": "/api/v1/hq/state",
    }


@protected_api.get("/api/v1/operations/daily/latest")
def get_latest_daily_operations() -> dict[str, object]:
    latest = RUN_STORE.latest_run()
    if latest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no Daily Operations run has been recorded yet",
        )
    return latest


@protected_api.get("/api/v1/operations/daily/history")
def get_daily_operations_history() -> dict[str, object]:
    return {
        "runs": RUN_STORE.recent_run_summaries(7),
    }


@protected_api.get("/api/v1/approvals")
def get_approvals(queue_status: str | None = None, limit: int = 20) -> dict[str, object]:
    normalized = queue_status.upper() if queue_status else None
    return {
        "items": APPROVAL_STORE.list(status=normalized, limit=limit),
    }


@protected_api.post("/api/v1/approvals/{approval_id}/decision")
def decide_approval(
    approval_id: str,
    request: ApprovalDecisionRequest,
) -> dict[str, object]:
    """Record a CEO decision only. This endpoint never executes a trade."""
    try:
        return APPROVAL_STORE.decide(
            approval_id=approval_id,
            decision=request.decision,
            note=request.note.strip() if request.note else None,
        )
    except ApprovalStoreError as exc:
        message = str(exc)
        http_status = (
            status.HTTP_404_NOT_FOUND
            if "not found" in message.lower()
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=http_status, detail=message) from exc


@protected_api.get("/api/v1/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, object]:
    recover_interrupted_work()
    job = JOB_STORE.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="job not found",
        )
    return job


@protected_api.post("/api/v1/jobs/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_interrupted_job(job_id: str) -> dict[str, object]:
    """Create a new job linked to a failed one; never place a brokerage order."""
    try:
        job = retry_job(job_id)
    except ActiveJobError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Another job is already running.",
                "active_job_id": exc.job_id,
            },
        ) from exc
    except RetryJobError as exc:
        http_status = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(exc).lower()
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=http_status, detail=str(exc)) from exc

    return {
        **job,
        "poll_path": f"/api/v1/jobs/{job['job_id']}",
        "hq_state_path": "/api/v1/hq/state",
    }


@protected_api.get("/api/v1/hq/state")
def get_hq_state() -> dict[str, object]:
    recover_interrupted_work()
    return JOB_STORE.latest_hq_state()


app.include_router(protected_api)
