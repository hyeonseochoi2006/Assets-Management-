import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4


_DEFAULT_RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime"
_RUNTIME_DIR = Path(os.getenv("ASSET_RUNTIME_DIR", str(_DEFAULT_RUNTIME_DIR)))
_DB_PATH = _RUNTIME_DIR / "operations.db"


class ApprovalStoreError(RuntimeError):
    pass


class ApprovalStore:
    """Durable CEO approval queue.

    Decisions are records only. This store never executes brokerage orders or
    automatically starts additional analysis.
    """

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
                CREATE TABLE IF NOT EXISTS approval_requests (
                    approval_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    reasons_json TEXT NOT NULL,
                    affected_tickers_json TEXT NOT NULL,
                    recommended_next_step TEXT NOT NULL,
                    briefing TEXT,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    created_at TEXT NOT NULL,
                    decided_at TEXT,
                    decision_note TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_approval_requests_status_created
                ON approval_requests(status, created_at DESC);
                """
            )

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_from_cio(
        self,
        *,
        run_id: str,
        category: str,
        summary: str,
        reasons: list[str],
        affected_tickers: list[str],
        recommended_next_step: str,
        briefing: str | None,
    ) -> dict[str, object]:
        title_map = {
            "RISK": "중요 위험 확인",
            "OPPORTUNITY": "투자기회 검토",
            "ANALYSIS_REQUEST": "추가 분석 승인 요청",
            "DECISION": "CEO 투자/정책 결정",
        }
        title = title_map.get(category, "CEO 확인 요청")
        approval_id = uuid4().hex
        created_at = self._now_iso()

        with self._lock, self._connect() as connection:
            existing = connection.execute(
                "SELECT approval_id FROM approval_requests WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if existing is not None:
                return self.get(str(existing["approval_id"])) or {}

            connection.execute(
                """
                INSERT INTO approval_requests(
                    approval_id, run_id, category, title, summary,
                    reasons_json, affected_tickers_json, recommended_next_step,
                    briefing, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                """,
                (
                    approval_id,
                    run_id,
                    category,
                    title,
                    summary,
                    json.dumps(reasons, ensure_ascii=False),
                    json.dumps(affected_tickers, ensure_ascii=False),
                    recommended_next_step,
                    briefing,
                    created_at,
                ),
            )

        return self.get(approval_id) or {}

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, object]:
        result = dict(row)
        result["reasons"] = json.loads(result.pop("reasons_json") or "[]")
        result["affected_tickers"] = json.loads(
            result.pop("affected_tickers_json") or "[]"
        )
        return result

    def get(self, approval_id: str) -> dict[str, object] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM approval_requests WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
        return self._row_to_dict(row) if row is not None else None

    def list(self, status: str | None = None, limit: int = 20) -> list[dict[str, object]]:
        safe_limit = max(1, min(limit, 50))
        with self._lock, self._connect() as connection:
            if status:
                rows = connection.execute(
                    """
                    SELECT * FROM approval_requests
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (status, safe_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM approval_requests
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def decide(
        self,
        approval_id: str,
        decision: str,
        note: str | None = None,
    ) -> dict[str, object]:
        allowed = {"APPROVED", "DEFERRED", "REJECTED", "ACKNOWLEDGED"}
        if decision not in allowed:
            raise ApprovalStoreError(f"Unsupported decision: {decision}")

        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM approval_requests WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
            if row is None:
                raise ApprovalStoreError("Approval request not found.")
            if row["status"] != "PENDING":
                raise ApprovalStoreError(
                    f"Approval request is already resolved: {row['status']}"
                )

            connection.execute(
                """
                UPDATE approval_requests
                SET status = ?, decided_at = ?, decision_note = ?
                WHERE approval_id = ?
                """,
                (decision, self._now_iso(), note, approval_id),
            )

        return self.get(approval_id) or {}


APPROVAL_STORE = ApprovalStore()
