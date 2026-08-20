from pathlib import Path

from operations.external_changes.models import ExternalDocument
from operations.external_changes.store import ExternalDocumentStore


def _document(external_id: str) -> ExternalDocument:
    return ExternalDocument(
        external_id=external_id,
        symbol="PANW",
        cik="0001327567",
        form="8-K",
        filing_date="2026-08-20",
        title="PANW filing",
        url=f"https://www.sec.gov/Archives/{external_id}",
    )


def test_same_run_can_recover_new_document_after_crash(tmp_path: Path) -> None:
    store = ExternalDocumentStore(tmp_path / "operations.db")
    baseline_doc = _document("baseline")
    new_doc = _document("new-filing")

    baseline_created, unseen = store.ingest(
        source="SEC_EDGAR",
        subject_key="0001327567",
        checked_at="2026-08-20T12:00:00+00:00",
        documents=[baseline_doc],
        run_id="baseline-run",
    )
    assert baseline_created is True
    assert unseen == []

    baseline_created, unseen = store.ingest(
        source="SEC_EDGAR",
        subject_key="0001327567",
        checked_at="2026-08-20T13:00:00+00:00",
        documents=[baseline_doc, new_doc],
        run_id="run-1",
    )
    assert baseline_created is False
    assert [item.external_id for item in unseen] == ["new-filing"]

    # Simulate the same Daily run restarting after durable SEC ingestion but
    # before its workflow checkpoint completed. The new filing must reappear.
    _, retry_unseen = store.ingest(
        source="SEC_EDGAR",
        subject_key="0001327567",
        checked_at="2026-08-20T13:00:00+00:00",
        documents=[baseline_doc, new_doc],
        run_id="run-1",
    )
    assert [item.external_id for item in retry_unseen] == ["new-filing"]

    # A genuinely later run must not alert the already-seen filing again.
    _, later_unseen = store.ingest(
        source="SEC_EDGAR",
        subject_key="0001327567",
        checked_at="2026-08-20T14:00:00+00:00",
        documents=[baseline_doc, new_doc],
        run_id="run-2",
    )
    assert later_unseen == []
