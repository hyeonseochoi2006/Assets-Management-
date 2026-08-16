from operations.models import (
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


def compare_portfolio_snapshots(
    previous: PortfolioSnapshot | None,
    current: PortfolioSnapshot,
) -> ChangeSet:
    """Compare observable facts only; never infer investment materiality."""
    if previous is None:
        return ChangeSet(
            baseline=True,
            previous_captured_at=None,
            current_captured_at=current.captured_at,
            changes=[],
            summary=(
                "BASELINE_CAPTURED — no previous portfolio snapshot exists yet. "
                "No change threshold or investment conclusion was inferred."
            ),
        )

    previous_by_symbol = {position.symbol: position for position in previous.positions}
    current_by_symbol = {position.symbol: position for position in current.positions}
    changes: list[PositionChange] = []

    all_symbols = sorted(set(previous_by_symbol) | set(current_by_symbol))
    for symbol in all_symbols:
        old = previous_by_symbol.get(symbol)
        new = current_by_symbol.get(symbol)

        if old is None and new is not None:
            changes.append(
                PositionChange(
                    symbol=symbol,
                    change_type="ADDED",
                    fields=[],
                )
            )
            continue

        if old is not None and new is None:
            changes.append(
                PositionChange(
                    symbol=symbol,
                    change_type="REMOVED",
                    fields=[],
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
                    FieldChange(
                        field=field,
                        previous=old_value,
                        current=new_value,
                    )
                )

        if field_changes:
            changes.append(
                PositionChange(
                    symbol=symbol,
                    change_type="UPDATED",
                    fields=field_changes,
                )
            )

    if changes:
        summary = (
            f"Observed {len(changes)} position-level change record(s). "
            "These are factual differences only; no materiality threshold was applied."
        )
    else:
        summary = "No observable position-level differences from the previous snapshot."

    return ChangeSet(
        baseline=False,
        previous_captured_at=previous.captured_at,
        current_captured_at=current.captured_at,
        changes=changes,
        summary=summary,
    )
