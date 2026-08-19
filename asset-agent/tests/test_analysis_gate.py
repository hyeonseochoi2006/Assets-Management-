from pathlib import Path

import pytest

import operations.daily_runner as daily_runner_module
from operations.analysis_gate import evaluate_daily_analysis_gate
from operations.change_detector import (
    build_change_event,
    compare_portfolio_snapshots,
    refresh_change_set,
)
from operations.change_event_store import ChangeEventStore
from operations.change_policy import PortfolioChangePolicy
from operations.external_changes.models import ExternalChangeReport
from operations.models import (
    DailyCioDecision,
    MonitoringReport,
    PortfolioSnapshot,
    PositionSnapshot,
)
from operations.run_store import DailyRunStore


def snapshot(
    captured_at: str,
    *,
    price: float = 100.0,
    symbol: str = "AAPL",
) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        captured_at=captured_at,
        account_seq="test-account",
        positions=[
            PositionSnapshot(
                symbol=symbol,
                currency="USD",
                quantity=10,
                price=price,
                position_value=price * 10,
                weight_pct=10,
            )
        ],
    )


def test_one_percent_price_move_skips_ai() -> None:
    previous = snapshot("2026-08-18T12:30:00+00:00")
    current = snapshot("2026-08-18T16:30:00+00:00", price=101)
    changes = compare_portfolio_snapshots(previous, current)

    gate = evaluate_daily_analysis_gate(changes, current, "SCAN")

    assert gate.decision == "SKIP_AI"
    assert gate.ai_monitoring_required is False
    assert gate.ai_cio_required is False


def test_price_only_watch_is_stored_without_ai() -> None:
    previous = snapshot("2026-08-18T12:30:00+00:00")
    current = snapshot("2026-08-18T16:30:00+00:00", price=105)
    changes = compare_portfolio_snapshots(previous, current)

    gate = evaluate_daily_analysis_gate(changes, current, "SCAN")

    assert changes.highest_severity == "WATCH"
    assert gate.decision == "SKIP_AI"
    assert "stored only" in " ".join(gate.reasons)


def test_material_price_move_routes_only_affected_symbol() -> None:
    previous = snapshot("2026-08-18T12:30:00+00:00")
    current = snapshot("2026-08-18T16:30:00+00:00", price=107)
    changes = compare_portfolio_snapshots(previous, current)

    gate = evaluate_daily_analysis_gate(changes, current, "SCAN")

    assert gate.decision == "CIO_REVIEW"
    assert gate.ai_monitoring_required is True
    assert gate.ai_cio_required is True
    assert gate.targeted_symbols == ["AAPL"]


def test_new_official_filing_routes_targeted_review() -> None:
    current = snapshot("2026-08-18T16:30:00+00:00")
    changes = compare_portfolio_snapshots(None, current)
    filing = build_change_event(
        event_type="FILING_FOUND",
        symbol="AAPL",
        severity="WATCH",
        detected_at=current.captured_at,
        previous_captured_at=None,
        previous=None,
        current="0000320193-26-000001",
        reason="New official filing.",
        policy=PortfolioChangePolicy(),
        source="SEC_EDGAR",
        identity_key="SEC_EDGAR:0000320193-26-000001",
        evidence=["official_url=https://www.sec.gov/example"],
    )
    changes.events.append(filing)
    refresh_change_set(changes)

    gate = evaluate_daily_analysis_gate(changes, current, "SCAN")

    assert gate.decision == "TARGETED_REVIEW"
    assert gate.targeted_symbols == ["AAPL"]
    assert gate.triggering_event_ids == [filing.event_id]


def test_blocked_data_routes_cio_without_company_web_research() -> None:
    current = snapshot("2026-08-18T16:30:00+00:00")
    current.positions.append(current.positions[0].model_copy())
    changes = compare_portfolio_snapshots(
        snapshot("2026-08-18T12:30:00+00:00"), current
    )

    gate = evaluate_daily_analysis_gate(changes, current, "CLOSE")

    assert changes.data_quality == "BLOCKED"
    assert gate.decision == "CIO_REVIEW"
    assert gate.ai_monitoring_required is False
    assert gate.ai_cio_required is True


def test_daily_runner_skips_all_ai_for_quiet_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "operations.db"
    run_store = DailyRunStore(db_path)
    event_store = ChangeEventStore(db_path)
    current = snapshot("2026-08-18T12:30:00+00:00")

    monkeypatch.setattr(daily_runner_module, "RUN_STORE", run_store)
    monkeypatch.setattr(daily_runner_module, "CHANGE_EVENT_STORE", event_store)
    monkeypatch.setattr(
        daily_runner_module,
        "get_live_portfolio_snapshots",
        lambda: ("test portfolio", current),
    )
    monkeypatch.setattr(
        daily_runner_module,
        "run_external_change_detection",
        lambda *_: (
            ExternalChangeReport(
                checked_at=current.captured_at,
                source_checks=[],
                new_documents=[],
                events_created=0,
                summary="No configured external source in test.",
            ),
            [],
        ),
    )
    monkeypatch.setattr(
        daily_runner_module,
        "run_daily_monitoring",
        lambda *_: pytest.fail("quiet scan must not call monitoring AI"),
    )
    monkeypatch.setattr(
        daily_runner_module,
        "run_daily_cio_decision",
        lambda *_: pytest.fail("quiet scan must not call CIO AI"),
    )

    result = daily_runner_module.run_daily_operations(run_kind="SCAN")
    latest = run_store.latest_run()

    assert result["gate"]["decision"] == "SKIP_AI"
    assert result["run_kind"] == "SCAN"
    assert result["monitoring"]["findings"] == []
    assert latest is not None
    assert latest["run_kind"] == "SCAN"
    assert latest["gate"]["decision"] == "SKIP_AI"


def test_daily_runner_calls_ai_only_for_target_symbol(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "operations.db"
    run_store = DailyRunStore(db_path)
    event_store = ChangeEventStore(db_path)
    current = snapshot("2026-08-18T16:30:00+00:00")
    filing = build_change_event(
        event_type="FILING_FOUND",
        symbol="AAPL",
        severity="WATCH",
        detected_at=current.captured_at,
        previous_captured_at=None,
        previous=None,
        current="filing-1",
        reason="New official filing.",
        policy=PortfolioChangePolicy(),
        source="SEC_EDGAR",
        identity_key="SEC_EDGAR:filing-1",
        evidence=["official_url=https://www.sec.gov/example"],
    )
    monitored: list[list[str]] = []

    monkeypatch.setattr(daily_runner_module, "RUN_STORE", run_store)
    monkeypatch.setattr(daily_runner_module, "CHANGE_EVENT_STORE", event_store)
    monkeypatch.setattr(
        daily_runner_module,
        "get_live_portfolio_snapshots",
        lambda: ("test portfolio", current),
    )
    monkeypatch.setattr(
        daily_runner_module,
        "run_external_change_detection",
        lambda *_: (
            ExternalChangeReport(
                checked_at=current.captured_at,
                source_checks=[],
                new_documents=[],
                events_created=1,
                summary="One new official filing.",
            ),
            [filing],
        ),
    )

    def fake_monitoring(
        positions: list[PositionSnapshot], _: str | None
    ) -> MonitoringReport:
        monitored.append([position.symbol for position in positions])
        return MonitoringReport(findings=[], data_quality="HIGH", notes=[])

    monkeypatch.setattr(daily_runner_module, "run_daily_monitoring", fake_monitoring)
    monkeypatch.setattr(
        daily_runner_module,
        "run_daily_cio_decision",
        lambda *_: DailyCioDecision(
            material_change=False,
            escalation="NONE",
            ceo_action_required=False,
            affected_tickers=[],
            summary="Reviewed filing; no CEO action required.",
            reasons=[],
            recommended_next_step="Continue monitoring.",
        ),
    )

    result = daily_runner_module.run_daily_operations(run_kind="SCAN")

    assert monitored == [["AAPL"]]
    assert result["gate"]["decision"] == "TARGETED_REVIEW"
    assert result["gate"]["opportunity_scout_required"] is False
