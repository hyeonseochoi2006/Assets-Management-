from typing import Literal

from pydantic import BaseModel, Field


class InstrumentIdentity(BaseModel):
    symbol: str
    name: str | None = None
    english_name: str | None = None
    isin_code: str | None = None
    market: str | None = None
    security_type: str | None = None
    status: str | None = None
    currency: str | None = None
    resolved: bool = False
    source: str = "Toss Securities Stock Info API"
    resolution_note: str | None = None


class PositionSnapshot(BaseModel):
    symbol: str
    currency: str | None = None
    quantity: float | None = None
    price: float | None = None
    position_value: float | None = None
    weight_pct: float | None = None
    instrument: InstrumentIdentity | None = None


class PortfolioSnapshot(BaseModel):
    captured_at: str
    account_seq: str
    positions: list[PositionSnapshot] = Field(default_factory=list)
    market_value_by_currency: dict[str, float] = Field(default_factory=dict)
    total_purchase_by_currency: dict[str, float] = Field(default_factory=dict)
    profit_loss_by_currency: dict[str, float] = Field(default_factory=dict)
    daily_profit_loss_by_currency: dict[str, float] = Field(default_factory=dict)
    cash_available: float | None = None
    cash_status: str = "UNAVAILABLE"


class FieldChange(BaseModel):
    field: str
    previous: float | str | None = None
    current: float | str | None = None


class PositionChange(BaseModel):
    symbol: str
    change_type: Literal["ADDED", "REMOVED", "UPDATED"]
    fields: list[FieldChange] = Field(default_factory=list)


class ChangeSet(BaseModel):
    baseline: bool
    previous_captured_at: str | None = None
    current_captured_at: str
    changes: list[PositionChange] = Field(default_factory=list)
    summary: str


class MonitoringFinding(BaseModel):
    ticker: str
    category: str
    importance: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    summary: str
    thesis_impact: bool
    evidence: list[str] = Field(default_factory=list)
    missing_or_unverified: list[str] = Field(default_factory=list)


class MonitoringReport(BaseModel):
    findings: list[MonitoringFinding] = Field(default_factory=list)
    data_quality: Literal["HIGH", "MEDIUM", "LOW"]
    notes: list[str] = Field(default_factory=list)


class DailyCioDecision(BaseModel):
    material_change: bool
    escalation: Literal[
        "NONE",
        "RISK",
        "OPPORTUNITY",
        "ANALYSIS_REQUEST",
        "DECISION",
    ]
    ceo_action_required: bool
    affected_tickers: list[str] = Field(default_factory=list)
    summary: str
    reasons: list[str] = Field(default_factory=list)
    recommended_next_step: str
