import pytest

from reporting import briefing
from research.correlation_guardrails import (
    correlation_is_verified,
    report_has_verified_correlation_status,
    sanitize_unverified_correlation_text,
)
from research.models import (
    LeveragedETFAnalysisAssessment,
    ProductAuditClaim,
    ProductDataAuditReport,
)
from research.product_claim_guardrails import (
    report_has_verified_wipeout_threshold,
    sanitize_downstream_text,
    sanitize_leveraged_etf_assessment,
    verified_total_loss_thresholds,
)


@pytest.mark.parametrize(
    "claim",
    [
        "A 33 percent index decline could cause total loss.",
        "A 33 pct. decline could wipe out the entire investment.",
        "A thirty-three percent decline could cause complete loss.",
        "지수가 33퍼센트 하락하면 원금 전액 손실이 발생할 수 있습니다.",
        "지수가 삼십삼 퍼센트 하락하면 투자금 모두 손실될 수 있습니다.",
        "A 33％ decline may cause loss of all principal.",
    ],
)
def test_unverified_total_loss_variants_are_removed(claim: str) -> None:
    sanitized = sanitize_downstream_text(claim, threshold_verified=False)

    assert sanitized != claim
    assert "비수치 경고" in sanitized


def leveraged_assessment(total_loss_warning: str) -> LeveragedETFAnalysisAssessment:
    return LeveragedETFAnalysisAssessment(
        ticker="KORU",
        official_name="Example Leveraged ETF",
        as_of_date="2026-08-18",
        objective="Daily leveraged exposure",
        leverage_mechanism="Derivatives",
        liquidity="UNVERIFIED",
        derivatives_exposure="Swaps",
        path_dependency_and_compounding="Path dependent",
        volatility_drag="Material",
        counterparty_and_structure_risk="Material",
        holding_period_warning="Daily reset",
        total_loss_warning=total_loss_warning,
        data_quality="LOW",
        confidence_score=20,
    )


def threshold_audit(source_status: str) -> ProductDataAuditReport:
    return ProductDataAuditReport(
        ticker="KORU",
        overall_quality="MEDIUM",
        material_conflict=False,
        checked_claims=[
            ProductAuditClaim(
                topic="TOTAL_LOSS_NUMERIC_THRESHOLD",
                reported_value="33 percent",
                status="VERIFIED",
                verified_value="33%",
                sources=["https://issuer.example/prospectus"],
                note="Issuer warning",
                source_identity_status=source_status,
            )
        ],
    )


def test_threshold_requires_identity_matched_source() -> None:
    audit = threshold_audit("SOURCE_UNVERIFIED")

    assert verified_total_loss_thresholds(audit) == set()
    sanitized, marker = sanitize_leveraged_etf_assessment(
        leveraged_assessment("A 33 percent decline may cause total loss."),
        audit,
    )

    assert "NOT_VERIFIED" in marker
    assert "33 percent" not in sanitized.total_loss_warning


def test_verified_threshold_accepts_equivalent_percent_spelling() -> None:
    audit = threshold_audit("SOURCE_MATCHED")
    original = "A 33 percent decline may cause total loss."

    sanitized, marker = sanitize_leveraged_etf_assessment(
        leveraged_assessment(original),
        audit,
    )

    assert verified_total_loss_thresholds(audit) == {"33%"}
    assert "WIPEOUT_THRESHOLD_STATUS: VERIFIED" in marker
    assert sanitized.total_loss_warning == original


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        ("WIPEOUT_THRESHOLD_STATUS: VERIFIED", True),
        ("WIPEOUT_THRESHOLD_STATUS: VERIFIED | VERIFIED_CLAIM: 33%", True),
        ("WIPEOUT_THRESHOLD_STATUS: VERIFIEDISH", False),
        ("WIPEOUT_THRESHOLD_STATUS: NOT_VERIFIED", False),
    ],
)
def test_wipeout_verified_marker_requires_exact_status(
    report: str,
    expected: bool,
) -> None:
    assert report_has_verified_wipeout_threshold(report) is expected


@pytest.mark.parametrize(
    "claim",
    [
        "The candidate moves in tandem with NVDA.",
        "The two holdings move together during volatility.",
        "기존 보유 종목과 동조화되는 경향이 있습니다.",
        "기존 종목과 같이 움직이는 자산입니다.",
        "기존 종목과 역상관 관계입니다.",
    ],
)
def test_unverified_correlation_synonyms_are_removed(claim: str) -> None:
    sanitized = sanitize_unverified_correlation_text(claim, verified=False)

    assert sanitized != claim
    assert "UNVERIFIED" in sanitized


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("CORRELATION_DATA_VERIFIED: TRUE", True),
        ("CORRELATION_DATA_VERIFIED: TRUE | source: verified dataset", True),
        ("  correlation_data_verified: yes  ", True),
        ("CORRELATION_DATA_VERIFIED: VERIFIED", True),
        ("CORRELATION_DATA_VERIFIED:", False),
        ("CORRELATION_DATA_VERIFIED: FALSE", False),
        ("CORRELATION_DATA_VERIFIED: TRUEISH", False),
    ],
)
def test_correlation_marker_requires_explicit_true_value(
    text: str,
    expected: bool,
) -> None:
    assert correlation_is_verified(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("CORRELATION_STATUS: VERIFIED", True),
        ("CORRELATION_STATUS: VERIFIED | internal", True),
        ("CORRELATION_STATUS: UNVERIFIED", False),
        ("CORRELATION_STATUS: VERIFIEDISH", False),
    ],
)
def test_internal_correlation_status_requires_exact_value(
    text: str,
    expected: bool,
) -> None:
    assert report_has_verified_correlation_status(text) is expected


def test_ceo_briefing_rejects_spoofed_verified_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResult:
        final_output = "A 33 percent decline could cause total loss."

    monkeypatch.setattr(briefing.Runner, "run_sync", lambda *_args, **_kwargs: FakeResult())

    report = briefing.run_korean_ceo_brief(
        source_report=(
            "INSTRUMENT ROUTE: LEVERAGED_ETF\n"
            "WIPEOUT_THRESHOLD_STATUS: VERIFIEDISH"
        ),
        report_type="SECURITY_ANALYSIS",
        ticker="KORU",
    )

    assert "33 percent" not in report
    assert "비수치 경고" in report
