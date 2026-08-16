import os

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api.job_store import JOB_STORE
from api.service import ActiveJobError, start_daily_operations, start_job
from operations.run_store import RUN_STORE


class JobRequest(BaseModel):
    command: str = Field(min_length=1, max_length=500)


app = FastAPI(
    title="Asset Management HQ API",
    description=(
        "Read-only bridge between the future React/3D HQ and the existing "
        "Python investment-agent company. This API does not place brokerage orders."
    ),
    version="0.2.0",
)


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
        allow_headers=["*"],
    )


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "asset-management-hq-api",
        "mode": os.getenv("ASSET_ENV", "UNKNOWN"),
        "branch": os.getenv("ASSET_BRANCH", "unknown"),
    }


@app.post("/api/v1/jobs", status_code=status.HTTP_202_ACCEPTED)
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


@app.post("/api/v1/operations/daily", status_code=status.HTTP_202_ACCEPTED)
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


@app.get("/api/v1/operations/daily/latest")
def get_latest_daily_operations() -> dict[str, object]:
    latest = RUN_STORE.latest_run()
    if latest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no Daily Operations run has been recorded yet",
        )
    return latest


@app.get("/api/v1/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, object]:
    job = JOB_STORE.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="job not found",
        )
    return job


@app.get("/api/v1/hq/state")
def get_hq_state() -> dict[str, object]:
    return JOB_STORE.latest_hq_state()
