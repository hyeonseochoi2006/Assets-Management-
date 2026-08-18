import pytest

from operations.change_detector import compare_portfolio_snapshots
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


def test_added_and_removed_holdings_are_material() -> None:
    previous = snapshot("2026-08-17T08:00:00+00:00", symbol="GOOGL")
    current = snapshot("2026-08-18T08:00:00+00:00", symbol="NVDA")

    result = compare_portfolio_snapshots(previous, current)

    assert [
        (event.symbol, event.event_type, event.severity) for event in result.events
    ] == [
        ("GOOGL", "HOLDING_REMOVED", "MATERIAL"),
        ("NVDA", "HOLDING_ADDED", "MATERIAL"),
    ]
    assert result.highest_severity == "MATERIAL"


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


def test_invalid_threshold_order_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_policy_env(monkeypatch)
    monkeypatch.setenv("ASSET_CHANGE_PRICE_WATCH_PCT", "8")
    monkeypatch.setenv("ASSET_CHANGE_PRICE_MATERIAL_PCT", "7")

    with pytest.raises(RuntimeError, match="Invalid portfolio change policy"):
        PortfolioChangePolicy.from_env()
