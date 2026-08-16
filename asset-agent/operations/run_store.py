import json
import os
import sqlite3
from pathlib import Path
from threading import RLock
from uuid import uuid4

from operations.models import PortfolioSnapshot


_DEFAULT_RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime"
_RUNTIME_DIR = Path(os.getenv("ASSET_RUNTIME_DIR", str(_DEFAULT_RUNTIME_DIR)))
_DB_PATH = _RUNTIME_DIR / "operations.db"


class DailyRunStore:
    """Durable local store for Daily Operations runs and snapshots."""

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self._lock = RLock()
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS daily_runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL,
                    snapshot_json TEXT,
                    changes_json TEXT,
                    monitoring_json TEXT,
                    cio_json TEXT,
                    briefing TEXT,
                    error TEXT
                );

                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES daily_runs(run_id)
                );

                CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_captured_at
                ON portfolio_snapshots(captured_at DESC);
                """
            )

    def start_run(self, started_at: str) -> str:
        run_id = uuid4().hex
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO daily_runs(run_id, started_at, status)
                VALUES (?, ?, 'RUNNING')
                """,
                (run_id, started_at),
            )
        return run_id

    def latest_snapshot(self) -> PortfolioSnapshot | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT snapshot_json
                FROM portfolio_snapshots
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return PortfolioSnapshot.model_validate_json(row["snapshot_json"])

    def save_snapshot(self, run_id: str, snapshot: PortfolioSnapshot) -> None:
        payload = snapshot.model_dump_json()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO portfolio_snapshots(run_id, captured_at, snapshot_json)
                VALUES (?, ?, ?)
                """,
                (run_id, snapshot.captured_at, payload),
            )
            connection.execute(
                "UPDATE daily_runs SET snapshot_json = ? WHERE run_id = ?",
                (payload, run_id),
            )

    def complete_run(
        self,
        run_id: str,
        completed_at: str,
        changes: dict[str, object],
        monitoring: dict[str, object],
        cio: dict[str, object],
        briefing: str | None,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE daily_runs
                SET completed_at = ?,
                    status = 'COMPLETED',
                    changes_json = ?,
                    monitoring_json = ?,
                    cio_json = ?,
                    briefing = ?,
                    error = NULL
                WHERE run_id = ?
                """,
                (
                    completed_at,
                    json.dumps(changes, ensure_ascii=False),
                    json.dumps(monitoring, ensure_ascii=False),
                    json.dumps(cio, ensure_ascii=False),
                    briefing,
                    run_id,
                ),
            )

    def fail_run(self, run_id: str, completed_at: str, error: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE daily_runs
                SET completed_at = ?, status = 'FAILED', error = ?
                WHERE run_id = ?
                """,
                (completed_at, error, run_id),
            )

    def latest_run(self) -> dict[str, object] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM daily_runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()

        if row is None:
            return None

        result = dict(row)
        for key in ("snapshot_json", "changes_json", "monitoring_json", "cio_json"):
            raw = result.pop(key, None)
            result[key.removesuffix("_json")] = json.loads(raw) if raw else None
        return result

    def recent_run_summaries(self, limit: int = 7) -> list[dict[str, object]]:
        safe_limit = max(1, min(limit, 30))
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT run_id, started_at, completed_at, status,
                       changes_json, monitoring_json, cio_json, briefing, error
                FROM daily_runs
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

        summaries: list[dict[str, object]] = []
        for row in rows:
            changes = json.loads(row["changes_json"]) if row["changes_json"] else None
            monitoring = (
                json.loads(row["monitoring_json"]) if row["monitoring_json"] else None
            )
            cio = json.loads(row["cio_json"]) if row["cio_json"] else None

            summaries.append(
                {
                    "run_id": row["run_id"],
                    "started_at": row["started_at"],
                    "completed_at": row["completed_at"],
                    "status": row["status"],
                    "material_change": cio.get("material_change") if cio else None,
                    "escalation": cio.get("escalation") if cio else None,
                    "ceo_action_required": (
                        cio.get("ceo_action_required") if cio else None
                    ),
                    "summary": cio.get("summary") if cio else None,
                    "affected_tickers": cio.get("affected_tickers", []) if cio else [],
                    "change_count": len(changes.get("changes", [])) if changes else 0,
                    "finding_count": (
                        len(monitoring.get("findings", [])) if monitoring else 0
                    ),
                    "has_briefing": bool(row["briefing"]),
                    "error": row["error"],
                }
            )

        return summaries


RUN_STORE = DailyRunStore()
