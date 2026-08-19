from pathlib import Path

import pytest
import requests

from operations.external_changes.models import ExternalDocument
from operations.external_changes.runner import run_external_change_detection
from operations.external_changes.sec_client import SecDataError, SecEdgarClient
from operations.models import InstrumentIdentity, PortfolioSnapshot, PositionSnapshot


class FakeResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> object:
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


def _snapshot(captured_at: str = "2026-08-19T10:00:00+00:00") -> PortfolioSnapshot:
    return PortfolioSnapshot(
        captured_at=captured_at,
        account_seq="account-1",
        positions=[
            PositionSnapshot(
                symbol="AAPL",
                currency="USD",
                quantity=1,
                instrument=InstrumentIdentity(
                    symbol="AAPL",
                    market="NASDAQ",
                    security_type="STOCK",
                    currency="USD",
                    resolved=True,
                ),
            )
        ],
    )


def _filing(accession: str, form: str = "10-Q") -> ExternalDocument:
    return ExternalDocument(
        external_id=accession,
        symbol="AAPL",
        cik="0000320193",
        form=form,
        filing_date="2026-08-19",
        title=f"SEC Form {form}",
        url=(
            "https://www.sec.gov/Archives/edgar/data/320193/"
            f"{accession.replace('-', '')}/document.htm"
        ),
    )


class FakeSecClient:
    def __init__(self, batches: list[list[ExternalDocument]]) -> None:
        self.batches = list(batches)

    def resolve_cik(self, symbol: str) -> str | None:
        assert symbol == "AAPL"
        return "0000320193"

    def recent_filings(self, symbol: str, cik: str) -> list[ExternalDocument]:
        assert symbol == "AAPL"
        assert cik == "0000320193"
        return self.batches.pop(0)


def test_sec_client_uses_exact_ticker_and_declared_user_agent() -> None:
    session = FakeSession(
        [
            FakeResponse(
                {
                    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple"},
                    "1": {"cik_str": 1, "ticker": "AAPLX", "title": "Other"},
                }
            )
        ]
    )
    client = SecEdgarClient(
        "Asset Agent admin@example.com",
        session=session,  # type: ignore[arg-type]
        sleep_fn=lambda _: None,
        monotonic_fn=lambda: 1.0,
    )

    assert client.resolve_cik("aapl") == "0000320193"
    assert client.resolve_cik("AAPLX") == "0000000001"
    assert session.calls[0]["headers"]["User-Agent"] == "Asset Agent admin@example.com"  # type: ignore[index]


def test_sec_client_normalizes_recent_submission() -> None:
    session = FakeSession(
        [
            FakeResponse(
                {
                    "filings": {
                        "recent": {
                            "accessionNumber": ["0000320193-26-000001"],
                            "filingDate": ["2026-08-19"],
                            "reportDate": ["2026-06-30"],
                            "acceptanceDateTime": ["20260819120000"],
                            "form": ["10-Q"],
                            "primaryDocument": ["aapl-20260630.htm"],
                            "primaryDocDescription": ["Quarterly report"],
                            "items": [""],
                        }
                    }
                }
            )
        ]
    )
    client = SecEdgarClient(
        "Asset Agent admin@example.com",
        session=session,  # type: ignore[arg-type]
        sleep_fn=lambda _: None,
        monotonic_fn=lambda: 1.0,
    )

    documents = client.recent_filings("AAPL", "0000320193")

    assert documents[0].external_id == "0000320193-26-000001"
    assert documents[0].form == "10-Q"
    assert documents[0].url.endswith(
        "/320193/000032019326000001/aapl-20260630.htm"
    )


def test_sec_client_rejects_malformed_submission() -> None:
    session = FakeSession(
        [
            FakeResponse(
                {
                    "filings": {
                        "recent": {
                            "accessionNumber": ["one"],
                            "filingDate": [],
                            "form": ["8-K"],
                            "primaryDocument": ["doc.htm"],
                        }
                    }
                }
            )
        ]
    )
    client = SecEdgarClient(
        "Asset Agent admin@example.com",
        session=session,  # type: ignore[arg-type]
        sleep_fn=lambda _: None,
        monotonic_fn=lambda: 1.0,
    )

    with pytest.raises(SecDataError, match="inconsistent lengths"):
        client.recent_filings("AAPL", "0000320193")


def test_first_check_is_baseline_then_only_new_filing_creates_event(
    tmp_path: Path,
) -> None:
    old = _filing("0000320193-26-000001")
    new = _filing("0000320193-26-000002", form="8-K")
    client = FakeSecClient([[old], [new, old], [new, old]])
    db_path = tmp_path / "operations.db"

    baseline_report, baseline_events = run_external_change_detection(
        _snapshot(), db_path=db_path, client=client  # type: ignore[arg-type]
    )
    second_report, second_events = run_external_change_detection(
        _snapshot("2026-08-20T10:00:00+00:00"),
        db_path=db_path,
        client=client,  # type: ignore[arg-type]
    )
    third_report, third_events = run_external_change_detection(
        _snapshot("2026-08-21T10:00:00+00:00"),
        db_path=db_path,
        client=client,  # type: ignore[arg-type]
    )

    assert baseline_events == []
    assert baseline_report.source_checks[0].status == "BASELINE_CAPTURED"
    assert len(second_events) == 1
    assert second_events[0].event_type == "FILING_FOUND"
    assert second_events[0].source == "SEC_EDGAR"
    assert second_events[0].severity == "WATCH"
    assert second_report.events_created == 1
    assert third_events == []
    assert third_report.events_created == 0


def test_missing_configuration_does_not_claim_no_change(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("ASSET_SEC_USER_AGENT", raising=False)

    report, events = run_external_change_detection(_snapshot(), db_path=tmp_path / "db")

    assert events == []
    assert report.source_checks[0].status == "NOT_CONFIGURED"
    assert "no SEC request was sent" in report.source_checks[0].note


def test_unresolved_instrument_is_skipped_without_sec_request(tmp_path: Path) -> None:
    snapshot = _snapshot()
    snapshot.positions[0].instrument.resolved = False  # type: ignore[union-attr]

    class MustNotBeCalled:
        def resolve_cik(self, symbol: str) -> str | None:
            raise AssertionError("SEC should not be called")

    report, events = run_external_change_detection(
        snapshot,
        db_path=tmp_path / "db",
        client=MustNotBeCalled(),  # type: ignore[arg-type]
    )

    assert events == []
    assert report.source_checks[0].status == "UNSUPPORTED"


def test_unavailable_check_does_not_create_a_false_baseline(tmp_path: Path) -> None:
    old = _filing("0000320193-26-000001")
    db_path = tmp_path / "operations.db"

    class UnavailableThenValid:
        def __init__(self) -> None:
            self.failed = False

        def resolve_cik(self, symbol: str) -> str | None:
            return "0000320193"

        def recent_filings(
            self, symbol: str, cik: str
        ) -> list[ExternalDocument]:
            if not self.failed:
                self.failed = True
                raise SecDataError("temporary failure")
            return [old]

    client = UnavailableThenValid()
    failed_report, failed_events = run_external_change_detection(
        _snapshot(), db_path=db_path, client=client  # type: ignore[arg-type]
    )
    recovered_report, recovered_events = run_external_change_detection(
        _snapshot("2026-08-20T10:00:00+00:00"),
        db_path=db_path,
        client=client,  # type: ignore[arg-type]
    )

    assert failed_events == []
    assert failed_report.source_checks[0].status == "UNAVAILABLE"
    assert recovered_events == []
    assert recovered_report.source_checks[0].status == "BASELINE_CAPTURED"
