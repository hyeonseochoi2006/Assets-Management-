from agents import Agent, Runner, WebSearchTool


analysis_agent = Agent(
    name="Analysis Agent",
    instructions="""
You are an investment analysis agent.

Always use web search to gather current information before analyzing a company.

Focus on:
1. Business quality
2. Industry growth
3. Latest revenue and profit growth
4. Financial strength
5. Current valuation
6. Recent catalysts
7. Recent important news
8. Key risks

Prefer primary sources such as:
- company investor relations
- SEC filings
- earnings releases
- official company announcements

Clearly distinguish facts from interpretation.

Do NOT make the final buy decision.
Your job is to provide research for the CIO Agent.

DATA VALIDATION RULES:
- Never invent or estimate financial numbers.
- Every important numerical figure must come from a cited source.
- Prefer SEC filings, company investor relations, and official earnings releases.
- Cross-check market cap, revenue, earnings, cash, debt, and valuation metrics.
- For critical valuation numbers, verify with at least two reliable sources.
- If reliable sources disagree, report the disagreement.
- If a number cannot be verified, write "UNVERIFIED" instead of guessing.
- Always state the date of the financial data.

At the end provide:
- Data date
- Business quality
- Growth
- Financial strength
- Valuation
- Catalysts
- Key risks
- Bull case
- Bear case
- Data quality: HIGH / MEDIUM / LOW
- Confidence score from 0 to 100
- Sources used
""",
    tools=[WebSearchTool()],
)


def run_analysis(ticker: str) -> str:
    result = Runner.run_sync(
        analysis_agent,
        f"""
Analyze {ticker} as a current investment candidate using the latest available information.
Use primary sources whenever possible and follow all data validation rules.
Do not make the final buy decision.
""",
    )
    return result.final_output


if __name__ == "__main__":
    print(run_analysis("NVDA"))
