"""Standalone automatic worker for scheduled asset-management operations.

Run this process separately from the FastAPI HQ. The API serves the CEO UI and
records decisions; this worker owns the recurring scheduler and keeps a durable
heartbeat/lease in the shared operations database.
"""

from __future__ import annotations

import os
import signal
import socket
from collections.abc import Callable
from threading import Event
from uuid import uuid4

from api.scheduler import DAILY_SCHEDULER, DailyScheduler
from api.service import recover_interrupted_work
from operations.worker_store import (
    WORKER_STORE,
    WorkerAlreadyRunningError,
    WorkerRuntimeStore,
)


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


class AssetWorker:
    """Owns scheduled automation independently from the HQ API process."""

    def __init__(
        self,
        *,
        store: WorkerRuntimeStore = WORKER_STORE,
        scheduler: DailyScheduler = DAILY_SCHEDULER,
        recover_fn: Callable[[], list[str]] = recover_interrupted_work,
        heartbeat_seconds: int | None = None,
    ) -> None:
        self.store = store
        self.scheduler = scheduler
        self.recover_fn = recover_fn
        self.heartbeat_seconds = heartbeat_seconds or _bounded_int(
            "ASSET_WORKER_HEARTBEAT_SECONDS",
            default=15,
            minimum=5,
            maximum=60,
        )
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex}"

    def run(self, stop_event: Event | None = None) -> None:
        stop = stop_event or Event()
        hostname = socket.gethostname()
        pid = os.getpid()
        acquired = False
        failure: str | None = None

        try:
            self.store.acquire(
                worker_id=self.worker_id,
                hostname=hostname,
                pid=pid,
                scheduler_snapshot=self.scheduler.snapshot(),
            )
            acquired = True

            # Recovery happens in the automatic worker so stale work is cleaned
            # up even when the HQ API is offline.
            self.recover_fn()
            self.scheduler.start()

            if not self.store.heartbeat(
                self.worker_id,
                scheduler_snapshot=self.scheduler.snapshot(),
            ):
                raise RuntimeError("Worker lease was lost during startup")

            while not stop.wait(self.heartbeat_seconds):
                if not self.store.heartbeat(
                    self.worker_id,
                    scheduler_snapshot=self.scheduler.snapshot(),
                ):
                    raise RuntimeError("Worker lease was lost")

        except Exception as exc:
            failure = f"{type(exc).__name__}: {exc}"
            if acquired:
                self.store.record_error(self.worker_id, failure)
            raise
        finally:
            # A process that failed to acquire the lease must not touch the
            # scheduler owned by the live worker.
            if acquired:
                self.scheduler.stop()
                self.store.release(self.worker_id, error=failure)


def _install_signal_handlers(stop_event: Event) -> None:
    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)


def main() -> int:
    stop_event = Event()
    _install_signal_handlers(stop_event)
    worker = AssetWorker()
    try:
        worker.run(stop_event)
    except WorkerAlreadyRunningError as exc:
        print(f"Automatic worker already running: {exc.worker_id}")
        return 2
    except Exception as exc:
        print(f"Automatic worker stopped with error: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
