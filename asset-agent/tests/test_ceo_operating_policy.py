from policies.ceo_operating_policy import (
    AUTONOMOUS_ACTIONS,
    CEO_APPROVAL_REQUIRED,
    ESCALATION_RULES,
    HARD_RULES,
    PROHIBITED_ACTIONS,
    EscalationLevel,
    WorkflowDirective,
    get_full_operating_policy,
    get_machine_operating_policy,
)


def _codes(rules) -> set[str]:
    return {rule.code for rule in rules}


def test_policy_rule_codes_are_unique_across_all_groups() -> None:
    groups = [
        HARD_RULES,
        AUTONOMOUS_ACTIONS,
        CEO_APPROVAL_REQUIRED,
        PROHIBITED_ACTIONS,
    ]
    all_codes = [rule.code for group in groups for rule in group]
    all_codes.extend(rule.code for rule in ESCALATION_RULES)

    assert len(all_codes) == len(set(all_codes))


def test_hard_rules_preserve_final_ceo_authority_and_no_real_trading() -> None:
    hard_text = " ".join(rule.statement for rule in HARD_RULES).lower()

    assert "ceo retains final authority" in hard_text
    assert "never place, modify, or cancel a real brokerage order" in hard_text


def test_no_data_no_decision_is_a_hard_rule() -> None:
    rule = next(rule for rule in HARD_RULES if rule.code == "HR-004")

    assert "NO DATA = NO DECISION" in rule.statement
    assert "guessed" in rule.statement


def test_deterministic_first_is_a_hard_rule() -> None:
    rule = next(rule for rule in HARD_RULES if rule.code == "HR-005")

    assert "deterministic" in rule.statement.lower()
    assert "before using AI" in rule.statement


def test_real_order_execution_is_explicitly_prohibited() -> None:
    prohibited = next(rule for rule in PROHIBITED_ACTIONS if rule.code == "PA-001")

    assert "real brokerage order" in prohibited.statement
    assert {"CA-001", "CA-006"}.issubset(_codes(CEO_APPROVAL_REQUIRED))


def test_missing_policy_cannot_be_silently_invented() -> None:
    prohibited = next(rule for rule in PROHIBITED_ACTIONS if rule.code == "PA-002")
    approval = next(rule for rule in CEO_APPROVAL_REQUIRED if rule.code == "CA-005")

    assert "policies" in prohibited.statement
    assert "NOT CONFIGURED" in approval.statement


def test_risk_and_audit_dissent_must_be_preserved() -> None:
    hard = next(rule for rule in HARD_RULES if rule.code == "HR-006")
    prohibited = next(rule for rule in PROHIBITED_ACTIONS if rule.code == "PA-011")

    assert "independent" in hard.statement
    assert "dissent" in hard.statement
    assert "Never suppress" in prohibited.statement


def test_green_and_watch_do_not_notify_ceo() -> None:
    green = [rule for rule in ESCALATION_RULES if rule.level == EscalationLevel.GREEN]
    watch = [rule for rule in ESCALATION_RULES if rule.level == EscalationLevel.WATCH]

    assert green
    assert watch
    assert all(rule.notify_ceo is False for rule in green + watch)


def test_critical_events_pause_and_notify_ceo() -> None:
    critical = [rule for rule in ESCALATION_RULES if rule.level == EscalationLevel.CRITICAL]

    assert critical
    assert all(rule.notify_ceo is True for rule in critical)
    assert all(
        rule.workflow_directive == WorkflowDirective.PAUSE_AND_NOTIFY
        for rule in critical
    )


def test_approval_events_wait_for_ceo() -> None:
    approval_codes = {"ER-004", "ER-005", "ER-006"}
    approval_rules = [rule for rule in ESCALATION_RULES if rule.code in approval_codes]

    assert {rule.code for rule in approval_rules} == approval_codes
    assert all(rule.notify_ceo for rule in approval_rules)
    assert all(
        rule.workflow_directive == WorkflowDirective.WAITING_FOR_CEO
        for rule in approval_rules
    )


def test_machine_policy_is_json_safe_shape() -> None:
    policy = get_machine_operating_policy()

    assert policy["version"] == "2.0"
    assert isinstance(policy["hard_rules"], list)
    assert isinstance(policy["autonomous_actions"], list)
    assert isinstance(policy["ceo_approval_required"], list)
    assert isinstance(policy["prohibited_actions"], list)
    assert isinstance(policy["escalation_rules"], list)

    escalation = policy["escalation_rules"][0]
    assert isinstance(escalation["level"], str)
    assert isinstance(escalation["notify_ceo"], bool)
    assert isinstance(escalation["workflow_directive"], str)


def test_full_agent_policy_includes_machine_constitution_and_legacy_context() -> None:
    text = get_full_operating_policy()

    assert "AUTONOMOUS COMPANY CONSTITUTION v2.0" in text
    assert "HARD RULES" in text
    assert "CEO OPERATING POLICY v1" in text
    assert "DAILY OPERATING ROUTINE" in text
    assert "PERIODIC REVIEW POLICY" in text
