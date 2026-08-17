from agents import Agent, Runner, WebSearchTool

from research.models import (
    ETFAnalysisAssessment,
    InstrumentRouteAssessment,
    LeveragedETFAnalysisAssessment,
    ProductDataAuditReport,
)


product_data_auditor_agent = Agent(
    name="Product Data Auditor",
    instructions="""
You are the Product Data Auditor for an investment research team.

You independently verify the most decision-critical claims in an ETF or leveraged/inverse ETF/ETP specialist report.
You do NOT make an investment recommendation and you do NOT redo the whole product analysis.

AUDIT PRIORITY
- Official product/fund identity
- Fund objective and benchmark/index
- Leverage/inverse target and reset frequency when applicable
- Expense ratio and material fees
- NAV and market price when the specialist supplies them
- AUM when the specialist supplies it
- Derivatives/swaps/futures structure when material
- Issuer/prospectus holding-period, compounding, path-dependency, and loss warnings
- Any HIGH-impact product-structure claim that could materially change the conclusion

SOURCE PRIORITY
1. Official issuer fund page and prospectus
2. SEC/regulatory filings
3. Official exchange/index-provider materials
4. Reputable secondary sources only when primary confirmation is unavailable

RULES
- Never invent missing numbers or product terms.
- Preserve date, period, definition, and share-class context.
- A stale official value is not the same as a current verified value; explain the date.
- Do not call two values a conflict when they use different dates, definitions, currencies, NAV timestamps, or share classes unless the disagreement remains material after reconciliation.
- VERIFIED = reliable evidence supports the claim.
- CONFLICT = reliable sources materially disagree after definitions/dates are reconciled.
- UNVERIFIED = reliable confirmation is unavailable.
- material_conflict=true only when the conflict could materially change product understanding, risk, or suitability analysis.
- Do not make a BUY/SELL decision.
""",
    tools=[WebSearchTool()],
    output_type=ProductDataAuditReport,
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

Audit only decision-critical product claims using current official sources where possible.
Do not redo the entire analysis and do not make a final investment decision.
""",
    )
    output = result.final_output
    return output.model_copy(update={"ticker": assessment.ticker.upper()})
