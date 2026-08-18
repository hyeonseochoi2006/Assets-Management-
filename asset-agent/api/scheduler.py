import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from threading import Event, RLock, Thread
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from api.job_store import DuplicateScheduledJobError, JOB_STORE
from api.service import ActiveJobError, start_daily_operations
from operations.schedule_store import SCHEDULE_STORE, DailyScheduleStore


LOGGER = logging.getLogger(__name__)
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off", ""}


@dataclass(frozen=True)
class DailyScheduleConfig:
    enabled: bool
    daily_time: time | None = None
    timezone_name: str | None = None
    timezone: ZoneInfo | None = None
    grace_minutes: int = 120
    poll_seconds: int = 30

    @classmethod
    def from_env(cls) -> "DailyScheduleConfig":
        raw_enabled = os.getenv("ASSET_DAILY_SCHEDULE_ENABLED", "false")
        normalized_enabled = raw_enabled.strip().lower()
        if normalized_enabled in _TRUE_VALUES:
            enabled = True
        elif normalized_enabled in _FALSE_VALUES:
            enabled = False
        else:
            raise RuntimeError(
                "ASSET_DAILY_SCHEDULE_ENABLED must be true or false"
            )

        if not enabled:
            return cls(enabled=False)

        raw_time = os.getenv("ASSET_DAILY_TIME", "").strip()
        raw_timezone = os.getenv("ASSET_TIMEZONE", "").strip()
        if not raw_time:
            raise RuntimeError(
                "ASSET_DAILY_TIME is required when the Daily schedule is enabled"
            )
        if not raw_timezone:
            raise RuntimeError(
                "ASSET_TIMEZONE is required when the Daily schedule is enabled"
            )

        if re.fullmatch(r"\d{2}:\d{2}", raw_time) is None:
            raise RuntimeError("ASSET_DAILY_TIME must use HH:MM format")
        try:
            parsed_time = time.fromisoformat(raw_time)
        except ValueError as exc:
            raise RuntimeError("ASSET_DAILY_TIME must use HH:MM format") from exc
        if parsed_time.second or parsed_time.microsecond:
            raise RuntimeError("ASSET_DAILY_TIME must use HH:MM format")

        try:
            parsed_timezone = ZoneInfo(raw_timezone)
        except ZoneInfoNotFoundError as exc:
            raise RuntimeError(
                f"ASSET_TIMEZONE is not a valid IANA timezone: {raw_timezone}"
            ) from exc

        grace_minutes = cls._bounded_int(
            "ASSET_DAILY_MISFIRE_GRACE_MINUTES",
            default=120,
            minimum=1,
            maximum=1440,
        )
        poll_seconds = cls._bounded_int(
            "ASSET_DAILY_POLL_SECONDS",
            default=30,
            minimum=5,
            maximum=300,
        )
        return cls(
            enabled=True,
            daily_time=parsed_time,
            timezone_name=raw_timezone,
            timezone=parsed_timezone,
            grace_minutes=grace_minutes,
            poll_seconds=poll_seconds,
        )

    @staticmethod
    def _bounded_int(
        name: str,
        default: int,
        minimum: int,
        maximum: int,
    ) -> int:
        raw = os.getenv(name, str(default)).strip()
        try:
            value = int(raw)
        except ValueError as exc:
            raise RuntimeError(f"{name} must be an integer") from exc
        if not minimum <= value <= maximum:
            raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
        return value


class DailyScheduler:
    """Small durable scheduler for one Daily Operations run per local date."""

    def __init__(self, schedule_store: DailyScheduleStore = SCHEDULE_STORE) -> None:
        self._lock = RLock()
        self._schedule_store = schedule_store
        self._config = DailyScheduleConfig(enabled=False)
        self._stop = Event()
        self._thread: Thread | None = None

    @property
    def config(self) -> DailyScheduleConfig:
        return self._config

    def start(self) -> None:
        config = DailyScheduleConfig.from_env()
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._config = config
            self._stop.clear()
            if not config.enabled:
                self._thread = None
                return
            self._thread = Thread(
                target=self._run_loop,
                daemon=True,
                name="asset-daily-scheduler",
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._stop.set()
        if thread is not None:
            thread.join(timeout=2)
        with self._lock:
            self._thread = None

    def _run_loop(self) -> None:
        self.run_due()
        while not self._stop.wait(self._config.poll_seconds):
            self.run_due()

    def run_due(self, now: datetime | None = None) -> dict[str, object] | None:
        config = self._config
        if not config.enabled:
            return None
        if config.timezone is None or config.daily_time is None:
            raise RuntimeError("Enabled Daily schedule is incomplete")

        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("Scheduler time must be timezone-aware")
        local_now = current.astimezone(config.timezone)
        scheduled_local = datetime.combine(
            local_now.date(),
            config.daily_time,
            tzinfo=config.timezone,
        )
        schedule_key = f"DAILY_OPERATIONS:{local_now.date().isoformat()}"

        recorded = self._schedule_store.get(schedule_key)
        if recorded is not None:
            job_id = recorded.get("job_id")
            if job_id:
                job = JOB_STORE.get_job(str(job_id))
                if job is not None and job["status"] != recorded["status"]:
                    self._schedule_store.finish_job(
                        str(job_id),
                        str(job["status"]),
                        str(job["error"]) if job.get("error") else None,
                    )
                    return self._schedule_store.get(schedule_key)
            return recorded

        existing_job = JOB_STORE.get_job_by_schedule_key(schedule_key)
        if existing_job is not None:
            return self._schedule_store.record_job(
                schedule_key=schedule_key,
                scheduled_for=scheduled_local.isoformat(),
                timezone_name=str(config.timezone_name),
                job_id=str(existing_job["job_id"]),
                status=str(existing_job["status"]),
            )

        delay = local_now - scheduled_local
        if delay < timedelta(0):
            return None
        if delay > timedelta(minutes=config.grace_minutes):
            return self._schedule_store.record_skipped(
                schedule_key=schedule_key,
                scheduled_for=scheduled_local.isoformat(),
                timezone_name=str(config.timezone_name),
                reason=(
                    "Server became available after the configured catch-up "
                    "window; automatic analysis was not started."
                ),
            )

        try:
            job = start_daily_operations(
                schedule_key=schedule_key,
                scheduled_for=scheduled_local.isoformat(),
                schedule_timezone=str(config.timezone_name),
            )
        except ActiveJobError:
            # Another CEO or SYSTEM job has priority. Retry on the next poll
            # until the catch-up window expires.
            return None
        except DuplicateScheduledJobError as exc:
            existing_job = JOB_STORE.get_job(exc.job_id)
            if existing_job is None:
                return None
            job = existing_job
        except Exception:
            LOGGER.exception("Scheduled Daily Operations could not be started")
            return None

        return self._schedule_store.record_job(
            schedule_key=schedule_key,
            scheduled_for=scheduled_local.isoformat(),
            timezone_name=str(config.timezone_name),
            job_id=str(job["job_id"]),
            status=str(job["status"]),
        )

    def _next_run_at(self, now: datetime | None = None) -> str | None:
        config = self._config
        if not config.enabled or config.timezone is None or config.daily_time is None:
            return None
        current = (now or datetime.now(timezone.utc)).astimezone(config.timezone)
        today_run = datetime.combine(
            current.date(),
            config.daily_time,
            tzinfo=config.timezone,
        )
        today_key = f"DAILY_OPERATIONS:{current.date().isoformat()}"
        today_recorded = self._schedule_store.get(today_key) is not None
        within_catch_up = current <= today_run + timedelta(
            minutes=config.grace_minutes
        )
        if not today_recorded and within_catch_up:
            return today_run.isoformat()
        return (today_run + timedelta(days=1)).isoformat()

    def snapshot(self) -> dict[str, object]:
        config = self._config
        return {
            "enabled": config.enabled,
            "daily_time": (
                config.daily_time.strftime("%H:%M")
                if config.daily_time is not None
                else None
            ),
            "timezone": config.timezone_name,
            "misfire_grace_minutes": config.grace_minutes,
            "next_run_at": self._next_run_at(),
            "recent_events": self._schedule_store.recent(7),
        }


DAILY_SCHEDULER = DailyScheduler()
