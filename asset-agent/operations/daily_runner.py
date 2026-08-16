from collections.abc import Callable
from datetime import datetime, timezone

from data.portfolio_monitor import get_live_portfolio_snapshots
from departments.monitoring import run_daily_monitoring
from executive.daily_cio import run_daily_cio_decision
from operations.change_detector import compare_portfolio_snapshots
from operations.run_store import RUN_STORE
from reporting.briefing import run_korean_ceo_brief


DailyStatusCallback = Callable[[str, str, str | None], None]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(
    status_callback: DailyStatusCallback | None,
    agent: str,
    status: str,
    task: str,
) -> None:
    if status_callback is not None:
        status_callback(agent, status, task)


def run_daily_operations(
    status_callback: DailyStatusCallback | None = None,
) -> dict[str, object]:
    """Run one read-only Daily Operations cycle and persist the result."""
    started_at = _now_iso()
    run_id = RUN_STORE.start_run(started_at)

    try:
        previous_snapshot = RUN_STORE.latest_snapshot()

        _emit(
            status_callback,
            "Portfolio",
            "WORKING",
            "Daily Operations · Toss 포트폴리오 + 종목식별 Snapshot",
        )
        readable_snapshot, current_snapshot = get_live_portfolio_snapshots()
        changes = compare_portfolio_snapshots(previous_snapshot, current_snapshot)
        RUN_STORE.save_snapshot(run_id, current_snapshot)
        _emit(
            status_callback,
            "Portfolio",
            "DONE",
            "Daily Operations · Toss 포트폴리오 + 종목식별 Snapshot",
        )

        _emit(
            status_callback,
            "Analysis",
            "WORKING",
            "Daily Operations · 보유종목 중요 변화 모니터링",
        )
        monitoring = run_daily_monitoring(
            current_snapshot.positions,
            previous_snapshot.captured_at if previous_snapshot else None,
        )
        _emit(
            status_callback,
            "Analysis",
            "DONE",
            "Daily Operations · 보유종목 중요 변화 모니터링",
        )

        _emit(
            status_callback,
            "CIO",
            "WORKING",
            "Daily Operations · CEO 에스컬레이션 판단",
        )
        cio_decision = run_daily_cio_decision(
            current_snapshot,
            changes,
            monitoring,
        )
        _emit(
            status_callback,
            "CIO",
            "DONE",
            "Daily Operations · CEO 에스컬레이션 판단",
        )

        should_brief_ceo = (
            cio_decision.material_change
            or cio_decision.escalation != "NONE"
            or cio_decision.ceo_action_required
        )

        briefing: str | None = None
        if should_brief_ceo:
            _emit(
                status_callback,
                "Briefing",
                "WORKING",
                "Daily Operations · CEO 보고서 작성",
            )
            source_report = "\n\n".join(
                [
                    "DAILY CIO DECISION:\n" + cio_decision.model_dump_json(indent=2),
                    "DETERMINISTIC PORTFOLIO CHANGES:\n" + changes.model_dump_json(indent=2),
                    "DAILY MONITORING:\n" + monitoring.model_dump_json(indent=2),
                ]
            )
            briefing = run_korean_ceo_brief(
                source_report=source_report,
                report_type="DAILY_OPERATIONS",
                portfolio_snapshot=readable_snapshot,
            )
            _emit(
                status_callback,
                "Briefing",
                "DONE",
                "Daily Operations · CEO 보고서 작성",
            )

        completed_at = _now_iso()
        RUN_STORE.complete_run(
            run_id=run_id,
            completed_at=completed_at,
            changes=changes.model_dump(),
            monitoring=monitoring.model_dump(),
            cio=cio_decision.model_dump(),
            briefing=briefing,
        )

        return {
            "run_id": run_id,
            "status": "COMPLETED",
            "started_at": started_at,
            "completed_at": completed_at,
            "changes": changes.model_dump(),
            "monitoring": monitoring.model_dump(),
            "cio": cio_decision.model_dump(),
            "briefing": briefing,
        }

    except Exception as exc:
        RUN_STORE.fail_run(
            run_id,
            _now_iso(),
            f"{type(exc).__name__}: {exc}",
        )
        raise
