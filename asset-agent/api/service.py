import json
import os
import socket
from collections.abc import Callable
from datetime import datetime, timezone
from threading import Event, Lock, Thread
from typing import Literal
from uuid import uuid4

from ceo_desk.command_router import CEOAction, CEOCommand, route_command
from ceo_desk.hq_state import AGENT_MISSIONS
from data.portfolio_monitor import get_live_portfolio_snapshot
from departments.portfolio import run_portfolio_review
from executive.cio import run_cio_pipeline
from operations.daily_recovery import DAILY_RECOVERY_STORE
from operations.daily_runner import run_daily_operations
from operations.run_store import RUN_STORE
from operations.schedule_store import SCHEDULE_STORE
from reporting.briefing import run_korean_ceo_brief

from api.job_store import ActiveJobExistsError, JOB_STORE


_START_LOCK = Lock()
_WORKER_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex}"
_HEARTBEAT_INTERVAL_SECONDS = 15


class ActiveJobError(RuntimeError):
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(f"Another job is already active: {job_id}")


class RetryJobError(RuntimeError):
    pass


def recover_interrupted_work() -> list[str]:
    """Mark jobs whose worker lease expired and link Daily runs to them."""
    recovered_ids = JOB_STORE.recover_stale_jobs()
    RUN_STORE.interrupt_jobs(
        recovered_ids,
        datetime.now(timezone.utc).isoformat(),
    )
    SCHEDULE_STORE.interrupt_jobs(
        recovered_ids,
        "Server stopped before the scheduled analysis completed.",
    )
    return recovered_ids


def _heartbeat_job(job_id: str, stop: Event) -> None:
    while not stop.wait(_HEARTBEAT_INTERVAL_SECONDS):
        if not JOB_STORE.heartbeat(job_id, _WORKER_ID):
            return


def _task_for(agent: str, subject: str) -> str:
    mission = AGENT_MISSIONS.get(agent, "업무 수행")
    return f"{subject} · {mission}"


def _help_text() -> str:
    return (
        "현재 가능한 명령:\n"
        "- PANW 분석해\n"
        "- 팔란티어 분석해\n"
        "- 내 포트폴리오 보여줘\n"
        "- 내 포트폴리오 점검해\n\n"
        "실제 주문은 실행하지 않으며 최종 투자 결정은 CEO가 합니다."
    )


def _unknown_text() -> str:
    return (
        "아직 그 지시는 정확히 분류하지 못했습니다. "
        "예: `PANW 분석해`, `내 포트폴리오 보여줘`, "
        "`내 포트폴리오 점검해`"
    )


def _run_job(job_id: str, command: CEOCommand) -> None:
    heartbeat_stop = Event()
    heartbeat_thread = Thread(
        target=_heartbeat_job,
        args=(job_id, heartbeat_stop),
        daemon=True,
        name=f"asset-heartbeat-{job_id}",
    )
    heartbeat_thread.start()

    try:
        if command.action == CEOAction.HELP:
            JOB_STORE.complete_job(job_id, _help_text(), "markdown")
            return

        if command.action == CEOAction.UNKNOWN:
            JOB_STORE.complete_job(job_id, _unknown_text(), "markdown")
            return

        if command.action == CEOAction.SHOW_PORTFOLIO:
            task = _task_for("Portfolio", "현재 Toss 포트폴리오 조회")
            JOB_STORE.update_agent(job_id, "Portfolio", "WORKING", task)
            snapshot = get_live_portfolio_snapshot()
            JOB_STORE.update_agent(job_id, "Portfolio", "DONE", task)
            JOB_STORE.complete_job(job_id, snapshot, "portfolio")
            return

        if command.action == CEOAction.REVIEW_PORTFOLIO:
            portfolio_task = _task_for("Portfolio", "전체 포트폴리오")
            JOB_STORE.update_agent(
                job_id,
                "Portfolio",
                "WORKING",
                portfolio_task,
            )
            snapshot = get_live_portfolio_snapshot()
            review = run_portfolio_review(snapshot)
            JOB_STORE.update_agent(job_id, "Portfolio", "DONE", portfolio_task)

            briefing_task = _task_for("Briefing", "전체 포트폴리오")
            JOB_STORE.update_agent(
                job_id,
                "Briefing",
                "WORKING",
                briefing_task,
            )
            report = run_korean_ceo_brief(
                source_report=review,
                report_type="WHOLE_PORTFOLIO_REVIEW",
                portfolio_snapshot=snapshot,
            )
            JOB_STORE.update_agent(job_id, "Briefing", "DONE", briefing_task)
            JOB_STORE.complete_job(job_id, report, "markdown")
            return

        if command.action == CEOAction.ANALYZE_COMPANY and command.ticker:
            ticker = command.ticker
            try:
                snapshot = get_live_portfolio_snapshot()
            except Exception:
                task = _task_for("Portfolio", f"{ticker} · 실제 계좌 불러오기")
                JOB_STORE.update_agent(job_id, "Portfolio", "ERROR", task)
                raise

            def status_callback(agent: str, status: str) -> None:
                JOB_STORE.update_agent(
                    job_id,
                    agent,
                    status,
                    _task_for(agent, ticker),
                )

            _, cio_report = run_cio_pipeline(
                ticker,
                portfolio_snapshot=snapshot,
                status_callback=status_callback,
            )

            briefing_task = _task_for("Briefing", ticker)
            JOB_STORE.update_agent(
                job_id,
                "Briefing",
                "WORKING",
                briefing_task,
            )
            report = run_korean_ceo_brief(
                source_report=cio_report,
                report_type="COMPANY_ANALYSIS",
                ticker=ticker,
                portfolio_snapshot=snapshot,
            )
            JOB_STORE.update_agent(job_id, "Briefing", "DONE", briefing_task)
            JOB_STORE.complete_job(job_id, report, "markdown")
            return

        JOB_STORE.complete_job(job_id, _unknown_text(), "markdown")

    except Exception as exc:
        JOB_STORE.fail_job(job_id, f"{type(exc).__name__}: {exc}")
    finally:
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=1)


def _daily_output(result: dict[str, object], run_kind: str) -> str:
    briefing = result.get("briefing")
    if isinstance(briefing, str) and briefing.strip():
        return briefing

    cio = result.get("cio")
    cio_summary = "중요 변화 없음."
    if isinstance(cio, dict):
        summary = cio.get("summary")
        if isinstance(summary, str) and summary.strip():
            cio_summary = summary
    return (
        f"=== DAILY {run_kind} COMPLETE ===\n"
        f"{cio_summary}\n"
        "CEO 행동 필요 없음.\n"
        f"Run ID: {result['run_id']}"
    )


def _run_daily_system_job(
    job_id: str,
    run_kind: Literal["SCAN", "CLOSE"] = "CLOSE",
    resume_run_id: str | None = None,
) -> None:
    heartbeat_stop = Event()
    heartbeat_thread = Thread(
        target=_heartbeat_job,
        args=(job_id, heartbeat_stop),
        daemon=True,
        name=f"asset-heartbeat-{job_id}",
    )
    heartbeat_thread.start()

    try:
        def status_callback(agent: str, status: str, task: str | None) -> None:
            JOB_STORE.update_agent(job_id, agent, status, task)

        result = run_daily_operations(
            status_callback=status_callback,
            job_id=job_id,
            run_kind=run_kind,
            resume_run_id=resume_run_id,
        )
        JOB_STORE.complete_job(job_id, _daily_output(result, run_kind), "markdown")
        SCHEDULE_STORE.finish_job(job_id, "COMPLETED")

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        JOB_STORE.fail_job(job_id, error)
        SCHEDULE_STORE.finish_job(job_id, "FAILED", error)
    finally:
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=1)


def _start_thread(
    job: dict[str, object],
    target: Callable[..., None],
    args: tuple[object, ...],
    name: str,
) -> None:
    job_id = str(job["job_id"])
    JOB_STORE.mark_running(job_id, _WORKER_ID)
    thread = Thread(
        target=target,
        args=args,
        daemon=True,
        name=name,
    )
    try:
        thread.start()
    except Exception as exc:
        error = f"ThreadStartError: {exc}"
        JOB_STORE.fail_job(job_id, error)
        SCHEDULE_STORE.finish_job(job_id, "FAILED", error)
        raise


def resume_interrupted_daily_work() -> list[str]:
    """Resume at most one interrupted scheduled Daily job from checkpoints.

    Manual CEO jobs are intentionally excluded. If the Daily run had already
    completed before the process died, only the outer job/schedule record is
    repaired; no analysis is repeated.
    """
    resumed_job_ids: list[str] = []
    with _START_LOCK:
        if JOB_STORE.active_job_id() is not None:
            return resumed_job_ids

        for item in DAILY_RECOVERY_STORE.recoverable_jobs():
            job_id = str(item["job_id"])
            action = str(item["action"])
            run_kind: Literal["SCAN", "CLOSE"] = (
                "SCAN" if action == "DAILY_SCAN" else "CLOSE"
            )
            run_id = str(item["run_id"]) if item.get("run_id") else None
            run_status = str(item["run_status"]) if item.get("run_status") else None

            if run_status == "COMPLETED" and run_id is not None:
                briefing = item.get("briefing")
                if isinstance(briefing, str) and briefing.strip():
                    output = briefing
                else:
                    summary = "중요 변화 없음."
                    raw_cio = item.get("cio_json")
                    if isinstance(raw_cio, str) and raw_cio:
                        try:
                            cio = json.loads(raw_cio)
                        except json.JSONDecodeError:
                            cio = None
                        if isinstance(cio, dict) and isinstance(cio.get("summary"), str):
                            summary = str(cio["summary"])
                    output = (
                        f"=== DAILY {run_kind} COMPLETE ===\n"
                        f"{summary}\n"
                        "복구 시 이미 완료된 Run을 확인했습니다. 분석을 반복하지 않았습니다.\n"
                        f"Run ID: {run_id}"
                    )
                if DAILY_RECOVERY_STORE.restore_completed_job(job_id, output):
                    resumed_job_ids.append(job_id)
                continue

            if run_status not in {None, "INTERRUPTED"}:
                continue
            if not DAILY_RECOVERY_STORE.requeue_interrupted_job(job_id):
                break
            job = JOB_STORE.get_job(job_id)
            if job is None:
                break
            _start_thread(
                job,
                _run_daily_system_job,
                (job_id, run_kind, run_id),
                f"asset-daily-resume-{job_id}",
            )
            resumed_job_ids.append(job_id)
            break

    return resumed_job_ids


def start_job(
    command_text: str,
    retry_of: str | None = None,
) -> dict[str, object]:
    command = route_command(command_text)

    with _START_LOCK:
        recover_interrupted_work()
        active_job_id = JOB_STORE.active_job_id()
        if active_job_id is not None:
            raise ActiveJobError(active_job_id)

        try:
            job = JOB_STORE.create_job(
                command=command_text,
                action=command.action.value,
                ticker=command.ticker,
                source="CEO",
                retry_of=retry_of,
            )
        except ActiveJobExistsError as exc:
            raise ActiveJobError(exc.job_id) from exc
        _start_thread(
            job,
            _run_job,
            (str(job["job_id"]), command),
            f"asset-job-{job['job_id']}",
        )

    return JOB_STORE.get_job(str(job["job_id"])) or job


def start_daily_operations(
    retry_of: str | None = None,
    schedule_key: str | None = None,
    scheduled_for: str | None = None,
    schedule_timezone: str | None = None,
    run_kind: Literal["SCAN", "CLOSE"] = "CLOSE",
) -> dict[str, object]:
    """Start one manual close check or scheduled low-cost scan."""
    if run_kind not in {"SCAN", "CLOSE"}:
        raise ValueError("run_kind must be SCAN or CLOSE")
    schedule_values = (schedule_key, scheduled_for, schedule_timezone)
    if any(value is not None for value in schedule_values) and not all(
        value is not None for value in schedule_values
    ):
        raise ValueError("Scheduled Daily Operations requires complete context")

    with _START_LOCK:
        recover_interrupted_work()
        active_job_id = JOB_STORE.active_job_id()
        if active_job_id is not None:
            raise ActiveJobError(active_job_id)

        try:
            job = JOB_STORE.create_job(
                command=(
                    "AUTO DAILY CHANGE SCAN"
                    if run_kind == "SCAN"
                    else "AUTO DAILY CLOSE"
                ),
                action=("DAILY_SCAN" if run_kind == "SCAN" else "DAILY_OPERATIONS"),
                ticker=None,
                source="SYSTEM",
                retry_of=retry_of,
                schedule_key=schedule_key,
            )
        except ActiveJobExistsError as exc:
            raise ActiveJobError(exc.job_id) from exc
        if schedule_key and scheduled_for and schedule_timezone:
            SCHEDULE_STORE.record_job(
                schedule_key=schedule_key,
                scheduled_for=scheduled_for,
                timezone_name=schedule_timezone,
                job_id=str(job["job_id"]),
                status="QUEUED",
            )
        _start_thread(
            job,
            _run_daily_system_job,
            (str(job["job_id"]), run_kind, None),
            f"asset-daily-{job['job_id']}",
        )

    latest_job = JOB_STORE.get_job(str(job["job_id"])) or job
    if schedule_key and scheduled_for and schedule_timezone:
        SCHEDULE_STORE.record_job(
            schedule_key=schedule_key,
            scheduled_for=scheduled_for,
            timezone_name=schedule_timezone,
            job_id=str(job["job_id"]),
            status=str(latest_job["status"]),
        )
    return latest_job


def retry_job(job_id: str) -> dict[str, object]:
    original = JOB_STORE.get_job(job_id)
    if original is None:
        raise RetryJobError("job not found")
    if original["status"] not in {"FAILED", "INTERRUPTED"}:
        raise RetryJobError("only FAILED or INTERRUPTED jobs can be retried")
    if original["action"] in {"DAILY_OPERATIONS", "DAILY_SCAN"}:
        return start_daily_operations(
            retry_of=job_id,
            run_kind=("SCAN" if original["action"] == "DAILY_SCAN" else "CLOSE"),
        )
    return start_job(str(original["command"]), retry_of=job_id)
