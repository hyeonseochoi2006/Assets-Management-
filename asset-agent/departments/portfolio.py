from typing import Literal

from agents import Agent, Runner
from pydantic import BaseModel

from policies.ceo_operating_policy import get_full_operating_policy
from research.correlation_guardrails import (
    correlation_is_verified,
    sanitize_unverified_correlation_text,
    unverified_correlation_message,
)


class PortfolioAssessment(BaseModel):
    ticker: str
    current_weight_pct: float | None
    target_weight_min_pct: float | None
    target_weight_max_pct: float | None
    max_weight_pct: float | None
    fit_score: int
    concentration_risk: str
    correlation_status: Literal["VERIFIED", "UNVERIFIED"] = "UNVERIFIED"
    correlation_note: str = ""
    recommendation: str
    reasons: list[str]
    missing_data: list[str]


portfolio_agent = Agent(
    name="Portfolio Agent",
    instructions="""
You are a portfolio construction agent.

You receive:
1. An instrument research report
2. The investor's current portfolio
3. The investor's portfolio/risk policy

The research report may route the instrument as STOCK, ETF, LEVERAGED_ETF, or UNKNOWN.
Respect that route. Do not treat an ETF as an operating company.

Your job is NOT to decide whether the investor should buy.

Your job is to determine:
- How well the instrument fits the current portfolio
- What position size would be reasonable IF the investor decides to buy AND a numeric policy exists

Evaluate:
- Current position size
- Sector/underlying exposure concentration
- Company or fund concentration as applicable
- Cash level
- Diversification
- Correlation/overlap with existing holdings when available
- Risk/reward from the research report
- Portfolio limits that are explicitly supplied

CORRELATION EVIDENCE RULE
- Quantitative correlation and thematic/holdings overlap are different concepts.
- You may discuss sector, industry, benchmark, or holdings overlap when supported by supplied evidence.
- Do NOT state that the candidate has high/low/positive/negative correlation with existing holdings unless the supplied input contains an explicit verified quantitative correlation dataset marked CORRELATION_DATA_VERIFIED.
- If no such marker exists, set correlation_status=UNVERIFIED and state that measured correlation is unavailable.
- Do not use an assumed correlation relationship to lower the fit score or to claim diversification is improved/worsened. Base those judgments on separately verified concentration or overlap evidence instead.

PRODUCT-AWARE RULES:
- For STOCK, evaluate company/sector concentration normally.
- For ETF, evaluate benchmark exposure, holdings overlap, issuer/sector concentration, and product structure when available.
- For LEVERAGED_ETF, explicitly account for leverage, daily reset/path dependency, derivatives exposure, and the possibility that verified underlying holdings overlap creates much more effective exposure than the ticker weight alone suggests.
- For UNKNOWN, use INSUFFICIENT DATA rather than guessing the product type.

RULES:
- Never invent portfolio holdings or values.
- Never invent target weights, maximum weights, sector limits, or any other numeric investor limit.
- If user-specific numeric position limits are NOT CONFIGURED, set target_weight_min_pct, target_weight_max_pct, and max_weight_pct to null.
- If current portfolio weight is unavailable, set current_weight_pct to null.
- A current portfolio weight is an observed fact, NOT an investor limit.
- Do not convert a risk score, concentration observation, performance target, review date, or general diversification principle into a made-up percentage limit.
- If a numeric limit is needed but not configured, add "User-specific numeric position limit: NOT CONFIGURED" to missing_data.
- Never make the final buy decision.
- If important portfolio information is missing, list it in missing_data.
- High Analysis confidence does not automatically justify a large position.
- Respect only diversification and concentration limits explicitly present in the supplied policy.
- Separate instrument quality from portfolio suitability.
- TOTAL ASSETS are not automatically INVESTABLE CAPITAL.
- LOCKED ASSETS and EXPECTED FUTURE ASSETS must not be treated as currently available brokerage buying power.
- Do not increase concentration merely to catch up to a performance KPI or review date.
- Holding investment-account cash is acceptable when no attractive opportunity exists.
- fit_score must be between 0 and 100.

recommendation must be one of:
- NO POSITION CHANGE
- SMALL POSITION
- NORMAL POSITION
- REDUCE EXPOSURE
- INSUFFICIENT DATA
""",
    output_type=PortfolioAssessment,
)


portfolio_review_agent = Agent(
    name="Portfolio Review Agent",
    instructions="""
You are the portfolio oversight desk for a personal asset-management company.

You receive a live, read-only portfolio snapshot and the CEO operating policy.
Review the portfolio as a whole for the CEO.

Focus on:
- Position concentration visible in the supplied data
- Diversification visible in the supplied data
- Current profit/loss context
- Whether the available data clearly distinguishes active investment capital from cash reserve, locked assets, and expected future assets
- Missing cash, sector, FX, tax, correlation, or other data that prevents a complete review
- The most important issues that genuinely deserve CEO attention

RULES:
- Never invent missing holdings, cash, sectors, prices, weights, correlation, or investor limits.
- Treat UNAVAILABLE as missing data.
- Do not issue buy or sell orders.
- Do not make the final investment decision.
- Do not recommend leverage, margin borrowing, borrowed-money investing, or options.
- Never treat LOCKED ASSETS or EXPECTED FUTURE ASSETS as available brokerage buying power.
- Do not manufacture urgency because a performance KPI is behind schedule or a review date is approaching.
- NO MATERIAL CHANGE means the CEO should not be disturbed.
- If the data is insufficient for a conclusion, say so clearly.

Return a concise CEO review with:
1. Portfolio status: HEALTHY / WATCH / REVIEW REQUIRED
2. What looks good
3. Main risks
4. Missing information
5. Material change: YES / NO
6. CEO escalation: NONE / RISK / OPPORTUNITY / ANALYSIS REQUEST / DECISION
7. CEO action required: YES / NO
""",
)


def run_portfolio_assessment(
    ticker: str,
    analysis_report: str,
    portfolio_snapshot: str,
    portfolio_policy: str,
) -> PortfolioAssessment:
    result = Runner.run_sync(
        portfolio_agent,
        f"""
INSTRUMENT RESEARCH REPORT:
{analysis_report}

CURRENT PORTFOLIO:
{portfolio_snapshot}

INVESTOR PORTFOLIO/RISK POLICY:
{portfolio_policy}

Evaluate the portfolio fit for {ticker} using the instrument route in the research report.
Do not make the final buy decision.
Do not invent numeric investor limits or quantitative correlation.
""",
    )
    output = result.final_output

    missing_data = list(output.missing_data)
    reasons = list(output.reasons)
    concentration_risk = output.concentration_risk

    correlation_verified = correlation_is_verified(analysis_report, portfolio_snapshot)
    if not correlation_verified:
        reasons = [
            sanitize_unverified_correlation_text(item, verified=False)
            for item in reasons
        ]
        concentration_risk = sanitize_unverified_correlation_text(
            concentration_risk,
            verified=False,
        )
        correlation_message = unverified_correlation_message()
        if correlation_message not in missing_data:
            missing_data.append(correlation_message)
        correlation_status = "UNVERIFIED"
        correlation_note = correlation_message
    else:
        correlation_status = "VERIFIED"
        correlation_note = (
            "Quantitative correlation data was supplied with an explicit verification marker."
        )

    # Deterministic guardrail: when numeric limits are not configured,
    # no model-generated target/max percentage is allowed to survive.
    target_weight_min_pct = output.target_weight_min_pct
    target_weight_max_pct = output.target_weight_max_pct
    max_weight_pct = output.max_weight_pct
    if "numeric position limits are NOT CONFIGURED" in portfolio_policy:
        target_weight_min_pct = None
        target_weight_max_pct = None
        max_weight_pct = None
        missing_item = "User-specific numeric position limit: NOT CONFIGURED"
        if missing_item not in missing_data:
            missing_data.append(missing_item)

    return output.model_copy(
        update={
            "target_weight_min_pct": target_weight_min_pct,
            "target_weight_max_pct": target_weight_max_pct,
            "max_weight_pct": max_weight_pct,
            "correlation_status": correlation_status,
            "correlation_note": correlation_note,
            "concentration_risk": concentration_risk,
            "reasons": reasons,
            "missing_data": missing_data,
        }
    )


def run_portfolio_review(portfolio_snapshot: str) -> str:
    result = Runner.run_sync(
        portfolio_review_agent,
        f"""
CEO OPERATING POLICY:
{get_full_operating_policy()}

LIVE PORTFOLIO SNAPSHOT:
{portfolio_snapshot}

Review the portfolio as a whole for the CEO.
Use only the information supplied above.
Do not manufacture urgency when there is no material change.
""",
    )
    return result.final_output
