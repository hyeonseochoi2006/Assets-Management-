import sys

from executive.cio import run_cio_pipeline
from reporting.briefing import render_briefing


def get_candidate_ticker() -> str:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip().upper()
    return "NVDA"


def main() -> None:
    ticker = get_candidate_ticker()
    portfolio_snapshot, cio_report = run_cio_pipeline(ticker)
    print(render_briefing(ticker, portfolio_snapshot, cio_report))


if __name__ == "__main__":
    main()
