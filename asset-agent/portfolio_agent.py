from pydantic import BaseModel
from agents import Agent, Runner

class PortfolioAssessment(BaseModel):
        ticker: str
        current_weight_pct: float
        target_weight_min_pct: float
        target_weight_max_pct: float
        max_weight_pct: float
        fit_score: int
        concentration_risk: str
        recommendation: str
        reasons: list[str]
        missing_data: list[str]




portfolio_agent = Agent(
name="Portfolio Agent",
instructions="""
You are a portfolio construction agent.

You receive:
1. An investment report from the Analysis Agent
2. The investor's current portfolio
3. Portfolio rules and limits

Your job is NOT to decide whether the investor should buy.

Your job is to determine:
- How well the stock fits the current portfolio
- What position size would be reasonable
IF the investor decides to buy

Evaluate:
- Current position size
- Sector concentration
- Company concentration
- Cash level
- Diversification
- Correlation with existing holdings
- Risk/reward from the Analysis Agent
- Portfolio limits

RULES:

- Never invent portfolio holdings or values.
- Never make the final buy decision.
- If important portfolio information is missing,
list it in missing_data.
- High Analysis confidence does not automatically
justify a large position.
- Respect diversification and concentration limits.
- Separate company quality from portfolio suitability.
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


portfolio_snapshot = """
TEST PORTFOLIO

Total portfolio value: $100,000
Cash: 20%

NVDA: 5%
MSFT: 15%
AAPL: 15%
Other equities: 45%

Risk tolerance: Moderate
Maximum single-stock allocation: 15%
Maximum technology-sector allocation: 50%
"""


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


result = Runner.run_sync(
portfolio_agent,
f"""
ANALYSIS AGENT REPORT:
{analysis_report}

CURRENT PORTFOLIO:
{portfolio_snapshot}

Evaluate the portfolio fit for NVDA.
""",
)


print(result.final_output.model_dump_json(indent=2))