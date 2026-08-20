from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event

import pytest

from operations.worker_store import WorkerAlreadyRunningError, WorkerRuntimeStore
from worker import AssetWorker


class FakeScheduler:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def snapshot(self) -> dict[str, object]:
        return {
            "enabled": True,
            "daily_time": "17:30",
            "scan_times": ["08:30", "12:30"],
            "timezone": "America/New_York",
            "next_run_at": "2026-08-20T17:30:00-04:00",
            "recent_events": [],
        }

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


def test_worker_store_prevents_second_live_scheduler_worker(tmp_path: Path) -> None:
    store = WorkerRuntimeStore(tmp_path / "operations.db", lease_seconds=90)
    now = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    store.acquire(
        worker_id="worker-a",
        hostname="host-a",
        pid=100,
        now=now,
    )

    with pytest.raises(WorkerAlreadyRunningError) as exc_info:
        store.acquire(
            worker_id="worker-b",
            hostname="host-b",
            pid=200,
            now=now + timedelta(seconds=10),
        )

    assert exc_info.value.worker_id == "worker-a"


def test_expired_worker_lease_can_be_taken_over(tmp_path: Path) -> None:
    store = WorkerRuntimeStore(tmp_path / "operations.db", lease_seconds=30)
    started = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    store.acquire(
        worker_id="worker-a",
        hostname="host-a",
        pid=100,
        now=started,
    )
    taken_over = store.acquire(
        worker_id="worker-b",
        hostname="host-b",
        pid=200,
        now=started + timedelta(seconds=31),
    )

    assert taken_over["worker_id"] == "worker-b"
    assert taken_over["status"] == "RUNNING"
    assert taken_over["healthy"] is True


def test_worker_status_marks_expired_running_lease_stale(tmp_path: Path) -> None:
    store = WorkerRuntimeStore(tmp_path / "operations.db", lease_seconds=30)
    started = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    store.acquire(
        worker_id="worker-a",
        hostname="host-a",
        pid=100,
        now=started,
    )
    status = store.status(now=started + timedelta(seconds=31))

    assert status is not None
    assert status["status"] == "STALE"
    assert status["healthy"] is False


def test_worker_heartbeat_persists_scheduler_snapshot(tmp_path: Path) -> None:
    store = WorkerRuntimeStore(tmp_path / "operations.db", lease_seconds=60)
    now = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    store.acquire(
        worker_id="worker-a",
        hostname="host-a",
        pid=100,
        now=now,
    )
    assert store.heartbeat(
        "worker-a",
        scheduler_snapshot={"enabled": True, "next_run_at": "later"},
        now=now + timedelta(seconds=10),
    )

    status = store.status(now=now + timedelta(seconds=10))
    assert status is not None
    assert status["scheduler_snapshot"] == {
        "enabled": True,
        "next_run_at": "later",
    }


def test_asset_worker_owns_scheduler_and_releases_lease(tmp_path: Path) -> None:
    store = WorkerRuntimeStore(tmp_path / "operations.db", lease_seconds=60)
    scheduler = FakeScheduler()
    recover_calls: list[str] = []
    stop = Event()
    stop.set()

    worker = AssetWorker(
        store=store,
        scheduler=scheduler,  # type: ignore[arg-type]
        recover_fn=lambda: recover_calls.append("recover") or [],
        heartbeat_seconds=5,
    )
    worker.run(stop)

    assert scheduler.started is True
    assert scheduler.stopped is True
    assert recover_calls == ["recover"]

    status = store.status()
    assert status is not None
    assert status["status"] == "STOPPED"
    assert status["healthy"] is False


def test_release_only_affects_current_worker(tmp_path: Path) -> None:
    store = WorkerRuntimeStore(tmp_path / "operations.db", lease_seconds=60)
    now = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
    store.acquire(
        worker_id="worker-a",
        hostname="host-a",
        pid=100,
        now=now,
    )

    assert store.release("worker-b", now=now + timedelta(seconds=1)) is False
    status = store.status(now=now + timedelta(seconds=1))
    assert status is not None
    assert status["worker_id"] == "worker-a"
    assert status["status"] == "RUNNING"
