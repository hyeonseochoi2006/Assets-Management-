from agents import Agent, Runner, WebSearchTool

from research.models import (
    ETFAnalysisAssessment,
    InstrumentRouteAssessment,
    LeveragedETFAnalysisAssessment,
    ProductAuditClaim,
    ProductDataAuditReport,
)
from research.source_identity_guardrails import enforce_product_source_identity


_THRESHOLD_TOPIC = "TOTAL_LOSS_NUMERIC_THRESHOLD"


product_data_auditor_agent = Agent(
    name="Product Data Auditor",
    instructions="""
You are the Product Data Auditor for an investment research team.

You independently verify the most decision-critical claims in an ETF or leveraged/inverse ETF/ETP specialist report.
You do NOT make an investment recommendation and you do NOT redo the whole product analysis.

MANDATORY PHASE 1 — SOURCE IDENTITY ANCHOR
Before trusting ANY product-specific number or declaring a data conflict, establish that each source actually belongs to the requested instrument.
Use the routed ticker and official fund/product name as the minimum identity anchors. When available, also use issuer/sponsor, CUSIP, ISIN, SEC series/class identifiers, or an exact official issuer product page.

For every checked_claim and every conflict, set source_identity_status to exactly one of:
- SOURCE_MATCHED: the evidence is demonstrably tied to this exact instrument or, for a benchmark-specific claim, to the exact official benchmark/index.
- SOURCE_MISMATCHED: the evidence belongs to a different security, fund, issuer product, share class, or unrelated entity.
- SOURCE_UNVERIFIED: identity cannot be established reliably.

SOURCE IDENTITY RULES
- A matching ticker alone is not enough when the symbol is ambiguous or reused in another context. Cross-check the official name and issuer/sponsor when possible.
- For fund-specific numbers such as AUM, shares outstanding, NAV, expense ratio, holdings, derivatives exposure, or market price, prefer the exact official issuer product page, prospectus, SEC filing, or another source that clearly identifies the same fund.
- If a source belongs to another instrument, IGNORE its number. Do not use it as one side of a CONFLICT.
- If two numbers differ but one source is SOURCE_MISMATCHED or SOURCE_UNVERIFIED, do NOT call that a valid official-data conflict. The mismatched/unverified value is rejected and the surviving claim remains VERIFIED only if independently supported; otherwise UNVERIFIED.
- Never label a value "official" merely because the webpage looks authoritative. The source must identify the same product.
- Put the identity reasoning in source_identity_note. Include identity-matched source references in sources.

PHASE 2 — PRODUCT DATA AUDIT
Only after source identity is resolved, audit:
- Official product/fund identity
- Fund objective and benchmark/index
- Leverage/inverse target and reset frequency when applicable
- Expense ratio and material fees
- NAV and market price when the specialist supplies them
- AUM when the specialist supplies it
- Shares outstanding when supplied
- Derivatives/swaps/futures structure when material
- Issuer/prospectus holding-period, compounding, path-dependency, and loss warnings
- Any HIGH-impact product-structure claim that could materially change the conclusion

MANDATORY LEVERAGED-ETF TOTAL-LOSS THRESHOLD CHECK
- For EVERY instrument routed as LEVERAGED_ETF, independently check primary issuer/prospectus/SEC materials for whether they explicitly state an exact or approximate numeric underlying-index move tied to total loss, wipeout, complete loss, or loss of the entire investment.
- Perform this check even when the Product Specialist did NOT mention a numeric threshold.
- Always return exactly one dedicated checked_claim for this check with topic EXACTLY: TOTAL_LOSS_NUMERIC_THRESHOLD
- The dedicated threshold claim must also carry source_identity_status. VERIFIED requires SOURCE_MATCHED primary evidence.
- If a reliable primary source explicitly states such a threshold and the relevant condition, set status=VERIFIED, put the primary-source wording/condition in verified_value, and include the primary source in sources.
- Preserve qualifiers such as approximately, intraday, at any point during the day, or similar conditions. Do not convert them into a more precise threshold.
- Do NOT verify an exact threshold merely by multiplying or dividing the leverage target. Never infer 50% from 2x or 33.3% from 3x.
- A generic issuer statement that total loss is possible does NOT verify an exact numeric threshold.
- If primary materials do not explicitly support an exact/approximate numeric threshold, set status=UNVERIFIED, verified_value=null, and explain that only a non-numeric total-loss warning is supported.
- If reliable identity-matched primary materials materially conflict, set status=CONFLICT and explain the conflict.
- Never fabricate the dedicated threshold claim or its source.

SOURCE PRIORITY
1. Exact official issuer product page and prospectus
2. SEC/regulatory filing tied to the exact fund/series/class
3. Official exchange/index-provider materials for benchmark-specific facts
4. Reputable secondary sources only for context, never as a substitute for product identity

RULES
- Never invent missing numbers or product terms.
- Preserve date, period, definition, currency, and share-class context.
- A stale official value is not the same as a current verified value; explain the date.
- Do not call two values a conflict when they use different dates, definitions, currencies, NAV timestamps, or share classes unless the disagreement remains material after reconciliation.
- VERIFIED = identity-matched reliable evidence supports the claim.
- CONFLICT = identity-matched reliable sources materially disagree after definitions/dates are reconciled.
- UNVERIFIED = reliable confirmation is unavailable.
- material_conflict=true only when an identity-matched conflict could materially change product understanding, risk, or suitability analysis.
- Do not make a BUY/SELL decision.
""",
    tools=[WebSearchTool()],
    output_type=ProductDataAuditReport,
)


def _normalize_topic(topic: str) -> str:
    return "_".join(topic.strip().upper().replace("-", " ").split())


def _ensure_threshold_check(
    route: InstrumentRouteAssessment,
    report: ProductDataAuditReport,
) -> ProductDataAuditReport:
    """Fail closed if a leveraged-product audit omits the mandatory threshold check."""
    if route.route != "LEVERAGED_ETF":
        return report

    has_threshold_claim = any(
        _normalize_topic(claim.topic) == _THRESHOLD_TOPIC
        for claim in report.checked_claims
    )
    if has_threshold_claim:
        return report

    fallback_claim = ProductAuditClaim(
        topic=_THRESHOLD_TOPIC,
        reported_value=None,
        status="UNVERIFIED",
        verified_value=None,
        sources=[],
        note=(
            "Mandatory leveraged-ETF numeric total-loss threshold check was not returned by the auditor. "
            "Treat every exact percentage threshold as unverified and use only a non-numeric loss warning."
        ),
        source_identity_status="SOURCE_UNVERIFIED",
        source_identity_note="Mandatory threshold source identity was not returned.",
    )
    notes = list(report.notes)
    notes.append(
        "Guardrail fallback: mandatory TOTAL_LOSS_NUMERIC_THRESHOLD audit claim was missing."
    )
    return report.model_copy(
        update={
            "checked_claims": [*report.checked_claims, fallback_claim],
            "notes": notes,
        }
    )


def run_product_data_audit(
    route: InstrumentRouteAssessment,
    assessment: ETFAnalysisAssessment | LeveragedETFAnalysisAssessment,
) -> ProductDataAuditReport:
    result = Runner.run_sync(
        product_data_auditor_agent,
        f"""
INSTRUMENT ROUTE:
{route.model_dump_json(indent=2)}

PRODUCT SPECIALIST ASSESSMENT:
{assessment.model_dump_json(indent=2)}

First establish the exact product identity for every source used.
Then audit only decision-critical product claims using current official sources where possible.
Reject numbers from a source that does not match this exact instrument; do not turn contaminated data into a conflict.
If the route is LEVERAGED_ETF, independently perform the mandatory TOTAL_LOSS_NUMERIC_THRESHOLD check even if the specialist supplied no threshold.
Do not infer a threshold from the leverage multiple.
Do not redo the entire analysis and do not make a final investment decision.
""",
    )
    output = result.final_output.model_copy(update={"ticker": assessment.ticker.upper()})
    output = _ensure_threshold_check(route, output)
    return enforce_product_source_identity(output)
