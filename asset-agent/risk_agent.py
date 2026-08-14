from pydantic import BaseModel
from agents import Agent, Runner


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

Your job is to determine whether the proposed investment
creates acceptable or unacceptable risk.

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
- Never ignore missing information.
- High business quality does not eliminate investment risk.
- High expected returns do not justify unlimited risk.
- Identify risks that could cause permanent capital loss.
- Explicitly identify concentration risks.
- Consider realistic stress scenarios.
- State limits that would reduce risk.
- If critical information is missing, use REVIEW REQUIRED.
""",

output_type=RiskAssessment,
)


analysis_report = """
Ticker: NVDA

Business Quality: 9/10
Growth: 9/10
Financial Strength: 9/10
Valuation: 6/10
Catalysts: 8/10
Risk: 7/10

Data Quality: HIGH
Confidence: 83/100

Bull Case:
Strong AI infrastructure growth and market leadership.

Bear Case:
High valuation, customer concentration,
competition and AI capital-spending slowdown risk.
"""


portfolio_report = """
Ticker: NVDA

Current Weight: 5.0%
Target Weight Range: 3.0% - 7.5%
Maximum Weight: 15.0%

Portfolio Fit Score: 78/100

Concentration Risk:
Moderate.

Technology exposure is already substantial.
NVDA may correlate with existing technology holdings.
"""


risk_limits = """
Investor risk tolerance: Moderate

Maximum single-stock allocation: 15%
Maximum technology-sector allocation: 50%

Capital preservation is important.

No leverage allowed.
No options allowed.
"""


result = Runner.run_sync(
    risk_agent,
        f"""
        ANALYSIS AGENT REPORT:

        {analysis_report}


        PORTFOLIO AGENT REPORT:

        {portfolio_report}


        INVESTOR RISK LIMITS:

        {risk_limits}


        Evaluate the risk of adding or maintaining NVDA
        within this portfolio.
        """,
        )


print(result.final_output.model_dump_json(indent=2))