import pytest
from pydantic import ValidationError

from departments.execution import ExecutionAssessment
from departments.portfolio import PortfolioAssessment
from departments.risk import RiskAssessment
from research.models import EvidencePack


def portfolio_data() -> dict[str, object]:
    return {
        "ticker": "NVDA",
        "current_weight_pct": 10,
        "target_weight_min_pct": 5,
        "target_weight_max_pct": 10,
        "max_weight_pct": 15,
        "fit_score": 70,
        "concentration_risk": "Moderate",
        "correlation_status": "UNVERIFIED",
        "correlation_note": "No verified dataset",
        "recommendation": "NO POSITION CHANGE",
        "reasons": [],
        "missing_data": [],
    }


@pytest.mark.parametrize("fit_score", [-1, 101, 999])
def test_portfolio_fit_score_must_be_between_zero_and_one_hundred(
    fit_score: int,
) -> None:
    data = portfolio_data()
    data["fit_score"] = fit_score

    with pytest.raises(ValidationError):
        PortfolioAssessment.model_validate(data)


def test_portfolio_rejects_unknown_recommendation() -> None:
    data = portfolio_data()
    data["recommendation"] = "BUY NOW"

    with pytest.raises(ValidationError):
        PortfolioAssessment.model_validate(data)


@pytest.mark.parametrize(
    ("minimum", "target_maximum", "policy_maximum"),
    [(20, 10, 30), (5, 20, 15)],
)
def test_portfolio_rejects_inverted_weight_ranges(
    minimum: float,
    target_maximum: float,
    policy_maximum: float,
) -> None:
    data = portfolio_data()
    data.update(
        {
            "target_weight_min_pct": minimum,
            "target_weight_max_pct": target_maximum,
            "max_weight_pct": policy_maximum,
        }
    )

    with pytest.raises(ValidationError):
        PortfolioAssessment.model_validate(data)


def execution_data() -> dict[str, object]:
    return {
        "ticker": "NVDA",
        "execution_risk_score": 50,
        "execution_risk_level": "MODERATE",
        "preferred_order_type": "LIMIT",
        "preferred_entry_method": "STAGED ENTRY",
        "suggested_tranches": 3,
        "max_position_pct": None,
        "timing_considerations": [],
        "execution_risks": [],
        "conditions_before_execution": [],
        "execution_verdict": "READY WITH CONDITIONS",
        "missing_data": [],
    }


@pytest.mark.parametrize("score", [-50, 101, 999])
def test_execution_score_must_be_between_zero_and_one_hundred(score: int) -> None:
    data = execution_data()
    data["execution_risk_score"] = score

    with pytest.raises(ValidationError):
        ExecutionAssessment.model_validate(data)


@pytest.mark.parametrize("order_type", ["YOLO", "BUY NOW", "OPTIONS"])
def test_execution_rejects_unknown_order_types(order_type: str) -> None:
    data = execution_data()
    data["preferred_order_type"] = order_type

    with pytest.raises(ValidationError):
        ExecutionAssessment.model_validate(data)


def test_execution_rejects_buy_verdict() -> None:
    data = execution_data()
    data["execution_verdict"] = "BUY"

    with pytest.raises(ValidationError):
        ExecutionAssessment.model_validate(data)


@pytest.mark.parametrize("tranches", [-3, 0, 1, 21])
def test_staged_entry_requires_two_to_twenty_tranches(tranches: int) -> None:
    data = execution_data()
    data["suggested_tranches"] = tranches

    with pytest.raises(ValidationError):
        ExecutionAssessment.model_validate(data)


def test_waiting_execution_plan_is_explicitly_non_actionable() -> None:
    data = execution_data()
    data.update(
        {
            "preferred_order_type": "NO ORDER RECOMMENDED",
            "preferred_entry_method": "WAIT",
            "suggested_tranches": 0,
            "execution_verdict": "WAIT",
        }
    )

    assessment = ExecutionAssessment.model_validate(data)

    assert assessment.suggested_tranches == 0
    assert assessment.preferred_order_type == "NO ORDER RECOMMENDED"


def test_wait_verdict_cannot_carry_an_actionable_order() -> None:
    data = execution_data()
    data["execution_verdict"] = "WAIT"

    with pytest.raises(ValidationError):
        ExecutionAssessment.model_validate(data)


def risk_data() -> dict[str, object]:
    return {
        "ticker": "NVDA",
        "risk_level": "MODERATE",
        "company_risk_level": "MODERATE",
        "valuation_risk_level": "MODERATE",
        "concentration_risk_level": "MODERATE",
        "market_risk_level": "MODERATE",
        "liquidity_risk_level": "LOW",
        "execution_risk_level": "LOW",
        "stress_scenarios": [],
        "major_risks": [],
        "risk_limits": [],
        "risk_verdict": "REVIEW REQUIRED",
        "missing_data": [],
    }


def test_risk_rejects_unknown_verdict() -> None:
    data = risk_data()
    data["risk_verdict"] = "BUY"

    with pytest.raises(ValidationError):
        RiskAssessment.model_validate(data)


def test_legacy_risk_scores_reject_out_of_range_values() -> None:
    data = risk_data()
    data["overall_risk_score"] = 999

    with pytest.raises(ValidationError):
        RiskAssessment.model_validate(data)


def test_evidence_pack_rejects_impossible_source_counts() -> None:
    with pytest.raises(ValidationError):
        EvidencePack(
            ticker="NVDA",
            company_name="NVIDIA",
            as_of_date="2026-08-18",
            business_summary="summary",
            industry_summary="summary",
            source_count=1,
            primary_source_count=2,
        )
