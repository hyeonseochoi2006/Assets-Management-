from html import escape

import streamlit as st


AGENT_ORDER = (
    "CIO",
    "Analysis",
    "Portfolio",
    "Risk",
    "Execution",
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


def ensure_hq_state() -> None:
    if "hq_agents" not in st.session_state:
        st.session_state.hq_agents = {
            agent: {
                "status": "IDLE",
                "task": "대기 중",
                "last_completed": "아직 완료된 업무 없음",
            }
            for agent in AGENT_ORDER
        }

    if "hq_selected_agent" not in st.session_state:
        st.session_state.hq_selected_agent = "CIO"


def reset_hq_state() -> None:
    ensure_hq_state()
    for agent in AGENT_ORDER:
        previous = st.session_state.hq_agents[agent]
        st.session_state.hq_agents[agent] = {
            "status": "IDLE",
            "task": "대기 중",
            "last_completed": previous.get(
                "last_completed", "아직 완료된 업무 없음"
            ),
        }


def set_agent_status(agent: str, status: str, task: str | None = None) -> None:
    ensure_hq_state()
    if agent not in AGENT_ORDER:
        return
    if status not in VALID_STATUSES:
        raise ValueError(f"Unsupported agent status: {status}")

    state = st.session_state.hq_agents[agent]
    if task is not None:
        state["task"] = task
    state["status"] = status

    if status == "DONE":
        state["last_completed"] = state.get("task", "완료")


def mark_working_agents_error() -> None:
    ensure_hq_state()
    for agent in AGENT_ORDER:
        state = st.session_state.hq_agents[agent]
        if state["status"] == "WORKING":
            state["status"] = "ERROR"


def task_for(agent: str, subject: str) -> str:
    mission = AGENT_MISSIONS.get(agent, "업무 수행")
    return f"{subject} · {mission}"


def render_agent_card(slot, agent: str) -> None:
    ensure_hq_state()
    state = st.session_state.hq_agents[agent]
    status = state["status"]
    icon = STATUS_ICONS.get(status, "⚪")
    name = AGENT_DISPLAY_NAMES[agent]
    task = escape(str(state.get("task", "대기 중")))

    slot.markdown(
        f"""
<div style="border:1px solid rgba(128,128,128,.35); border-radius:14px; padding:14px 16px; min-height:132px;">
  <div style="font-size:12px; opacity:.65; letter-spacing:.08em;">DEPARTMENT</div>
  <div style="font-size:20px; font-weight:700; margin:2px 0 8px 0;">{escape(name)}</div>
  <div style="font-size:14px; font-weight:600;">{icon} {escape(status)}</div>
  <div style="font-size:12px; opacity:.72; margin-top:9px; line-height:1.45;">{task}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_hq_dashboard() -> dict[str, object]:
    ensure_hq_state()

    st.subheader("ASSET MANAGEMENT HQ")
    st.caption(
        "실제 Agent 파이프라인 상태입니다. 업무가 다음 부서로 넘어갈 때 카드 상태도 함께 바뀝니다."
    )

    slots: dict[str, object] = {}
    for row_agents in (AGENT_ORDER[:3], AGENT_ORDER[3:]):
        columns = st.columns(3)
        for column, agent in zip(columns, row_agents):
            with column:
                slot = st.empty()
                render_agent_card(slot, agent)
                slots[agent] = slot
                if st.button(
                    f"{AGENT_DISPLAY_NAMES[agent]} 상세",
                    key=f"inspect_{agent}",
                    width="stretch",
                ):
                    st.session_state.hq_selected_agent = agent

    return slots


def refresh_agent_card(slots: dict[str, object], agent: str) -> None:
    slot = slots.get(agent)
    if slot is not None:
        render_agent_card(slot, agent)


def refresh_all_agent_cards(slots: dict[str, object]) -> None:
    for agent in AGENT_ORDER:
        refresh_agent_card(slots, agent)


def render_agent_inspector() -> None:
    ensure_hq_state()
    agent = st.session_state.hq_selected_agent
    state = st.session_state.hq_agents[agent]

    with st.expander(
        f"Agent Inspector — {AGENT_DISPLAY_NAMES[agent]}",
        expanded=False,
    ):
        st.write(f"**상태:** {STATUS_ICONS[state['status']]} {state['status']}")
        st.write(f"**역할:** {AGENT_MISSIONS[agent]}")
        st.write(f"**현재 업무:** {state['task']}")
        st.write(f"**최근 완료 업무:** {state['last_completed']}")
