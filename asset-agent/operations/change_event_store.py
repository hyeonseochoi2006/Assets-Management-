import os
import sqlite3
from pathlib import Path
from threading import RLock

from operations.change_detector import build_change_event, refresh_change_set
from operations.change_policy import PortfolioChangePolicy
from operations.models import (
    ChangeEvent,
    ChangeSet,
    EventPersistenceSummary,
    PortfolioSnapshot,
    PositionChange,
)


_DEFAULT_RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime"
_RUNTIME_DIR = Path(os.getenv("ASSET_RUNTIME_DIR", str(_DEFAULT_RUNTIME_DIR)))
_DB_PATH = _RUNTIME_DIR / "operations.db"


class ChangeEventStore:
    """Durable event ledger and two-observation holding-removal confirmation."""

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
                CREATE TABLE IF NOT EXISTS change_events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    seen_count INTEGER NOT NULL DEFAULT 1
                );

                CREATE INDEX IF NOT EXISTS idx_change_events_created_at
                ON change_events(created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_change_events_symbol
                ON change_events(symbol, created_at DESC);

                CREATE TABLE IF NOT EXISTS holding_missing_confirmations (
                    account_seq TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    first_missing_at TEXT NOT NULL,
                    last_missing_at TEXT NOT NULL,
                    miss_count INTEGER NOT NULL,
                    previous_quantity REAL,
                    status TEXT NOT NULL,
                    confirmed_event_id TEXT,
                    PRIMARY KEY(account_seq, symbol)
                );
                """
            )

    def process(
        self,
        run_id: str,
        current: PortfolioSnapshot,
        change_set: ChangeSet,
        policy: PortfolioChangePolicy | None = None,
    ) -> ChangeSet:
        selected_policy = policy or PortfolioChangePolicy.from_env()
        if change_set.data_quality != "BLOCKED":
            confirmed, transient_gaps = self._reconcile_missing_holdings(
                current,
                change_set,
                selected_policy,
            )
            for event in transient_gaps:
                change_set.events = [
                    existing
                    for existing in change_set.events
                    if not (
                        existing.symbol == event.symbol
                        and existing.event_type == "HOLDING_ADDED"
                    )
                ]
                change_set.changes = [
                    change
                    for change in change_set.changes
                    if not (
                        change.symbol == event.symbol
                        and change.change_type == "ADDED"
                    )
                ]
                change_set.events.append(event)

            for event in confirmed:
                change_set.events = [
                    existing
                    for existing in change_set.events
                    if not (
                        existing.symbol == event.symbol
                        and existing.event_type == "HOLDING_MISSING_UNCONFIRMED"
                    )
                ]
                change_set.events.append(event)
                matching_change = next(
                    (
                        change
                        for change in change_set.changes
                        if change.symbol == event.symbol
                    ),
                    None,
                )
                if matching_change is None:
                    change_set.changes.append(
                        PositionChange(
                            symbol=event.symbol,
                            change_type="REMOVED",
                            fields=[],
                        )
                    )
                else:
                    matching_change.change_type = "REMOVED"

        refresh_change_set(change_set)
        change_set.persistence = self.save_events(run_id, change_set.events)
        return change_set

    def _reconcile_missing_holdings(
        self,
        current: PortfolioSnapshot,
        change_set: ChangeSet,
        policy: PortfolioChangePolicy,
    ) -> tuple[list[ChangeEvent], list[ChangeEvent]]:
        observed_symbols = {position.symbol for position in current.positions}
        newly_missing = {
            event.symbol: event
            for event in change_set.events
            if event.event_type == "HOLDING_MISSING_UNCONFIRMED"
        }
        confirmed: list[ChangeEvent] = []
        transient_gaps: list[ChangeEvent] = []

        with self._lock, self._connect() as connection:
            for symbol in observed_symbols:
                state = connection.execute(
                    """
                    SELECT * FROM holding_missing_confirmations
                    WHERE account_seq = ? AND symbol = ?
                    """,
                    (current.account_seq, symbol),
                ).fetchone()
                if state is not None and state["status"] == "PENDING":
                    position = next(
                        item for item in current.positions if item.symbol == symbol
                    )
                    transient_gaps.append(
                        build_change_event(
                            event_type="DATA_QUALITY_WARNING",
                            symbol=symbol,
                            severity="QUIET",
                            detected_at=current.captured_at,
                            previous_captured_at=str(state["first_missing_at"]),
                            previous=None,
                            current=position.quantity,
                            reason=(
                                "The holding reappeared after one missing snapshot; "
                                "the transient gap was closed without inferring an "
                                "addition or removal."
                            ),
                            policy=policy,
                        )
                    )
                connection.execute(
                    """
                    DELETE FROM holding_missing_confirmations
                    WHERE account_seq = ? AND symbol = ?
                    """,
                    (current.account_seq, symbol),
                )

            for symbol, event in newly_missing.items():
                state = connection.execute(
                    """
                    SELECT * FROM holding_missing_confirmations
                    WHERE account_seq = ? AND symbol = ?
                    """,
                    (current.account_seq, symbol),
                ).fetchone()
                if state is None:
                    connection.execute(
                        """
                        INSERT INTO holding_missing_confirmations(
                            account_seq, symbol, first_missing_at,
                            last_missing_at, miss_count, previous_quantity,
                            status, confirmed_event_id
                        )
                        VALUES (?, ?, ?, ?, 1, ?, 'PENDING', NULL)
                        """,
                        (
                            current.account_seq,
                            symbol,
                            current.captured_at,
                            current.captured_at,
                            event.previous,
                        ),
                    )
                elif (
                    state["status"] == "PENDING"
                    and state["last_missing_at"] != current.captured_at
                ):
                    connection.execute(
                        """
                        UPDATE holding_missing_confirmations
                        SET last_missing_at = ?, miss_count = miss_count + 1
                        WHERE account_seq = ? AND symbol = ?
                        """,
                        (current.captured_at, current.account_seq, symbol),
                    )

            states = connection.execute(
                """
                SELECT * FROM holding_missing_confirmations
                WHERE account_seq = ? AND status = 'PENDING'
                """,
                (current.account_seq,),
            ).fetchall()
            for state in states:
                symbol = str(state["symbol"])
                if symbol in observed_symbols:
                    continue

                miss_count = int(state["miss_count"])
                last_missing_at = str(state["last_missing_at"])
                if last_missing_at != current.captured_at:
                    miss_count += 1
                    connection.execute(
                        """
                        UPDATE holding_missing_confirmations
                        SET last_missing_at = ?, miss_count = ?
                        WHERE account_seq = ? AND symbol = ?
                        """,
                        (
                            current.captured_at,
                            miss_count,
                            current.account_seq,
                            symbol,
                        ),
                    )

                if miss_count < 2:
                    continue

                event = build_change_event(
                    event_type="HOLDING_REMOVED",
                    symbol=symbol,
                    severity="MATERIAL",
                    detected_at=current.captured_at,
                    previous_captured_at=str(state["first_missing_at"]),
                    previous=state["previous_quantity"],
                    current=None,
                    reason=(
                        "The holding remained absent for two consecutive snapshots; "
                        "removal is now confirmed for operational routing."
                    ),
                    policy=policy,
                )
                connection.execute(
                    """
                    UPDATE holding_missing_confirmations
                    SET status = 'CONFIRMED', confirmed_event_id = ?
                    WHERE account_seq = ? AND symbol = ?
                    """,
                    (event.event_id, current.account_seq, symbol),
                )
                confirmed.append(event)

        return confirmed, transient_gaps

    def save_events(
        self,
        run_id: str,
        events: list[ChangeEvent],
    ) -> EventPersistenceSummary:
        inserted = 0
        duplicates = 0
        with self._lock, self._connect() as connection:
            for event in events:
                existing = connection.execute(
                    "SELECT event_id FROM change_events WHERE event_id = ?",
                    (event.event_id,),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        """
                        INSERT INTO change_events(
                            event_id, run_id, symbol, event_type, severity,
                            event_json, created_at, last_seen_at, seen_count
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                        """,
                        (
                            event.event_id,
                            run_id,
                            event.symbol,
                            event.event_type,
                            event.severity,
                            event.model_dump_json(),
                            event.detected_at,
                            event.detected_at,
                        ),
                    )
                    inserted += 1
                else:
                    connection.execute(
                        """
                        UPDATE change_events
                        SET last_seen_at = ?, seen_count = seen_count + 1
                        WHERE event_id = ?
                        """,
                        (event.detected_at, event.event_id),
                    )
                    duplicates += 1
        return EventPersistenceSummary(inserted=inserted, duplicates=duplicates)

    def event_count(self) -> int:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM change_events"
            ).fetchone()
        return int(row["count"])

    def missing_state(self, account_seq: str, symbol: str) -> dict[str, object] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM holding_missing_confirmations
                WHERE account_seq = ? AND symbol = ?
                """,
                (account_seq, symbol),
            ).fetchone()
        return dict(row) if row is not None else None


CHANGE_EVENT_STORE = ChangeEventStore()
