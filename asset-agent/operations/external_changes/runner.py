import os
from pathlib import Path

from operations.change_detector import build_change_event
from operations.change_policy import PortfolioChangePolicy
from operations.external_changes.models import (
    ExternalChangeReport,
    ExternalDocument,
    ExternalSourceCheck,
)
from operations.external_changes.sec_client import SecDataError, SecEdgarClient
from operations.external_changes.store import ExternalDocumentStore
from operations.models import ChangeEvent, PortfolioSnapshot, PositionSnapshot


_DEFAULT_RUNTIME_DIR = Path(__file__).resolve().parents[2] / "runtime"
_IMPORTANT_FORMS = {
    "8-K",
    "8-K/A",
    "10-K",
    "10-K/A",
    "10-Q",
    "10-Q/A",
    "20-F",
    "20-F/A",
    "40-F",
    "40-F/A",
    "6-K",
}


def _now_or_snapshot(snapshot: PortfolioSnapshot) -> str:
    return snapshot.captured_at


def _supported_us_stock(position: PositionSnapshot) -> tuple[bool, str]:
    identity = position.instrument
    if identity is None or not identity.resolved:
        return False, "Exact Toss instrument identity is unavailable."
    security_type = (identity.security_type or "").strip().upper()
    if not (
        security_type == "STOCK"
        or "COMMON STOCK" in security_type
        or "EQUITY" in security_type
    ):
        return False, "Initial SEC collector supports resolved stocks only."
    currency = (identity.currency or position.currency or "").strip().upper()
    if currency != "USD":
        return False, "Initial SEC collector supports USD-listed stocks only."
    return True, "Resolved U.S. stock identity."


def _filing_event(
    document: ExternalDocument,
    detected_at: str,
    policy: PortfolioChangePolicy,
) -> ChangeEvent:
    important = document.form.upper() in _IMPORTANT_FORMS
    severity = "WATCH" if important else "QUIET"
    return build_change_event(
        event_type="FILING_FOUND",
        symbol=document.symbol,
        severity=severity,
        detected_at=detected_at,
        previous_captured_at=None,
        previous=None,
        current=document.external_id,
        reason=(
            f"A new official SEC {document.form} filing was observed. "
            "This routes attention only and is not an investment conclusion."
        ),
        policy=policy,
        source="SEC_EDGAR",
        identity_key=f"SEC_EDGAR:{document.external_id}",
        evidence=[
            f"accession={document.external_id}",
            f"form={document.form}",
            f"filing_date={document.filing_date}",
            f"cik={document.cik}",
            f"official_url={document.url}",
        ],
    )


def run_external_change_detection(
    snapshot: PortfolioSnapshot,
    *,
    db_path: Path | None = None,
    client: SecEdgarClient | None = None,
) -> tuple[ExternalChangeReport, list[ChangeEvent]]:
    checked_at = _now_or_snapshot(snapshot)
    source_checks: list[ExternalSourceCheck] = []
    new_documents: list[ExternalDocument] = []

    user_agent = os.getenv("ASSET_SEC_USER_AGENT", "").strip()
    if client is None and not user_agent:
        source_checks.append(
            ExternalSourceCheck(
                source="SEC_EDGAR",
                status="NOT_CONFIGURED",
                checked_at=checked_at,
                note=(
                    "ASSET_SEC_USER_AGENT is missing; no SEC request was sent and "
                    "the result is not reported as 'no change'."
                ),
            )
        )
    else:
        sec_client = client or SecEdgarClient(user_agent=user_agent)
        runtime_dir = Path(
            os.getenv("ASSET_RUNTIME_DIR", str(_DEFAULT_RUNTIME_DIR))
        )
        store = ExternalDocumentStore(db_path or runtime_dir / "operations.db")

        for position in snapshot.positions:
            symbol = position.symbol.strip().upper()
            supported, note = _supported_us_stock(position)
            if not supported:
                source_checks.append(
                    ExternalSourceCheck(
                        source="SEC_EDGAR",
                        status="UNSUPPORTED",
                        symbol=symbol,
                        checked_at=checked_at,
                        note=note,
                    )
                )
                continue
            try:
                cik = sec_client.resolve_cik(symbol)
                if cik is None:
                    source_checks.append(
                        ExternalSourceCheck(
                            source="SEC_EDGAR",
                            status="UNSUPPORTED",
                            symbol=symbol,
                            checked_at=checked_at,
                            note="Exact ticker was not found in the official SEC ticker file.",
                        )
                    )
                    continue
                documents = sec_client.recent_filings(symbol, cik)
                baseline, unseen = store.ingest(
                    source="SEC_EDGAR",
                    subject_key=cik,
                    checked_at=checked_at,
                    documents=documents,
                )
                new_documents.extend(unseen)
                source_checks.append(
                    ExternalSourceCheck(
                        source="SEC_EDGAR",
                        status="BASELINE_CAPTURED" if baseline else "OK",
                        symbol=symbol,
                        checked_at=checked_at,
                        documents_seen=len(documents),
                        new_documents=len(unseen),
                        note=(
                            "Initial official filing baseline stored; no old filing was alerted."
                            if baseline
                            else "Compared official filings with the durable baseline."
                        ),
                    )
                )
            except Exception as exc:
                note = str(exc) if isinstance(exc, SecDataError) else type(exc).__name__
                source_checks.append(
                    ExternalSourceCheck(
                        source="SEC_EDGAR",
                        status="UNAVAILABLE",
                        symbol=symbol,
                        checked_at=checked_at,
                        note=(
                            "Official SEC check was unavailable; no 'no change' "
                            f"conclusion was recorded. Error: {note}"
                        ),
                    )
                )

    source_checks.extend(
        [
            ExternalSourceCheck(
                source="COMPANY_IR",
                status="NOT_CONFIGURED",
                checked_at=checked_at,
                note="Company IR source registry is deferred; no page was guessed or scraped.",
            ),
            ExternalSourceCheck(
                source="NEWS",
                status="NOT_CONFIGURED",
                checked_at=checked_at,
                note="Licensed news source is not configured; no article body was scraped.",
            ),
        ]
    )

    policy = PortfolioChangePolicy.from_env()
    events = [_filing_event(document, checked_at, policy) for document in new_documents]
    statuses = ", ".join(
        f"{check.source}:{check.status}" for check in source_checks
    )
    report = ExternalChangeReport(
        checked_at=checked_at,
        source_checks=source_checks,
        new_documents=new_documents,
        events_created=len(events),
        summary=(
            f"Official-source checks completed; {len(new_documents)} new document(s), "
            f"{len(events)} deterministic event(s). Statuses: {statuses}."
        ),
    )
    return report, events
