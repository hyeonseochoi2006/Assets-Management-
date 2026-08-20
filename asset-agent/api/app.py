import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api.auth import get_configured_api_token, require_api_token
from api.job_store import JOB_STORE
from api.scheduler import DailyScheduleConfig
from api.service import (
    ActiveJobError,
    RetryJobError,
    recover_interrupted_work,
    retry_job,
    start_daily_operations,
    start_job,
)
from operations.approval_store import APPROVAL_STORE, ApprovalStoreError
from operations.checkpoint_store import CHECKPOINT_STORE
from operations.run_store import RUN_STORE
from operations.schedule_store import SCHEDULE_STORE
from operations.worker_store import WORKER_STORE


class JobRequest(BaseModel):
    command: str = Field(min_length=1, max_length=500)


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["APPROVED", "DEFERRED", "REJECTED", "ACKNOWLEDGED"]
    note: str | None = Field(default=None, max_length=1000)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Fail closed: never serve portfolio or approval data without a strong token.
    get_configured_api_token()
    # State cleanup is safe here, but the recurring scheduler is deliberately
    # NOT started by the API. Automatic scheduling belongs to worker.py.
    recover_interrupted_work()
    yield


app = FastAPI(
    title="Asset Management HQ API",
    description=(
        "Read-only brokerage bridge and CEO operating API for the Python "
        "investment-agent company. Recurring scheduling runs in the separate "
        "asset worker. Approval decisions are recorded but never place, modify, "
        "or cancel brokerage orders."
    ),
    version="0.9.0",
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


def _configured_schedule_fallback() -> dict[str, object]:
    """Describe configured schedule when no live worker snapshot exists yet."""
    config = DailyScheduleConfig.from_env()
    return {
        "enabled": config.enabled,
        "daily_time": (
            config.daily_time.strftime("%H:%M")
            if config.daily_time is not None
            else None
        ),
        "scan_times": [item.strftime("%H:%M") for item in config.scan_times],
        "schedule_times": [
            *[
                {"run_kind": "SCAN", "time": item.strftime("%H:%M")}
                for item in config.scan_times
            ],
            {
                "run_kind": "CLOSE",
                "time": (
                    config.daily_time.strftime("%H:%M")
                    if config.daily_time is not None
                    else None
                ),
            },
        ],
        "timezone": config.timezone_name,
        "misfire_grace_minutes": config.grace_minutes,
        "next_run_at": None,
        "recent_events": SCHEDULE_STORE.recent(7),
    }


def _worker_public_status() -> dict[str, object]:
    worker = WORKER_STORE.status()
    if worker is None:
        return {
            "status": "NOT_STARTED",
            "healthy": False,
            "worker_id": None,
            "heartbeat_at": None,
            "lease_expires_at": None,
            "last_error": None,
        }
    public = dict(worker)
    public.pop("scheduler_snapshot", None)
    return public


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
    run_id = str(latest["run_id"])
    return {
        **latest,
        "checkpoints": CHECKPOINT_STORE.list_for_run(run_id),
        "next_checkpoint": CHECKPOINT_STORE.next_step(run_id),
    }


@protected_api.get("/api/v1/operations/daily/{run_id}/checkpoints")
def get_daily_operation_checkpoints(run_id: str) -> dict[str, object]:
    checkpoints = CHECKPOINT_STORE.list_for_run(run_id)
    if not checkpoints:
        latest = RUN_STORE.latest_run()
        if latest is None or str(latest.get("run_id")) != run_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Daily Operations run or checkpoints not found",
            )
    return {
        "run_id": run_id,
        "checkpoints": checkpoints,
        "next_checkpoint": CHECKPOINT_STORE.next_step(run_id),
    }


@protected_api.get("/api/v1/operations/daily/history")
def get_daily_operations_history() -> dict[str, object]:
    return {
        "runs": RUN_STORE.recent_run_summaries(7),
    }


@protected_api.get("/api/v1/operations/daily/schedule")
def get_daily_operations_schedule() -> dict[str, object]:
    worker = WORKER_STORE.status()
    worker_snapshot = (
        worker.get("scheduler_snapshot")
        if worker and worker.get("healthy") is True
        else None
    )
    schedule = (
        dict(worker_snapshot)
        if isinstance(worker_snapshot, dict)
        else _configured_schedule_fallback()
    )
    return {
        **schedule,
        "execution_owner": "asset-worker",
        "worker": _worker_public_status(),
    }


@protected_api.get("/api/v1/worker/status")
def get_worker_status() -> dict[str, object]:
    """Return the durable heartbeat/lease state of the automatic worker."""
    return _worker_public_status()


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
