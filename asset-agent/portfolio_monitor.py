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

    This function only calls Toss endpoints for:
    - OAuth token
    - account list
    - holdings
    - current prices

    It does not create, modify, or cancel orders.
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


if __name__ == "__main__":
    # Deliberately never print client_secret or access_token.
    portfolio = get_live_portfolio()
    print(json.dumps(portfolio, ensure_ascii=False, indent=2))
