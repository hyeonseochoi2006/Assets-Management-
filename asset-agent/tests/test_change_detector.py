import pytest

from operations.change_detector import (
    compare_portfolio_snapshots,
    compare_portfolio_with_daily_reference,
)
from operations.change_policy import POLICY_ENV_NAMES, PortfolioChangePolicy
from operations.models import PortfolioSnapshot, PositionSnapshot


def snapshot(
    captured_at: str,
    *,
    symbol: str = "GOOGL",
    price: float = 100.0,
    quantity: float = 5.0,
    position_value: float = 500.0,
    weight_pct: float = 10.0,
) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        captured_at=captured_at,
        account_seq="test-account",
        positions=[
            PositionSnapshot(
                symbol=symbol,
                currency="USD",
                quantity=quantity,
                price=price,
                position_value=position_value,
                weight_pct=weight_pct,
            )
        ],
    )


def clear_policy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in POLICY_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_first_snapshot_is_quiet_baseline() -> None:
    result = compare_portfolio_snapshots(
        None,
        snapshot("2026-08-18T08:00:00+00:00"),
    )

    assert result.baseline is True
    assert result.events == []
    assert result.highest_severity == "QUIET"


@pytest.mark.parametrize(
    ("new_price", "expected_severity", "expected_route"),
    [
        (102.9, "QUIET", "STORE_ONLY"),
        (105.0, "WATCH", "MONITOR"),
        (107.0, "MATERIAL", "CIO_REVIEW"),
    ],
)
def test_price_change_uses_configured_attention_bands(
    new_price: float,
    expected_severity: str,
    expected_route: str,
) -> None:
    previous = snapshot("2026-08-17T08:00:00+00:00")
    current = snapshot("2026-08-18T08:00:00+00:00", price=new_price)

    result = compare_portfolio_snapshots(previous, current)

    assert len(result.events) == 1
    assert result.events[0].event_type == "PRICE_CHANGE"
    assert result.events[0].severity == expected_severity
    assert result.events[0].recommended_route == expected_route
    assert result.highest_severity == expected_severity


def test_weight_uses_percentage_points_not_percent_change() -> None:
    previous = snapshot("2026-08-17T08:00:00+00:00", weight_pct=10.0)
    current = snapshot("2026-08-18T08:00:00+00:00", weight_pct=12.0)

    result = compare_portfolio_snapshots(previous, current)
    event = result.events[0]

    assert event.event_type == "WEIGHT_CHANGE"
    assert event.absolute_change == 2.0
    assert event.percent_change == 20.0
    assert event.severity == "WATCH"


def test_added_holding_is_material_but_first_missing_observation_is_not() -> None:
    previous = snapshot("2026-08-17T08:00:00+00:00", symbol="GOOGL")
    current = snapshot("2026-08-18T08:00:00+00:00", symbol="NVDA")

    result = compare_portfolio_snapshots(previous, current)

    assert [
        (event.symbol, event.event_type, event.severity) for event in result.events
    ] == [
        ("GOOGL", "HOLDING_MISSING_UNCONFIRMED", "WATCH"),
        ("NVDA", "HOLDING_ADDED", "MATERIAL"),
    ]
    assert result.highest_severity == "MATERIAL"


def test_related_price_value_and_weight_events_have_one_symbol_summary() -> None:
    previous = snapshot("2026-08-17T08:00:00+00:00")
    current = snapshot(
        "2026-08-18T08:00:00+00:00",
        price=105.0,
        position_value=525.0,
        weight_pct=11.0,
    )

    result = compare_portfolio_snapshots(previous, current)

    assert len(result.events) == 3
    assert len(result.symbol_summaries) == 1
    summary = result.symbol_summaries[0]
    assert summary.symbol == "GOOGL"
    assert summary.primary_event_type == "PRICE_CHANGE"
    assert summary.severity == "WATCH"
    assert set(summary.related_event_types) == {
        "POSITION_VALUE_CHANGE",
        "WEIGHT_CHANGE",
    }


def test_duplicate_symbols_block_snapshot_comparison() -> None:
    current = snapshot("2026-08-18T08:00:00+00:00")
    current.positions.append(current.positions[0].model_copy())

    result = compare_portfolio_snapshots(
        snapshot("2026-08-17T08:00:00+00:00"),
        current,
    )

    assert result.data_quality == "BLOCKED"
    assert result.changes == []
    assert [event.event_type for event in result.events] == ["DATA_QUALITY_WARNING"]
    assert "duplicate holding symbols" in result.validation_issues[0]


def test_different_account_blocks_snapshot_comparison() -> None:
    previous = snapshot("2026-08-17T08:00:00+00:00")
    current = snapshot("2026-08-18T08:00:00+00:00")
    current.account_seq = "different-account"

    result = compare_portfolio_snapshots(previous, current)

    assert result.data_quality == "BLOCKED"
    assert result.changes == []
    assert "different account" in result.validation_issues[0]


def test_non_finite_number_blocks_before_event_hashing() -> None:
    current = snapshot("2026-08-18T08:00:00+00:00", price=float("nan"))

    result = compare_portfolio_snapshots(
        snapshot("2026-08-17T08:00:00+00:00"),
        current,
    )

    assert result.data_quality == "BLOCKED"
    assert result.changes == []
    assert "not finite" in result.validation_issues[0]


def test_event_id_is_stable_when_same_snapshots_are_reprocessed() -> None:
    previous = snapshot("2026-08-17T08:00:00+00:00")
    current = snapshot("2026-08-18T08:00:00+00:00", price=105.0)

    first = compare_portfolio_snapshots(previous, current)
    second = compare_portfolio_snapshots(previous, current)

    assert first.events[0].event_id == second.events[0].event_id
    assert first.events[0].event_id.startswith("chg_")


def test_environment_can_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_policy_env(monkeypatch)
    monkeypatch.setenv("ASSET_CHANGE_PRICE_WATCH_PCT", "1")
    monkeypatch.setenv("ASSET_CHANGE_PRICE_MATERIAL_PCT", "2")

    result = compare_portfolio_snapshots(
        snapshot("2026-08-17T08:00:00+00:00"),
        snapshot("2026-08-18T08:00:00+00:00", price=102.0),
    )

    assert result.events[0].severity == "MATERIAL"


def test_daily_reference_catches_gradual_cumulative_material_move() -> None:
    previous_close = snapshot("2026-08-17T21:30:00+00:00", price=100)
    previous_scan = snapshot("2026-08-18T16:30:00+00:00", price=106)
    current = snapshot("2026-08-18T21:30:00+00:00", price=107.1)

    rolling_only = compare_portfolio_snapshots(previous_scan, current)
    with_daily_reference = compare_portfolio_with_daily_reference(
        previous_scan,
        previous_close,
        current,
    )

    rolling_price = next(
        event for event in rolling_only.events if event.event_type == "PRICE_CHANGE"
    )
    daily_price = next(
        event
        for event in with_daily_reference.events
        if event.event_type == "PRICE_CHANGE"
    )
    assert rolling_price.severity == "QUIET"
    assert daily_price.severity == "MATERIAL"
    assert daily_price.previous == 100
    assert daily_price.current == 107.1


def test_daily_reference_does_not_repeat_intraday_holding_addition() -> None:
    previous_close = snapshot(
        "2026-08-17T21:30:00+00:00", symbol="GOOGL"
    )
    previous_scan = snapshot("2026-08-18T12:30:00+00:00", symbol="AAPL")
    current = snapshot("2026-08-18T16:30:00+00:00", symbol="AAPL")

    result = compare_portfolio_with_daily_reference(
        previous_scan,
        previous_close,
        current,
    )

    assert result.events == []
    assert result.changes == []


def test_invalid_threshold_order_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_policy_env(monkeypatch)
    monkeypatch.setenv("ASSET_CHANGE_PRICE_WATCH_PCT", "8")
    monkeypatch.setenv("ASSET_CHANGE_PRICE_MATERIAL_PCT", "7")

    with pytest.raises(RuntimeError, match="Invalid portfolio change policy"):
        PortfolioChangePolicy.from_env()
