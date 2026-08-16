from agents import Agent, Runner
from pydantic import BaseModel


class RiskAssessment(BaseModel):
    ticker: str
    overall_risk_score: int
    risk_level: str
    company_risk: int
    valuation_risk: int
    concentration_risk: int
    market_risk: int
    liquidity_risk: int
    execution_risk: int
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
1. Analysis Agent research
2. Portfolio Agent assessment
3. Investor risk limits

Your job is NOT to decide whether the investor should buy.

Your job is to determine whether the proposed investment creates acceptable or unacceptable risk.

Evaluate:
- Company-specific risk
- Valuation risk
- Portfolio concentration
- Sector concentration
- Market risk
- Liquidity risk
- Execution risk
- Downside scenarios
- Correlation with existing holdings

SCORING:
All individual risk scores must be between 0 and 100.
0 = very low risk
100 = extremely high risk

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
- A risk score is NOT a position-size limit.
- A current portfolio weight is NOT a policy limit.
- If the supplied policy says numeric limits are NOT CONFIGURED, risk_limits must contain only a NOT CONFIGURED message and must not contain percentages.
- If a numeric limit is needed but not configured, list it in missing_data instead of guessing.
- Never ignore missing information.
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
ANALYSIS AGENT REPORT:
{analysis_report}

PORTFOLIO AGENT REPORT:
{portfolio_report}

INVESTOR RISK LIMITS:
{risk_limits}

Evaluate the risk of adding or maintaining {ticker} within this portfolio.
Do not make the final buy decision.
Do not invent numeric investor limits.
""",
    )
    output = result.final_output

    # Deterministic guardrail: policy-free percentages must never become hard limits.
    if "numeric position limits are NOT CONFIGURED" in risk_limits:
        output.risk_limits = [
            "NOT CONFIGURED — CEO policy required before any numeric position limit can be enforced."
        ]
        missing_item = "User-specific numeric position limit: NOT CONFIGURED"
        if missing_item not in output.missing_data:
            output.missing_data.append(missing_item)

    return output
