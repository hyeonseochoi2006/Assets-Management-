from pathlib import Path

import pytest

import operations.daily_runner as daily_runner_module
from operations.change_detector import compare_portfolio_snapshots
from operations.change_event_store import ChangeEventStore
from operations.models import (
    DailyCioDecision,
    MonitoringReport,
    OpportunityScoutReport,
    PortfolioSnapshot,
    PositionSnapshot,
)
from operations.run_store import DailyRunStore


def snapshot(
    captured_at: str,
    *,
    positions: list[PositionSnapshot] | None = None,
) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        captured_at=captured_at,
        account_seq="test-account",
        positions=(
            positions
            if positions is not None
            else [
                PositionSnapshot(
                    symbol="GOOGL",
                    currency="USD",
                    quantity=5.0,
                    price=100.0,
                    position_value=500.0,
                    weight_pct=10.0,
                )
            ]
        ),
    )


def make_store(tmp_path: Path) -> ChangeEventStore:
    return ChangeEventStore(tmp_path / "operations.db")


def test_holding_removal_requires_two_consecutive_absent_snapshots(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path)
    original = snapshot("2026-08-17T08:00:00+00:00")
    first_absent = snapshot("2026-08-18T08:00:00+00:00", positions=[])
    second_absent = snapshot("2026-08-19T08:00:00+00:00", positions=[])

    first = store.process(
        "run-1",
        first_absent,
        compare_portfolio_snapshots(original, first_absent),
    )
    state = store.missing_state("test-account", "GOOGL")

    assert state is not None
    assert state["status"] == "PENDING"
    assert state["miss_count"] == 1
    assert any(
        event.event_type == "HOLDING_MISSING_UNCONFIRMED"
        for event in first.events
    )
    assert not any(event.event_type == "HOLDING_REMOVED" for event in first.events)

    second = store.process(
        "run-2",
        second_absent,
        compare_portfolio_snapshots(first_absent, second_absent),
    )
    state = store.missing_state("test-account", "GOOGL")

    assert state is not None
    assert state["status"] == "CONFIRMED"
    assert state["miss_count"] == 2
    assert [event.event_type for event in second.events] == ["HOLDING_REMOVED"]
    assert second.events[0].severity == "MATERIAL"
    assert second.changes[0].change_type == "REMOVED"


def test_confirmed_removal_is_not_emitted_again(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    original = snapshot("2026-08-17T08:00:00+00:00")
    first_absent = snapshot("2026-08-18T08:00:00+00:00", positions=[])
    second_absent = snapshot("2026-08-19T08:00:00+00:00", positions=[])
    third_absent = snapshot("2026-08-20T08:00:00+00:00", positions=[])

    store.process(
        "run-1",
        first_absent,
        compare_portfolio_snapshots(original, first_absent),
    )
    store.process(
        "run-2",
        second_absent,
        compare_portfolio_snapshots(first_absent, second_absent),
    )
    third = store.process(
        "run-3",
        third_absent,
        compare_portfolio_snapshots(second_absent, third_absent),
    )

    assert third.events == []


def test_reappearing_holding_clears_pending_missing_state(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    original = snapshot("2026-08-17T08:00:00+00:00")
    absent = snapshot("2026-08-18T08:00:00+00:00", positions=[])
    reappeared = snapshot("2026-08-19T08:00:00+00:00")

    store.process(
        "run-1",
        absent,
        compare_portfolio_snapshots(original, absent),
    )
    result = store.process(
        "run-2",
        reappeared,
        compare_portfolio_snapshots(absent, reappeared),
    )

    assert store.missing_state("test-account", "GOOGL") is None
    assert not any(event.event_type == "HOLDING_ADDED" for event in result.events)
    assert [event.event_type for event in result.events] == ["DATA_QUALITY_WARNING"]
    assert result.events[0].severity == "QUIET"


def test_event_ledger_rejects_duplicate_event_identity(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    previous = snapshot("2026-08-17T08:00:00+00:00")
    current = snapshot("2026-08-18T08:00:00+00:00")
    current.positions[0].price = 105.0
    events = compare_portfolio_snapshots(previous, current).events

    first = store.save_events("run-1", events)
    second = store.save_events("run-2", events)

    assert first.inserted == 1
    assert first.duplicates == 0
    assert second.inserted == 0
    assert second.duplicates == 1
    assert store.event_count() == 1


def test_daily_operations_persists_grouped_change_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "operations.db"
    run_store = DailyRunStore(db_path)
    event_store = ChangeEventStore(db_path)
    first_snapshot = snapshot("2026-08-17T08:00:00+00:00")
    second_snapshot = snapshot("2026-08-18T08:00:00+00:00")
    second_snapshot.positions[0].price = 105.0
    live_snapshots = iter([first_snapshot, second_snapshot])

    monkeypatch.setattr(daily_runner_module, "RUN_STORE", run_store)
    monkeypatch.setattr(daily_runner_module, "CHANGE_EVENT_STORE", event_store)
    monkeypatch.setattr(
        daily_runner_module,
        "get_live_portfolio_snapshots",
        lambda: ("test portfolio", next(live_snapshots)),
    )
    monkeypatch.setattr(
        daily_runner_module,
        "run_daily_monitoring",
        lambda *_: MonitoringReport(findings=[], data_quality="HIGH", notes=[]),
    )
    monkeypatch.setattr(
        daily_runner_module,
        "run_opportunity_scout",
        lambda *_: OpportunityScoutReport(
            candidates=[],
            data_quality="HIGH",
            scan_scope="test",
            notes=[],
        ),
    )
    monkeypatch.setattr(
        daily_runner_module,
        "run_daily_cio_decision",
        lambda *_: DailyCioDecision(
            material_change=False,
            escalation="NONE",
            ceo_action_required=False,
            affected_tickers=[],
            summary="No material change.",
            reasons=[],
            recommended_next_step="No action.",
        ),
    )

    daily_runner_module.run_daily_operations()
    result = daily_runner_module.run_daily_operations()
    changes = result["changes"]

    assert changes["events"][0]["event_type"] == "PRICE_CHANGE"
    assert changes["symbol_summaries"][0]["primary_event_type"] == "PRICE_CHANGE"
    assert changes["persistence"] == {"inserted": 1, "duplicates": 0}
    assert event_store.event_count() == 1


def test_blocked_snapshot_is_recorded_but_not_used_as_next_baseline(
    tmp_path: Path,
) -> None:
    store = DailyRunStore(tmp_path / "operations.db")
    valid = snapshot("2026-08-17T08:00:00+00:00")
    invalid = snapshot("2026-08-18T08:00:00+00:00")
    invalid.account_seq = "different-account"
    valid_run = store.start_run(valid.captured_at)
    invalid_run = store.start_run(invalid.captured_at)

    store.save_snapshot(valid_run, valid)
    store.save_snapshot(invalid_run, invalid, baseline_eligible=False)

    latest_baseline = store.latest_snapshot()
    assert latest_baseline is not None
    assert latest_baseline.captured_at == valid.captured_at
    assert latest_baseline.account_seq == valid.account_seq
