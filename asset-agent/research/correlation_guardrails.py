CORRELATION_VERIFIED_MARKER = "CORRELATION_DATA_VERIFIED:"

_CORRELATION_TERMS = (
    "correlation",
    "correlated",
    "highly correlated",
    "상관성",
    "상관관계",
)

_GENERIC_UNVERIFIED_CORRELATION = (
    "Quantitative correlation with existing holdings: UNVERIFIED — "
    "no verified correlation dataset was supplied."
)


def correlation_is_verified(*texts: str) -> bool:
    return any(CORRELATION_VERIFIED_MARKER in text for text in texts if text)


def contains_correlation_language(text: str) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in _CORRELATION_TERMS)


def sanitize_unverified_correlation_text(text: str, verified: bool) -> str:
    """Remove unsupported quantitative-correlation assertions.

    Sector/industry/holdings overlap is not the same as measured correlation and
    should be discussed separately when supported by evidence.
    """
    if verified or not contains_correlation_language(text):
        return text

    output: list[str] = []
    replacement_added = False
    for line in text.splitlines():
        if contains_correlation_language(line):
            if not replacement_added:
                prefix = "- " if line.lstrip().startswith("-") else ""
                output.append(prefix + _GENERIC_UNVERIFIED_CORRELATION)
                replacement_added = True
            continue
        output.append(line)
    return "\n".join(output)


def unverified_correlation_message() -> str:
    return _GENERIC_UNVERIFIED_CORRELATION
