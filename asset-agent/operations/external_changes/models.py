from typing import Literal

from pydantic import BaseModel, Field


class ExternalDocument(BaseModel):
    source: Literal["SEC_EDGAR"] = "SEC_EDGAR"
    external_id: str
    symbol: str
    cik: str
    form: str
    filing_date: str
    report_date: str | None = None
    accepted_at: str | None = None
    items: str | None = None
    title: str
    url: str


class ExternalSourceCheck(BaseModel):
    source: Literal["SEC_EDGAR", "COMPANY_IR", "NEWS"]
    status: Literal[
        "OK",
        "BASELINE_CAPTURED",
        "NOT_CONFIGURED",
        "UNSUPPORTED",
        "UNAVAILABLE",
    ]
    symbol: str | None = None
    checked_at: str
    documents_seen: int = 0
    new_documents: int = 0
    note: str


class ExternalChangeReport(BaseModel):
    checked_at: str
    source_checks: list[ExternalSourceCheck] = Field(default_factory=list)
    new_documents: list[ExternalDocument] = Field(default_factory=list)
    events_created: int = 0
    summary: str
