from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import pytest

from api.job_store import ActiveJobExistsError, JobStore
from operations.run_store import DailyRunStore


def make_store(tmp_path: Path, lease_seconds: int = 30) -> JobStore:
    return JobStore(tmp_path / "operations.db", lease_seconds=lease_seconds)


def test_existing_job_database_is_migrated_for_schedule_keys(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "operations.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE agent_jobs (
                job_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                command TEXT NOT NULL,
                action TEXT NOT NULL,
                ticker TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                agents_json TEXT NOT NULL,
                result_type TEXT,
                result TEXT,
                error TEXT,
                worker_id TEXT,
                heartbeat_at TEXT,
                lease_expires_at TEXT,
                retry_of TEXT
            )
            """
        )

    JobStore(db_path)

    with sqlite3.connect(db_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(agent_jobs)").fetchall()
        }
    assert "schedule_key" in columns


def test_completed_job_survives_store_restart(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    job = store.create_job("PANW 분석해", "ANALYZE_COMPANY", "PANW")
    job_id = str(job["job_id"])

    store.mark_running(job_id, "worker-one")
    store.update_agent(job_id, "Analysis", "WORKING", "PANW 분석")
    store.update_agent(job_id, "Analysis", "DONE", "PANW 분석")
    store.complete_job(job_id, "완료된 보고서", "markdown")

    restarted_store = make_store(tmp_path)
    restored = restarted_store.get_job(job_id)

    assert restored is not None
    assert restored["status"] == "COMPLETED"
    assert restored["result"] == "완료된 보고서"
    assert restored["agents"]["Analysis"]["status"] == "DONE"


def test_stale_running_job_becomes_interrupted(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    job = store.create_job("NVDA 분석해", "ANALYZE_COMPANY", "NVDA")
    job_id = str(job["job_id"])
    store.mark_running(job_id, "dead-worker")
    store.update_agent(job_id, "Risk", "WORKING", "위험 분석")

    recovered = store.recover_stale_jobs(
        datetime.now(timezone.utc) + timedelta(seconds=31)
    )
    interrupted = store.get_job(job_id)

    assert recovered == [job_id]
    assert interrupted is not None
    assert interrupted["status"] == "INTERRUPTED"
    assert interrupted["agents"]["Risk"]["status"] == "ERROR"
    assert "retry safely" in str(interrupted["error"])


def test_live_worker_lease_is_not_interrupted(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    job = store.create_job("help", "HELP", None)
    job_id = str(job["job_id"])
    store.mark_running(job_id, "live-worker")

    recovered = store.recover_stale_jobs(datetime.now(timezone.utc))

    assert recovered == []
    assert store.get_job(job_id)["status"] == "RUNNING"


def test_newly_queued_job_is_not_recovered_during_worker_race(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    job = store.create_job("help", "HELP", None)

    recovered = store.recover_stale_jobs(datetime.now(timezone.utc))

    assert recovered == []
    assert store.get_job(str(job["job_id"]))["status"] == "QUEUED"


def test_only_one_active_job_is_allowed_by_database(tmp_path: Path) -> None:
    first_store = make_store(tmp_path)
    second_store = make_store(tmp_path)
    first = first_store.create_job("help", "HELP", None)

    with pytest.raises(ActiveJobExistsError) as exc_info:
        second_store.create_job("PANW 분석해", "ANALYZE_COMPANY", "PANW")

    assert exc_info.value.job_id == first["job_id"]


def test_retry_is_linked_without_overwriting_original(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    original = store.create_job("PANW 분석해", "ANALYZE_COMPANY", "PANW")
    original_id = str(original["job_id"])
    store.mark_running(original_id, "worker-one")
    store.fail_job(original_id, "temporary failure")

    retried = store.create_job(
        "PANW 분석해",
        "ANALYZE_COMPANY",
        "PANW",
        retry_of=original_id,
    )

    assert retried["job_id"] != original_id
    assert retried["retry_of"] == original_id
    assert store.get_job(original_id)["status"] == "FAILED"


def test_interrupted_job_marks_linked_daily_run(tmp_path: Path) -> None:
    db_path = tmp_path / "operations.db"
    job_store = JobStore(db_path, lease_seconds=30)
    run_store = DailyRunStore(db_path)
    job = job_store.create_job(
        "AUTO DAILY OPERATIONS",
        "DAILY_OPERATIONS",
        None,
        source="SYSTEM",
    )
    job_id = str(job["job_id"])
    job_store.mark_running(job_id, "dead-worker")
    run_id = run_store.start_run(datetime.now(timezone.utc).isoformat(), job_id=job_id)
    recovery_time = datetime.now(timezone.utc) + timedelta(seconds=31)

    recovered = job_store.recover_stale_jobs(recovery_time)
    run_store.interrupt_jobs(recovered, recovery_time.isoformat())
    latest = run_store.latest_run()

    assert latest is not None
    assert latest["run_id"] == run_id
    assert latest["status"] == "INTERRUPTED"
    assert "Server stopped" in str(latest["error"])
