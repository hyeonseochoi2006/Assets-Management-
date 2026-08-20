import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock


_DEFAULT_RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime"
_RUNTIME_DIR = Path(os.getenv("ASSET_RUNTIME_DIR", str(_DEFAULT_RUNTIME_DIR)))
_DB_PATH = _RUNTIME_DIR / "operations.db"
SCHEDULER_WORKER_NAME = "asset-scheduler-worker"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WorkerAlreadyRunningError(RuntimeError):
    def __init__(self, worker_id: str) -> None:
        self.worker_id = worker_id
        super().__init__(f"Scheduler worker is already running: {worker_id}")


class WorkerRuntimeStore:
    """Durable singleton lease and heartbeat for the automatic scheduler worker."""

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
                CREATE TABLE IF NOT EXISTS worker_runtime (
                    worker_name TEXT PRIMARY KEY,
                    worker_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    hostname TEXT NOT NULL,
                    pid INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    heartbeat_at TEXT NOT NULL,
                    lease_expires_at TEXT NOT NULL,
                    stopped_at TEXT,
                    last_error TEXT,
                    scheduler_snapshot_json TEXT
                );
                """
            )

    @staticmethod
    def _decode_snapshot(raw: object) -> dict[str, object] | None:
        if raw is None:
            return None
        try:
            value = json.loads(str(raw))
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _lease_is_live(row: sqlite3.Row, now: datetime) -> bool:
        if str(row["status"]) != "RUNNING":
            return False
        try:
            lease_expires = datetime.fromisoformat(str(row["lease_expires_at"]))
        except ValueError:
            return False
        return lease_expires > now

    def acquire(
        self,
        *,
        worker_id: str,
        hostname: str,
        pid: int,
        scheduler_snapshot: dict[str, object] | None = None,
        now: datetime | None = None,
    ) -> dict[str, object]:
        acquired_at = now or _now()
        lease_expires_at = acquired_at + timedelta(seconds=self._lease_seconds)
        snapshot_json = (
            json.dumps(scheduler_snapshot, ensure_ascii=False)
            if scheduler_snapshot is not None
            else None
        )

        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM worker_runtime WHERE worker_name = ?",
                (SCHEDULER_WORKER_NAME,),
            ).fetchone()
            if (
                row is not None
                and str(row["worker_id"]) != worker_id
                and self._lease_is_live(row, acquired_at)
            ):
                connection.rollback()
                raise WorkerAlreadyRunningError(str(row["worker_id"]))

            connection.execute(
                """
                INSERT INTO worker_runtime(
                    worker_name, worker_id, status, hostname, pid,
                    started_at, heartbeat_at, lease_expires_at,
                    stopped_at, last_error, scheduler_snapshot_json
                )
                VALUES (?, ?, 'RUNNING', ?, ?, ?, ?, ?, NULL, NULL, ?)
                ON CONFLICT(worker_name) DO UPDATE SET
                    worker_id = excluded.worker_id,
                    status = 'RUNNING',
                    hostname = excluded.hostname,
                    pid = excluded.pid,
                    started_at = excluded.started_at,
                    heartbeat_at = excluded.heartbeat_at,
                    lease_expires_at = excluded.lease_expires_at,
                    stopped_at = NULL,
                    last_error = NULL,
                    scheduler_snapshot_json = excluded.scheduler_snapshot_json
                """,
                (
                    SCHEDULER_WORKER_NAME,
                    worker_id,
                    hostname,
                    pid,
                    acquired_at.isoformat(),
                    acquired_at.isoformat(),
                    lease_expires_at.isoformat(),
                    snapshot_json,
                ),
            )
            connection.commit()
        return self.status(now=acquired_at) or {}

    def heartbeat(
        self,
        worker_id: str,
        scheduler_snapshot: dict[str, object] | None = None,
        now: datetime | None = None,
    ) -> bool:
        heartbeat_at = now or _now()
        lease_expires_at = heartbeat_at + timedelta(seconds=self._lease_seconds)
        snapshot_json = (
            json.dumps(scheduler_snapshot, ensure_ascii=False)
            if scheduler_snapshot is not None
            else None
        )
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE worker_runtime
                SET heartbeat_at = ?, lease_expires_at = ?,
                    scheduler_snapshot_json = COALESCE(?, scheduler_snapshot_json)
                WHERE worker_name = ? AND worker_id = ? AND status = 'RUNNING'
                """,
                (
                    heartbeat_at.isoformat(),
                    lease_expires_at.isoformat(),
                    snapshot_json,
                    SCHEDULER_WORKER_NAME,
                    worker_id,
                ),
            )
        return cursor.rowcount == 1

    def record_error(self, worker_id: str, error: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE worker_runtime
                SET last_error = ?
                WHERE worker_name = ? AND worker_id = ?
                """,
                (error, SCHEDULER_WORKER_NAME, worker_id),
            )

    def release(
        self,
        worker_id: str,
        *,
        error: str | None = None,
        now: datetime | None = None,
    ) -> bool:
        stopped_at = now or _now()
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE worker_runtime
                SET status = 'STOPPED', stopped_at = ?, heartbeat_at = ?,
                    lease_expires_at = ?, last_error = COALESCE(?, last_error)
                WHERE worker_name = ? AND worker_id = ? AND status = 'RUNNING'
                """,
                (
                    stopped_at.isoformat(),
                    stopped_at.isoformat(),
                    stopped_at.isoformat(),
                    error,
                    SCHEDULER_WORKER_NAME,
                    worker_id,
                ),
            )
        return cursor.rowcount == 1

    def status(self, now: datetime | None = None) -> dict[str, object] | None:
        checked_at = now or _now()
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM worker_runtime WHERE worker_name = ?",
                (SCHEDULER_WORKER_NAME,),
            ).fetchone()
        if row is None:
            return None

        result = dict(row)
        result["scheduler_snapshot"] = self._decode_snapshot(
            result.pop("scheduler_snapshot_json", None)
        )
        live = self._lease_is_live(row, checked_at)
        result["healthy"] = live
        if result["status"] == "RUNNING" and not live:
            result["status"] = "STALE"
        return result


WORKER_STORE = WorkerRuntimeStore()
