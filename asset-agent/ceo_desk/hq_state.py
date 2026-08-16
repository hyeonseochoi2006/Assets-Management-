from copy import deepcopy


AGENT_ORDER = (
    "CIO",
    "Analysis",
    "Portfolio",
    "Risk",
    "Execution",
    "Briefing",
)

PIPELINE_ORDER = (
    "Analysis",
    "Portfolio",
    "Risk",
    "Execution",
    "CIO",
    "Briefing",
)

AGENT_DISPLAY_NAMES = {
    "CIO": "CIO",
    "Analysis": "ANALYSIS",
    "Portfolio": "PORTFOLIO",
    "Risk": "RISK",
    "Execution": "EXECUTION",
    "Briefing": "BRIEFING",
}

AGENT_MISSIONS = {
    "CIO": "부서 보고를 통합해 CEO 판단자료 작성",
    "Analysis": "기업·산업·재무·밸류에이션 분석",
    "Portfolio": "현재 계좌와 포트폴리오 적합성 검토",
    "Risk": "하방·집중도·주요 위험 검토",
    "Execution": "진입 방식과 실행 조건 검토",
    "Briefing": "최종 결과를 한국어 CEO 보고서로 작성",
}

STATUS_ICONS = {
    "IDLE": "⚪",
    "WORKING": "🟡",
    "DONE": "🟢",
    "ERROR": "🔴",
}

VALID_STATUSES = set(STATUS_ICONS)


def new_hq_agents() -> dict[str, dict[str, str]]:
    return {
        agent: {
            "status": "IDLE",
            "task": "대기 중",
            "last_completed": "아직 완료된 업무 없음",
        }
        for agent in AGENT_ORDER
    }


def reset_hq_agents(
    agents: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    reset = new_hq_agents()
    for agent in AGENT_ORDER:
        previous = agents.get(agent, {})
        reset[agent]["last_completed"] = previous.get(
            "last_completed", "아직 완료된 업무 없음"
        )
    return reset


def update_agent(
    agents: dict[str, dict[str, str]],
    agent: str,
    status: str,
    task: str | None = None,
) -> dict[str, dict[str, str]]:
    if agent not in AGENT_ORDER:
        return agents
    if status not in VALID_STATUSES:
        raise ValueError(f"Unsupported agent status: {status}")

    state = agents[agent]
    if task is not None:
        state["task"] = task
    state["status"] = status

    if status == "DONE":
        state["last_completed"] = state.get("task", "완료")

    return agents


def mark_active_errors(
    agents: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    for agent in AGENT_ORDER:
        if agents[agent]["status"] == "WORKING":
            agents[agent]["status"] = "ERROR"
    return agents


def hq_snapshot(agents: dict[str, dict[str, str]]) -> dict[str, object]:
    """Return a UI-independent snapshot suitable for a future API/React client."""
    return {
        "pipeline_order": list(PIPELINE_ORDER),
        "agents": deepcopy(agents),
    }
