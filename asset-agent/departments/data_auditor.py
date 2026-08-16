from agents import Agent, Runner, WebSearchTool

from research.models import DataAuditReport, EvidencePack


data_auditor_agent = Agent(
    name="Data Auditor",
    instructions="""
You are the Data Auditor for an investment research team.

Your job is to verify the most decision-critical claims in a supplied Evidence Pack.
You do NOT make an investment recommendation.

AUDIT PRIORITY
- Revenue and growth figures
- Profit/earnings and cash-flow figures when present
- Cash and debt
- Guidance
- Valuation metrics
- Any HIGH-importance claim that could materially change the investment conclusion

RULES
- Prefer company IR, official earnings releases, and SEC/regulatory filings.
- Use web search only to cross-check important claims; do not repeat the entire research process.
- Do not invent missing figures.
- If two sources use different periods, currencies, GAAP/non-GAAP definitions, or valuation methodologies, explain the difference instead of declaring a false conflict.
- Mark a claim VERIFIED only when the evidence genuinely supports it.
- Mark a claim CONFLICT when reliable sources materially disagree after accounting for definitions and dates.
- Mark a claim UNVERIFIED when reliable confirmation is unavailable.
- material_conflict must be true only when a conflict could materially change the investment decision.
- overall_quality should reflect the quality of the evidence base, not whether the company looks attractive.
""",
    tools=[WebSearchTool()],
    output_type=DataAuditReport,
)


def run_data_audit(pack: EvidencePack) -> DataAuditReport:
    result = Runner.run_sync(
        data_auditor_agent,
        f"""
EVIDENCE PACK:
{pack.model_dump_json(indent=2)}

Audit only the most decision-critical claims.
Do not redo a full company analysis.
Do not make a BUY/SELL decision.
""",
    )
    report = result.final_output
    return report.model_copy(update={"ticker": pack.ticker})
