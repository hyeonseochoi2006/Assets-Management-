from agents import Agent, Runner

from data.portfolio_monitor import get_live_portfolio_snapshot
from departments.analysis import run_analysis
from departments.execution import run_execution_assessment
from departments.portfolio import run_portfolio_assessment
from departments.risk import run_risk_assessment
from policies.investment_policy import EXECUTION_CONSTRAINTS, RISK_POLICY


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
- Treat UNAVAILABLE values in the portfolio snapshot as genuinely missing data.

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
    portfolio_snapshot: str | None = None,
) -> tuple[str, str]:
    """Run the full read-only investment decision-support pipeline."""
    if portfolio_snapshot is None:
        portfolio_snapshot = get_live_portfolio_snapshot()

    analysis_report = run_analysis(ticker)

    portfolio_output = run_portfolio_assessment(
        ticker,
        analysis_report,
        portfolio_snapshot,
    )
    portfolio_report = portfolio_output.model_dump_json(indent=2)

    risk_output = run_risk_assessment(
        ticker,
        analysis_report,
        portfolio_report,
        RISK_POLICY,
    )
    risk_report = risk_output.model_dump_json(indent=2)

    execution_output = run_execution_assessment(
        ticker,
        analysis_report,
        portfolio_report,
        risk_report,
        EXECUTION_CONSTRAINTS,
    )
    execution_report = execution_output.model_dump_json(indent=2)

    cio_result = Runner.run_sync(
        cio_agent,
        f"""
CANDIDATE:
{ticker}

LIVE TOSS PORTFOLIO SNAPSHOT:
{portfolio_snapshot}

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

    return portfolio_snapshot, cio_result.final_output
