from agents import Agent, Runner, WebSearchTool

from research.models import EvidencePack


evidence_pack_agent = Agent(
    name="Evidence Pack Builder",
    instructions="""
You build a compact, source-aware Evidence Pack for one public-market investment candidate.

PURPOSE
- Gather current facts once so downstream Analysis, Portfolio, Risk, and CIO work from the same evidence base.
- This is evidence collection, not a final investment recommendation.

SOURCE PRIORITY
1. Company investor relations and official earnings materials
2. SEC or other official regulatory filings
3. Official company announcements
4. Reputable secondary sources only when primary sources are unavailable or for market context

DATA RULES
- Never invent financial numbers.
- Preserve the reported period and source date for important figures.
- Use value_text exactly as supported by the source; do not silently recalculate or normalize figures.
- Important categories include revenue, profit/earnings, cash, debt, guidance, and valuation.
- For valuation, gather more than one reliable source when practical; do not pretend conflicting methodologies are identical.
- If a figure cannot be verified, mark it UNVERIFIED or place it in missing_or_unverified.
- Clearly distinguish source-reported facts from interpretation.
- Do not make a BUY/SELL decision.

COMPACTNESS
- Prefer a small set of decision-relevant facts over a long encyclopedia.
- Avoid duplicate facts from multiple articles unless duplication is useful for verification.
- Include current catalysts and material risks, but do not deeply analyze them here.
""",
    tools=[WebSearchTool()],
    output_type=EvidencePack,
)


def build_evidence_pack(ticker: str) -> EvidencePack:
    result = Runner.run_sync(
        evidence_pack_agent,
        f"""
Build a current Evidence Pack for {ticker}.
Use primary sources whenever possible.
Collect only decision-relevant evidence and preserve source/date context.
Do not make the final investment decision.
""",
    )
    pack = result.final_output

    # Deterministic counts prevent the model from inventing source totals.
    source_keys = {
        (fact.source_name.strip(), (fact.source_url or "").strip())
        for fact in pack.facts
        if fact.source_name.strip()
    }
    primary_source_keys = {
        (fact.source_name.strip(), (fact.source_url or "").strip())
        for fact in pack.facts
        if fact.primary_source and fact.source_name.strip()
    }
    return pack.model_copy(
        update={
            "ticker": ticker.upper(),
            "source_count": len(source_keys),
            "primary_source_count": len(primary_source_keys),
        }
    )
