from agents import Agent, Runner, WebSearchTool

from operations.models import MonitoringReport


daily_monitoring_agent = Agent(
    name="Daily Monitoring Agent",
    instructions="""
You are the daily monitoring desk for a personal asset-management company.

Your task is narrow: check the supplied current portfolio holdings for NEW, MATERIAL company developments since the prior monitoring timestamp.

Focus on:
- earnings or guidance changes
- SEC or company filings
- management changes
- material regulation or litigation
- major product or business developments
- events that could materially alter an existing investment thesis

Ignore routine market noise, ordinary commentary, small price moves by themselves, and low-value repetition.
Prefer primary sources such as SEC filings, company investor-relations pages, earnings releases, and official announcements.

RULES:
- Do not make a buy or sell decision.
- Do not invent financial numbers, dates, events, or sources.
- If evidence is incomplete, identify it as missing or unverified.
- A price move alone is not proof of a thesis change.
- Keep the result compact because this is a routine daily task.
- HIGH or CRITICAL importance must be reserved for genuinely material developments.
- If nothing material is found, return an empty findings list.
""",
    tools=[WebSearchTool()],
    output_type=MonitoringReport,
)


def run_daily_monitoring(
    symbols: list[str],
    previous_captured_at: str | None,
) -> MonitoringReport:
    if not symbols:
        return MonitoringReport(
            findings=[],
            data_quality="HIGH",
            notes=["No stock positions detected; no company monitoring was required."],
        )

    prior_context = previous_captured_at or "No prior snapshot; use the latest relevant developments only."
    result = Runner.run_sync(
        daily_monitoring_agent,
        f"""
CURRENT HOLDINGS:
{', '.join(symbols)}

PRIOR PORTFOLIO SNAPSHOT TIME:
{prior_context}

Check only for new material developments relevant to these existing holdings.
Do not perform a full investment analysis of every company.
Do not make a buy/sell decision.
""",
    )
    return result.final_output
