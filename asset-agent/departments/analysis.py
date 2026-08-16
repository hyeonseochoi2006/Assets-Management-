from agents import Agent, Runner

from departments.bear_case import run_bear_case
from departments.data_auditor import run_data_audit
from research.evidence_pack import build_evidence_pack
from research.models import AnalysisLeadAssessment, DataAuditReport, EvidencePack


analysis_lead_agent = Agent(
    name="Analysis Lead",
    instructions="""
You are the Analysis Lead for an investment research team.

You receive a shared Evidence Pack and an independent Data Audit.
Your job is to interpret the evidence, not to search the web again and not to make the final investment decision.

ANALYSIS RESPONSIBILITIES
- Business quality and competitive position
- Industry/growth context
- Financial strength
- Current valuation based only on supplied evidence
- Catalysts
- Key risks
- Bull case
- Initial bear-case hypothesis
- Missing information and confidence

EVIDENCE DISCIPLINE
- Treat the Evidence Pack as the common factual base.
- Treat Data Auditor conflicts and unverified claims as real uncertainty.
- Never repair a missing number by estimating it.
- Do not silently choose one side of a material data conflict.
- If valuation evidence is insufficient or conflicting, say INSUFFICIENT / UNVERIFIED rather than inventing a conclusion.
- Distinguish company quality from stock attractiveness at the current valuation.
- confidence_score measures confidence in the assessment, not expected return.

BEAR CASE ROUTING
Set bear_case_required=true when an independent adversarial review could materially improve the decision, especially when:
- the setup appears FAVORABLE,
- important assumptions are fragile,
- valuation expectations are demanding,
- the audit contains material conflict,
- or the thesis depends heavily on a small number of catalysts.
Do not request Bear Case merely as ritual for clearly weak/insufficient candidates unless it would add decision value.

OVERALL VIEW
- FAVORABLE: evidence merits serious continued investment review; this is NOT a BUY decision.
- NEUTRAL: mixed evidence or risk/reward not clearly compelling.
- UNFAVORABLE: evidence argues against further priority research at present.
- INSUFFICIENT_DATA: evidence quality is too weak for a reliable conclusion.

Do not make a BUY/SELL decision.
""",
    output_type=AnalysisLeadAssessment,
)


def _run_analysis_lead(
    ticker: str,
    evidence_pack: EvidencePack,
    audit: DataAuditReport,
) -> AnalysisLeadAssessment:
    result = Runner.run_sync(
        analysis_lead_agent,
        f"""
CANDIDATE:
{ticker}

SHARED EVIDENCE PACK:
{evidence_pack.model_dump_json(indent=2)}

DATA AUDITOR REPORT:
{audit.model_dump_json(indent=2)}

Produce the Analysis Lead assessment.
Do not search for new facts.
Do not make the final investment decision.
""",
    )
    output = result.final_output
    return output.model_copy(update={"ticker": ticker.upper()})


def run_analysis(ticker: str) -> str:
    """Run Agent Intelligence v2 Phase A while preserving the legacy string interface."""
    normalized_ticker = ticker.strip().upper()
    evidence_pack = build_evidence_pack(normalized_ticker)

    try:
        audit = run_data_audit(evidence_pack)
    except Exception as exc:
        audit = DataAuditReport(
            ticker=normalized_ticker,
            overall_quality="LOW",
            material_conflict=False,
            checked_claims=[],
            conflicts=[],
            unverified_claims=["Data Auditor unavailable for this run."],
            notes=[f"Data Auditor error type: {type(exc).__name__}"],
        )

    lead = _run_analysis_lead(normalized_ticker, evidence_pack, audit)

    should_run_bear_case = (
        lead.bear_case_required
        or audit.material_conflict
        or lead.overall_view == "FAVORABLE"
    )

    bear_case_json = "NOT CALLED — Analysis Lead determined no material decision value."
    if should_run_bear_case:
        try:
            bear_case = run_bear_case(evidence_pack, audit, lead)
            bear_case_json = bear_case.model_dump_json(indent=2)
        except Exception as exc:
            bear_case_json = (
                "UNAVAILABLE — Bear Case Specialist failed independently. "
                f"Error type: {type(exc).__name__}. Do not treat the missing challenge as positive evidence."
            )

    return "\n\n".join(
        [
            "=== AGENT INTELLIGENCE v2 · PHASE A ===",
            "CANDIDATE:\n" + normalized_ticker,
            "SHARED EVIDENCE PACK:\n" + evidence_pack.model_dump_json(indent=2),
            "DATA AUDITOR:\n" + audit.model_dump_json(indent=2),
            "ANALYSIS LEAD:\n" + lead.model_dump_json(indent=2),
            "BEAR CASE SPECIALIST:\n" + bear_case_json,
            (
                "PROCESS NOTE:\n"
                "Evidence was gathered once and shared across the research team. "
                "The Bear Case Specialist is conditional. This report is research for Portfolio, Risk, and CIO; "
                "it is not a final BUY/SELL decision."
            ),
        ]
    )
