from typing import Any

from operations.models import InstrumentIdentity


_SOURCE = "Toss Securities Stock Info API"


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _stock_info_map(stocks_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = stocks_payload.get("result", [])
    if not isinstance(result, list):
        return {}

    resolved: dict[str, dict[str, Any]] = {}
    for item in result:
        if not isinstance(item, dict):
            continue
        symbol = _clean_text(item.get("symbol"))
        if symbol:
            resolved[symbol] = item
    return resolved


def resolve_instruments(
    symbols: list[str],
    stocks_payload: dict[str, Any],
    stock_info_error: str | None = None,
) -> dict[str, InstrumentIdentity]:
    """Resolve broker symbols using Toss stock-master metadata only.

    No ticker-to-company guesswork is allowed. If Toss does not return a matching
    stock-master record, the symbol remains unresolved rather than being mapped
    to a similarly named public security.
    """
    stock_map = _stock_info_map(stocks_payload)
    identities: dict[str, InstrumentIdentity] = {}

    for raw_symbol in symbols:
        symbol = str(raw_symbol).strip()
        record = stock_map.get(symbol)

        if record is None:
            note = "NOT RESOLVED BY TOSS STOCK INFO API"
            if stock_info_error:
                note = f"{note}: {stock_info_error}"
            identities[symbol] = InstrumentIdentity(
                symbol=symbol,
                resolved=False,
                source=_SOURCE,
                resolution_note=note,
            )
            continue

        currency = _clean_text(record.get("currency"))
        identities[symbol] = InstrumentIdentity(
            symbol=symbol,
            name=_clean_text(record.get("name")),
            english_name=_clean_text(record.get("englishName")),
            isin_code=_clean_text(record.get("isinCode")),
            market=_clean_text(record.get("market")),
            security_type=_clean_text(record.get("securityType")),
            status=_clean_text(record.get("status")),
            currency=currency.upper() if currency else None,
            resolved=True,
            source=_SOURCE,
            resolution_note="EXACT SYMBOL MATCH FROM TOSS STOCK MASTER",
        )

    return identities
