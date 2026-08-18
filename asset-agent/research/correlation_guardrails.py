import re


CORRELATION_VERIFIED_MARKER = "CORRELATION_DATA_VERIFIED: TRUE"

_CORRELATION_TERMS = (
    "correlation",
    "correlated",
    "highly correlated",
    "co-move",
    "co-movement",
    "move in tandem",
    "moves in tandem",
    "moving in tandem",
    "move together",
    "moves together",
    "moving together",
    "move in sync",
    "moves in sync",
    "moving in sync",
    "in lockstep",
    "상관성",
    "상관관계",
    "상관계수",
    "역상관",
    "동조화",
    "동조",
    "같이 움직",
    "함께 움직",
    "반대로 움직",
    "같은 방향으로 움직",
    "동일하게 움직",
    "커플링",
)

_GENERIC_UNVERIFIED_CORRELATION = (
    "Quantitative correlation with existing holdings: UNVERIFIED — "
    "no verified correlation dataset was supplied."
)


def correlation_is_verified(*texts: str) -> bool:
    marker_pattern = re.compile(
        r"(?m)^\s*CORRELATION_DATA_VERIFIED:\s*(?:TRUE|YES|VERIFIED)(?:\s*\||\s*$)",
        re.IGNORECASE,
    )
    return any(marker_pattern.search(text) is not None for text in texts if text)


def report_has_verified_correlation_status(text: str) -> bool:
    return bool(
        re.search(
            r"(?m)^\s*CORRELATION_STATUS:\s*VERIFIED(?:\s*\||\s*$)",
            text,
        )
    )


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
