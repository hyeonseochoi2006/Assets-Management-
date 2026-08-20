import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from ceo_desk.hq_state import new_hq_agents


_DEFAULT_RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime"
_RUNTIME_DIR = Path(os.getenv("ASSET_RUNTIME_DIR", str(_DEFAULT_RUNTIME_DIR)))
_DB_PATH = _RUNTIME_DIR / "operations.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DailyRecoveryStore:
    """Coordinate crash recovery across jobs, Daily runs, and schedule state."""

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self._lock = RLock()
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(daily_runs)"
                ).fetchall()
            }
            if columns and "resume_count" not in columns:
                connection.execute(
                    "ALTER TABLE daily_runs ADD COLUMN resume_count INTEGER NOT NULL DEFAULT 0"
                )

    def snapshot_saved(self, run_id: str) -> bool:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM portfolio_snapshots
                WHERE run_id = ?
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()
        return row is not None

    def recoverable_jobs(self, limit: int = 20) -> list[dict[str, object]]:
        safe_limit = max(1, min(limit, 100))
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    j.job_id,
                    j.action,
                    j.schedule_key,
                    j.status AS job_status,
                    r.run_id,
                    r.status AS run_status,
                    r.run_kind,
                    r.started_at,
                    r.briefing,
                    r.cio_json,
                    COALESCE(r.resume_count, 0) AS resume_count
                FROM agent_jobs AS j
                LEFT JOIN daily_runs AS r ON r.job_id = j.job_id
                WHERE j.source = 'SYSTEM'
                  AND j.action IN ('DAILY_OPERATIONS', 'DAILY_SCAN')
                  AND j.status = 'INTERRUPTED'
                ORDER BY j.created_at ASC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def prepare_run_resume(
        self,
        run_id: str,
        job_id: str,
        run_kind: str,
    ) -> dict[str, object]:
        if run_kind not in {"SCAN", "CLOSE"}:
            raise ValueError("run_kind must be SCAN or CLOSE")
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM daily_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"Daily run not found for resume: {run_id}")
            if row["status"] not in {"INTERRUPTED", "FAILED", "RUNNING"}:
                raise RuntimeError(
                    f"Daily run cannot resume from {row['status']}: {run_id}"
                )
            if row["run_kind"] != run_kind:
                raise RuntimeError(
                    f"Daily run kind mismatch: stored={row['run_kind']} requested={run_kind}"
                )
            connection.execute(
                """
                UPDATE daily_runs
                SET job_id = ?, status = 'RUNNING', completed_at = NULL,
                    error = NULL, resume_count = COALESCE(resume_count, 0) + 1
                WHERE run_id = ?
                """,
                (job_id, run_id),
            )
            updated = connection.execute(
                "SELECT * FROM daily_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return dict(updated) if updated is not None else {}

    def requeue_interrupted_job(self, job_id: str) -> bool:
        agents_json = json.dumps(new_hq_agents(), ensure_ascii=False)
        now = _now_iso()
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            active = connection.execute(
                """
                SELECT job_id FROM agent_jobs
                WHERE status IN ('QUEUED', 'RUNNING') AND job_id != ?
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
            if active is not None:
                connection.rollback()
                return False
            cursor = connection.execute(
                """
                UPDATE agent_jobs
                SET status = 'QUEUED', started_at = NULL, completed_at = NULL,
                    agents_json = ?, result_type = NULL, result = NULL,
                    error = NULL, worker_id = NULL, heartbeat_at = NULL,
                    lease_expires_at = NULL
                WHERE job_id = ? AND status = 'INTERRUPTED'
                """,
                (agents_json, job_id),
            )
            if cursor.rowcount == 1:
                connection.execute(
                    """
                    UPDATE daily_schedule_events
                    SET status = 'QUEUED', reason = ?, updated_at = ?
                    WHERE job_id = ?
                    """,
                    ("Automatic worker is resuming interrupted work.", now, job_id),
                )
            connection.commit()
        return cursor.rowcount == 1

    def restore_completed_job(
        self,
        job_id: str,
        result: str,
        result_type: str = "markdown",
    ) -> bool:
        now = _now_iso()
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE agent_jobs
                SET status = 'COMPLETED', result = ?, result_type = ?,
                    completed_at = ?, error = NULL, worker_id = NULL,
                    heartbeat_at = NULL, lease_expires_at = NULL
                WHERE job_id = ? AND status = 'INTERRUPTED'
                """,
                (result, result_type, now, job_id),
            )
            if cursor.rowcount == 1:
                connection.execute(
                    """
                    UPDATE daily_schedule_events
                    SET status = 'COMPLETED', reason = NULL, updated_at = ?
                    WHERE job_id = ?
                    """,
                    (now, job_id),
                )
        return cursor.rowcount == 1


DAILY_RECOVERY_STORE = DailyRecoveryStore()
