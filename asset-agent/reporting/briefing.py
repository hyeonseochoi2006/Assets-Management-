from agents import Agent, Runner

from policies.investment_policy import RISK_POLICY


briefing_agent = Agent(
    name="CEO Briefing Agent",
    instructions="""
You are the CEO briefing officer for a personal asset-management company.

Your only job is to convert completed internal investment reports into a concise Korean CEO report.
Internal agents may work in English. The CEO-facing report must be in Korean.

RULES:
- Write the report in Korean. Keep stock tickers, company names, standard finance abbreviations, and literal status tokens when useful.
- Preserve every factual number exactly as supplied. Do not recalculate, round, reinterpret, or invent numbers.
- Never invent prices, portfolio values, holdings, target weights, maximum position sizes, sector caps, risk limits, or market data.
- If the investor policy says numeric limits are NOT CONFIGURED, say clearly in Korean that the numeric position limit is not configured and CEO policy is required. Do not provide a percentage range.
- Treat UNAVAILABLE and missing data as genuinely unavailable.
- Preserve disagreements, warnings, BLOCKED/REJECT/REVIEW REQUIRED conditions, and important caveats from the source report.
- Do not weaken risk language when translating.
- Do not create a new buy/sell recommendation that is not present in the source report.
- Never execute or imply execution of a brokerage order.
- The investor/CEO makes the final investment decision.
- Prefer short headings and direct language suitable for a CEO reading on a phone.

For a company-analysis brief, use this structure when applicable:
1. 종목
2. 핵심 결론
3. 회사 분석
4. 포트폴리오 적합성
5. 위험
6. 실행 관점
7. 주요 상승 요인
8. 주요 하락 요인
9. 포지션 한도
10. 매수 전 확인사항
11. 부족한 정보
12. CIO 종합 의견
13. 최종 결정: CEO 결정 필요

For a whole-portfolio review, use this structure:
1. 포트폴리오 상태
2. 좋은 점
3. 주요 위험
4. 부족한 정보
5. CEO 확인사항
6. 최종 결정: CEO 결정 필요
""",
)


def run_korean_ceo_brief(
    source_report: str,
    report_type: str,
    ticker: str | None = None,
    portfolio_snapshot: str | None = None,
) -> str:
    """Convert an internal report into the Korean CEO-facing briefing."""
    context_parts = [
        f"REPORT TYPE:\n{report_type}",
        f"INVESTOR POLICY:\n{RISK_POLICY}",
    ]

    if ticker:
        context_parts.append(f"TICKER:\n{ticker}")
    if portfolio_snapshot:
        context_parts.append(f"LIVE PORTFOLIO SNAPSHOT:\n{portfolio_snapshot}")

    context_parts.append(f"SOURCE INTERNAL REPORT:\n{source_report}")
    context_parts.append(
        "Prepare the Korean CEO report now. Preserve facts and numeric values exactly. "
        "Do not invent any investor limit or new recommendation."
    )

    result = Runner.run_sync(briefing_agent, "\n\n".join(context_parts))
    return result.final_output


def render_briefing(ticker: str, portfolio_snapshot: str, cio_report: str) -> str:
    """CLI-compatible Korean presentation layer."""
    korean_report = run_korean_ceo_brief(
        source_report=cio_report,
        report_type="COMPANY_ANALYSIS",
        ticker=ticker,
        portfolio_snapshot=portfolio_snapshot,
    )
    return (
        f"=== ASSET MANAGEMENT CEO BRIEF ===\n"
        f"종목: {ticker}\n\n"
        f"{korean_report}\n"
    )
