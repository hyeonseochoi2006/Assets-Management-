from agents import Agent, Runner, WebSearchTool

from data.instrument_resolver import resolve_instruments
from data.toss_client import get_access_token, get_stocks
from operations.models import (
    InstrumentIdentity,
    OpportunityCandidate,
    OpportunityScoutReport,
    PortfolioSnapshot,
)
from policies.ceo_operating_policy import get_full_operating_policy
from policies.investment_policy import RISK_POLICY


opportunity_scout_agent = Agent(
    name="Opportunity Scout",
    instructions="""
You are the Opportunity Scout for an autonomous personal asset-management company.

Your job is to perform ONE compact routine discovery pass for potentially attractive public-market research candidates.
This is not an exhaustive market screen and not a full investment analysis.

COST DISCIPLINE:
- Return at most 3 candidates.
- Do not deeply analyze dozens of companies.
- Prefer a small number of candidates supported by recent, meaningful evidence.
- Weak ideas should be omitted rather than returned for completeness.

DISCOVERY RULES:
- Look for current developments that may justify further research: improving business fundamentals, meaningful earnings/guidance changes, durable industry tailwinds, important product/business catalysts, or a potentially interesting valuation setup supported by evidence.
- Prefer primary sources such as company investor-relations releases, SEC filings, earnings materials, and official announcements.
- Use reputable secondary sources only when useful for discovery or context.
- Do not return a company already present in CURRENT HOLDINGS.
- Do not invent revenue, profit, valuation, market-share, price-target, expected-return, or catalyst numbers.
- Do not produce a BUY/SELL recommendation.
- Do not claim a candidate is suitable for the portfolio; Portfolio and Risk review happen later.

POLICY RULES:
- The CEO has NOT CONFIGURED the allowed investment market/security universe yet.
- Every result is only a RESEARCH CANDIDATE, never an approved or actionable investment.
- screening_status WATCHLIST means interesting enough to retain internally.
- screening_status CIO_REVIEW is reserved for unusually strong, current, evidence-backed candidates that merit CIO attention.
- If identity, evidence, or timing is uncertain, list it under missing_or_unverified and lower confidence.
- Do not use performance targets or review dates as a reason to lower standards or chase risky ideas.

OUTPUT QUALITY:
- Keep reason and why_now concise.
- Evidence should identify the supporting source or event clearly enough for later verification.
- Include the most important downside risks even at this early stage.
""",
    tools=[WebSearchTool()],
    output_type=OpportunityScoutReport,
)


def _holdings_context(snapshot: PortfolioSnapshot) -> str:
    if not snapshot.positions:
        return "No current stock positions detected."

    lines: list[str] = []
    for position in snapshot.positions:
        instrument = position.instrument
        if instrument is not None and instrument.resolved:
            name = instrument.english_name or instrument.name or "UNAVAILABLE"
            lines.append(f"- {position.symbol}: {name}")
        else:
            lines.append(f"- {position.symbol}: identity unresolved")
    return "\n".join(lines)


def _verify_candidate_identities(
    candidates: list[OpportunityCandidate],
) -> list[OpportunityCandidate]:
    symbols = list(dict.fromkeys(candidate.symbol.strip() for candidate in candidates if candidate.symbol.strip()))
    if not symbols:
        return candidates

    stock_info_error: str | None = None
    stocks_payload: dict[str, object] = {"result": []}
    try:
        access_token = get_access_token()
        stocks_payload = get_stocks(access_token, symbols)
    except Exception as exc:
        stock_info_error = f"{type(exc).__name__}: candidate identity verification unavailable"

    identities = resolve_instruments(
        symbols,
        stocks_payload,
        stock_info_error=stock_info_error,
    )

    verified: list[OpportunityCandidate] = []
    for candidate in candidates:
        identity = identities.get(candidate.symbol)
        if identity is None:
            identity = InstrumentIdentity(
                symbol=candidate.symbol,
                resolved=False,
                resolution_note="NOT RESOLVED BY TOSS STOCK INFO API",
            )
        verified.append(candidate.model_copy(update={"instrument": identity}))
    return verified


def run_opportunity_scout(snapshot: PortfolioSnapshot) -> OpportunityScoutReport:
    held_symbols = {position.symbol.upper() for position in snapshot.positions}

    result = Runner.run_sync(
        opportunity_scout_agent,
        f"""
COMPANY OPERATING POLICY:
{get_full_operating_policy()}

INVESTOR RISK POLICY:
{RISK_POLICY}

CURRENT HOLDINGS:
{_holdings_context(snapshot)}

Run one compact opportunity-discovery pass now.
Return no more than 3 research candidates.
Do not return current holdings.
Do not make a final investment recommendation.
""",
    )
    report = result.final_output

    deduped: list[OpportunityCandidate] = []
    seen: set[str] = set()
    for candidate in report.candidates:
        symbol = candidate.symbol.strip().upper()
        if not symbol or symbol in held_symbols or symbol in seen:
            continue
        seen.add(symbol)
        deduped.append(candidate.model_copy(update={"symbol": symbol}))
        if len(deduped) == 3:
            break

    verified = _verify_candidate_identities(deduped)
    unresolved = [
        candidate.symbol
        for candidate in verified
        if candidate.instrument is None or not candidate.instrument.resolved
    ]

    notes = list(report.notes)
    notes.append(
        "Candidates are research-only because the CEO allowed investment universe is NOT CONFIGURED."
    )
    if unresolved:
        notes.append(
            "Broker identity unresolved for: " + ", ".join(unresolved) + ". Do not treat these as actionable securities."
        )

    data_quality = report.data_quality
    if unresolved and data_quality == "HIGH":
        data_quality = "MEDIUM"

    return report.model_copy(
        update={
            "candidates": verified,
            "data_quality": data_quality,
            "notes": notes,
        }
    )
