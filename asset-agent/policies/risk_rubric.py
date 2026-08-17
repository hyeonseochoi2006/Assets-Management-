from typing import Literal


RiskLevel = Literal["LOW", "MODERATE", "HIGH", "CRITICAL"]


_RISK_ORDER: dict[str, int] = {
    "LOW": 0,
    "MODERATE": 1,
    "HIGH": 2,
    "CRITICAL": 3,
}


def normalize_risk_level(value: str) -> RiskLevel:
    normalized = str(value).strip().upper()
    if normalized not in _RISK_ORDER:
        return "MODERATE"
    return normalized  # type: ignore[return-value]


def aggregate_risk_level(levels: list[str]) -> RiskLevel:
    """Deterministically aggregate component ratings using the highest severity.

    This is intentionally simple and transparent. It is not a probability model,
    expected-loss estimate, or investor limit.
    """
    normalized = [normalize_risk_level(level) for level in levels]
    if not normalized:
        return "MODERATE"
    return max(normalized, key=lambda level: _RISK_ORDER[level])


def enforce_minimum_review_verdict(
    proposed_verdict: str,
    overall_level: str,
    policy_review_required: bool,
) -> str:
    """Prevent severe or unresolved-policy cases from being silently passed."""
    verdict = str(proposed_verdict).strip().upper()
    if verdict not in {"PASS", "PASS WITH LIMITS", "REVIEW REQUIRED", "REJECT"}:
        verdict = "REVIEW REQUIRED"

    if verdict == "REJECT":
        return verdict

    if normalize_risk_level(overall_level) == "CRITICAL" or policy_review_required:
        return "REVIEW REQUIRED"

    return verdict
