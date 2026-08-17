from agents import Agent, Runner

from departments.bear_case import run_bear_case
from departments.data_auditor import run_data_audit
from departments.etf import run_etf_analysis
from departments.leveraged_etf import run_leveraged_etf_analysis
from departments.product_data_auditor import run_product_data_audit
from research.evidence_pack import build_evidence_pack
from research.instrument_router import classify_instrument
from research.models import (
    AnalysisLeadAssessment,
    DataAuditReport,
    ETFAnalysisAssessment,
    EvidencePack,
    InstrumentRouteAssessment,
    LeveragedETFAnalysisAssessment,
    ProductDataAuditReport,
)
from research.product_claim_guardrails import (
    sanitize_leveraged_etf_assessment,
    sanitize_product_audit_for_downstream,
)


analysis_lead_agent = Agent(
    name="Analysis Lead",
    instructions="""
You are the Analysis Lead for an investment research team.

You receive a shared Evidence Pack and an independent Data Audit for an OPERATING-COMPANY STOCK.
Your job is to interpret the evidence, not to search the web again and not to make the final investment decision.

ANALYSIS RESPONSIBILITIES
- Business quality and competitive position
- Industry/growth context
- Financial strength
- Current valuation based only on supplied evidence
- Catalysts
- Key risks
- Bull case
- Initial bear-case hypothesis
- Missing information and confidence

EVIDENCE DISCIPLINE
- Treat the Evidence Pack as the common factual base.
- Treat Data Auditor conflicts and unverified claims as real uncertainty.
- Never repair a missing number by estimating it.
- Do not silently choose one side of a material data conflict.
- If valuation evidence is insufficient or conflicting, say INSUFFICIENT / UNVERIFIED rather than inventing a conclusion.
- Distinguish company quality from stock attractiveness at the current valuation.
- confidence_score measures confidence in the assessment, not expected return.

BEAR CASE ROUTING
Set bear_case_required=true when an independent adversarial review could materially improve the decision, especially when:
- the setup appears FAVORABLE,
- important assumptions are fragile,
- valuation expectations are demanding,
- the audit contains material conflict,
- or the thesis depends heavily on a small number of catalysts.
Do not request Bear Case merely as ritual for clearly weak/insufficient candidates unless it would add decision value.

OVERALL VIEW
- FAVORABLE: evidence merits serious continued investment review; this is NOT a BUY decision.
- NEUTRAL: mixed evidence or risk/reward not clearly compelling.
- UNFAVORABLE: evidence argues against further priority research at present.
- INSUFFICIENT_DATA: evidence quality is too weak for a reliable conclusion.

Do not make a BUY/SELL decision.
""",
    output_type=AnalysisLeadAssessment,
)


def _run_analysis_lead(
    ticker: str,
    evidence_pack: EvidencePack,
    audit: DataAuditReport,
) -> AnalysisLeadAssessment:
    result = Runner.run_sync(
        analysis_lead_agent,
        f"""
CANDIDATE:
{ticker}

SHARED EVIDENCE PACK:
{evidence_pack.model_dump_json(indent=2)}

DATA AUDITOR REPORT:
{audit.model_dump_json(indent=2)}

Produce the Analysis Lead assessment for this operating-company stock.
Do not search for new facts.
Do not make the final investment decision.
""",
    )
    output = result.final_output
    return output.model_copy(update={"ticker": ticker.upper()})


def _run_stock_analysis(ticker: str, route: InstrumentRouteAssessment) -> str:
    evidence_pack = build_evidence_pack(ticker)

    try:
        audit = run_data_audit(evidence_pack)
    except Exception as exc:
        audit = DataAuditReport(
            ticker=ticker,
            overall_quality="LOW",
            material_conflict=False,
            checked_claims=[],
            conflicts=[],
            unverified_claims=["Data Auditor unavailable for this run."],
            notes=[f"Data Auditor error type: {type(exc).__name__}"],
        )

    lead = _run_analysis_lead(ticker, evidence_pack, audit)

    should_run_bear_case = (
        lead.bear_case_required
        or audit.material_conflict
        or lead.overall_view == "FAVORABLE"
    )

    bear_case_json = "NOT CALLED — Analysis Lead determined no material decision value."
    if should_run_bear_case:
        try:
            bear_case = run_bear_case(evidence_pack, audit, lead)
            bear_case_json = bear_case.model_dump_json(indent=2)
        except Exception as exc:
            bear_case_json = (
                "UNAVAILABLE — Bear Case Specialist failed independently. "
                f"Error type: {type(exc).__name__}. Do not treat the missing challenge as positive evidence."
            )

    return "\n\n".join(
        [
            "=== AGENT INTELLIGENCE v2 · STOCK RESEARCH ===",
            "INSTRUMENT ROUTE:\n" + route.model_dump_json(indent=2),
            "CANDIDATE:\n" + ticker,
            "SHARED EVIDENCE PACK:\n" + evidence_pack.model_dump_json(indent=2),
            "DATA AUDITOR:\n" + audit.model_dump_json(indent=2),
            "ANALYSIS LEAD:\n" + lead.model_dump_json(indent=2),
            "BEAR CASE SPECIALIST:\n" + bear_case_json,
            (
                "PROCESS NOTE:\n"
                "The instrument was routed as STOCK. Evidence was gathered once and shared across the stock research team. "
                "The Bear Case Specialist is conditional. This report is research for Portfolio, Risk, and CIO; "
                "it is not a final BUY/SELL decision."
            ),
        ]
    )


def _safe_product_audit(
    ticker: str,
    route: InstrumentRouteAssessment,
    assessment: ETFAnalysisAssessment | LeveragedETFAnalysisAssessment,
) -> ProductDataAuditReport:
    try:
        return run_product_data_audit(route, assessment)
    except Exception as exc:
        return ProductDataAuditReport(
            ticker=ticker,
            overall_quality="LOW",
            material_conflict=False,
            checked_claims=[],
            conflicts=[],
            unverified_claims=["Product Data Auditor unavailable for this run."],
            notes=[
                f"Product Data Auditor error type: {type(exc).__name__}",
                "Do not treat unaudited product figures as verified evidence.",
            ],
        )


def _run_etf_product_analysis(ticker: str, route: InstrumentRouteAssessment) -> str:
    assessment = run_etf_analysis(ticker, route)
    audit = _safe_product_audit(ticker, route, assessment)
    return "\n\n".join(
        [
            "=== AGENT INTELLIGENCE v2 · ETF PRODUCT RESEARCH ===",
            "INSTRUMENT ROUTE:\n" + route.model_dump_json(indent=2),
            "ETF RESEARCH SPECIALIST:\n" + assessment.model_dump_json(indent=2),
            "PRODUCT DATA AUDITOR:\n" + audit.model_dump_json(indent=2),
            (
                "PROCESS NOTE:\n"
                "This instrument was analyzed as an ETF product, not as an operating company. "
                "Company revenue/profit/FCF analysis was intentionally not used. "
                "The Product Data Auditor independently re-checks decision-critical product claims and may mark them VERIFIED, CONFLICT, or UNVERIFIED. "
                "This is research for Portfolio, Risk, and CIO; it is not a final BUY/SELL decision."
            ),
        ]
    )


def _run_leveraged_product_analysis(ticker: str, route: InstrumentRouteAssessment) -> str:
    raw_assessment = run_leveraged_etf_analysis(ticker, route)
    raw_audit = _safe_product_audit(ticker, route, raw_assessment)
    assessment, wipeout_marker = sanitize_leveraged_etf_assessment(raw_assessment, raw_audit)
    audit = sanitize_product_audit_for_downstream(raw_audit)

    return "\n\n".join(
        [
            "=== AGENT INTELLIGENCE v2 · LEVERAGED ETF PRODUCT RESEARCH ===",
            "INSTRUMENT ROUTE:\n" + route.model_dump_json(indent=2),
            wipeout_marker,
            "LEVERAGED ETF SPECIALIST:\n" + assessment.model_dump_json(indent=2),
            "PRODUCT DATA AUDITOR:\n" + audit.model_dump_json(indent=2),
            (
                "PROCESS NOTE:\n"
                "This instrument was analyzed as a leveraged/inverse ETF or ETP, not as an operating company. "
                "Daily target, reset structure, derivatives, path dependency, volatility drag, and structural risks take priority. "
                "The Product Data Auditor independently re-checks decision-critical product claims and may mark them VERIFIED, CONFLICT, or UNVERIFIED. "
                "Exact numeric total-loss/wipeout thresholds are removed unless the dedicated audit claim is explicitly VERIFIED from reliable primary evidence. "
                "This is research for Portfolio, Risk, and CIO; it is not a final BUY/SELL decision."
            ),
        ]
    )


def _unknown_instrument_report(ticker: str, route: InstrumentRouteAssessment) -> str:
    return "\n\n".join(
        [
            "=== AGENT INTELLIGENCE v2 · UNKNOWN INSTRUMENT ===",
            "INSTRUMENT ROUTE:\n" + route.model_dump_json(indent=2),
            (
                "RESEARCH STATUS:\nINSUFFICIENT_DATA — instrument type could not be verified safely. "
                "Do not analyze it as an operating company and do not make an investment decision until identity/structure is resolved."
            ),
        ]
    )


def run_analysis(ticker: str) -> str:
    """Route the instrument before research while preserving the legacy string interface."""
    normalized_ticker = ticker.strip().upper()
    route = classify_instrument(normalized_ticker)

    if route.route == "STOCK":
        return _run_stock_analysis(normalized_ticker, route)
    if route.route == "ETF":
        return _run_etf_product_analysis(normalized_ticker, route)
    if route.route == "LEVERAGED_ETF":
        return _run_leveraged_product_analysis(normalized_ticker, route)
    return _unknown_instrument_report(normalized_ticker, route)
