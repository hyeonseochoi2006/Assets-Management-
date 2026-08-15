from agents import Agent, Runner

from analysis_agent import run_analysis
from portfolio_agent import run_portfolio_assessment
from risk_agent import run_risk_assessment
from execution_agent import run_execution_assessment


cio_agent = Agent(
    name="CIO Agent",
    instructions="""
You are the Chief Investment Officer agent for a personal asset-management system.

You receive completed reports from four specialist agents:
1. Analysis Agent
2. Portfolio Agent
3. Risk Agent
4. Execution Agent

Your job is to synthesize their work into one clear decision brief for the investor.

You do NOT make the final buy decision.
The investor makes the final buy decision.

You must:
- Preserve disagreements between specialist agents instead of hiding them.
- Clearly distinguish verified facts from judgments.
- Highlight missing or unverified information.
- Respect every hard risk limit from the Risk Agent.
- If Risk Agent says REJECT, clearly mark the proposal as BLOCKED.
- Never invent prices, financial figures, portfolio holdings, or market conditions.
- Never recommend leverage or options.

Return a concise report with these sections:
1. Candidate
2. Analysis conclusion
3. Portfolio conclusion
4. Risk conclusion
5. Execution conclusion
6. Main upside
7. Main downside
8. Suggested position range
9. Conditions before any purchase
10. Missing information
11. CIO synthesis
12. FINAL DECISION: INVESTOR REQUIRED

The CIO synthesis may state whether the setup appears favorable, neutral, or unfavorable,
but must never issue or execute a final BUY order.
""",
)


def run_cio_pipeline(
    ticker: str,
    portfolio_snapshot: str,
    risk_limits: str,
    execution_constraints: str,
) -> str:
    # 1. Analysis Agent researches the candidate using current web information.
    analysis_report = run_analysis(ticker)

    # 2. Portfolio Agent evaluates fit using the actual Analysis report.
    portfolio_output = run_portfolio_assessment(
        ticker,
        analysis_report,
        portfolio_snapshot,
    )
    portfolio_report = portfolio_output.model_dump_json(indent=2)

    # 3. Risk Agent evaluates the candidate using both prior reports.
    risk_output = run_risk_assessment(
        ticker,
        analysis_report,
        portfolio_report,
        risk_limits,
    )
    risk_report = risk_output.model_dump_json(indent=2)

    # 4. Execution Agent evaluates how the idea could be implemented if approved.
    execution_output = run_execution_assessment(
        ticker,
        analysis_report,
        portfolio_report,
        risk_report,
        execution_constraints,
    )
    execution_report = execution_output.model_dump_json(indent=2)

    # 5. CIO synthesizes all specialist outputs into one investor-facing brief.
    cio_result = Runner.run_sync(
        cio_agent,
        f"""
CANDIDATE:
{ticker}

ANALYSIS AGENT REPORT:
{analysis_report}

PORTFOLIO AGENT REPORT:
{portfolio_report}

RISK AGENT REPORT:
{risk_report}

EXECUTION AGENT REPORT:
{execution_report}

Prepare the final CIO decision brief for the investor.
Do not make the final buy decision.
""",
    )

    return cio_result.final_output


if __name__ == "__main__":
    # TEST DATA ONLY. Replace this with the investor's real portfolio later.
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

    risk_limits = """
Investor risk tolerance: Moderate
Maximum single-stock allocation: 15%
Maximum technology-sector allocation: 50%
Capital preservation is important.
No leverage allowed.
No options allowed.
"""

    execution_constraints = """
Investor makes the final buy decision.
No leverage.
No options.
Capital preservation is important.
Do not execute a real trade.
If live price, spread, volume, or volatility data are missing, report them as missing.
"""

    print(
        run_cio_pipeline(
            ticker="NVDA",
            portfolio_snapshot=portfolio_snapshot,
            risk_limits=risk_limits,
            execution_constraints=execution_constraints,
        )
    )
