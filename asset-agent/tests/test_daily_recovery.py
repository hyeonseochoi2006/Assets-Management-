from datetime import datetime, timedelta, timezone
from pathlib import Path

from api.job_store import JobStore
from operations.daily_recovery import DailyRecoveryStore
from operations.run_store import DailyRunStore
from operations.schedule_store import DailyScheduleStore


def _interrupt_scheduled_job(
    db_path: Path,
    *,
    run_kind: str = "SCAN",
    complete_run_first: bool = False,
) -> tuple[JobStore, DailyRunStore, DailyScheduleStore, str, str]:
    jobs = JobStore(db_path, lease_seconds=30)
    runs = DailyRunStore(db_path)
    schedules = DailyScheduleStore(db_path)
    action = "DAILY_SCAN" if run_kind == "SCAN" else "DAILY_OPERATIONS"
    schedule_key = f"DAILY_{run_kind}:2026-08-20:08:30"
    job = jobs.create_job(
        command=f"AUTO {run_kind}",
        action=action,
        ticker=None,
        source="SYSTEM",
        schedule_key=schedule_key,
    )
    job_id = str(job["job_id"])
    jobs.mark_running(job_id, "old-worker")
    run_id = runs.start_run(
        "2026-08-20T12:30:00+00:00",
        job_id=job_id,
        run_kind=run_kind,
    )
    schedules.record_job(
        schedule_key=schedule_key,
        scheduled_for="2026-08-20T08:30:00-04:00",
        timezone_name="America/New_York",
        job_id=job_id,
        status="RUNNING",
    )

    if complete_run_first:
        runs.complete_run(
            run_id=run_id,
            completed_at="2026-08-20T12:31:00+00:00",
            changes={},
            external_changes={},
            gate={},
            monitoring={},
            opportunities={},
            cio={"summary": "completed before crash"},
            briefing=None,
        )

    future = datetime.now(timezone.utc) + timedelta(seconds=31)
    recovered = jobs.recover_stale_jobs(now=future)
    assert recovered == [job_id]
    runs.interrupt_jobs(recovered, future.isoformat())
    schedules.interrupt_jobs(recovered, "worker stopped")
    return jobs, runs, schedules, job_id, run_id


def test_interrupted_scheduled_job_can_requeue_and_resume_same_run(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "operations.db"
    jobs, _runs, schedules, job_id, run_id = _interrupt_scheduled_job(db_path)
    recovery = DailyRecoveryStore(db_path)

    candidates = recovery.recoverable_jobs()
    assert len(candidates) == 1
    assert candidates[0]["job_id"] == job_id
    assert candidates[0]["run_id"] == run_id
    assert candidates[0]["run_status"] == "INTERRUPTED"

    assert recovery.requeue_interrupted_job(job_id) is True
    requeued = jobs.get_job(job_id)
    assert requeued is not None
    assert requeued["status"] == "QUEUED"
    event = schedules.get("DAILY_SCAN:2026-08-20:08:30")
    assert event is not None
    assert event["status"] == "QUEUED"

    resumed = recovery.prepare_run_resume(run_id, job_id, "SCAN")
    assert resumed["status"] == "RUNNING"
    assert resumed["run_id"] == run_id
    assert resumed["resume_count"] == 1


def test_completed_daily_run_repairs_outer_interrupted_job_without_rerun(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "operations.db"
    jobs, _runs, schedules, job_id, run_id = _interrupt_scheduled_job(
        db_path,
        complete_run_first=True,
    )
    recovery = DailyRecoveryStore(db_path)

    candidates = recovery.recoverable_jobs()
    assert len(candidates) == 1
    assert candidates[0]["run_id"] == run_id
    assert candidates[0]["run_status"] == "COMPLETED"

    assert recovery.restore_completed_job(job_id, "already completed") is True
    restored = jobs.get_job(job_id)
    assert restored is not None
    assert restored["status"] == "COMPLETED"
    assert restored["result"] == "already completed"
    event = schedules.get("DAILY_SCAN:2026-08-20:08:30")
    assert event is not None
    assert event["status"] == "COMPLETED"


def test_manual_daily_validation_job_is_not_auto_resume_candidate(tmp_path: Path) -> None:
    db_path = tmp_path / "operations.db"
    jobs = JobStore(db_path, lease_seconds=30)
    runs = DailyRunStore(db_path)
    job = jobs.create_job(
        command="MANUAL DAILY VALIDATION",
        action="DAILY_OPERATIONS",
        ticker=None,
        source="SYSTEM",
        schedule_key=None,
    )
    job_id = str(job["job_id"])
    jobs.mark_running(job_id, "old-worker")
    runs.start_run(
        "2026-08-20T12:30:00+00:00",
        job_id=job_id,
        run_kind="CLOSE",
    )
    future = datetime.now(timezone.utc) + timedelta(seconds=31)
    recovered = jobs.recover_stale_jobs(now=future)
    runs.interrupt_jobs(recovered, future.isoformat())

    recovery = DailyRecoveryStore(db_path)
    assert recovery.recoverable_jobs() == []
