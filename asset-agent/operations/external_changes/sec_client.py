from collections.abc import Callable
import time
from typing import Any

import requests

from operations.external_changes.models import ExternalDocument


_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"


class SecDataError(RuntimeError):
    """The official SEC source was unavailable or returned invalid data."""


class SecEdgarClient:
    """Small SEC EDGAR client with an intentionally conservative request rate."""

    def __init__(
        self,
        user_agent: str,
        *,
        timeout_seconds: float = 10.0,
        request_interval_seconds: float = 0.2,
        session: requests.Session | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._user_agent = user_agent.strip()
        self._timeout_seconds = timeout_seconds
        self._request_interval_seconds = max(0.1, request_interval_seconds)
        self._session = session or requests.Session()
        self._sleep = sleep_fn
        self._monotonic = monotonic_fn
        self._last_request_at: float | None = None
        self._ticker_to_cik: dict[str, str] | None = None

    def _get_json(self, url: str) -> Any:
        if not self._user_agent:
            raise SecDataError("SEC User-Agent is not configured.")
        now = self._monotonic()
        if self._last_request_at is not None:
            remaining = self._request_interval_seconds - (now - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
        try:
            response = self._session.get(
                url,
                headers={
                    "User-Agent": self._user_agent,
                    "Accept-Encoding": "gzip, deflate",
                },
                timeout=self._timeout_seconds,
            )
            self._last_request_at = self._monotonic()
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise SecDataError(f"SEC request failed: {type(exc).__name__}") from exc

    def ticker_map(self) -> dict[str, str]:
        if self._ticker_to_cik is not None:
            return self._ticker_to_cik
        payload = self._get_json(_TICKERS_URL)
        if not isinstance(payload, dict):
            raise SecDataError("SEC ticker file is not a JSON object.")

        result: dict[str, str] = {}
        for item in payload.values():
            if not isinstance(item, dict):
                continue
            ticker = str(item.get("ticker", "")).strip().upper()
            cik_raw = item.get("cik_str")
            if not ticker or isinstance(cik_raw, bool):
                continue
            try:
                cik = f"{int(cik_raw):010d}"
            except (TypeError, ValueError):
                continue
            result[ticker] = cik
        if not result:
            raise SecDataError("SEC ticker file contains no usable identities.")
        self._ticker_to_cik = result
        return result

    def resolve_cik(self, symbol: str) -> str | None:
        return self.ticker_map().get(symbol.strip().upper())

    def recent_filings(self, symbol: str, cik: str) -> list[ExternalDocument]:
        payload = self._get_json(_SUBMISSIONS_URL.format(cik=cik))
        filings = payload.get("filings") if isinstance(payload, dict) else None
        recent = filings.get("recent") if isinstance(filings, dict) else None
        if not isinstance(recent, dict):
            raise SecDataError("SEC submissions response has no filings.recent object.")

        required = ("accessionNumber", "filingDate", "form", "primaryDocument")
        columns: dict[str, list[Any]] = {}
        for key in required:
            value = recent.get(key)
            if not isinstance(value, list):
                raise SecDataError(f"SEC submissions response has invalid {key} data.")
            columns[key] = value
        lengths = {len(value) for value in columns.values()}
        if len(lengths) != 1:
            raise SecDataError("SEC submissions columns have inconsistent lengths.")

        documents: list[ExternalDocument] = []
        for index in range(len(columns["accessionNumber"])):
            accession = str(columns["accessionNumber"][index]).strip()
            filing_date = str(columns["filingDate"][index]).strip()
            form = str(columns["form"][index]).strip()
            primary_document = str(columns["primaryDocument"][index]).strip()
            if not all((accession, filing_date, form, primary_document)):
                raise SecDataError("SEC submissions response contains a blank required field.")

            description = _optional_column(recent, "primaryDocDescription", index)
            report_date = _optional_column(recent, "reportDate", index)
            accepted_at = _optional_column(recent, "acceptanceDateTime", index)
            items = _optional_column(recent, "items", index)
            url = _ARCHIVE_URL.format(
                cik=int(cik),
                accession=accession.replace("-", ""),
                document=primary_document,
            )
            documents.append(
                ExternalDocument(
                    external_id=accession,
                    symbol=symbol.strip().upper(),
                    cik=cik,
                    form=form,
                    filing_date=filing_date,
                    report_date=report_date,
                    accepted_at=accepted_at,
                    items=items,
                    title=description or f"SEC Form {form}",
                    url=url,
                )
            )
        return documents


def _optional_column(data: dict[str, Any], key: str, index: int) -> str | None:
    values = data.get(key)
    if not isinstance(values, list) or index >= len(values):
        return None
    value = str(values[index]).strip()
    return value or None
