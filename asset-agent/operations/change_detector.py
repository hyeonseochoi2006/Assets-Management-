import hashlib
import json
from typing import Literal

from operations.change_policy import PortfolioChangePolicy
from operations.models import (
    ChangeEvent,
    ChangeSet,
    FieldChange,
    PortfolioSnapshot,
    PositionChange,
)


_COMPARE_FIELDS = (
    "currency",
    "quantity",
    "price",
    "position_value",
    "weight_pct",
)

_FIELD_EVENT_TYPES = {
    "currency": "CURRENCY_CHANGE",
    "quantity": "QUANTITY_CHANGE",
    "price": "PRICE_CHANGE",
    "position_value": "POSITION_VALUE_CHANGE",
    "weight_pct": "WEIGHT_CHANGE",
}

_SEVERITY_RANK = {"QUIET": 0, "WATCH": 1, "MATERIAL": 2}


def _percent_change(previous: object, current: object) -> float | None:
    if not isinstance(previous, (int, float)) or not isinstance(current, (int, float)):
        return None
    if previous == 0:
        return None
    return round(((current - previous) / abs(previous)) * 100, 6)


def _absolute_change(previous: object, current: object) -> float | None:
    if not isinstance(previous, (int, float)) or not isinstance(current, (int, float)):
        return None
    return round(current - previous, 6)


def _route_for(
    severity: Literal["QUIET", "WATCH", "MATERIAL"],
) -> Literal["STORE_ONLY", "MONITOR", "CIO_REVIEW"]:
    return {
        "QUIET": "STORE_ONLY",
        "WATCH": "MONITOR",
        "MATERIAL": "CIO_REVIEW",
    }[severity]


def _event_id(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return "chg_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def _classify_field_change(
    field: str,
    previous: float | str | None,
    current: float | str | None,
    policy: PortfolioChangePolicy,
) -> tuple[Literal["QUIET", "WATCH", "MATERIAL"], str]:
    pct = _percent_change(previous, current)
    absolute = _absolute_change(previous, current)

    if previous is None or current is None:
        return "QUIET", "Data availability changed; no numeric materiality was inferred."

    if field == "price" and pct is not None:
        magnitude = abs(pct)
        if magnitude >= policy.price_material_pct:
            return (
                "MATERIAL",
                f"Price change reached the {policy.price_material_pct:g}% material threshold.",
            )
        if magnitude >= policy.price_watch_pct:
            return (
                "WATCH",
                f"Price change reached the {policy.price_watch_pct:g}% watch threshold.",
            )
        return (
            "QUIET",
            f"Price change stayed below the {policy.price_watch_pct:g}% watch threshold.",
        )

    if field == "weight_pct" and absolute is not None:
        magnitude = abs(absolute)
        if magnitude >= policy.weight_material_points:
            return (
                "MATERIAL",
                "Portfolio weight change reached the "
                f"{policy.weight_material_points:g} percentage-point material threshold.",
            )
        if magnitude >= policy.weight_watch_points:
            return (
                "WATCH",
                "Portfolio weight change reached the "
                f"{policy.weight_watch_points:g} percentage-point watch threshold.",
            )
        return (
            "QUIET",
            "Portfolio weight change stayed below the "
            f"{policy.weight_watch_points:g} percentage-point watch threshold.",
        )

    if field == "quantity" and pct is not None:
        if abs(pct) >= policy.quantity_material_pct:
            return (
                "MATERIAL",
                f"Quantity change reached the {policy.quantity_material_pct:g}% material threshold.",
            )
        return "WATCH", "A non-zero holding quantity change requires routine monitoring."

    if field == "position_value" and pct is not None:
        magnitude = abs(pct)
        if magnitude >= policy.position_value_material_pct:
            return (
                "MATERIAL",
                "Position value change reached the "
                f"{policy.position_value_material_pct:g}% material threshold.",
            )
        if magnitude >= policy.position_value_watch_pct:
            return (
                "WATCH",
                "Position value change reached the "
                f"{policy.position_value_watch_pct:g}% watch threshold.",
            )
        return (
            "QUIET",
            "Position value change stayed below the "
            f"{policy.position_value_watch_pct:g}% watch threshold.",
        )

    if field == "currency":
        return (
            "WATCH",
            "Position currency changed and should be checked for identity or data-quality issues.",
        )

    return "QUIET", "Observable change recorded without a matching escalation rule."


def _build_event(
    *,
    event_type: str,
    symbol: str,
    severity: Literal["QUIET", "WATCH", "MATERIAL"],
    detected_at: str,
    previous_captured_at: str | None,
    previous: float | str | None,
    current: float | str | None,
    reason: str,
    policy: PortfolioChangePolicy,
) -> ChangeEvent:
    source = "PORTFOLIO_SNAPSHOT_COMPARISON"
    identity = {
        "event_type": event_type,
        "symbol": symbol,
        "source": source,
        "previous_captured_at": previous_captured_at,
        "current_captured_at": detected_at,
        "previous": previous,
        "current": current,
    }
    return ChangeEvent(
        event_id=_event_id(identity),
        event_type=event_type,
        symbol=symbol,
        severity=severity,
        recommended_route=_route_for(severity),
        detected_at=detected_at,
        source=source,
        previous=previous,
        current=current,
        absolute_change=_absolute_change(previous, current),
        percent_change=_percent_change(previous, current),
        reason=reason,
        policy_version=policy.version,
        evidence=[
            f"previous_snapshot={previous_captured_at or 'NONE'}",
            f"current_snapshot={detected_at}",
        ],
    )


def _highest_severity(
    events: list[ChangeEvent],
) -> Literal["QUIET", "WATCH", "MATERIAL"]:
    if not events:
        return "QUIET"
    return max(events, key=lambda event: _SEVERITY_RANK[event.severity]).severity


def compare_portfolio_snapshots(
    previous: PortfolioSnapshot | None,
    current: PortfolioSnapshot,
    policy: PortfolioChangePolicy | None = None,
) -> ChangeSet:
    """Compare facts and apply deterministic operational attention thresholds."""
    selected_policy = policy or PortfolioChangePolicy.from_env()
    if previous is None:
        return ChangeSet(
            baseline=True,
            previous_captured_at=None,
            current_captured_at=current.captured_at,
            changes=[],
            events=[],
            highest_severity="QUIET",
            policy_version=selected_policy.version,
            summary=(
                "BASELINE_CAPTURED — no previous portfolio snapshot exists yet. "
                "No operational threshold or investment conclusion was applied."
            ),
        )

    previous_by_symbol = {position.symbol: position for position in previous.positions}
    current_by_symbol = {position.symbol: position for position in current.positions}
    changes: list[PositionChange] = []
    events: list[ChangeEvent] = []

    all_symbols = sorted(set(previous_by_symbol) | set(current_by_symbol))
    for symbol in all_symbols:
        old = previous_by_symbol.get(symbol)
        new = current_by_symbol.get(symbol)

        if old is None and new is not None:
            changes.append(
                PositionChange(symbol=symbol, change_type="ADDED", fields=[])
            )
            events.append(
                _build_event(
                    event_type="HOLDING_ADDED",
                    symbol=symbol,
                    severity="MATERIAL",
                    detected_at=current.captured_at,
                    previous_captured_at=previous.captured_at,
                    previous=None,
                    current=new.quantity,
                    reason="A new holding appeared in the portfolio snapshot.",
                    policy=selected_policy,
                )
            )
            continue

        if old is not None and new is None:
            changes.append(
                PositionChange(symbol=symbol, change_type="REMOVED", fields=[])
            )
            events.append(
                _build_event(
                    event_type="HOLDING_REMOVED",
                    symbol=symbol,
                    severity="MATERIAL",
                    detected_at=current.captured_at,
                    previous_captured_at=previous.captured_at,
                    previous=old.quantity,
                    current=None,
                    reason="A previously observed holding is absent from the current snapshot.",
                    policy=selected_policy,
                )
            )
            continue

        if old is None or new is None:
            continue

        field_changes: list[FieldChange] = []
        for field in _COMPARE_FIELDS:
            old_value = getattr(old, field)
            new_value = getattr(new, field)
            if old_value != new_value:
                field_changes.append(
                    FieldChange(field=field, previous=old_value, current=new_value)
                )
                severity, reason = _classify_field_change(
                    field, old_value, new_value, selected_policy
                )
                events.append(
                    _build_event(
                        event_type=_FIELD_EVENT_TYPES[field],
                        symbol=symbol,
                        severity=severity,
                        detected_at=current.captured_at,
                        previous_captured_at=previous.captured_at,
                        previous=old_value,
                        current=new_value,
                        reason=reason,
                        policy=selected_policy,
                    )
                )

        if field_changes:
            changes.append(
                PositionChange(symbol=symbol, change_type="UPDATED", fields=field_changes)
            )

    highest_severity = _highest_severity(events)
    if changes:
        severity_counts = {
            severity: sum(event.severity == severity for event in events)
            for severity in ("QUIET", "WATCH", "MATERIAL")
        }
        summary = (
            f"Observed {len(changes)} position-level change record(s). "
            f"Operational events: QUIET={severity_counts['QUIET']}, "
            f"WATCH={severity_counts['WATCH']}, MATERIAL={severity_counts['MATERIAL']}. "
            "These are attention-routing thresholds, not buy/sell conclusions."
        )
    else:
        summary = "No observable position-level differences from the previous snapshot."

    return ChangeSet(
        baseline=False,
        previous_captured_at=previous.captured_at,
        current_captured_at=current.captured_at,
        changes=changes,
        events=events,
        highest_severity=highest_severity,
        policy_version=selected_policy.version,
        summary=summary,
    )
