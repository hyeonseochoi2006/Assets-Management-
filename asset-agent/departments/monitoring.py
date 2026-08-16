from agents import Agent, Runner, WebSearchTool

from operations.models import MonitoringReport, PositionSnapshot


daily_monitoring_agent = Agent(
    name="Daily Monitoring Agent",
    instructions="""
You are the daily monitoring desk for a personal asset-management company.

Your task is narrow: check the supplied current portfolio holdings for NEW, MATERIAL developments since the prior monitoring timestamp.

INSTRUMENT IDENTITY RULES:
- The supplied Toss Securities stock-master metadata is the source of truth for instrument identity in this workflow.
- Never identify a company, ETF, or security from a ticker string alone.
- For a RESOLVED instrument, use the official name, English name, ISIN, market, security type, and broker symbol together to disambiguate web research.
- Never substitute a different security merely because it has the same or a similar ticker.
- If security_type is not STOCK, monitor the identified security as that instrument type; do not silently reinterpret it as an operating company.
- For an UNRESOLVED instrument, do not guess its issuer or underlying exposure. Do not perform ticker-only company research as if identity were confirmed.
- If identity is unresolved, you may record a DATA_QUALITY finding, but identity ambiguity alone is not verified investment loss risk and must not be described as a thesis-changing corporate event.

Focus on:
- earnings or guidance changes
- SEC or company filings
- management changes
- material regulation or litigation
- major product or business developments
- listing/security-status changes
- events that could materially alter an existing investment thesis

Ignore routine market noise, ordinary commentary, small price moves by themselves, and low-value repetition.
Prefer primary sources such as SEC filings, company investor-relations pages, earnings releases, and official announcements.

RULES:
- Do not make a buy or sell decision.
- Do not invent financial numbers, dates, events, sources, or instrument identity.
- If evidence is incomplete, identify it as missing or unverified.
- A price move alone is not proof of a thesis change.
- Keep the result compact because this is a routine daily task.
- HIGH or CRITICAL importance must be reserved for genuinely material, verified developments.
- If nothing material is found, return an empty findings list.
""",
    tools=[WebSearchTool()],
    output_type=MonitoringReport,
)


def _position_context(position: PositionSnapshot) -> str:
    instrument = position.instrument
    if instrument is None or not instrument.resolved:
        note = (
            instrument.resolution_note
            if instrument is not None and instrument.resolution_note
            else "No confirmed Toss stock-master identity."
        )
        return (
            f"- BROKER SYMBOL: {position.symbol}\n"
            "  IDENTITY STATUS: UNRESOLVED\n"
            f"  NOTE: {note}"
        )

    return (
        f"- BROKER SYMBOL: {position.symbol}\n"
        "  IDENTITY STATUS: RESOLVED\n"
        f"  OFFICIAL NAME: {instrument.name or 'UNAVAILABLE'}\n"
        f"  ENGLISH NAME: {instrument.english_name or 'UNAVAILABLE'}\n"
        f"  ISIN: {instrument.isin_code or 'UNAVAILABLE'}\n"
        f"  MARKET: {instrument.market or 'UNAVAILABLE'}\n"
        f"  SECURITY TYPE: {instrument.security_type or 'UNAVAILABLE'}\n"
        f"  LISTING STATUS: {instrument.status or 'UNAVAILABLE'}\n"
        f"  CURRENCY: {instrument.currency or position.currency or 'UNAVAILABLE'}"
    )


def run_daily_monitoring(
    positions: list[PositionSnapshot],
    previous_captured_at: str | None,
) -> MonitoringReport:
    if not positions:
        return MonitoringReport(
            findings=[],
            data_quality="HIGH",
            notes=["No stock positions detected; no company monitoring was required."],
        )

    prior_context = previous_captured_at or "No prior snapshot; use the latest relevant developments only."
    identity_context = "\n".join(_position_context(position) for position in positions)

    result = Runner.run_sync(
        daily_monitoring_agent,
        f"""
CURRENT HOLDINGS WITH OFFICIAL IDENTITY METADATA:
{identity_context}

PRIOR PORTFOLIO SNAPSHOT TIME:
{prior_context}

Check only for new material developments relevant to these exact instruments.
Do not perform a full investment analysis of every company.
Do not make a buy/sell decision.
Do not infer issuer identity from ticker alone.
""",
    )
    return result.final_output
