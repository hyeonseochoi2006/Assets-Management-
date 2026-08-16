from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from ceo_desk.hq_state import hq_snapshot, mark_active_errors, new_hq_agents, update_agent


JOB_STATUSES = {"QUEUED", "RUNNING", "COMPLETED", "FAILED"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    """Thread-safe in-memory store for frontend-visible Agent jobs."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._jobs: dict[str, dict[str, object]] = {}
        self._latest_job_id: str | None = None

    def create_job(
        self,
        command: str,
        action: str,
        ticker: str | None,
    ) -> dict[str, object]:
        with self._lock:
            job_id = uuid4().hex
            job = {
                "job_id": job_id,
                "command": command,
                "action": action,
                "ticker": ticker,
                "status": "QUEUED",
                "created_at": _now_iso(),
                "started_at": None,
                "completed_at": None,
                "agents": new_hq_agents(),
                "result_type": None,
                "result": None,
                "error": None,
            }
            self._jobs[job_id] = job
            self._latest_job_id = job_id
            return deepcopy(job)

    def get_job(self, job_id: str) -> dict[str, object] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return deepcopy(job) if job is not None else None

    def active_job_id(self) -> str | None:
        with self._lock:
            for job_id, job in self._jobs.items():
                if job["status"] in {"QUEUED", "RUNNING"}:
                    return job_id
            return None

    def mark_running(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job["status"] = "RUNNING"
            job["started_at"] = _now_iso()

    def update_agent(
        self,
        job_id: str,
        agent: str,
        status: str,
        task: str | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job["agents"] = update_agent(
                job["agents"],
                agent,
                status,
                task,
            )

    def complete_job(
        self,
        job_id: str,
        result: str,
        result_type: str,
    ) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job["status"] = "COMPLETED"
            job["result"] = result
            job["result_type"] = result_type
            job["completed_at"] = _now_iso()

    def fail_job(self, job_id: str, error: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job["agents"] = mark_active_errors(job["agents"])
            job["status"] = "FAILED"
            job["error"] = error
            job["completed_at"] = _now_iso()

    def latest_hq_state(self) -> dict[str, object]:
        with self._lock:
            if self._latest_job_id is None:
                snapshot = hq_snapshot(new_hq_agents())
                return {
                    "latest_job_id": None,
                    "job_status": "IDLE",
                    **snapshot,
                }

            job = self._jobs[self._latest_job_id]
            snapshot = hq_snapshot(job["agents"])
            return {
                "latest_job_id": self._latest_job_id,
                "job_status": job["status"],
                "command": job["command"],
                "ticker": job["ticker"],
                **snapshot,
            }


JOB_STORE = JobStore()
