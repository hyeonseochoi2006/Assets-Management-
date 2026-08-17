from research.models import ProductDataAuditReport


def enforce_product_source_identity(
    report: ProductDataAuditReport,
) -> ProductDataAuditReport:
    """Fail closed when product claims are not tied to the correct instrument.

    The Product Data Auditor assigns SOURCE_MATCHED / SOURCE_MISMATCHED /
    SOURCE_UNVERIFIED to every checked claim and conflict. Only SOURCE_MATCHED
    evidence may survive as VERIFIED or as a real data CONFLICT.
    """
    checked_claims = []
    unverified_claims = list(report.unverified_claims)
    notes = list(report.notes)
    rejected_topics: list[str] = []

    for claim in report.checked_claims:
        if claim.source_identity_status == "SOURCE_MATCHED":
            checked_claims.append(claim)
            continue

        if claim.status in {"VERIFIED", "CONFLICT"}:
            reason = (
                "Source identity mismatch"
                if claim.source_identity_status == "SOURCE_MISMATCHED"
                else "Source identity was not verified"
            )
            checked_claims.append(
                claim.model_copy(
                    update={
                        "status": "UNVERIFIED",
                        "verified_value": None,
                        "note": f"{reason}. {claim.note}".strip(),
                    }
                )
            )
            rejected_topics.append(claim.topic)
            unverified_claims.append(
                f"{claim.topic}: UNVERIFIED because the source was not identity-matched to this instrument."
            )
        else:
            checked_claims.append(claim)

    conflicts = []
    for conflict in report.conflicts:
        if conflict.source_identity_status == "SOURCE_MATCHED":
            conflicts.append(conflict)
            continue

        rejected_topics.append(conflict.topic)
        status = conflict.source_identity_status
        notes.append(
            "SOURCE_CONTAMINATION_REJECTED: "
            f"{conflict.topic} conflict excluded because source identity status was {status}."
        )
        unverified_claims.append(
            f"{conflict.topic}: conflicting values were not treated as a valid product-data conflict because source identity was not verified."
        )

    material_conflict = any(conflict.material for conflict in conflicts)
    overall_quality = report.overall_quality
    if rejected_topics and overall_quality == "HIGH":
        overall_quality = "MEDIUM"

    if rejected_topics:
        unique_topics = ", ".join(sorted(set(rejected_topics)))
        notes.append(
            "Source Identity Guardrail rejected or downgraded product data for: "
            + unique_topics
        )

    return report.model_copy(
        update={
            "overall_quality": overall_quality,
            "material_conflict": material_conflict,
            "checked_claims": checked_claims,
            "conflicts": conflicts,
            "unverified_claims": unverified_claims,
            "notes": notes,
        }
    )
