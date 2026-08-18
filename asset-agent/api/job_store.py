import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

from ceo_desk.hq_state import hq_snapshot, mark_active_errors, new_hq_agents, update_agent


JOB_STATUSES = {"QUEUED", "RUNNING", "COMPLETED", "FAILED", "INTERRUPTED"}
ACTIVE_JOB_STATUSES = {"QUEUED", "RUNNING"}
JOB_SOURCES = {"CEO", "SYSTEM"}

_DEFAULT_RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime"
_RUNTIME_DIR = Path(os.getenv("ASSET_RUNTIME_DIR", str(_DEFAULT_RUNTIME_DIR)))
_DB_PATH = _RUNTIME_DIR / "operations.db"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


class ActiveJobExistsError(RuntimeError):
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(f"Another job is already active: {job_id}")


class JobStore:
    """SQLite-backed store for frontend-visible Agent jobs.

    SQLite keeps job history available after an API restart. A database-level
    partial unique index enforces one active job even when multiple API workers
    race to create work.
    """

    def __init__(self, db_path: Path = _DB_PATH, lease_seconds: int = 90) -> None:
        self._lock = RLock()
        self._db_path = db_path
        self._lease_seconds = max(30, lease_seconds)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_jobs (
                    job_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    command TEXT NOT NULL,
                    action TEXT NOT NULL,
                    ticker TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    agents_json TEXT NOT NULL,
                    result_type TEXT,
                    result TEXT,
                    error TEXT,
                    worker_id TEXT,
                    heartbeat_at TEXT,
                    lease_expires_at TEXT,
                    retry_of TEXT,
                    FOREIGN KEY(retry_of) REFERENCES agent_jobs(job_id)
                );

                CREATE INDEX IF NOT EXISTS idx_agent_jobs_created
                ON agent_jobs(created_at DESC);

                CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_jobs_single_active
                ON agent_jobs((1))
                WHERE status IN ('QUEUED', 'RUNNING');
                """
            )

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> dict[str, object]:
        job = dict(row)
        job["agents"] = json.loads(str(job.pop("agents_json")))
        job.pop("worker_id", None)
        job.pop("heartbeat_at", None)
        job.pop("lease_expires_at", None)
        return job

    @staticmethod
    def _mark_interrupted_agents(raw_agents: str) -> str:
        agents = json.loads(raw_agents)
        return json.dumps(mark_active_errors(agents), ensure_ascii=False)

    def create_job(
        self,
        command: str,
        action: str,
        ticker: str | None,
        source: str = "CEO",
        retry_of: str | None = None,
    ) -> dict[str, object]:
        if source not in JOB_SOURCES:
            raise ValueError(f"Unsupported job source: {source}")

        job_id = uuid4().hex
        created_at = _now_iso()
        agents_json = json.dumps(new_hq_agents(), ensure_ascii=False)

        with self._lock, self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO agent_jobs(
                        job_id, source, command, action, ticker, status,
                        created_at, agents_json, retry_of
                    )
                    VALUES (?, ?, ?, ?, ?, 'QUEUED', ?, ?, ?)
                    """,
                    (
                        job_id,
                        source,
                        command,
                        action,
                        ticker,
                        created_at,
                        agents_json,
                        retry_of,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                active = connection.execute(
                    """
                    SELECT job_id FROM agent_jobs
                    WHERE status IN ('QUEUED', 'RUNNING')
                    ORDER BY created_at DESC LIMIT 1
                    """
                ).fetchone()
                if active is not None:
                    raise ActiveJobExistsError(str(active["job_id"])) from exc
                raise

        return self.get_job(job_id) or {}

    def get_job(self, job_id: str) -> dict[str, object] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM agent_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return self._row_to_job(row) if row is not None else None

    def latest_job(self) -> dict[str, object] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM agent_jobs ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return self._row_to_job(row) if row is not None else None

    def active_job_id(self) -> str | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT job_id FROM agent_jobs
                WHERE status IN ('QUEUED', 'RUNNING')
                ORDER BY created_at ASC LIMIT 1
                """
            ).fetchone()
        return str(row["job_id"]) if row is not None else None

    def mark_running(self, job_id: str, worker_id: str) -> None:
        now = _now()
        lease_expires_at = (now + timedelta(seconds=self._lease_seconds)).isoformat()
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE agent_jobs
                SET status = 'RUNNING', started_at = ?, worker_id = ?,
                    heartbeat_at = ?, lease_expires_at = ?
                WHERE job_id = ? AND status = 'QUEUED'
                """,
                (now.isoformat(), worker_id, now.isoformat(), lease_expires_at, job_id),
            )
        if cursor.rowcount != 1:
            raise RuntimeError(f"Job cannot transition to RUNNING: {job_id}")

    def heartbeat(self, job_id: str, worker_id: str) -> bool:
        now = _now()
        lease_expires_at = (now + timedelta(seconds=self._lease_seconds)).isoformat()
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE agent_jobs
                SET heartbeat_at = ?, lease_expires_at = ?
                WHERE job_id = ? AND status = 'RUNNING' AND worker_id = ?
                """,
                (now.isoformat(), lease_expires_at, job_id, worker_id),
            )
        return cursor.rowcount == 1

    def update_agent(
        self,
        job_id: str,
        agent: str,
        status: str,
        task: str | None = None,
    ) -> None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT agents_json FROM agent_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            agents = json.loads(row["agents_json"])
            agents = update_agent(agents, agent, status, task)
            connection.execute(
                """
                UPDATE agent_jobs SET agents_json = ?
                WHERE job_id = ? AND status = 'RUNNING'
                """,
                (json.dumps(agents, ensure_ascii=False), job_id),
            )

    def complete_job(self, job_id: str, result: str, result_type: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE agent_jobs
                SET status = 'COMPLETED', result = ?, result_type = ?,
                    completed_at = ?, error = NULL, worker_id = NULL,
                    heartbeat_at = NULL, lease_expires_at = NULL
                WHERE job_id = ? AND status = 'RUNNING'
                """,
                (result, result_type, _now_iso(), job_id),
            )

    def fail_job(self, job_id: str, error: str) -> None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT agents_json FROM agent_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                return
            agents_json = self._mark_interrupted_agents(row["agents_json"])
            connection.execute(
                """
                UPDATE agent_jobs
                SET agents_json = ?, status = 'FAILED', error = ?,
                    completed_at = ?, worker_id = NULL, heartbeat_at = NULL,
                    lease_expires_at = NULL
                WHERE job_id = ? AND status IN ('QUEUED', 'RUNNING')
                """,
                (agents_json, error, _now_iso(), job_id),
            )

    def recover_stale_jobs(self, now: datetime | None = None) -> list[str]:
        recovery_time = now or _now()
        recovery_iso = recovery_time.isoformat()
        queued_before_iso = (
            recovery_time - timedelta(seconds=self._lease_seconds)
        ).isoformat()
        error = "Server stopped before this job completed. Review it and retry safely."

        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT job_id, agents_json FROM agent_jobs
                WHERE (status = 'QUEUED' AND created_at <= ?)
                   OR (status = 'RUNNING' AND lease_expires_at <= ?)
                """,
                (queued_before_iso, recovery_iso),
            ).fetchall()
            recovered_ids: list[str] = []
            for row in rows:
                cursor = connection.execute(
                    """
                    UPDATE agent_jobs
                    SET status = 'INTERRUPTED', agents_json = ?, error = ?,
                        completed_at = ?, worker_id = NULL, heartbeat_at = NULL,
                        lease_expires_at = NULL
                    WHERE job_id = ?
                      AND ((status = 'QUEUED' AND created_at <= ?)
                        OR (status = 'RUNNING' AND lease_expires_at <= ?))
                    """,
                    (
                        self._mark_interrupted_agents(row["agents_json"]),
                        error,
                        recovery_iso,
                        row["job_id"],
                        queued_before_iso,
                        recovery_iso,
                    ),
                )
                if cursor.rowcount == 1:
                    recovered_ids.append(str(row["job_id"]))
        return recovered_ids

    def latest_hq_state(self) -> dict[str, object]:
        job = self.latest_job()
        if job is None:
            snapshot = hq_snapshot(new_hq_agents())
            return {
                "latest_job_id": None,
                "job_status": "IDLE",
                "source": None,
                "action": None,
                **snapshot,
            }

        snapshot = hq_snapshot(job["agents"])
        return {
            "latest_job_id": job["job_id"],
            "job_status": job["status"],
            "source": job["source"],
            "action": job["action"],
            "command": job["command"],
            "ticker": job["ticker"],
            **snapshot,
        }


JOB_STORE = JobStore()
