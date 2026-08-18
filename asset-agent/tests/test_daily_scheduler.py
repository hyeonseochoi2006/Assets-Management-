from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import api.scheduler as scheduler_module
import api.service as service_module
from api.job_store import DuplicateScheduledJobError, JobStore
from api.scheduler import DailyScheduleConfig, DailyScheduler
from operations.schedule_store import DailyScheduleStore
from operations.run_store import DailyRunStore


SCHEDULE_ENV_NAMES = (
    "ASSET_DAILY_SCHEDULE_ENABLED",
    "ASSET_DAILY_TIME",
    "ASSET_TIMEZONE",
    "ASSET_DAILY_MISFIRE_GRACE_MINUTES",
    "ASSET_DAILY_POLL_SECONDS",
)


def clear_schedule_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in SCHEDULE_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def enabled_config(grace_minutes: int = 120) -> DailyScheduleConfig:
    return DailyScheduleConfig(
        enabled=True,
        daily_time=time(8, 0),
        timezone_name="America/Vancouver",
        timezone=ZoneInfo("America/Vancouver"),
        grace_minutes=grace_minutes,
        poll_seconds=30,
    )


def test_schedule_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_schedule_env(monkeypatch)

    config = DailyScheduleConfig.from_env()

    assert config.enabled is False
    assert config.daily_time is None
    assert config.timezone is None


def test_enabled_schedule_requires_explicit_valid_time_and_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_schedule_env(monkeypatch)
    monkeypatch.setenv("ASSET_DAILY_SCHEDULE_ENABLED", "true")
    monkeypatch.setenv("ASSET_DAILY_TIME", "08:00")
    monkeypatch.setenv("ASSET_TIMEZONE", "America/Vancouver")

    config = DailyScheduleConfig.from_env()

    assert config.enabled is True
    assert config.daily_time == time(8, 0)
    assert str(config.timezone) == "America/Vancouver"


@pytest.mark.parametrize(
    ("daily_time", "timezone_name", "error"),
    [
        ("", "America/Vancouver", "ASSET_DAILY_TIME"),
        ("8:00", "America/Vancouver", "HH:MM"),
        ("25:00", "America/Vancouver", "HH:MM"),
        ("08:00", "Not/A_Timezone", "ASSET_TIMEZONE"),
    ],
)
def test_invalid_enabled_schedule_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    daily_time: str,
    timezone_name: str,
    error: str,
) -> None:
    clear_schedule_env(monkeypatch)
    monkeypatch.setenv("ASSET_DAILY_SCHEDULE_ENABLED", "true")
    monkeypatch.setenv("ASSET_DAILY_TIME", daily_time)
    monkeypatch.setenv("ASSET_TIMEZONE", timezone_name)

    with pytest.raises(RuntimeError, match=error):
        DailyScheduleConfig.from_env()


def test_due_schedule_starts_exactly_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "operations.db"
    job_store = JobStore(db_path)
    schedule_store = DailyScheduleStore(db_path)
    scheduler = DailyScheduler(schedule_store)
    scheduler._config = enabled_config()
    calls: list[str] = []

    def fake_start(schedule_key: str | None = None, **_: object) -> dict[str, object]:
        assert schedule_key is not None
        calls.append(schedule_key)
        return job_store.create_job(
            command="AUTO DAILY OPERATIONS",
            action="DAILY_OPERATIONS",
            ticker=None,
            source="SYSTEM",
            schedule_key=schedule_key,
        )

    monkeypatch.setattr(scheduler_module, "JOB_STORE", job_store)
    monkeypatch.setattr(scheduler_module, "start_daily_operations", fake_start)
    now = datetime(2026, 8, 18, 15, 30, tzinfo=timezone.utc)

    first = scheduler.run_due(now)
    second = scheduler.run_due(now)

    assert calls == ["DAILY_OPERATIONS:2026-08-18"]
    assert first is not None
    assert first["status"] == "QUEUED"
    assert second is not None
    assert second["schedule_key"] == first["schedule_key"]


def test_schedule_waits_before_local_run_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "operations.db"
    job_store = JobStore(db_path)
    scheduler = DailyScheduler(DailyScheduleStore(db_path))
    scheduler._config = enabled_config()
    monkeypatch.setattr(scheduler_module, "JOB_STORE", job_store)
    monkeypatch.setattr(
        scheduler_module,
        "start_daily_operations",
        lambda **_: pytest.fail("schedule started before its local time"),
    )

    result = scheduler.run_due(
        datetime(2026, 8, 18, 14, 59, tzinfo=timezone.utc)
    )

    assert result is None


def test_late_server_start_is_recorded_without_running_analysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "operations.db"
    job_store = JobStore(db_path)
    schedule_store = DailyScheduleStore(db_path)
    scheduler = DailyScheduler(schedule_store)
    scheduler._config = enabled_config(grace_minutes=60)
    monkeypatch.setattr(scheduler_module, "JOB_STORE", job_store)
    monkeypatch.setattr(
        scheduler_module,
        "start_daily_operations",
        lambda **_: pytest.fail("late schedule should not incur analysis cost"),
    )

    event = scheduler.run_due(
        datetime(2026, 8, 18, 17, 30, tzinfo=timezone.utc)
    )

    assert event is not None
    assert event["status"] == "SKIPPED"
    assert event["job_id"] is None
    assert "catch-up window" in str(event["reason"])


def test_database_rejects_duplicate_schedule_key(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "operations.db")
    first = store.create_job(
        "AUTO DAILY OPERATIONS",
        "DAILY_OPERATIONS",
        None,
        source="SYSTEM",
        schedule_key="DAILY_OPERATIONS:2026-08-18",
    )
    store.mark_running(str(first["job_id"]), "worker")
    store.complete_job(str(first["job_id"]), "done", "markdown")

    with pytest.raises(DuplicateScheduledJobError) as exc_info:
        store.create_job(
            "AUTO DAILY OPERATIONS",
            "DAILY_OPERATIONS",
            None,
            source="SYSTEM",
            schedule_key="DAILY_OPERATIONS:2026-08-18",
        )

    assert exc_info.value.job_id == first["job_id"]


def test_schedule_event_tracks_terminal_job_status(tmp_path: Path) -> None:
    store = DailyScheduleStore(tmp_path / "operations.db")
    store.record_job(
        schedule_key="DAILY_OPERATIONS:2026-08-18",
        scheduled_for="2026-08-18T08:00:00-07:00",
        timezone_name="America/Vancouver",
        job_id="job-1",
        status="RUNNING",
    )

    store.finish_job("job-1", "COMPLETED")

    event = store.get("DAILY_OPERATIONS:2026-08-18")
    assert event is not None
    assert event["status"] == "COMPLETED"


def test_service_records_schedule_before_background_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "operations.db"
    job_store = JobStore(db_path)
    schedule_store = DailyScheduleStore(db_path)
    monkeypatch.setattr(service_module, "JOB_STORE", job_store)
    monkeypatch.setattr(service_module, "RUN_STORE", DailyRunStore(db_path))
    monkeypatch.setattr(service_module, "SCHEDULE_STORE", schedule_store)
    monkeypatch.setattr(service_module, "_start_thread", lambda *_, **__: None)

    job = service_module.start_daily_operations(
        schedule_key="DAILY_OPERATIONS:2026-08-18",
        scheduled_for="2026-08-18T08:00:00-07:00",
        schedule_timezone="America/Vancouver",
    )

    event = schedule_store.get("DAILY_OPERATIONS:2026-08-18")
    assert event is not None
    assert event["job_id"] == job["job_id"]
    assert event["status"] == "QUEUED"


def test_service_rejects_partial_schedule_context() -> None:
    with pytest.raises(ValueError, match="complete context"):
        service_module.start_daily_operations(
            schedule_key="DAILY_OPERATIONS:2026-08-18"
        )
