import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock


DAILY_WORKFLOW_STEPS = (
    "SNAPSHOT_READY",
    "DATA_READY",
    "MONITORING_READY",
    "CIO_READY",
    "BRIEFING_READY",
    "APPROVAL_READY",
)

_DEFAULT_RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime"
_RUNTIME_DIR = Path(os.getenv("ASSET_RUNTIME_DIR", str(_DEFAULT_RUNTIME_DIR)))
_DB_PATH = _RUNTIME_DIR / "operations.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DailyCheckpointStore:
    """Durable stage checkpoints for resumable Daily Operations workflows."""

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
                CREATE TABLE IF NOT EXISTS daily_run_checkpoints (
                    run_id TEXT NOT NULL,
                    step TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    error TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY(run_id, step)
                );

                CREATE INDEX IF NOT EXISTS idx_daily_run_checkpoints_run
                ON daily_run_checkpoints(run_id, started_at);
                """
            )

    @staticmethod
    def _validate_step(step: str) -> str:
        normalized = step.strip().upper()
        if normalized not in DAILY_WORKFLOW_STEPS:
            raise ValueError(f"Unsupported Daily Operations checkpoint: {step}")
        return normalized

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, object]:
        result = dict(row)
        raw = result.pop("payload_json", None)
        result["payload"] = json.loads(raw) if raw else None
        return result

    def begin(self, run_id: str, step: str) -> dict[str, object]:
        normalized = self._validate_step(step)
        started_at = _now_iso()
        with self._lock, self._connect() as connection:
            existing = connection.execute(
                """
                SELECT status, attempt_count FROM daily_run_checkpoints
                WHERE run_id = ? AND step = ?
                """,
                (run_id, normalized),
            ).fetchone()
            if existing is not None and existing["status"] == "COMPLETED":
                return self.get(run_id, normalized) or {}

            if existing is None:
                connection.execute(
                    """
                    INSERT INTO daily_run_checkpoints(
                        run_id, step, status, payload_json, started_at,
                        completed_at, error, attempt_count
                    ) VALUES (?, ?, 'RUNNING', NULL, ?, NULL, NULL, 1)
                    """,
                    (run_id, normalized, started_at),
                )
            else:
                connection.execute(
                    """
                    UPDATE daily_run_checkpoints
                    SET status = 'RUNNING', payload_json = NULL,
                        started_at = ?, completed_at = NULL, error = NULL,
                        attempt_count = attempt_count + 1
                    WHERE run_id = ? AND step = ?
                    """,
                    (started_at, run_id, normalized),
                )
        return self.get(run_id, normalized) or {}

    def complete(
        self,
        run_id: str,
        step: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        normalized = self._validate_step(step)
        completed_at = _now_iso()
        encoded = json.dumps(payload, ensure_ascii=False)
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE daily_run_checkpoints
                SET status = 'COMPLETED', payload_json = ?, completed_at = ?,
                    error = NULL
                WHERE run_id = ? AND step = ? AND status = 'RUNNING'
                """,
                (encoded, completed_at, run_id, normalized),
            )
            if cursor.rowcount != 1:
                existing = connection.execute(
                    """
                    SELECT status FROM daily_run_checkpoints
                    WHERE run_id = ? AND step = ?
                    """,
                    (run_id, normalized),
                ).fetchone()
                if existing is None:
                    raise RuntimeError(
                        f"Checkpoint was not started: {run_id}/{normalized}"
                    )
                if existing["status"] != "COMPLETED":
                    raise RuntimeError(
                        f"Checkpoint cannot complete from {existing['status']}: "
                        f"{run_id}/{normalized}"
                    )
        return self.get(run_id, normalized) or {}

    def fail(self, run_id: str, step: str, error: str) -> None:
        normalized = self._validate_step(step)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE daily_run_checkpoints
                SET status = 'FAILED', completed_at = ?, error = ?
                WHERE run_id = ? AND step = ? AND status = 'RUNNING'
                """,
                (_now_iso(), error, run_id, normalized),
            )

    def interrupt_running(self, run_id: str, reason: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE daily_run_checkpoints
                SET status = 'INTERRUPTED', completed_at = ?, error = ?
                WHERE run_id = ? AND status = 'RUNNING'
                """,
                (_now_iso(), reason, run_id),
            )

    def get(self, run_id: str, step: str) -> dict[str, object] | None:
        normalized = self._validate_step(step)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM daily_run_checkpoints
                WHERE run_id = ? AND step = ?
                """,
                (run_id, normalized),
            ).fetchone()
        return self._row_to_dict(row) if row is not None else None

    def completed_payload(
        self,
        run_id: str,
        step: str,
    ) -> dict[str, object] | None:
        checkpoint = self.get(run_id, step)
        if checkpoint is None or checkpoint["status"] != "COMPLETED":
            return None
        payload = checkpoint.get("payload")
        return dict(payload) if isinstance(payload, dict) else None

    def list_for_run(self, run_id: str) -> list[dict[str, object]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM daily_run_checkpoints
                WHERE run_id = ?
                ORDER BY CASE step
                    WHEN 'SNAPSHOT_READY' THEN 1
                    WHEN 'DATA_READY' THEN 2
                    WHEN 'MONITORING_READY' THEN 3
                    WHEN 'CIO_READY' THEN 4
                    WHEN 'BRIEFING_READY' THEN 5
                    WHEN 'APPROVAL_READY' THEN 6
                    ELSE 99
                END
                """,
                (run_id,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def next_step(self, run_id: str) -> str | None:
        completed = {
            str(item["step"])
            for item in self.list_for_run(run_id)
            if item["status"] == "COMPLETED"
        }
        return next((step for step in DAILY_WORKFLOW_STEPS if step not in completed), None)


CHECKPOINT_STORE = DailyCheckpointStore()
