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

    account_seqs: list[str] = []
    for value in _collect_values_by_key(accounts_payload, "accountSeq"):
        text = str(value)
        if text not in account_seqs:
            account_seqs.append(text)

    if not account_seqs:
        raise TossAPIError("Could not find accountSeq in the accounts response.")

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
    symbols: list[str] = []

    for value in _collect_values_by_key(holdings_payload, "symbol"):
        if not isinstance(value, str):
            continue
        value = value.strip()
        if value and value not in symbols:
            symbols.append(value)

    return symbols


def _validate_symbol_batch(symbols: list[str], operation: str) -> None:
    if len(symbols) > 200:
        raise TossAPIError(
            f"{operation} supports up to 200 symbols per request; got {len(symbols)}."
        )


def get_prices(access_token: str, symbols: list[str]) -> dict[str, Any]:
    if not symbols:
        return {"result": []}

    _validate_symbol_batch(symbols, "Price lookup")
    response = requests.get(
        f"{BASE_URL}/api/v1/prices",
        headers=_auth_headers(access_token),
        params={"symbols": ",".join(symbols)},
        timeout=TIMEOUT_SECONDS,
    )
    _raise_for_api_error(response)
    return response.json()


def get_stocks(access_token: str, symbols: list[str]) -> dict[str, Any]:
    """Fetch official Toss stock-master metadata for exact broker symbols."""
    if not symbols:
        return {"result": []}

    _validate_symbol_batch(symbols, "Stock info lookup")
    response = requests.get(
        f"{BASE_URL}/api/v1/stocks",
        headers=_auth_headers(access_token),
        params={"symbols": ",".join(symbols)},
        timeout=TIMEOUT_SECONDS,
    )
    _raise_for_api_error(response)
    return response.json()


def get_live_portfolio() -> dict[str, Any]:
    """Read-only Toss portfolio fetch. This function never sends orders."""
    access_token = get_access_token()
    accounts_payload = get_accounts(access_token)
    account_seq = choose_account_seq(accounts_payload)
    holdings_payload = get_holdings(access_token, account_seq)
    symbols = extract_symbols(holdings_payload)
    prices_payload = get_prices(access_token, symbols)

    stock_info_error: str | None = None
    try:
        stocks_payload = get_stocks(access_token, symbols)
    except TossAPIError as exc:
        # Identity enrichment must not erase an otherwise valid read-only
        # portfolio snapshot. The resolver will mark every missing identity as
        # UNRESOLVED and the Daily CIO will treat it as data quality, not as a
        # guessed security identity.
        stocks_payload = {"result": []}
        stock_info_error = str(exc)

    return {
        "accountSeq": account_seq,
        "symbols": symbols,
        "holdings": holdings_payload,
        "prices": prices_payload,
        "stocks": stocks_payload,
        "stockInfoError": stock_info_error,
    }
