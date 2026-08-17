from typing import Literal

from pydantic import BaseModel, Field


class EvidenceFact(BaseModel):
    category: Literal[
        "BUSINESS",
        "INDUSTRY",
        "REVENUE",
        "PROFIT",
        "CASH",
        "DEBT",
        "GUIDANCE",
        "VALUATION",
        "CATALYST",
        "RISK",
        "OTHER",
    ]
    statement: str
    value_text: str | None = None
    period: str | None = None
    source_name: str
    source_url: str | None = None
    source_date: str | None = None
    primary_source: bool
    importance: Literal["LOW", "MEDIUM", "HIGH"]
    verification_status: Literal["SOURCE_REPORTED", "UNVERIFIED"]


class EvidencePack(BaseModel):
    ticker: str
    company_name: str
    as_of_date: str
    business_summary: str
    industry_summary: str
    facts: list[EvidenceFact] = Field(default_factory=list)
    missing_or_unverified: list[str] = Field(default_factory=list)
    source_count: int = 0
    primary_source_count: int = 0


class AuditClaim(BaseModel):
    claim: str
    status: Literal["VERIFIED", "CONFLICT", "UNVERIFIED"]
    sources: list[str] = Field(default_factory=list)
    note: str


class DataConflict(BaseModel):
    topic: str
    source_a: str
    source_b: str
    explanation: str
    material: bool


class DataAuditReport(BaseModel):
    ticker: str
    overall_quality: Literal["HIGH", "MEDIUM", "LOW"]
    material_conflict: bool
    checked_claims: list[AuditClaim] = Field(default_factory=list)
    conflicts: list[DataConflict] = Field(default_factory=list)
    unverified_claims: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AnalysisLeadAssessment(BaseModel):
    ticker: str
    data_date: str
    overall_view: Literal["FAVORABLE", "NEUTRAL", "UNFAVORABLE", "INSUFFICIENT_DATA"]
    business_quality: str
    growth: str
    financial_strength: str
    valuation: str
    catalysts: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    bull_case: str
    bear_case_seed: str
    missing_information: list[str] = Field(default_factory=list)
    data_quality: Literal["HIGH", "MEDIUM", "LOW"]
    confidence_score: int = Field(ge=0, le=100)
    bear_case_required: bool
    bear_case_reason: str


class BearCaseAssessment(BaseModel):
    ticker: str
    severity: Literal["LOW", "MODERATE", "HIGH", "CRITICAL"]
    strongest_bear_case: str
    thesis_breakers: list[str] = Field(default_factory=list)
    disconfirming_evidence: list[str] = Field(default_factory=list)
    downside_scenarios: list[str] = Field(default_factory=list)
    key_unknowns: list[str] = Field(default_factory=list)
    recommended_followup: str


class InstrumentRouteAssessment(BaseModel):
    ticker: str
    route: Literal["STOCK", "ETF", "LEVERAGED_ETF", "UNKNOWN"]
    official_name: str | None = None
    broker_security_type: str | None = None
    leverage_target: str | None = None
    reset_frequency: str | None = None
    classification_source: str
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    reasons: list[str] = Field(default_factory=list)
    missing_or_unverified: list[str] = Field(default_factory=list)


class ETFAnalysisAssessment(BaseModel):
    ticker: str
    official_name: str
    as_of_date: str
    objective: str
    benchmark: str | None = None
    expense_ratio: str | None = None
    nav: str | None = None
    market_price: str | None = None
    aum: str | None = None
    liquidity: str
    holdings_and_concentration: str
    tracking_and_premium_discount: str
    derivatives_exposure: str
    key_risks: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    data_quality: Literal["HIGH", "MEDIUM", "LOW"]
    confidence_score: int = Field(ge=0, le=100)
    sources: list[str] = Field(default_factory=list)


class LeveragedETFAnalysisAssessment(BaseModel):
    ticker: str
    official_name: str
    as_of_date: str
    objective: str
    benchmark: str | None = None
    daily_target: str | None = None
    reset_frequency: str | None = None
    leverage_mechanism: str
    expense_ratio: str | None = None
    nav: str | None = None
    market_price: str | None = None
    aum: str | None = None
    liquidity: str
    derivatives_exposure: str
    path_dependency_and_compounding: str
    volatility_drag: str
    counterparty_and_structure_risk: str
    holding_period_warning: str
    total_loss_warning: str
    key_risks: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    data_quality: Literal["HIGH", "MEDIUM", "LOW"]
    confidence_score: int = Field(ge=0, le=100)
    sources: list[str] = Field(default_factory=list)
