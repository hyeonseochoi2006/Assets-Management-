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
from operations.checkpoint_store import CHECKPOINT_STORE
from operations.daily_recovery import DAILY_RECOVERY_STORE
from operations.external_changes import run_external_change_detection
from operations.external_changes.models import ExternalChangeReport
from operations.models import (
    ChangeSet,
    DailyAnalysisGate,
    DailyCioDecision,
    MonitoringReport,
    OpportunityScoutReport,
    PortfolioSnapshot,
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


def _optional_snapshot(value: object) -> PortfolioSnapshot | None:
    return PortfolioSnapshot.model_validate(value) if isinstance(value, dict) else None


def run_daily_operations(
    status_callback: DailyStatusCallback | None = None,
    job_id: str | None = None,
    run_kind: Literal["SCAN", "CLOSE"] = "CLOSE",
    resume_run_id: str | None = None,
) -> dict[str, object]:
    """Run or resume one read-only Daily Operations cycle.

    Completed workflow checkpoints are reused after a process interruption. No
    checkpoint grants trading authority; this remains decision support only.
    """
    if run_kind not in {"SCAN", "CLOSE"}:
        raise ValueError("run_kind must be SCAN or CLOSE")

    resumed = resume_run_id is not None
    if resumed:
        run_id = str(resume_run_id)
        CHECKPOINT_STORE.interrupt_running(
            run_id,
            "Previous process stopped before this checkpoint completed.",
        )
        resumed_run = DAILY_RECOVERY_STORE.prepare_run_resume(
            run_id,
            str(job_id or "UNASSIGNED"),
            run_kind,
        )
        started_at = str(resumed_run["started_at"])
        resume_count = int(resumed_run.get("resume_count", 0))
    else:
        started_at = _now_iso()
        run_id = RUN_STORE.start_run(started_at, job_id=job_id, run_kind=run_kind)
        resume_count = 0

    active_step: str | None = None

    try:
        # STEP 1: Freeze the exact current and reference snapshots first. A
        # resumed run must not fetch a newer portfolio and accidentally count a
        # process restart as another market observation.
        snapshot_payload = CHECKPOINT_STORE.completed_payload(
            run_id,
            "SNAPSHOT_READY",
        )
        if snapshot_payload is not None:
            readable_snapshot = str(snapshot_payload["readable_snapshot"])
            current_snapshot = PortfolioSnapshot.model_validate(
                snapshot_payload["current_snapshot"]
            )
            previous_snapshot = _optional_snapshot(
                snapshot_payload.get("previous_snapshot")
            )
            previous_close_snapshot = _optional_snapshot(
                snapshot_payload.get("previous_close_snapshot")
            )
        else:
            active_step = "SNAPSHOT_READY"
            CHECKPOINT_STORE.begin(run_id, active_step)
            previous_snapshot = RUN_STORE.latest_snapshot()
            previous_close_snapshot = RUN_STORE.latest_close_snapshot()

            _emit(
                status_callback,
                "Portfolio",
                "WORKING",
                "Daily Operations · Toss 포트폴리오 + 종목식별 Snapshot",
            )
            readable_snapshot, current_snapshot = get_live_portfolio_snapshots()
            CHECKPOINT_STORE.complete(
                run_id,
                active_step,
                {
                    "readable_snapshot": readable_snapshot,
                    "current_snapshot": current_snapshot.model_dump(),
                    "previous_snapshot": (
                        previous_snapshot.model_dump() if previous_snapshot else None
                    ),
                    "previous_close_snapshot": (
                        previous_close_snapshot.model_dump()
                        if previous_close_snapshot
                        else None
                    ),
                },
            )
            active_step = None

        # STEP 2: Deterministic changes, official-source checks, event ledger,
        # and AI gate. These outputs are frozen so downstream AI never sees a
        # different data state after restart.
        data_payload = CHECKPOINT_STORE.completed_payload(run_id, "DATA_READY")
        if data_payload is not None:
            changes = ChangeSet.model_validate(data_payload["changes"])
            external_changes = ExternalChangeReport.model_validate(
                data_payload["external_changes"]
            )
            gate = DailyAnalysisGate.model_validate(data_payload["gate"])
        else:
            active_step = "DATA_READY"
            CHECKPOINT_STORE.begin(run_id, active_step)
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
                current_snapshot,
                run_id=run_id,
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
            CHECKPOINT_STORE.complete(
                run_id,
                active_step,
                {
                    "changes": changes.model_dump(),
                    "external_changes": external_changes.model_dump(),
                    "gate": gate.model_dump(),
                },
            )
            active_step = None

        # Saving the comparison baseline is made effectively idempotent for a
        # resumed run by checking whether this run already owns a snapshot row.
        if not DAILY_RECOVERY_STORE.snapshot_saved(run_id):
            RUN_STORE.save_snapshot(
                run_id,
                current_snapshot,
                baseline_eligible=changes.data_quality != "BLOCKED",
                run_kind=run_kind,
            )
        else:
            # Ensure daily_runs.snapshot_json remains populated even after a
            # recovery path; save_snapshot already did this on the first pass.
            pass
        _emit(
            status_callback,
            "Portfolio",
            "DONE",
            "Daily Operations · Toss 포트폴리오 + 종목식별 Snapshot",
        )

        # STEP 3: Targeted AI monitoring. If it completed before the crash, the
        # exact model result is reused instead of spending tokens again.
        monitoring_payload = CHECKPOINT_STORE.completed_payload(
            run_id,
            "MONITORING_READY",
        )
        if monitoring_payload is not None:
            monitoring = MonitoringReport.model_validate(
                monitoring_payload["monitoring"]
            )
            opportunities = OpportunityScoutReport.model_validate(
                monitoring_payload["opportunities"]
            )
        else:
            active_step = "MONITORING_READY"
            CHECKPOINT_STORE.begin(run_id, active_step)
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
            CHECKPOINT_STORE.complete(
                run_id,
                active_step,
                {
                    "monitoring": monitoring.model_dump(),
                    "opportunities": opportunities.model_dump(),
                },
            )
            active_step = None

        # STEP 4: CIO synthesis.
        cio_payload = CHECKPOINT_STORE.completed_payload(run_id, "CIO_READY")
        if cio_payload is not None:
            cio_decision = DailyCioDecision.model_validate(cio_payload["cio"])
        else:
            active_step = "CIO_READY"
            CHECKPOINT_STORE.begin(run_id, active_step)
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
            CHECKPOINT_STORE.complete(
                run_id,
                active_step,
                {"cio": cio_decision.model_dump()},
            )
            active_step = None

        should_brief_ceo = (
            cio_decision.material_change
            or cio_decision.escalation != "NONE"
            or cio_decision.ceo_action_required
        )

        # STEP 5: CEO briefing.
        briefing_payload = CHECKPOINT_STORE.completed_payload(
            run_id,
            "BRIEFING_READY",
        )
        if briefing_payload is not None:
            raw_briefing = briefing_payload.get("briefing")
            briefing = str(raw_briefing) if raw_briefing is not None else None
        else:
            active_step = "BRIEFING_READY"
            CHECKPOINT_STORE.begin(run_id, active_step)
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
                        "DETERMINISTIC PORTFOLIO CHANGES:\n"
                        + changes.model_dump_json(indent=2),
                        "OFFICIAL EXTERNAL CHANGES:\n"
                        + external_changes.model_dump_json(indent=2),
                        "DAILY ANALYSIS GATE:\n" + gate.model_dump_json(indent=2),
                        "DAILY MONITORING:\n" + monitoring.model_dump_json(indent=2),
                        "OPPORTUNITY SCOUT:\n"
                        + opportunities.model_dump_json(indent=2),
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
            CHECKPOINT_STORE.complete(
                run_id,
                active_step,
                {"briefing": briefing},
            )
            active_step = None

        # STEP 6: Approval creation is already idempotent by run_id. Persisting
        # its result means a restart will not create another CEO request.
        approval_payload = CHECKPOINT_STORE.completed_payload(
            run_id,
            "APPROVAL_READY",
        )
        if approval_payload is not None:
            raw_approval = approval_payload.get("approval")
            approval = dict(raw_approval) if isinstance(raw_approval, dict) else None
        else:
            active_step = "APPROVAL_READY"
            CHECKPOINT_STORE.begin(run_id, active_step)
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
            CHECKPOINT_STORE.complete(
                run_id,
                active_step,
                {"approval": approval},
            )
            active_step = None

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
            "resumed": resumed,
            "resume_count": resume_count,
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
        error = f"{type(exc).__name__}: {exc}"
        if active_step is not None:
            CHECKPOINT_STORE.fail(run_id, active_step, error)
        RUN_STORE.fail_run(run_id, _now_iso(), error)
        raise
