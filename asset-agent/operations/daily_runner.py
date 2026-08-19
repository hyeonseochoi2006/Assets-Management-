from collections.abc import Callable
from datetime import datetime, timezone
from typing import Literal

from data.portfolio_monitor import get_live_portfolio_snapshots
from departments.monitoring import run_daily_monitoring
from executive.daily_cio import run_daily_cio_decision
from operations.approval_store import APPROVAL_STORE
from operations.analysis_gate import evaluate_daily_analysis_gate
from operations.change_detector import compare_portfolio_with_daily_reference
from operations.change_event_store import CHANGE_EVENT_STORE
from operations.external_changes import run_external_change_detection
from operations.models import (
    DailyCioDecision,
    MonitoringReport,
    OpportunityScoutReport,
)
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
    job_id: str | None = None,
    run_kind: Literal["SCAN", "CLOSE"] = "CLOSE",
) -> dict[str, object]:
    """Run one read-only Daily Operations cycle and persist the result."""
    started_at = _now_iso()
    run_id = RUN_STORE.start_run(started_at, job_id=job_id, run_kind=run_kind)

    try:
        previous_snapshot = RUN_STORE.latest_snapshot()
        previous_close_snapshot = RUN_STORE.latest_close_snapshot()

        _emit(
            status_callback,
            "Portfolio",
            "WORKING",
            "Daily Operations · Toss 포트폴리오 + 종목식별 Snapshot",
        )
        readable_snapshot, current_snapshot = get_live_portfolio_snapshots()
        changes = compare_portfolio_with_daily_reference(
            previous_snapshot,
            previous_close_snapshot if run_kind == "CLOSE" else None,
            current_snapshot,
        )

        _emit(
            status_callback,
            "Analysis",
            "WORKING",
            "Daily Operations · 공식 공시 저비용 변화 확인",
        )
        external_changes, external_events = run_external_change_detection(
            current_snapshot
        )
        changes = CHANGE_EVENT_STORE.process(
            run_id,
            current_snapshot,
            changes,
            additional_events=external_events,
        )
        gate = evaluate_daily_analysis_gate(changes, current_snapshot, run_kind)
        _emit(
            status_callback,
            "Analysis",
            "DONE",
            "Daily Operations · 공식 공시 저비용 변화 확인",
        )
        RUN_STORE.save_snapshot(
            run_id,
            current_snapshot,
            baseline_eligible=changes.data_quality != "BLOCKED",
            run_kind=run_kind,
        )
        _emit(
            status_callback,
            "Portfolio",
            "DONE",
            "Daily Operations · Toss 포트폴리오 + 종목식별 Snapshot",
        )

        if gate.ai_monitoring_required:
            _emit(
                status_callback,
                "Analysis",
                "WORKING",
                "Daily Operations · 변화 종목만 AI 모니터링",
            )
            targeted_positions = [
                position
                for position in current_snapshot.positions
                if position.symbol.strip().upper() in gate.targeted_symbols
            ]
            monitoring = run_daily_monitoring(
                targeted_positions,
                previous_snapshot.captured_at if previous_snapshot else None,
            )
            _emit(
                status_callback,
                "Analysis",
                "DONE",
                "Daily Operations · 변화 종목만 AI 모니터링",
            )
        else:
            monitoring = MonitoringReport(
                findings=[],
                data_quality=(
                    "LOW" if changes.data_quality == "BLOCKED" else "HIGH"
                ),
                notes=[
                    "AI monitoring skipped by deterministic daily-analysis gate.",
                    *gate.reasons,
                ],
            )
            _emit(
                status_callback,
                "Analysis",
                "DONE",
                "Daily Operations · 중요 변화 없음, AI 호출 생략",
            )

        opportunities = OpportunityScoutReport(
            candidates=[],
            data_quality="HIGH",
            scan_scope="SKIPPED BY ROUTINE DAILY ANALYSIS GATE",
            notes=[
                "Opportunity Scout is separated from routine scans to avoid "
                "unrelated daily AI cost."
            ],
        )

        if gate.ai_cio_required:
            _emit(
                status_callback,
                "CIO",
                "WORKING",
                "Daily Operations · 중요 변화 CIO 검토",
            )
            cio_decision = run_daily_cio_decision(
                current_snapshot,
                changes,
                monitoring,
                opportunities,
            )
            _emit(
                status_callback,
                "CIO",
                "DONE",
                "Daily Operations · 중요 변화 CIO 검토",
            )
        else:
            conclusion = (
                "Final close check completed with no event requiring AI review."
                if run_kind == "CLOSE"
                else "Low-cost change scan completed with no event requiring AI review."
            )
            cio_decision = DailyCioDecision(
                material_change=False,
                escalation="NONE",
                ceo_action_required=False,
                affected_tickers=[],
                summary=conclusion,
                reasons=gate.reasons,
                recommended_next_step=(
                    "Store the observations and wait for the next scheduled scan."
                ),
            )
            _emit(
                status_callback,
                "CIO",
                "DONE",
                "Daily Operations · AI 검토 불필요",
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
                    "OFFICIAL EXTERNAL CHANGES:\n"
                    + external_changes.model_dump_json(indent=2),
                    "DAILY ANALYSIS GATE:\n" + gate.model_dump_json(indent=2),
                    "DAILY MONITORING:\n" + monitoring.model_dump_json(indent=2),
                    "OPPORTUNITY SCOUT:\n" + opportunities.model_dump_json(indent=2),
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

        approval: dict[str, object] | None = None
        if cio_decision.escalation != "NONE" or cio_decision.ceo_action_required:
            approval_category = (
                cio_decision.escalation
                if cio_decision.escalation != "NONE"
                else "DECISION"
            )
            approval = APPROVAL_STORE.create_from_cio(
                run_id=run_id,
                category=approval_category,
                summary=cio_decision.summary,
                reasons=cio_decision.reasons,
                affected_tickers=cio_decision.affected_tickers,
                recommended_next_step=cio_decision.recommended_next_step,
                briefing=briefing,
            )

        completed_at = _now_iso()
        RUN_STORE.complete_run(
            run_id=run_id,
            completed_at=completed_at,
            changes=changes.model_dump(),
            external_changes=external_changes.model_dump(),
            gate=gate.model_dump(),
            monitoring=monitoring.model_dump(),
            opportunities=opportunities.model_dump(),
            cio=cio_decision.model_dump(),
            briefing=briefing,
        )

        return {
            "run_id": run_id,
            "status": "COMPLETED",
            "started_at": started_at,
            "completed_at": completed_at,
            "run_kind": run_kind,
            "changes": changes.model_dump(),
            "external_changes": external_changes.model_dump(),
            "gate": gate.model_dump(),
            "monitoring": monitoring.model_dump(),
            "opportunities": opportunities.model_dump(),
            "cio": cio_decision.model_dump(),
            "briefing": briefing,
            "approval": approval,
        }

    except Exception as exc:
        RUN_STORE.fail_run(
            run_id,
            _now_iso(),
            f"{type(exc).__name__}: {exc}",
        )
        raise
