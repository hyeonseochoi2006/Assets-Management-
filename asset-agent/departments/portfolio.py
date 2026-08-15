from agents import Agent, Runner
from pydantic import BaseModel


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
- What position size would be reasonable IF the investor decides to buy

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
- If important portfolio information is missing, list it in missing_data.
- High Analysis confidence does not automatically justify a large position.
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


portfolio_review_agent = Agent(
    name="Portfolio Review Agent",
    instructions="""
You are the portfolio oversight desk for a personal asset-management company.

You receive a live, read-only portfolio snapshot from the brokerage.
Review the portfolio as a whole for the CEO.

Focus on:
- Position concentration visible in the supplied data
- Diversification visible in the supplied data
- Current profit/loss context
- Missing cash, sector, FX, tax, correlation, or other data that prevents a complete review
- The most important issues that deserve CEO attention

RULES:
- Never invent missing holdings, cash, sectors, prices, weights, or investor limits.
- Treat UNAVAILABLE as missing data.
- Do not issue buy or sell orders.
- Do not make the final investment decision.
- Do not recommend leverage or options.
- If the data is insufficient for a conclusion, say so clearly.

Return a concise CEO review with:
1. Portfolio status: HEALTHY / WATCH / REVIEW REQUIRED
2. What looks good
3. Main risks
4. Missing information
5. CEO attention items
""",
)


def run_portfolio_assessment(
    ticker: str,
    analysis_report: str,
    portfolio_snapshot: str,
) -> PortfolioAssessment:
    result = Runner.run_sync(
        portfolio_agent,
        f"""
ANALYSIS AGENT REPORT:
{analysis_report}

CURRENT PORTFOLIO:
{portfolio_snapshot}

Evaluate the portfolio fit for {ticker}.
Do not make the final buy decision.
""",
    )
    return result.final_output


def run_portfolio_review(portfolio_snapshot: str) -> str:
    result = Runner.run_sync(
        portfolio_review_agent,
        f"""
LIVE PORTFOLIO SNAPSHOT:
{portfolio_snapshot}

Review the portfolio as a whole for the CEO.
Use only the information supplied above.
""",
    )
    return result.final_output
