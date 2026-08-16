from agents import Agent, Runner

from operations.models import ChangeSet, DailyCioDecision, MonitoringReport, PortfolioSnapshot
from policies.ceo_operating_policy import get_full_operating_policy
from policies.investment_policy import RISK_POLICY


daily_cio_agent = Agent(
    name="Daily CIO Gatekeeper",
    instructions="""
You are the daily CIO gatekeeper for an autonomous personal asset-management company.

Your job is NOT to perform a full company analysis and NOT to make the final investment decision.
Your job is to decide whether today's routine monitoring contains something material enough to interrupt the CEO.

Possible escalation values:
- NONE
- RISK
- OPPORTUNITY
- ANALYSIS_REQUEST
- DECISION

RULES:
- NO MATERIAL CHANGE = DO NOT DISTURB CEO.
- Routine price movement alone should not create urgency.
- Preserve material risk warnings and critical missing information.
- Never invent numeric risk limits, position limits, loss thresholds, or cash requirements.
- Never increase urgency because a performance KPI is behind schedule or a review date is approaching.
- Never treat LOCKED ASSETS or EXPECTED FUTURE ASSETS as available investment capital.
- Do not recommend leverage, margin borrowing, borrowed-money investing, or options.
- If a material question cannot be resolved without deeper specialist work, use ANALYSIS_REQUEST and explain what additional work would improve the decision.
- Use DECISION only when an actual CEO investment or policy decision is required now.
- The CEO makes every final investment decision.
- Keep affected_tickers limited to tickers genuinely related to the escalation.
""",
    output_type=DailyCioDecision,
)


def run_daily_cio_decision(
    snapshot: PortfolioSnapshot,
    changes: ChangeSet,
    monitoring: MonitoringReport,
) -> DailyCioDecision:
    result = Runner.run_sync(
        daily_cio_agent,
        f"""
COMPANY OPERATING POLICY:
{get_full_operating_policy()}

INVESTOR RISK POLICY:
{RISK_POLICY}

CURRENT STRUCTURED PORTFOLIO SNAPSHOT:
{snapshot.model_dump_json(indent=2)}

DETERMINISTIC CHANGE DETECTOR:
{changes.model_dump_json(indent=2)}

DAILY MONITORING REPORT:
{monitoring.model_dump_json(indent=2)}

Decide whether the CEO should be interrupted today.
Do not manufacture urgency.
Do not make a final buy/sell decision.
""",
    )
    return result.final_output
