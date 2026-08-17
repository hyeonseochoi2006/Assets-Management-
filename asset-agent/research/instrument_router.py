import re
from typing import Any

from agents import Agent, Runner, WebSearchTool

from data.toss_client import get_access_token, get_stocks
from research.models import InstrumentRouteAssessment


_LEVERAGED_PATTERN = re.compile(
    r"(?:\b[+-]?[123]X\b|\bULTRA\b|\bULTRAPRO\b|\bLEVERAGED\b|\bDAILY\b.*\b(?:BULL|BEAR|LONG|SHORT)\b)",
    re.IGNORECASE,
)

_FUND_HINT_PATTERN = re.compile(
    r"\b(?:DIREXION|PROSHARES|ISHARES|SPDR|VANGUARD|GLOBAL X|WISDOMTREE|ARK ETF|ETF|EXCHANGE TRADED FUND)\b",
    re.IGNORECASE,
)


instrument_router_agent = Agent(
    name="Instrument Router",
    instructions="""
You classify one exchange-traded investment instrument before the research team analyzes it.

Allowed routes:
- STOCK: operating-company common/equity stock.
- ETF: non-leveraged exchange-traded fund.
- LEVERAGED_ETF: leveraged or inverse ETF/ETP with a stated daily or periodic multiple/inverse target, including products using derivatives to pursue that target.
- UNKNOWN: identity or structure cannot be verified reliably.

SOURCE RULES
- Prefer the official issuer/fund page, prospectus, SEC/regulatory filings, and exchange materials.
- Broker metadata is useful context but do not force a classification when it conflicts with official product documentation.
- Never infer an instrument is an operating company merely because it trades under a stock-like ticker.
- Never infer a leveraged product from price volatility alone.
- For leveraged/inverse products, preserve the exact stated target and reset period when verified.
- Do not make an investment recommendation.

Return UNKNOWN when the identity cannot be verified safely.
""",
    tools=[WebSearchTool()],
    output_type=InstrumentRouteAssessment,
)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _broker_record(ticker: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        token = get_access_token()
        payload = get_stocks(token, [ticker])
    except Exception as exc:
        return None, f"{type(exc).__name__}: Toss stock metadata unavailable"

    result = payload.get("result", [])
    if not isinstance(result, list):
        return None, "Unexpected Toss stock metadata format"

    for item in result:
        if not isinstance(item, dict):
            continue
        symbol = _clean(item.get("symbol"))
        if symbol and symbol.upper() == ticker.upper():
            return item, None
    return None, "Ticker not returned by Toss stock metadata"


def _deterministic_route(
    ticker: str,
    record: dict[str, Any] | None,
) -> InstrumentRouteAssessment | None:
    if record is None:
        return None

    name = _clean(record.get("englishName")) or _clean(record.get("name"))
    security_type = _clean(record.get("securityType"))
    combined = " ".join(part for part in (name, security_type) if part)
    upper_type = (security_type or "").upper()

    # Product structure wins over a stock-like broker label. This catches clear
    # names such as "Daily ... Bull 3X Shares" without treating them as companies.
    if _LEVERAGED_PATTERN.search(combined):
        return InstrumentRouteAssessment(
            ticker=ticker,
            route="LEVERAGED_ETF",
            official_name=name,
            broker_security_type=security_type,
            classification_source="Toss broker metadata + deterministic leveraged-product name rule",
            confidence="HIGH",
            reasons=[
                "Exact Toss symbol metadata was available.",
                "Official/broker product name contains an explicit leveraged, inverse, or daily-multiple marker.",
            ],
        )

    if "ETF" in upper_type or "EXCHANGE TRADED FUND" in combined.upper():
        return InstrumentRouteAssessment(
            ticker=ticker,
            route="ETF",
            official_name=name,
            broker_security_type=security_type,
            classification_source="Toss broker metadata",
            confidence="HIGH",
            reasons=["Exact Toss symbol metadata classifies the instrument as an ETF."],
        )

    # Some broker taxonomies can use stock-like labels for exchange-traded
    # products. Known fund-name hints force official-source verification first.
    if _FUND_HINT_PATTERN.search(name or ""):
        return None

    if upper_type == "STOCK" or "COMMON STOCK" in upper_type or "EQUITY" in upper_type:
        return InstrumentRouteAssessment(
            ticker=ticker,
            route="STOCK",
            official_name=name,
            broker_security_type=security_type,
            classification_source="Toss broker metadata",
            confidence="HIGH",
            reasons=["Exact Toss symbol metadata classifies the instrument as stock/equity."],
        )

    return None


def classify_instrument(ticker: str) -> InstrumentRouteAssessment:
    normalized = ticker.strip().upper()
    record, broker_error = _broker_record(normalized)

    deterministic = _deterministic_route(normalized, record)
    if deterministic is not None:
        return deterministic

    broker_context = {
        "symbol": _clean(record.get("symbol")) if record else None,
        "name": _clean(record.get("name")) if record else None,
        "englishName": _clean(record.get("englishName")) if record else None,
        "securityType": _clean(record.get("securityType")) if record else None,
        "market": _clean(record.get("market")) if record else None,
        "broker_error": broker_error,
    }

    result = Runner.run_sync(
        instrument_router_agent,
        f"""
TICKER:
{normalized}

BROKER METADATA CONTEXT:
{broker_context}

Verify the instrument identity and structure using official current sources.
Classify it as STOCK, ETF, LEVERAGED_ETF, or UNKNOWN.
Do not make an investment recommendation.
""",
    )
    output = result.final_output

    missing = list(output.missing_or_unverified)
    if broker_error:
        missing.append(broker_error)

    broker_name = broker_context.get("englishName") or broker_context.get("name")
    return output.model_copy(
        update={
            "ticker": normalized,
            "official_name": output.official_name or broker_name,
            "broker_security_type": output.broker_security_type
            or broker_context.get("securityType"),
            "missing_or_unverified": list(dict.fromkeys(missing)),
        }
    )
