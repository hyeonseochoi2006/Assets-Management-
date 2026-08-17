from typing import Literal

from agents import Agent, Runner
from pydantic import BaseModel

from policies.risk_rubric import aggregate_risk_level, enforce_minimum_review_verdict
from research.correlation_guardrails import (
    sanitize_unverified_correlation_text,
    unverified_correlation_message,
)
from research.product_claim_guardrails import (
    report_has_verified_wipeout_threshold,
    sanitize_downstream_text,
)


RiskLevel = Literal["LOW", "MODERATE", "HIGH", "CRITICAL"]


class RiskAssessment(BaseModel):
    ticker: str

    # Legacy numeric fields remain nullable for API compatibility, but are
    # deterministically cleared after every model run. They are not calibrated.
    overall_risk_score: int | None = None
    company_risk: int | None = None
    valuation_risk: int | None = None
    concentration_risk: int | None = None
    market_risk: int | None = None
    liquidity_risk: int | None = None
    execution_risk: int | None = None

    risk_level: RiskLevel
    company_risk_level: RiskLevel
    valuation_risk_level: RiskLevel
    concentration_risk_level: RiskLevel
    market_risk_level: RiskLevel
    liquidity_risk_level: RiskLevel
    execution_risk_level: RiskLevel

    stress_scenarios: list[str]
    major_risks: list[str]
    risk_limits: list[str]
    risk_verdict: str
    missing_data: list[str]


risk_agent = Agent(
    name="Risk Agent",
    instructions="""
You are an investment risk management agent.

You receive:
1. Analysis Lead / Research Team report
2. Portfolio Agent assessment
3. Investor risk limits

The research report may route the instrument as STOCK, ETF, LEVERAGED_ETF, or UNKNOWN.
Respect that route. Never treat an ETF as an operating company.

For STOCK research, the report may contain a Shared Evidence Pack, Data Auditor report, and conditional Bear Case Specialist report.
Treat Data Auditor CONFLICT/UNVERIFIED items and Bear Case thesis-breakers as explicit risk inputs. Do not erase them because the Analysis Lead is favorable.

For ETF/LEVERAGED_ETF research, the report may contain a Product Data Auditor report.
Treat Product Data Auditor CONFLICT/UNVERIFIED items as explicit risk/data-quality inputs.
Treat SOURCE_MISMATCHED evidence as rejected contamination, not as a valid product-data conflict.
Never silently use a CONFLICT, UNVERIFIED, or source-mismatched AUM, NAV, expense ratio, benchmark, leverage target, reset period, derivatives claim, or prospectus warning as verified fact.
If WIPEOUT_THRESHOLD_STATUS is NOT_VERIFIED, do not calculate, infer, or state any exact percentage threshold for total loss/wipeout.

CORRELATION RULE
- Read correlation_status from the Portfolio Agent report.
- If correlation_status=UNVERIFIED, do not state or imply that the candidate has high/low/positive/negative measured correlation with existing holdings.
- Sector, industry, benchmark, or holdings overlap may still be discussed when separately supported, but do not relabel overlap as correlation.

Your job is NOT to decide whether the investor should buy.
Your job is to determine whether the proposed investment creates acceptable or unacceptable risk.

Evaluate as applicable:
- Company-specific OR product-structure risk
- Valuation risk for stocks, or NAV/premium-discount/expectation risk for funds
- Portfolio concentration
- Sector/underlying exposure concentration
- Market risk
- Liquidity risk
- Execution risk
- Downside scenarios
- Verified correlation/overlap with existing holdings when actually available
- Material evidence conflicts and missing verification
- Bear Case thesis-breakers and disconfirming evidence

LEVERAGED ETF RULES:
- Treat leverage, daily reset/rebalancing, compounding/path dependency, volatility drag, derivatives, counterparty exposure, tracking, liquidity, and rebalance risk as first-class risks.
- A daily leverage target must never be projected mechanically across multi-day holding periods.
- Do not manufacture a total-loss threshold with simple arithmetic. Preserve official issuer/prospectus warnings instead.
- Do not use company revenue/profit/FCF as evidence about a leveraged ETF product.
- Margin borrowing and borrowed-money investing are prohibited.
- Leveraged/inverse ETF or ETP product eligibility is a separate policy field. If it is NOT CONFIGURED, report that as missing policy and do not treat the product as approved/actionable.
- Do not infer product permission or prohibition from the margin/borrowing ban; use the explicit product-eligibility status.

QUALITATIVE RISK RUBRIC:
For each component, output exactly one of LOW / MODERATE / HIGH / CRITICAL.
- company_risk_level: company-specific risk for STOCK, or fund/product-structure risk for ETF products.
- valuation_risk_level: stock valuation risk, or product pricing/NAV/expectation risk for funds.
- concentration_risk_level: portfolio and underlying exposure concentration.
- market_risk_level: sensitivity to market/sector/index movements.
- liquidity_risk_level: ability to trade without unacceptable liquidity/spread risk based on verified evidence.
- execution_risk_level: timing, event, rebalance, spread, and execution uncertainty.

Do NOT assign precise 0-100 scores. Numeric risk-score fields are legacy compatibility fields and must be null.
The application will deterministically aggregate the component levels; do not pretend a 96 is meaningfully different from a 97.

risk_level must be one of:
LOW
MODERATE
HIGH
CRITICAL

risk_verdict must be one of:
PASS
PASS WITH LIMITS
REVIEW REQUIRED
REJECT

RULES:
- Never make the final buy decision.
- Never invent portfolio information.
- Never invent numeric investor limits, target weights, maximum position sizes, or sector caps.
- A qualitative risk level is NOT a position-size limit.
- A current portfolio weight is NOT a policy limit.
- If the supplied policy says numeric limits are NOT CONFIGURED, risk_limits must contain only a NOT CONFIGURED message and must not contain percentages.
- If a numeric limit is needed but not configured, list it in missing_data instead of guessing.
- Never ignore missing information.
- A material Data Auditor or Product Data Auditor conflict must remain unresolved unless later evidence explicitly resolves it.
- If required Bear Case work or product audit work is unavailable, list that as missing analysis rather than assuming the thesis/product is safe.
- High business quality does not eliminate investment risk.
- High expected returns do not justify unlimited risk.
- Identify risks that could cause permanent capital loss.
- Explicitly identify concentration risks.
- Consider realistic stress scenarios.
- Only state enforceable limits that are explicitly supplied by the investor policy.
- If critical information is missing, use REVIEW REQUIRED.
""",
    output_type=RiskAssessment,
)


def run_risk_assessment(
    ticker: str,
    analysis_report: str,
    portfolio_report: str,
    risk_limits: str,
) -> RiskAssessment:
    result = Runner.run_sync(
        risk_agent,
        f"""
ANALYSIS LEAD / RESEARCH TEAM REPORT:
{analysis_report}

PORTFOLIO AGENT REPORT:
{portfolio_report}

INVESTOR RISK LIMITS:
{risk_limits}

Evaluate the risk of adding or maintaining {ticker} within this portfolio.
Respect the instrument route in the research report.
Preserve Data Auditor, Product Data Auditor, and Bear Case dissent when present.
Reject SOURCE_MISMATCHED product data.
Respect the Portfolio Agent correlation_status; do not invent measured correlation.
Use qualitative risk levels, not precise numeric scores.
Do not make the final buy decision.
Do not invent numeric investor limits.
""",
    )
    output = result.final_output

    component_levels = [
        output.company_risk_level,
        output.valuation_risk_level,
        output.concentration_risk_level,
        output.market_risk_level,
        output.liquidity_risk_level,
        output.execution_risk_level,
    ]
    overall_level = aggregate_risk_level(component_levels)

    policy_review_required = (
        "LEVERAGED_ETF" in analysis_report
        and "Leveraged/inverse ETF or ETP eligibility is NOT CONFIGURED" in risk_limits
    )
    verdict = enforce_minimum_review_verdict(
        output.risk_verdict,
        overall_level,
        policy_review_required,
    )

    risk_limit_items = list(output.risk_limits)
    missing_data = list(output.missing_data)
    stress_scenarios = list(output.stress_scenarios)
    major_risks = list(output.major_risks)

    threshold_guard_active = (
        "WIPEOUT_THRESHOLD_STATUS:" in analysis_report
        and not report_has_verified_wipeout_threshold(analysis_report)
    )
    if threshold_guard_active:
        stress_scenarios = [
            sanitize_downstream_text(item, threshold_verified=False)
            for item in stress_scenarios
        ]
        major_risks = [
            sanitize_downstream_text(item, threshold_verified=False)
            for item in major_risks
        ]
        missing_data = [
            sanitize_downstream_text(item, threshold_verified=False)
            for item in missing_data
        ]

    correlation_verified = '"correlation_status": "VERIFIED"' in portfolio_report
    if not correlation_verified:
        stress_scenarios = [
            sanitize_unverified_correlation_text(item, verified=False)
            for item in stress_scenarios
        ]
        major_risks = [
            sanitize_unverified_correlation_text(item, verified=False)
            for item in major_risks
        ]
        missing_data = [
            sanitize_unverified_correlation_text(item, verified=False)
            for item in missing_data
        ]
        correlation_message = unverified_correlation_message()
        if correlation_message not in missing_data:
            missing_data.append(correlation_message)

    # Deterministic guardrail: policy-free percentages must never become hard limits.
    if "numeric position limits are NOT CONFIGURED" in risk_limits:
        risk_limit_items = [
            "NOT CONFIGURED — CEO policy required before any numeric position limit can be enforced."
        ]
        missing_item = "User-specific numeric position limit: NOT CONFIGURED"
        if missing_item not in missing_data:
            missing_data.append(missing_item)

    if policy_review_required:
        missing_item = "Leveraged/inverse ETF or ETP eligibility: NOT CONFIGURED"
        if missing_item not in missing_data:
            missing_data.append(missing_item)

    return output.model_copy(
        update={
            "overall_risk_score": None,
            "company_risk": None,
            "valuation_risk": None,
            "concentration_risk": None,
            "market_risk": None,
            "liquidity_risk": None,
            "execution_risk": None,
            "risk_level": overall_level,
            "risk_verdict": verdict,
            "risk_limits": risk_limit_items,
            "missing_data": missing_data,
            "stress_scenarios": stress_scenarios,
            "major_risks": major_risks,
        }
    )
