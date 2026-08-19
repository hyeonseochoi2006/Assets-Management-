from collections import Counter, defaultdict
import hashlib
import json
import math
from typing import Literal

from operations.change_policy import PortfolioChangePolicy
from operations.models import (
    ChangeEvent,
    ChangeSet,
    FieldChange,
    PortfolioSnapshot,
    PositionChange,
    SymbolChangeSummary,
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

_EVENT_PRIORITY = {
    "DATA_QUALITY_WARNING": 100,
    "HOLDING_REMOVED": 90,
    "HOLDING_ADDED": 90,
    "EARNINGS_CHANGED": 85,
    "HOLDING_MISSING_UNCONFIRMED": 80,
    "FILING_FOUND": 75,
    "QUANTITY_CHANGE": 70,
    "PRICE_CHANGE": 60,
    "NEWS_FOUND": 55,
    "WEIGHT_CHANGE": 50,
    "POSITION_VALUE_CHANGE": 40,
    "CURRENCY_CHANGE": 30,
}


def _validate_snapshots(
    previous: PortfolioSnapshot | None,
    current: PortfolioSnapshot,
) -> tuple[Literal["VALID", "WARNING", "BLOCKED"], list[str]]:
    blocking: list[str] = []
    warnings: list[str] = []

    if previous is not None and previous.account_seq != current.account_seq:
        blocking.append("Current snapshot belongs to a different account than the baseline.")

    numeric_fields = ("quantity", "price", "position_value", "weight_pct")
    snapshots = [("Current", current)]
    if previous is not None:
        snapshots.append(("Previous", previous))

    for label, snapshot in snapshots:
        symbols = [position.symbol.strip().upper() for position in snapshot.positions]
        if any(not symbol for symbol in symbols):
            blocking.append(f"{label} snapshot contains a blank holding symbol.")
        duplicates = sorted(
            symbol for symbol, count in Counter(symbols).items() if count > 1
        )
        if duplicates:
            blocking.append(
                f"{label} snapshot contains duplicate holding symbols: "
                + ", ".join(duplicates)
                + "."
            )

        for position in snapshot.positions:
            missing = [
                field for field in numeric_fields if getattr(position, field) is None
            ]
            if missing:
                warnings.append(
                    f"{label} {position.symbol}: missing numeric fields: "
                    + ", ".join(missing)
                    + "."
                )
            for field in numeric_fields:
                value = getattr(position, field)
                if value is None:
                    continue
                if not math.isfinite(value):
                    blocking.append(
                        f"{label} {position.symbol}: {field} is not finite."
                    )
                elif value < 0:
                    blocking.append(
                        f"{label} {position.symbol}: {field} is negative."
                    )
            if position.weight_pct is not None and position.weight_pct > 100:
                blocking.append(
                    f"{label} {position.symbol}: weight_pct is greater than 100."
                )

    if previous is not None and previous.positions and not current.positions:
        warnings.append(
            "All previously observed holdings are absent; removal requires a second observation."
        )

    if blocking:
        return "BLOCKED", blocking + warnings
    if warnings:
        return "WARNING", warnings
    return "VALID", []


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


def build_change_event(
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
    source: str = "PORTFOLIO_SNAPSHOT_COMPARISON",
    identity_key: str | None = None,
    evidence: list[str] | None = None,
) -> ChangeEvent:
    identity = {
        "event_type": event_type,
        "symbol": symbol,
        "source": source,
        "identity_key": identity_key,
    }
    if identity_key is None:
        identity.update(
            {
                "previous_captured_at": previous_captured_at,
                "current_captured_at": detected_at,
                "previous": previous,
                "current": current,
            }
        )
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
        evidence=evidence
        or [
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


def group_change_events(events: list[ChangeEvent]) -> list[SymbolChangeSummary]:
    """Keep raw audit events while presenting one non-duplicative summary per symbol."""
    grouped: dict[str, list[ChangeEvent]] = defaultdict(list)
    for event in events:
        grouped[event.symbol].append(event)

    summaries: list[SymbolChangeSummary] = []
    for symbol in sorted(grouped):
        symbol_events = grouped[symbol]
        primary = max(
            symbol_events,
            key=lambda event: (
                _SEVERITY_RANK[event.severity],
                _EVENT_PRIORITY.get(event.event_type, 0),
            ),
        )
        related_types = list(
            dict.fromkeys(
                event.event_type
                for event in symbol_events
                if event.event_id != primary.event_id
            )
        )
        summaries.append(
            SymbolChangeSummary(
                symbol=symbol,
                severity=primary.severity,
                primary_event_id=primary.event_id,
                primary_event_type=primary.event_type,
                related_event_types=related_types,
                event_ids=[event.event_id for event in symbol_events],
                reason=primary.reason,
            )
        )
    return summaries


def refresh_change_set(change_set: ChangeSet) -> ChangeSet:
    """Recompute derived routing fields after durable confirmation adds an event."""
    change_set.highest_severity = _highest_severity(change_set.events)
    change_set.symbol_summaries = group_change_events(change_set.events)
    if change_set.events:
        severity_counts = {
            severity: sum(event.severity == severity for event in change_set.events)
            for severity in ("QUIET", "WATCH", "MATERIAL")
        }
        change_set.summary = (
            f"Observed {len(change_set.changes)} position-level change record(s) "
            f"across {len(change_set.symbol_summaries)} grouped subject(s). "
            f"Operational events: QUIET={severity_counts['QUIET']}, "
            f"WATCH={severity_counts['WATCH']}, "
            f"MATERIAL={severity_counts['MATERIAL']}. "
            f"Data quality: {change_set.data_quality}. "
            "These are attention-routing thresholds, not buy/sell conclusions."
        )
    elif not change_set.baseline:
        change_set.summary = (
            "No observable position-level differences from the previous snapshot. "
            f"Data quality: {change_set.data_quality}."
        )
    return change_set


def compare_portfolio_snapshots(
    previous: PortfolioSnapshot | None,
    current: PortfolioSnapshot,
    policy: PortfolioChangePolicy | None = None,
) -> ChangeSet:
    """Compare facts and apply deterministic operational attention thresholds."""
    selected_policy = policy or PortfolioChangePolicy.from_env()
    data_quality, validation_issues = _validate_snapshots(previous, current)
    validation_events: list[ChangeEvent] = []
    if validation_issues:
        validation_events.append(
            build_change_event(
                event_type="DATA_QUALITY_WARNING",
                symbol="PORTFOLIO",
                severity="WATCH",
                detected_at=current.captured_at,
                previous_captured_at=(
                    previous.captured_at if previous is not None else None
                ),
                previous=None,
                current=None,
                reason=" ".join(validation_issues),
                policy=selected_policy,
            )
        )

    if data_quality == "BLOCKED":
        return refresh_change_set(
            ChangeSet(
                baseline=previous is None,
                previous_captured_at=(
                    previous.captured_at if previous is not None else None
                ),
                current_captured_at=current.captured_at,
                changes=[],
                events=validation_events,
                data_quality=data_quality,
                validation_issues=validation_issues,
                policy_version=selected_policy.version,
                summary="Snapshot comparison blocked by deterministic data validation.",
            )
        )

    if previous is None:
        return refresh_change_set(
            ChangeSet(
                baseline=True,
                previous_captured_at=None,
                current_captured_at=current.captured_at,
                changes=[],
                events=validation_events,
                data_quality=data_quality,
                validation_issues=validation_issues,
                policy_version=selected_policy.version,
                summary=(
                    "BASELINE_CAPTURED — no previous portfolio snapshot exists yet. "
                    "No operational threshold or investment conclusion was applied."
                ),
            )
        )

    previous_by_symbol = {
        position.symbol.strip().upper(): position for position in previous.positions
    }
    current_by_symbol = {
        position.symbol.strip().upper(): position for position in current.positions
    }
    changes: list[PositionChange] = []
    events: list[ChangeEvent] = list(validation_events)

    all_symbols = sorted(set(previous_by_symbol) | set(current_by_symbol))
    for symbol in all_symbols:
        old = previous_by_symbol.get(symbol)
        new = current_by_symbol.get(symbol)

        if old is None and new is not None:
            changes.append(
                PositionChange(symbol=symbol, change_type="ADDED", fields=[])
            )
            events.append(
                build_change_event(
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
                PositionChange(
                    symbol=symbol,
                    change_type="MISSING_UNCONFIRMED",
                    fields=[],
                )
            )
            events.append(
                build_change_event(
                    event_type="HOLDING_MISSING_UNCONFIRMED",
                    symbol=symbol,
                    severity="WATCH",
                    detected_at=current.captured_at,
                    previous_captured_at=previous.captured_at,
                    previous=old.quantity,
                    current=None,
                    reason=(
                        "A previously observed holding is absent once; a second "
                        "observation is required before confirming removal."
                    ),
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
                    build_change_event(
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

    return refresh_change_set(
        ChangeSet(
            baseline=False,
            previous_captured_at=previous.captured_at,
            current_captured_at=current.captured_at,
            changes=changes,
            events=events,
            data_quality=data_quality,
            validation_issues=validation_issues,
            policy_version=selected_policy.version,
            summary="",
        )
    )
