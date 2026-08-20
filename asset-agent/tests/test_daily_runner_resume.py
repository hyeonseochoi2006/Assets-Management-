from pathlib import Path

import pytest

import operations.daily_runner as daily_runner
from operations.checkpoint_store import DailyCheckpointStore
from operations.daily_recovery import DailyRecoveryStore
from operations.external_changes.models import ExternalChangeReport
from operations.models import (
    ChangeSet,
    DailyAnalysisGate,
    DailyCioDecision,
    InstrumentIdentity,
    MonitoringReport,
    PortfolioSnapshot,
    PositionSnapshot,
)
from operations.run_store import DailyRunStore


class FakeChangeEventStore:
    def process(self, _run_id, _current, change_set, **_kwargs):
        return change_set


def _snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        captured_at="2026-08-20T12:30:00+00:00",
        account_seq="account-1",
        positions=[
            PositionSnapshot(
                symbol="PANW",
                currency="USD",
                quantity=1,
                price=100,
                position_value=100,
                weight_pct=100,
                instrument=InstrumentIdentity(
                    symbol="PANW",
                    name="Palo Alto Networks",
                    market="NASDAQ",
                    security_type="STOCK",
                    currency="USD",
                    resolved=True,
                ),
            )
        ],
        market_value_by_currency={"USD": 100},
        total_purchase_by_currency={"USD": 90},
        profit_loss_by_currency={"USD": 10},
        daily_profit_loss_by_currency={"USD": 1},
    )


def _changes() -> ChangeSet:
    return ChangeSet(
        baseline=False,
        previous_captured_at="2026-08-20T11:30:00+00:00",
        current_captured_at="2026-08-20T12:30:00+00:00",
        changes=[],
        events=[],
        highest_severity="WATCH",
        data_quality="VALID",
        validation_issues=[],
        summary="review PANW",
    )


def _gate() -> DailyAnalysisGate:
    return DailyAnalysisGate(
        decision="TARGETED_REVIEW",
        run_kind="SCAN",
        ai_monitoring_required=True,
        ai_cio_required=True,
        targeted_symbols=["PANW"],
        triggering_event_ids=[],
        reasons=["test trigger"],
    )


def test_resume_skips_completed_snapshot_data_and_monitoring_steps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "operations.db"
    run_store = DailyRunStore(db_path)
    checkpoint_store = DailyCheckpointStore(db_path)
    recovery_store = DailyRecoveryStore(db_path)
    calls = {"snapshot": 0, "monitoring": 0, "cio": 0}

    monkeypatch.setattr(daily_runner, "RUN_STORE", run_store)
    monkeypatch.setattr(daily_runner, "CHECKPOINT_STORE", checkpoint_store)
    monkeypatch.setattr(daily_runner, "DAILY_RECOVERY_STORE", recovery_store)
    monkeypatch.setattr(daily_runner, "CHANGE_EVENT_STORE", FakeChangeEventStore())

    def fake_snapshots():
        calls["snapshot"] += 1
        return "READABLE SNAPSHOT", _snapshot()

    def fake_monitoring(_positions, _previous_at):
        calls["monitoring"] += 1
        return MonitoringReport(
            findings=[],
            data_quality="HIGH",
            notes=["monitoring result"],
        )

    def crash_cio(*_args, **_kwargs):
        calls["cio"] += 1
        raise SystemExit("simulated process crash")

    monkeypatch.setattr(daily_runner, "get_live_portfolio_snapshots", fake_snapshots)
    monkeypatch.setattr(
        daily_runner,
        "compare_portfolio_with_daily_reference",
        lambda *_args, **_kwargs: _changes(),
    )
    monkeypatch.setattr(
        daily_runner,
        "run_external_change_detection",
        lambda *_args, **_kwargs: (
            ExternalChangeReport(
                checked_at="2026-08-20T12:30:00+00:00",
                source_checks=[],
                new_documents=[],
                events_created=0,
                summary="none",
            ),
            [],
        ),
    )
    monkeypatch.setattr(
        daily_runner,
        "evaluate_daily_analysis_gate",
        lambda *_args, **_kwargs: _gate(),
    )
    monkeypatch.setattr(daily_runner, "run_daily_monitoring", fake_monitoring)
    monkeypatch.setattr(daily_runner, "run_daily_cio_decision", crash_cio)

    with pytest.raises(SystemExit, match="simulated process crash"):
        daily_runner.run_daily_operations(run_kind="SCAN")

    interrupted = run_store.latest_run()
    assert interrupted is not None
    run_id = str(interrupted["run_id"])
    assert interrupted["status"] == "RUNNING"
    assert checkpoint_store.next_step(run_id) == "CIO_READY"
    assert calls == {"snapshot": 1, "monitoring": 1, "cio": 1}

    checkpoint_store.interrupt_running(run_id, "process died")

    def successful_cio(*_args, **_kwargs):
        calls["cio"] += 1
        return DailyCioDecision(
            material_change=False,
            escalation="NONE",
            ceo_action_required=False,
            affected_tickers=["PANW"],
            summary="resumed at CIO",
            reasons=["checkpoint reuse"],
            recommended_next_step="continue monitoring",
        )

    monkeypatch.setattr(daily_runner, "run_daily_cio_decision", successful_cio)
    result = daily_runner.run_daily_operations(
        run_kind="SCAN",
        resume_run_id=run_id,
    )

    assert result["run_id"] == run_id
    assert result["resumed"] is True
    assert result["resume_count"] == 1
    assert calls["snapshot"] == 1
    assert calls["monitoring"] == 1
    assert calls["cio"] == 2
    assert checkpoint_store.next_step(run_id) is None
    completed = run_store.latest_run()
    assert completed is not None
    assert completed["status"] == "COMPLETED"
