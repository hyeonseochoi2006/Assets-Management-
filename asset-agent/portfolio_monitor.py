import json
import os
from typing import Any

import requests


BASE_URL = "https://openapi.tossinvest.com"
TIMEOUT_SECONDS = 15


class TossAPIError(RuntimeError):
    pass


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _raise_for_api_error(response: requests.Response) -> None:
    if response.ok:
        return

    try:
        payload = response.json()
    except ValueError:
        payload = {"message": response.text[:500]}

    raise TossAPIError(
        f"Toss API request failed: HTTP {response.status_code} | {payload}"
    )


def get_access_token() -> str:
    client_id = _require_env("TOSS_CLIENT_ID")
    client_secret = _require_env("TOSS_CLIENT_SECRET")

    response = requests.post(
        f"{BASE_URL}/oauth2/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=TIMEOUT_SECONDS,
    )
    _raise_for_api_error(response)

    payload = response.json()
    access_token = payload.get("access_token")

    if not access_token:
        raise TossAPIError(
            "Token response did not contain access_token. "
            f"Returned keys: {list(payload.keys())}"
        )

    return access_token


def _auth_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }


def get_accounts(access_token: str) -> dict[str, Any]:
    response = requests.get(
        f"{BASE_URL}/api/v1/accounts",
        headers=_auth_headers(access_token),
        timeout=TIMEOUT_SECONDS,
    )
    _raise_for_api_error(response)
    return response.json()


def _collect_values_by_key(data: Any, key: str) -> list[Any]:
    values: list[Any] = []

    if isinstance(data, dict):
        for current_key, value in data.items():
            if current_key == key:
                values.append(value)
            values.extend(_collect_values_by_key(value, key))
    elif isinstance(data, list):
        for item in data:
            values.extend(_collect_values_by_key(item, key))

    return values


def choose_account_seq(accounts_payload: dict[str, Any]) -> str:
    configured = os.getenv("TOSS_ACCOUNT_SEQ")
    if configured:
        return configured

    account_seqs = []
    for value in _collect_values_by_key(accounts_payload, "accountSeq"):
        text = str(value)
        if text not in account_seqs:
            account_seqs.append(text)

    if not account_seqs:
        raise TossAPIError(
            "Could not find accountSeq in the accounts response. "
            "Run this script and inspect the accounts response format."
        )

    if len(account_seqs) > 1:
        raise TossAPIError(
            "Multiple Toss accounts were found. Add a Codespaces secret named "
            f"TOSS_ACCOUNT_SEQ with one of these values: {account_seqs}"
        )

    return account_seqs[0]


def get_holdings(access_token: str, account_seq: str) -> dict[str, Any]:
    headers = _auth_headers(access_token)
    headers["X-Tossinvest-Account"] = account_seq

    response = requests.get(
        f"{BASE_URL}/api/v1/holdings",
        headers=headers,
        timeout=TIMEOUT_SECONDS,
    )
    _raise_for_api_error(response)
    return response.json()


def extract_symbols(holdings_payload: dict[str, Any]) -> list[str]:
    symbols = []

    for value in _collect_values_by_key(holdings_payload, "symbol"):
        if not isinstance(value, str):
            continue
        value = value.strip()
        if value and value not in symbols:
            symbols.append(value)

    return symbols


def get_prices(access_token: str, symbols: list[str]) -> dict[str, Any]:
    if not symbols:
        return {"result": []}

    if len(symbols) > 200:
        raise TossAPIError(
            f"Price lookup supports up to 200 symbols per request; got {len(symbols)}."
        )

    response = requests.get(
        f"{BASE_URL}/api/v1/prices",
        headers=_auth_headers(access_token),
        params={"symbols": ",".join(symbols)},
        timeout=TIMEOUT_SECONDS,
    )
    _raise_for_api_error(response)
    return response.json()


def get_live_portfolio() -> dict[str, Any]:
    """
    Read-only portfolio monitor.

    Calls only Toss endpoints for:
    - OAuth token
    - account list
    - holdings
    - current prices

    It never creates, modifies, or cancels orders.
    """
    access_token = get_access_token()
    accounts_payload = get_accounts(access_token)
    account_seq = choose_account_seq(accounts_payload)
    holdings_payload = get_holdings(access_token, account_seq)
    symbols = extract_symbols(holdings_payload)
    prices_payload = get_prices(access_token, symbols)

    return {
        "accountSeq": account_seq,
        "symbols": symbols,
        "holdings": holdings_payload,
        "prices": prices_payload,
    }


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
    """Extract direct KRW/USD amounts from a Toss money object."""
    pairs: list[tuple[str, float]] = []
    if not isinstance(value, dict):
        return pairs

    for currency in ("krw", "usd"):
        amount = _to_float(value.get(currency))
        if amount is not None:
            pairs.append((currency.upper(), amount))
    return pairs


def _format_money(value: Any) -> str:
    pairs = _money_pairs(value)
    if not pairs:
        return "UNAVAILABLE"
    return " | ".join(
        f"{currency} {_format_number(amount, 2)}" for currency, amount in pairs
    )


def _find_symbol_records(data: Any) -> list[dict[str, Any]]:
    """Find holding-like dictionaries that directly contain a symbol field."""
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


def _best_holding_record_by_symbol(holdings_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """
    A Toss response may contain a symbol more than once.
    Keep the richest record for each symbol instead of guessing from duplicates.
    """
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
    totals: dict[str, float] = {}
    for currency, value in _money_pairs(amount):
        totals[currency] = value
    return totals


def build_portfolio_snapshot(portfolio: dict[str, Any]) -> str:
    """
    Convert the raw Toss response into a compact, agent-friendly snapshot.

    Rules:
    - Never invent missing values.
    - Compute position value only when both quantity and current price are available.
    - Compute weight only when position value and same-currency portfolio total exist.
    - Cash is not inferred from the holdings response.
    """
    account_seq = str(portfolio.get("accountSeq", "UNAVAILABLE"))
    holdings_payload = portfolio.get("holdings", {})
    prices_payload = portfolio.get("prices", {})

    if not isinstance(holdings_payload, dict):
        raise TossAPIError("Unexpected holdings payload type.")
    if not isinstance(prices_payload, dict):
        raise TossAPIError("Unexpected prices payload type.")

    result = holdings_payload.get("result", {})
    if not isinstance(result, dict):
        result = {}

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
            (
                "quantity",
                "holdingQuantity",
                "totalQuantity",
                "balanceQuantity",
            ),
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


if __name__ == "__main__":
    # Deliberately never print client_secret or access_token.
    print(get_live_portfolio_snapshot())
