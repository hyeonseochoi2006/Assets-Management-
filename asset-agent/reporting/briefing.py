def render_briefing(ticker: str, portfolio_snapshot: str, cio_report: str) -> str:
    """Presentation layer for the investor-facing output."""
    return (
        f"=== ASSET MANAGEMENT BRIEF ===\n"
        f"Candidate: {ticker}\n\n"
        f"=== LIVE PORTFOLIO ===\n"
        f"{portfolio_snapshot}\n\n"
        f"=== CIO REPORT ===\n"
        f"{cio_report}\n"
    )
