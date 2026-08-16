from agents import Agent, Runner, WebSearchTool

from research.models import (
    AnalysisLeadAssessment,
    BearCaseAssessment,
    DataAuditReport,
    EvidencePack,
)


bear_case_agent = Agent(
    name="Bear Case Specialist",
    instructions="""
You are the independent Bear Case Specialist for an investment committee.

Your role is adversarial but evidence-based: challenge the bullish interpretation and search for reasons the thesis could fail.
You are NOT required to be negative. If the bear case is weak, say so.

FOCUS
- Thesis-breaking business deterioration
- Competitive pressure or loss of moat
- Accounting, cash-flow, balance-sheet, or dilution concerns
- Regulatory/legal risk
- Management credibility or capital-allocation problems
- Valuation risk and expectation risk
- Customer/product concentration where relevant
- Evidence that contradicts the Analysis Lead's favorable claims

RULES
- Prefer primary sources and official filings.
- Never invent facts or numeric downside targets.
- Do not manufacture a bear case merely to disagree.
- Separate verified disconfirming evidence from hypothetical downside scenarios.
- Do not make the final BUY/SELL decision.
- Keep the output focused on issues that could materially affect the investment thesis.
""",
    tools=[WebSearchTool()],
    output_type=BearCaseAssessment,
)


def run_bear_case(
    pack: EvidencePack,
    audit: DataAuditReport,
    lead: AnalysisLeadAssessment,
) -> BearCaseAssessment:
    result = Runner.run_sync(
        bear_case_agent,
        f"""
EVIDENCE PACK:
{pack.model_dump_json(indent=2)}

DATA AUDIT:
{audit.model_dump_json(indent=2)}

ANALYSIS LEAD ASSESSMENT:
{lead.model_dump_json(indent=2)}

Challenge the thesis using current evidence.
Do not make a final investment decision.
""",
    )
    output = result.final_output
    return output.model_copy(update={"ticker": pack.ticker})
