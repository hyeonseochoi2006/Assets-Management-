from pathlib import Path

from operations.checkpoint_store import DailyCheckpointStore


def test_checkpoint_survives_store_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "operations.db"
    first = DailyCheckpointStore(db_path)
    first.begin("run-1", "DATA_READY")
    first.complete(
        "run-1",
        "DATA_READY",
        {"snapshot": {"account_seq": "abc"}, "gate": {"decision": "SKIP_AI"}},
    )

    reopened = DailyCheckpointStore(db_path)
    payload = reopened.completed_payload("run-1", "DATA_READY")

    assert payload is not None
    assert payload["snapshot"]["account_seq"] == "abc"
    assert payload["gate"]["decision"] == "SKIP_AI"
    assert reopened.next_step("run-1") == "MONITORING_READY"


def test_restarting_interrupted_step_increments_attempt(tmp_path: Path) -> None:
    store = DailyCheckpointStore(tmp_path / "operations.db")
    first = store.begin("run-1", "MONITORING_READY")
    assert first["attempt_count"] == 1

    store.interrupt_running("run-1", "process stopped")
    interrupted = store.get("run-1", "MONITORING_READY")
    assert interrupted is not None
    assert interrupted["status"] == "INTERRUPTED"

    second = store.begin("run-1", "MONITORING_READY")
    assert second["status"] == "RUNNING"
    assert second["attempt_count"] == 2


def test_completed_checkpoint_is_not_reopened(tmp_path: Path) -> None:
    store = DailyCheckpointStore(tmp_path / "operations.db")
    store.begin("run-1", "CIO_READY")
    completed = store.complete("run-1", "CIO_READY", {"summary": "done"})

    reopened = store.begin("run-1", "CIO_READY")

    assert reopened["status"] == "COMPLETED"
    assert reopened["attempt_count"] == completed["attempt_count"]
    assert reopened["payload"] == {"summary": "done"}


def test_next_step_follows_workflow_order(tmp_path: Path) -> None:
    store = DailyCheckpointStore(tmp_path / "operations.db")
    assert store.next_step("run-1") == "DATA_READY"

    for step in (
        "DATA_READY",
        "MONITORING_READY",
        "CIO_READY",
        "BRIEFING_READY",
        "APPROVAL_READY",
    ):
        store.begin("run-1", step)
        store.complete("run-1", step, {})

    assert store.next_step("run-1") is None
