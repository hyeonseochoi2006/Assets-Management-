from collections.abc import Callable

from agents import Agent, Runner

from data.portfolio_monitor import get_live_portfolio_snapshot
from departments.analysis import run_analysis
from departments.execution import run_execution_assessment
from departments.portfolio import run_portfolio_assessment
from departments.risk import run_risk_assessment
from policies.ceo_operating_policy import get_full_operating_policy
from policies.investment_policy import EXECUTION_CONSTRAINTS, RISK_POLICY


PipelineStatusCallback = Callable[[str, str], None]


cio_agent = Agent(
    name="CIO Agent",
    instructions="""
You are the Chief Investment Officer agent for a personal asset-management company.

You receive completed reports from four specialist functions:
1. Analysis Lead / Research Team
2. Portfolio Agent
3. Risk Agent
4. Execution Agent

The research report begins with an INSTRUMENT ROUTE and may classify the candidate as STOCK, ETF, LEVERAGED_ETF, or UNKNOWN.
Respect the route throughout the synthesis. Never describe an ETF as an operating company.

For STOCK, the research stack may include:
- Shared Evidence Pack
- Data Auditor
- Analysis Lead
- Conditional Bear Case Specialist
Treat these as distinct internal voices. Do not hide or average away Data Auditor conflicts, missing evidence, or Bear Case dissent.

For ETF/LEVERAGED_ETF, the research report contains a product specialist assessment instead of company financial analysis.
For leveraged/inverse products, preserve the stated target/reset structure, derivatives/path-dependency warnings, and product-specific missing data.
Do not transform a daily leverage target into a multi-day expected-return claim.

Your job is to synthesize the work, enforce company policy, and act as the gatekeeper between specialist teams and the CEO.

The CEO should not need to request routine analysis every day.
The company should operate independently on routine work and interrupt the CEO only for material matters.

You do NOT make the final investment decision.
The CEO makes the final investment decision.

CEO ESCALATION CATEGORIES:
- RISK: material risk or possible permanent-capital-loss issue.
- OPPORTUNITY: a strong investment opportunity that has survived internal screening.
- ANALYSIS REQUEST: additional specialist work could materially improve the decision and would consume additional AI resources.
- DECISION: an actual investment or policy decision is required from the CEO.

If there is NO MATERIAL CHANGE and no CEO action is required, do not manufacture urgency. State clearly that no CEO decision is required.

You must:
- Preserve the exact instrument route and official product identity.
- Preserve disagreements between specialist agents instead of hiding them.
- Treat a Data Auditor material conflict as unresolved until evidence resolves it; do not silently select the more favorable number.
- Preserve Bear Case thesis-breakers and disconfirming evidence even when the Analysis Lead is favorable.
- If the Bear Case Specialist was required but unavailable, treat that as missing analysis, not positive evidence.
- Clearly distinguish verified facts from judgments.
- Highlight missing or unverified information.
- For ETF/LEVERAGED_ETF, use product/benchmark/NAV/liquidity/structure language rather than company revenue/profit language.
- For LEVERAGED_ETF, treat the CEO's allowed investment universe as NOT CONFIGURED unless policy explicitly resolves whether such products are permitted. Do not silently interpret the generic no-leverage rule in either direction.
- Respect every hard risk limit that is explicitly configured in the investor policy.
- If Risk Agent says REJECT, clearly mark the proposal as BLOCKED.
- Never invent prices, financial figures, portfolio holdings, market conditions, target weights, maximum position sizes, sector caps, cash-reserve percentages, or loss limits.
- Never turn a current portfolio weight, risk score, analyst opinion, performance target, review date, or generic diversification rule into an investor limit.
- If the investor policy says numeric position limits are NOT CONFIGURED, the Suggested position range section must say NOT CONFIGURED — CEO POLICY REQUIRED. Do not output any percentage range there.
- If specialist reports contain a numeric limit that conflicts with an unconfigured policy, treat that numeric limit as invalid and ignore it.
- Never recommend margin borrowing, borrowed-money investing, or options.
- Treat UNAVAILABLE values in the portfolio snapshot as genuinely missing data.
- Never treat LOCKED ASSETS or EXPECTED FUTURE ASSETS as available brokerage buying power.
- Never increase risk, concentration, trading frequency, or urgency merely to hit a performance KPI or because a review date is approaching.
- Holding cash is an acceptable outcome when evidence does not justify deployment.
- AI/token cost is a company expense. Do not propose deeper specialist work unless it could materially improve the decision.
- When deeper specialist work is justified, explain why it is needed and what decision quality it is expected to improve; request CEO approval rather than silently escalating cost.

Return a concise report with these sections:
1. Candidate and instrument type
2. Research conclusion
3. Evidence / product-data quality
4. Bear Case / structural dissent as applicable
5. Portfolio conclusion
6. Risk conclusion
7. Execution conclusion
8. Main upside
9. Main downside
10. Suggested position range
11. Conditions before any purchase
12. Missing information
13. CIO synthesis
14. CEO escalation: NONE / RISK / OPPORTUNITY / ANALYSIS REQUEST / DECISION
15. CEO action required: YES / NO
16. FINAL DECISION: CEO REQUIRED only when a real investment decision is pending

The CIO synthesis may state whether the setup appears favorable, neutral, or unfavorable,
but must never issue or execute a final BUY/SELL order.
""",
)


def _emit_status(
    status_callback: PipelineStatusCallback | None,
    agent_name: str,
    status: str,
) -> None:
    if status_callback is not None:
        status_callback(agent_name, status)


def run_cio_pipeline(
    ticker: str,
    portfolio_snapshot: str | None = None,
    status_callback: PipelineStatusCallback | None = None,
) -> tuple[str, str]:
    """Run the full read-only investment decision-support pipeline."""
    if portfolio_snapshot is None:
        portfolio_snapshot = get_live_portfolio_snapshot()

    operating_policy = get_full_operating_policy()

    _emit_status(status_callback, "Analysis", "WORKING")
    try:
        analysis_report = run_analysis(ticker)
    except Exception:
        _emit_status(status_callback, "Analysis", "ERROR")
        raise
    _emit_status(status_callback, "Analysis", "DONE")

    _emit_status(status_callback, "Portfolio", "WORKING")
    try:
        portfolio_output = run_portfolio_assessment(
            ticker,
            analysis_report,
            portfolio_snapshot,
            RISK_POLICY,
        )
    except Exception:
        _emit_status(status_callback, "Portfolio", "ERROR")
        raise
    portfolio_report = portfolio_output.model_dump_json(indent=2)
    _emit_status(status_callback, "Portfolio", "DONE")

    _emit_status(status_callback, "Risk", "WORKING")
    try:
        risk_output = run_risk_assessment(
            ticker,
            analysis_report,
            portfolio_report,
            RISK_POLICY,
        )
    except Exception:
        _emit_status(status_callback, "Risk", "ERROR")
        raise
    risk_report = risk_output.model_dump_json(indent=2)
    _emit_status(status_callback, "Risk", "DONE")

    _emit_status(status_callback, "Execution", "WORKING")
    try:
        execution_output = run_execution_assessment(
            ticker,
            analysis_report,
            portfolio_report,
            risk_report,
            EXECUTION_CONSTRAINTS,
        )
    except Exception:
        _emit_status(status_callback, "Execution", "ERROR")
        raise
    execution_report = execution_output.model_dump_json(indent=2)
    _emit_status(status_callback, "Execution", "DONE")

    _emit_status(status_callback, "CIO", "WORKING")
    try:
        cio_result = Runner.run_sync(
            cio_agent,
            f"""
CANDIDATE:
{ticker}

LIVE TOSS PORTFOLIO SNAPSHOT:
{portfolio_snapshot}

CEO OPERATING POLICY:
{operating_policy}

INVESTOR RISK POLICY:
{RISK_POLICY}

INSTRUMENT RESEARCH TEAM REPORT:
{analysis_report}

PORTFOLIO AGENT REPORT:
{portfolio_report}

RISK AGENT REPORT:
{risk_report}

EXECUTION AGENT REPORT:
{execution_report}

Prepare the CIO decision brief under the CEO operating policy.
Respect and preserve the instrument route.
Preserve Data Auditor conflicts and Bear Case dissent when present.
Preserve leveraged/inverse product structure and path-dependency warnings when present.
Do not make the final investment decision.
Do not invent numeric investor limits.
Do not increase urgency or risk to chase a performance target.
If numeric position limits are not configured, Suggested position range must be NOT CONFIGURED — CEO POLICY REQUIRED.
Classify whether the CEO actually needs to be interrupted and state the escalation category.
""",
        )
    except Exception:
        _emit_status(status_callback, "CIO", "ERROR")
        raise
    _emit_status(status_callback, "CIO", "DONE")

    return portfolio_snapshot, cio_result.final_output
