import sqlite3
from pathlib import Path
from threading import RLock

from operations.external_changes.models import ExternalDocument


class ExternalDocumentStore:
    """Durable baseline and deduplication ledger for official documents."""

    def __init__(self, db_path: Path) -> None:
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
                CREATE TABLE IF NOT EXISTS external_documents (
                    source TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    cik TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    is_baseline INTEGER NOT NULL,
                    PRIMARY KEY(source, external_id)
                );

                CREATE TABLE IF NOT EXISTS external_source_checkpoints (
                    source TEXT NOT NULL,
                    subject_key TEXT NOT NULL,
                    initialized_at TEXT NOT NULL,
                    last_checked_at TEXT NOT NULL,
                    PRIMARY KEY(source, subject_key)
                );
                """
            )

    def ingest(
        self,
        *,
        source: str,
        subject_key: str,
        checked_at: str,
        documents: list[ExternalDocument],
    ) -> tuple[bool, list[ExternalDocument]]:
        """Return (baseline_created, newly observed documents)."""
        with self._lock, self._connect() as connection:
            checkpoint = connection.execute(
                """
                SELECT initialized_at FROM external_source_checkpoints
                WHERE source = ? AND subject_key = ?
                """,
                (source, subject_key),
            ).fetchone()
            baseline_created = checkpoint is None
            new_documents: list[ExternalDocument] = []

            for document in documents:
                inserted = connection.execute(
                    """
                    INSERT OR IGNORE INTO external_documents(
                        source, external_id, symbol, cik, document_json,
                        first_seen_at, is_baseline
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source,
                        document.external_id,
                        document.symbol,
                        document.cik,
                        document.model_dump_json(),
                        checked_at,
                        1 if baseline_created else 0,
                    ),
                )
                if not baseline_created and inserted.rowcount == 1:
                    new_documents.append(document)

            if baseline_created:
                connection.execute(
                    """
                    INSERT INTO external_source_checkpoints(
                        source, subject_key, initialized_at, last_checked_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (source, subject_key, checked_at, checked_at),
                )
            else:
                connection.execute(
                    """
                    UPDATE external_source_checkpoints SET last_checked_at = ?
                    WHERE source = ? AND subject_key = ?
                    """,
                    (checked_at, source, subject_key),
                )
        return baseline_created, new_documents
