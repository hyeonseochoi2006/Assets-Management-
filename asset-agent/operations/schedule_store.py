import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock


_DEFAULT_RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime"
_RUNTIME_DIR = Path(os.getenv("ASSET_RUNTIME_DIR", str(_DEFAULT_RUNTIME_DIR)))
_DB_PATH = _RUNTIME_DIR / "operations.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DailyScheduleStore:
    """Durable audit log for scheduled Daily Operations decisions."""

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
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS daily_schedule_events (
                    schedule_key TEXT PRIMARY KEY,
                    scheduled_for TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    status TEXT NOT NULL,
                    job_id TEXT,
                    reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_daily_schedule_events_created
                ON daily_schedule_events(created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_daily_schedule_events_job
                ON daily_schedule_events(job_id);
                """
            )

    def get(self, schedule_key: str) -> dict[str, object] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM daily_schedule_events
                WHERE schedule_key = ?
                """,
                (schedule_key,),
            ).fetchone()
        return dict(row) if row is not None else None

    def record_job(
        self,
        schedule_key: str,
        scheduled_for: str,
        timezone_name: str,
        job_id: str,
        status: str,
    ) -> dict[str, object]:
        now = _now_iso()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO daily_schedule_events(
                    schedule_key, scheduled_for, timezone, status, job_id,
                    reason, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
                ON CONFLICT(schedule_key) DO UPDATE SET
                    status = excluded.status,
                    job_id = excluded.job_id,
                    reason = NULL,
                    updated_at = excluded.updated_at
                """,
                (
                    schedule_key,
                    scheduled_for,
                    timezone_name,
                    status,
                    job_id,
                    now,
                    now,
                ),
            )
        return self.get(schedule_key) or {}

    def record_skipped(
        self,
        schedule_key: str,
        scheduled_for: str,
        timezone_name: str,
        reason: str,
    ) -> dict[str, object]:
        now = _now_iso()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO daily_schedule_events(
                    schedule_key, scheduled_for, timezone, status, job_id,
                    reason, created_at, updated_at
                )
                VALUES (?, ?, ?, 'SKIPPED', NULL, ?, ?, ?)
                """,
                (schedule_key, scheduled_for, timezone_name, reason, now, now),
            )
        return self.get(schedule_key) or {}

    def finish_job(
        self,
        job_id: str,
        status: str,
        reason: str | None = None,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE daily_schedule_events
                SET status = ?, reason = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (status, reason, _now_iso(), job_id),
            )

    def interrupt_jobs(self, job_ids: list[str], reason: str) -> None:
        if not job_ids:
            return
        placeholders = ",".join("?" for _ in job_ids)
        with self._lock, self._connect() as connection:
            connection.execute(
                f"""
                UPDATE daily_schedule_events
                SET status = 'INTERRUPTED', reason = ?, updated_at = ?
                WHERE job_id IN ({placeholders})
                """,
                (reason, _now_iso(), *job_ids),
            )

    def recent(self, limit: int = 7) -> list[dict[str, object]]:
        safe_limit = max(1, min(limit, 30))
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM daily_schedule_events
                ORDER BY scheduled_for DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]


SCHEDULE_STORE = DailyScheduleStore()
