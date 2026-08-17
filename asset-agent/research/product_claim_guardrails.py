import re

from research.models import LeveragedETFAnalysisAssessment, ProductDataAuditReport


_PERCENT_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*%")
_TOTAL_LOSS_TERMS = (
    "total loss",
    "complete loss",
    "entire investment",
    "full loss",
    "wipeout",
    "wipe-out",
    "wipe out",
    "loss of the entire",
    "loss of all",
    "전액 손실",
    "원금 전액",
    "총손실",
    "완전 손실",
    "전부 손실",
)
_GENERIC_TOTAL_LOSS_WARNING = (
    "Issuer/prospectus materials may warn of rapid and potentially complete loss in extreme conditions. "
    "No exact numeric total-loss threshold is verified for this report; do not infer one mechanically from the leverage multiple."
)
_REDACTED_THRESHOLD = "[UNVERIFIED NUMERIC TOTAL-LOSS THRESHOLD REDACTED]"
_THRESHOLD_TOPIC = "TOTAL_LOSS_NUMERIC_THRESHOLD"


def _percent_tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    return {f"{match.group(1)}%" for match in _PERCENT_RE.finditer(text)}


def _contains_total_loss_language(text: str | None) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(term in lowered for term in _TOTAL_LOSS_TERMS)


def _is_numeric_total_loss_claim(text: str | None) -> bool:
    return bool(_percent_tokens(text)) and _contains_total_loss_language(text)


def _normalize_topic(topic: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", topic.strip().upper()).strip("_")


def _redact_percentages(text: str | None) -> str | None:
    if text is None:
        return None
    return _PERCENT_RE.sub(_REDACTED_THRESHOLD, text)


def _verified_threshold_claims(audit: ProductDataAuditReport):
    return [
        claim
        for claim in audit.checked_claims
        if _normalize_topic(claim.topic) == _THRESHOLD_TOPIC
        and claim.status == "VERIFIED"
        and claim.verified_value
        and _percent_tokens(claim.verified_value)
        and claim.sources
    ]


def verified_total_loss_thresholds(audit: ProductDataAuditReport) -> set[str]:
    """Return only exact percent thresholds explicitly verified by Product Data Auditor."""
    verified: set[str] = set()
    for claim in _verified_threshold_claims(audit):
        verified.update(_percent_tokens(claim.verified_value))
    return verified


def verified_total_loss_threshold_details(audit: ProductDataAuditReport) -> list[str]:
    """Return full audited wording so qualifiers are preserved downstream.

    The percentage alone is insufficient. For example, 'approximately 33% during
    the trading day' must not become an exact 33.0% mechanical liquidation rule.
    """
    details: list[str] = []
    for claim in _verified_threshold_claims(audit):
        source_text = "; ".join(claim.sources)
        details.append(
            f"{claim.verified_value} | primary/reliable source(s): {source_text}"
        )
    return details


def sanitize_product_audit_for_downstream(
    audit: ProductDataAuditReport,
) -> ProductDataAuditReport:
    """Redact exact numeric wipeout thresholds unless the dedicated claim is VERIFIED."""
    sanitized_claims = []
    for claim in audit.checked_claims:
        if (
            _normalize_topic(claim.topic) == _THRESHOLD_TOPIC
            and claim.status != "VERIFIED"
        ):
            sanitized_claims.append(
                claim.model_copy(
                    update={
                        "reported_value": _redact_percentages(claim.reported_value),
                        "verified_value": None,
                        "note": _redact_percentages(claim.note),
                    }
                )
            )
        else:
            sanitized_claims.append(claim)

    sanitized_conflicts = []
    for conflict in audit.conflicts:
        combined = " ".join(
            [
                conflict.topic,
                conflict.specialist_claim,
                conflict.conflicting_evidence,
                conflict.explanation,
            ]
        )
        if _normalize_topic(conflict.topic) == _THRESHOLD_TOPIC or _is_numeric_total_loss_claim(combined):
            sanitized_conflicts.append(
                conflict.model_copy(
                    update={
                        "specialist_claim": _redact_percentages(conflict.specialist_claim),
                        "conflicting_evidence": _redact_percentages(conflict.conflicting_evidence),
                        "explanation": _redact_percentages(conflict.explanation),
                    }
                )
            )
        else:
            sanitized_conflicts.append(conflict)

    sanitized_unverified = [
        _redact_percentages(item) if _is_numeric_total_loss_claim(item) else item
        for item in audit.unverified_claims
    ]
    sanitized_notes = [
        _redact_percentages(item) if _is_numeric_total_loss_claim(item) else item
        for item in audit.notes
    ]

    return audit.model_copy(
        update={
            "checked_claims": sanitized_claims,
            "conflicts": sanitized_conflicts,
            "unverified_claims": sanitized_unverified,
            "notes": sanitized_notes,
        }
    )


def _sanitize_text(text: str, allowed_thresholds: set[str]) -> str:
    if not _is_numeric_total_loss_claim(text):
        return text
    claimed = _percent_tokens(text)
    if claimed and claimed.issubset(allowed_thresholds):
        return text
    return _GENERIC_TOTAL_LOSS_WARNING


def sanitize_leveraged_etf_assessment(
    assessment: LeveragedETFAnalysisAssessment,
    audit: ProductDataAuditReport,
) -> tuple[LeveragedETFAnalysisAssessment, str]:
    """Remove unverified numeric wipeout thresholds before downstream agents see them."""
    verified = verified_total_loss_thresholds(audit)
    verified_details = verified_total_loss_threshold_details(audit)

    updates: dict[str, object] = {
        "total_loss_warning": _sanitize_text(assessment.total_loss_warning, verified),
        "holding_period_warning": _sanitize_text(assessment.holding_period_warning, verified),
        "path_dependency_and_compounding": _sanitize_text(
            assessment.path_dependency_and_compounding, verified
        ),
        "counterparty_and_structure_risk": _sanitize_text(
            assessment.counterparty_and_structure_risk, verified
        ),
        "key_risks": [_sanitize_text(item, verified) for item in assessment.key_risks],
    }

    sanitized = assessment.model_copy(update=updates)
    if verified_details:
        marker = "\n".join(
            [
                "WIPEOUT_THRESHOLD_STATUS: VERIFIED",
                *[
                    "WIPEOUT_THRESHOLD_VERIFIED_CLAIM: " + detail
                    for detail in verified_details
                ],
                (
                    "WIPEOUT_THRESHOLD_RULE: preserve the official qualifiers exactly; "
                    "do not convert the verified warning into a mechanical liquidation formula."
                ),
            ]
        )
    else:
        marker = (
            "WIPEOUT_THRESHOLD_STATUS: NOT_VERIFIED — do not calculate, infer, or state any exact "
            "percentage threshold for total loss/wipeout. Use only a non-numeric loss warning."
        )
    return sanitized, marker


def sanitize_downstream_text(text: str, threshold_verified: bool) -> str:
    """Deterministically scrub unverified numeric total-loss claims from generated text."""
    if threshold_verified:
        return text

    output: list[str] = []
    replacement_added = False
    for line in text.splitlines():
        if _is_numeric_total_loss_claim(line):
            if not replacement_added:
                prefix = "- " if line.lstrip().startswith("-") else ""
                output.append(
                    prefix
                    + "공식 자료로 검증된 정확한 전액손실 임계값은 없습니다. "
                    "급격한 손실 또는 원금 전액 손실 가능성은 비수치 경고로만 취급합니다."
                )
                replacement_added = True
            continue
        output.append(line)
    return "\n".join(output)


def report_has_verified_wipeout_threshold(source_report: str) -> bool:
    return "WIPEOUT_THRESHOLD_STATUS: VERIFIED" in source_report
