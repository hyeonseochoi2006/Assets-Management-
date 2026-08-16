from agents import Agent, Runner
from pydantic import BaseModel


class PortfolioAssessment(BaseModel):
    ticker: str
    current_weight_pct: float | None
    target_weight_min_pct: float | None
    target_weight_max_pct: float | None
    max_weight_pct: float | None
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
3. The investor's portfolio/risk policy

Your job is NOT to decide whether the investor should buy.

Your job is to determine:
- How well the stock fits the current portfolio
- What position size would be reasonable IF the investor decides to buy AND a numeric policy exists

Evaluate:
- Current position size
- Sector concentration
- Company concentration
- Cash level
- Diversification
- Correlation with existing holdings
- Risk/reward from the Analysis Agent
- Portfolio limits that are explicitly supplied

RULES:
- Never invent portfolio holdings or values.
- Never invent target weights, maximum weights, sector limits, or any other numeric investor limit.
- If user-specific numeric position limits are NOT CONFIGURED, set target_weight_min_pct, target_weight_max_pct, and max_weight_pct to null.
- If current portfolio weight is unavailable, set current_weight_pct to null.
- A current portfolio weight is an observed fact, NOT an investor limit.
- Do not convert a risk score, concentration observation, or general diversification principle into a made-up percentage limit.
- If a numeric limit is needed but not configured, add "User-specific numeric position limit: NOT CONFIGURED" to missing_data.
- Never make the final buy decision.
- If important portfolio information is missing, list it in missing_data.
- High Analysis confidence does not automatically justify a large position.
- Respect only diversification and concentration limits explicitly present in the supplied policy.
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
    portfolio_policy: str,
) -> PortfolioAssessment:
    result = Runner.run_sync(
        portfolio_agent,
        f"""
ANALYSIS AGENT REPORT:
{analysis_report}

CURRENT PORTFOLIO:
{portfolio_snapshot}

INVESTOR PORTFOLIO/RISK POLICY:
{portfolio_policy}

Evaluate the portfolio fit for {ticker}.
Do not make the final buy decision.
Do not invent numeric investor limits.
""",
    )
    output = result.final_output

    # Deterministic guardrail: when numeric limits are not configured,
    # no model-generated target/max percentage is allowed to survive.
    if "numeric position limits are NOT CONFIGURED" in portfolio_policy:
        output.target_weight_min_pct = None
        output.target_weight_max_pct = None
        output.max_weight_pct = None
        missing_item = "User-specific numeric position limit: NOT CONFIGURED"
        if missing_item not in output.missing_data:
            output.missing_data.append(missing_item)

    return output


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
