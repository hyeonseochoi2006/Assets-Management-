from typing import Literal

from operations.models import ChangeSet, DailyAnalysisGate, PortfolioSnapshot


_WATCH_REVIEW_TYPES = {
    "FILING_FOUND",
    "EARNINGS_CHANGED",
    "NEWS_FOUND",
    "HOLDING_MISSING_UNCONFIRMED",
    "DATA_QUALITY_WARNING",
    "CURRENCY_CHANGE",
    "QUANTITY_CHANGE",
    "WEIGHT_CHANGE",
}


def evaluate_daily_analysis_gate(
    changes: ChangeSet,
    snapshot: PortfolioSnapshot,
    run_kind: Literal["SCAN", "CLOSE"],
) -> DailyAnalysisGate:
    """Route attention with deterministic rules before any AI call is allowed."""
    material = [event for event in changes.events if event.severity == "MATERIAL"]
    reviewable_watch = [
        event
        for event in changes.events
        if event.severity == "WATCH" and event.event_type in _WATCH_REVIEW_TYPES
    ]
    material_ids = {event.event_id for event in material}
    triggers = material + [
        event for event in reviewable_watch if event.event_id not in material_ids
    ]

    if not triggers:
        quiet_count = sum(event.severity == "QUIET" for event in changes.events)
        reasons = [
            "No material or reviewable WATCH event was detected; AI calls were skipped."
        ]
        if changes.events and quiet_count != len(changes.events):
            reasons.append(
                "Price/value movement alone stayed below the material "
                "threshold and was stored only."
            )
        return DailyAnalysisGate(
            decision="SKIP_AI",
            run_kind=run_kind,
            ai_monitoring_required=False,
            ai_cio_required=False,
            targeted_symbols=[],
            triggering_event_ids=[],
            reasons=reasons,
        )

    current_symbols = {
        position.symbol.strip().upper() for position in snapshot.positions
    }
    targeted_symbols = sorted(
        {
            event.symbol.strip().upper()
            for event in triggers
            if event.symbol.strip().upper() in current_symbols
            and event.symbol.strip().upper() != "PORTFOLIO"
        }
    )
    has_researchable_trigger = any(
        event.symbol.strip().upper() in targeted_symbols
        and event.event_type != "DATA_QUALITY_WARNING"
        for event in triggers
    )
    decision = (
        "CIO_REVIEW"
        if material or changes.data_quality == "BLOCKED"
        else "TARGETED_REVIEW"
    )
    return DailyAnalysisGate(
        decision=decision,
        run_kind=run_kind,
        ai_monitoring_required=has_researchable_trigger,
        ai_cio_required=True,
        targeted_symbols=targeted_symbols,
        triggering_event_ids=[event.event_id for event in triggers],
        reasons=[
            (
                "At least one MATERIAL event requires CIO review."
                if material
                else "A reviewable WATCH event requires targeted monitoring."
            ),
            "Opportunity scouting remains disabled in routine scans; "
            "it will use a separate approved cadence.",
        ],
    )
