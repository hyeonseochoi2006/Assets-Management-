import re
from dataclasses import dataclass
from enum import Enum


class CEOAction(str, Enum):
    ANALYZE_COMPANY = "ANALYZE_COMPANY"
    SHOW_PORTFOLIO = "SHOW_PORTFOLIO"
    REVIEW_PORTFOLIO = "REVIEW_PORTFOLIO"
    HELP = "HELP"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CEOCommand:
    action: CEOAction
    ticker: str | None = None
    original_text: str = ""


COMPANY_ALIASES = {
    "팔란티어": "PLTR",
    "palantir": "PLTR",
    "엔비디아": "NVDA",
    "nvidia": "NVDA",
    "애플": "AAPL",
    "apple": "AAPL",
    "구글": "GOOGL",
    "알파벳": "GOOGL",
    "alphabet": "GOOGL",
    "마이크로소프트": "MSFT",
    "microsoft": "MSFT",
    "테슬라": "TSLA",
    "tesla": "TSLA",
    "팔로알토": "PANW",
    "palo alto": "PANW",
    "크라우드스트라이크": "CRWD",
    "crowdstrike": "CRWD",
}

PORTFOLIO_WORDS = ("포트폴리오", "계좌", "보유종목", "보유 종목", "내 자산", "자산현황", "자산 현황")
REVIEW_WORDS = ("점검", "리뷰", "검토", "위험", "risk", "review")
SHOW_WORDS = ("보여", "현황", "얼마", "목록", "조회", "show")
HELP_WORDS = ("도움", "help", "뭐 할 수", "무엇을 할 수", "사용법")


def _find_alias(text: str) -> str | None:
    lowered = text.lower()
    for alias, ticker in COMPANY_ALIASES.items():
        if alias.lower() in lowered:
            return ticker
    return None


def _find_ticker(text: str) -> str | None:
    # Accept conventional US-style ticker tokens such as PANW, NVDA, PLTR.
    candidates = re.findall(r"(?<![A-Za-z])[A-Za-z]{1,5}(?![A-Za-z])", text)
    ignored = {
        "A", "AN", "AND", "CEO", "CIO", "HELP", "MY", "SHOW", "THE",
        "RISK", "REVIEW", "BUY", "SELL", "STOCK",
    }
    for candidate in candidates:
        ticker = candidate.upper()
        if ticker not in ignored:
            return ticker
    return None


def route_command(text: str) -> CEOCommand:
    cleaned = text.strip()
    lowered = cleaned.lower()

    if not cleaned:
        return CEOCommand(CEOAction.UNKNOWN, original_text=text)

    if any(word in lowered for word in HELP_WORDS):
        return CEOCommand(CEOAction.HELP, original_text=text)

    has_portfolio_word = any(word in lowered for word in PORTFOLIO_WORDS)
    if has_portfolio_word and any(word in lowered for word in REVIEW_WORDS):
        return CEOCommand(CEOAction.REVIEW_PORTFOLIO, original_text=text)

    if has_portfolio_word and (
        any(word in lowered for word in SHOW_WORDS) or len(cleaned) <= 20
    ):
        return CEOCommand(CEOAction.SHOW_PORTFOLIO, original_text=text)

    ticker = _find_alias(cleaned) or _find_ticker(cleaned)
    if ticker:
        return CEOCommand(
            CEOAction.ANALYZE_COMPANY,
            ticker=ticker,
            original_text=text,
        )

    return CEOCommand(CEOAction.UNKNOWN, original_text=text)
