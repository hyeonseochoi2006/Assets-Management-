import json
from datetime import datetime, timezone
from typing import Any

from data.toss_client import TossAPIError, get_live_portfolio
from operations.models import PortfolioSnapshot, PositionSnapshot


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _format_number(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "UNAVAILABLE"
    return f"{value:,.{digits}f}"


def _money_pairs(value: Any) -> list[tuple[str, float]]:
    pairs: list[tuple[str, float]] = []
    if not isinstance(value, dict):
        return pairs

    for currency in ("krw", "usd"):
        amount = _to_float(value.get(currency))
        if amount is not None:
            pairs.append((currency.upper(), amount))
    return pairs


def _money_dict(value: Any) -> dict[str, float]:
    return {currency: amount for currency, amount in _money_pairs(value)}


def _format_money(value: Any) -> str:
    pairs = _money_pairs(value)
    if not pairs:
        return "UNAVAILABLE"
    return " | ".join(
        f"{currency} {_format_number(amount, 2)}" for currency, amount in pairs
    )


def _find_symbol_records(data: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    if isinstance(data, dict):
        if isinstance(data.get("symbol"), str):
            records.append(data)
        for value in data.values():
            records.extend(_find_symbol_records(value))
    elif isinstance(data, list):
        for item in data:
            records.extend(_find_symbol_records(item))

    return records


def _best_holding_record_by_symbol(
    holdings_payload: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}

    for record in _find_symbol_records(holdings_payload):
        symbol = str(record.get("symbol", "")).strip()
        if not symbol:
            continue
        current = best.get(symbol)
        if current is None or len(json.dumps(record, ensure_ascii=False)) > len(
            json.dumps(current, ensure_ascii=False)
        ):
            best[symbol] = record

    return best


def _price_map(prices_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = prices_payload.get("result", [])
    if not isinstance(result, list):
        return {}

    prices: dict[str, dict[str, Any]] = {}
    for item in result:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).strip()
        if symbol:
            prices[symbol] = item
    return prices


def _first_numeric(record: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key in record:
            value = _to_float(record.get(key))
            if value is not None:
                return value
    return None


def _holding_value_from_record(
    record: dict[str, Any],
    currency: str | None,
) -> float | None:
    for key in ("marketValue", "evaluationAmount", "valuationAmount"):
        value = record.get(key)
        if isinstance(value, dict) and currency:
            direct = _to_float(value.get(currency.lower()))
            if direct is not None:
                return direct
            nested_amount = value.get("amount")
            if isinstance(nested_amount, dict):
                nested = _to_float(nested_amount.get(currency.lower()))
                if nested is not None:
                    return nested
        else:
            numeric = _to_float(value)
            if numeric is not None:
                return numeric
    return None


def _total_market_by_currency(holdings_payload: dict[str, Any]) -> dict[str, float]:
    result = holdings_payload.get("result", {})
    if not isinstance(result, dict):
        return {}

    market_value = result.get("marketValue", {})
    if not isinstance(market_value, dict):
        return {}

    amount = market_value.get("amount", market_value)
    return _money_dict(amount)


def _validated_payloads(
    portfolio: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    holdings_payload = portfolio.get("holdings", {})
    prices_payload = portfolio.get("prices", {})

    if not isinstance(holdings_payload, dict):
        raise TossAPIError("Unexpected holdings payload type.")
    if not isinstance(prices_payload, dict):
        raise TossAPIError("Unexpected prices payload type.")

    result = holdings_payload.get("result", {})
    if not isinstance(result, dict):
        result = {}

    return holdings_payload, prices_payload, result


def build_structured_portfolio_snapshot(
    portfolio: dict[str, Any],
) -> PortfolioSnapshot:
    """Build a machine-comparable snapshot without inventing unavailable values."""
    account_seq = str(portfolio.get("accountSeq", "UNAVAILABLE"))
    holdings_payload, prices_payload, result = _validated_payloads(portfolio)

    total_purchase = result.get("totalPurchaseAmount")
    market_value = result.get("marketValue", {})
    profit_loss = result.get("profitLoss", {})
    daily_profit_loss = result.get("dailyProfitLoss", {})

    market_amount = market_value.get("amount") if isinstance(market_value, dict) else None
    profit_amount = profit_loss.get("amount") if isinstance(profit_loss, dict) else None
    daily_profit_amount = (
        daily_profit_loss.get("amount")
        if isinstance(daily_profit_loss, dict)
        else None
    )

    holding_records = _best_holding_record_by_symbol(holdings_payload)
    prices = _price_map(prices_payload)
    total_market = _total_market_by_currency(holdings_payload)

    symbols = portfolio.get("symbols", [])
    if not isinstance(symbols, list):
        symbols = []

    positions: list[PositionSnapshot] = []
    for raw_symbol in symbols:
        symbol = str(raw_symbol)
        record = holding_records.get(symbol, {})
        price_info = prices.get(symbol, {})

        currency = price_info.get("currency")
        currency_text = str(currency).upper() if currency else None
        last_price = _to_float(price_info.get("lastPrice"))
        quantity = _first_numeric(
            record,
            ("quantity", "holdingQuantity", "totalQuantity", "balanceQuantity"),
        )

        position_value = _holding_value_from_record(record, currency_text)
        if position_value is None and quantity is not None and last_price is not None:
            position_value = quantity * last_price

        weight = None
        if currency_text and position_value is not None:
            currency_total = total_market.get(currency_text)
            if currency_total is not None and currency_total > 0:
                weight = position_value / currency_total * 100

        positions.append(
            PositionSnapshot(
                symbol=symbol,
                currency=currency_text,
                quantity=quantity,
                price=last_price,
                position_value=position_value,
                weight_pct=weight,
            )
        )

    return PortfolioSnapshot(
        captured_at=datetime.now(timezone.utc).isoformat(),
        account_seq=account_seq,
        positions=positions,
        market_value_by_currency=_money_dict(market_amount),
        total_purchase_by_currency=_money_dict(total_purchase),
        profit_loss_by_currency=_money_dict(profit_amount),
        daily_profit_loss_by_currency=_money_dict(daily_profit_amount),
        cash_available=None,
        cash_status="UNAVAILABLE FROM CURRENT HOLDINGS DATA",
    )


def build_portfolio_snapshot(portfolio: dict[str, Any]) -> str:
    """Convert raw Toss data into a compact, agent-friendly snapshot."""
    account_seq = str(portfolio.get("accountSeq", "UNAVAILABLE"))
    holdings_payload, prices_payload, result = _validated_payloads(portfolio)

    total_purchase = result.get("totalPurchaseAmount")
    market_value = result.get("marketValue", {})
    profit_loss = result.get("profitLoss", {})
    daily_profit_loss = result.get("dailyProfitLoss", {})

    market_amount = market_value.get("amount") if isinstance(market_value, dict) else None
    profit_amount = profit_loss.get("amount") if isinstance(profit_loss, dict) else None
    daily_profit_amount = (
        daily_profit_loss.get("amount")
        if isinstance(daily_profit_loss, dict)
        else None
    )

    holding_records = _best_holding_record_by_symbol(holdings_payload)
    prices = _price_map(prices_payload)
    total_market = _total_market_by_currency(holdings_payload)

    lines = [
        "LIVE TOSS PORTFOLIO SNAPSHOT",
        f"Account Seq: {account_seq}",
        "Data Source: Toss Securities Open API (read-only)",
        "",
        "PORTFOLIO TOTALS",
        f"Total Purchase Amount: {_format_money(total_purchase)}",
        f"Market Value: {_format_money(market_amount)}",
        f"Profit/Loss: {_format_money(profit_amount)}",
        f"Daily Profit/Loss: {_format_money(daily_profit_amount)}",
        "Cash: UNAVAILABLE FROM CURRENT HOLDINGS DATA",
        "",
        "POSITIONS",
    ]

    symbols = portfolio.get("symbols", [])
    if not isinstance(symbols, list):
        symbols = []

    if not symbols:
        lines.append("No stock positions detected.")

    for symbol in symbols:
        symbol = str(symbol)
        record = holding_records.get(symbol, {})
        price_info = prices.get(symbol, {})

        currency = price_info.get("currency")
        currency_text = str(currency).upper() if currency else None
        last_price = _to_float(price_info.get("lastPrice"))

        quantity = _first_numeric(
            record,
            ("quantity", "holdingQuantity", "totalQuantity", "balanceQuantity"),
        )

        position_value = _holding_value_from_record(record, currency_text)
        value_source = "Toss holding value"

        if position_value is None and quantity is not None and last_price is not None:
            position_value = quantity * last_price
            value_source = "quantity × current price"

        weight = None
        if currency_text and position_value is not None:
            currency_total = total_market.get(currency_text)
            if currency_total is not None and currency_total > 0:
                weight = position_value / currency_total * 100

        lines.append(f"- {symbol}")
        lines.append(
            "  Current Price: "
            + (
                f"{currency_text} {_format_number(last_price, 4)}"
                if currency_text and last_price is not None
                else "UNAVAILABLE"
            )
        )
        lines.append(f"  Quantity: {_format_number(quantity, 6)}")
        lines.append(
            "  Position Value: "
            + (
                f"{currency_text} {_format_number(position_value, 2)} ({value_source})"
                if currency_text and position_value is not None
                else "UNAVAILABLE"
            )
        )
        lines.append(
            "  Portfolio Weight: "
            + (f"{weight:.2f}%" if weight is not None else "UNAVAILABLE")
        )

    lines.extend(
        [
            "",
            "DATA LIMITATIONS",
            "- Do not infer cash from stock holdings.",
            "- UNAVAILABLE means the Toss response did not provide enough data to calculate safely.",
            "- Mixed-currency weights are not combined without an explicit FX conversion step.",
        ]
    )

    return "\n".join(lines)


def get_live_portfolio_snapshot() -> str:
    return build_portfolio_snapshot(get_live_portfolio())


def get_live_portfolio_snapshots() -> tuple[str, PortfolioSnapshot]:
    """Fetch Toss once and return both human-readable and structured snapshots."""
    portfolio = get_live_portfolio()
    return (
        build_portfolio_snapshot(portfolio),
        build_structured_portfolio_snapshot(portfolio),
    )


if __name__ == "__main__":
    print(get_live_portfolio_snapshot())
