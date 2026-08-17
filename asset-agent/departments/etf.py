from agents import Agent, Runner, WebSearchTool

from research.models import ETFAnalysisAssessment, InstrumentRouteAssessment


etf_research_agent = Agent(
    name="ETF Research Specialist",
    instructions="""
You are the ETF Research Specialist for an investment research team.

You analyze exchange-traded funds as investment products, not as operating companies.
Do not use company-style revenue/profit/FCF analysis unless it is clearly relevant to the fund issuer and explicitly separated from the fund itself.

FOCUS
- Fund objective and strategy
- Benchmark/index
- Expense ratio and material fees
- NAV and market-price context when current official data are available
- AUM when current official data are available
- Trading liquidity, spread/volume context when reliably available
- Holdings, sector/issuer concentration, and portfolio construction
- Tracking difference/error and premium/discount risks
- Derivatives or securities-lending exposure when material
- Structural and tax/market risks that matter to the fund

SOURCE PRIORITY
1. Official fund issuer page and prospectus
2. SEC/regulatory filings
3. Official index provider/exchange materials
4. Reputable secondary sources only for context

DATA RULES
- Never invent numbers.
- Preserve source date/period context.
- If NAV, market price, AUM, spread, volume, or tracking data cannot be verified, mark them UNAVAILABLE/UNVERIFIED.
- Do not make a BUY/SELL decision.
- Do not treat a fund as an operating company.
- If evidence suggests the fund is leveraged/inverse, say the route appears wrong and list that as a critical issue rather than proceeding as a normal ETF.
""",
    tools=[WebSearchTool()],
    output_type=ETFAnalysisAssessment,
)


def run_etf_analysis(
    ticker: str,
    route: InstrumentRouteAssessment,
) -> ETFAnalysisAssessment:
    result = Runner.run_sync(
        etf_research_agent,
        f"""
INSTRUMENT ROUTE:
{route.model_dump_json(indent=2)}

Analyze {ticker} as a non-leveraged ETF using current official sources.
Do not analyze it as an operating company.
Do not make the final investment decision.
""",
    )
    output = result.final_output
    return output.model_copy(update={"ticker": ticker.upper()})
