from html import escape

import streamlit as st

from ceo_desk.hq_state import (
    AGENT_DISPLAY_NAMES,
    AGENT_MISSIONS,
    AGENT_ORDER,
    PIPELINE_ORDER,
    STATUS_ICONS,
    VALID_STATUSES,
    mark_active_errors,
    new_hq_agents,
    reset_hq_agents,
    update_agent,
)


def ensure_hq_state() -> None:
    if "hq_agents" not in st.session_state:
        st.session_state.hq_agents = new_hq_agents()
    else:
        for agent, default_state in new_hq_agents().items():
            st.session_state.hq_agents.setdefault(agent, default_state)

    if "hq_selected_agent" not in st.session_state:
        st.session_state.hq_selected_agent = "CIO"


def reset_hq_state() -> None:
    ensure_hq_state()
    st.session_state.hq_agents = reset_hq_agents(st.session_state.hq_agents)


def set_agent_status(agent: str, status: str, task: str | None = None) -> None:
    ensure_hq_state()
    if status not in VALID_STATUSES:
        raise ValueError(f"Unsupported agent status: {status}")
    st.session_state.hq_agents = update_agent(
        st.session_state.hq_agents,
        agent,
        status,
        task,
    )


def mark_working_agents_error() -> None:
    ensure_hq_state()
    st.session_state.hq_agents = mark_active_errors(st.session_state.hq_agents)


def task_for(agent: str, subject: str) -> str:
    mission = AGENT_MISSIONS.get(agent, "업무 수행")
    return f"{subject} · {mission}"


def _room_visual(status: str) -> tuple[str, str]:
    if status == "WORKING":
        return "rgba(245, 183, 66, .55)", "0 0 0 2px rgba(245, 183, 66, .12)"
    if status == "DONE":
        return "rgba(66, 190, 120, .45)", "none"
    if status == "ERROR":
        return "rgba(235, 85, 85, .6)", "0 0 0 2px rgba(235, 85, 85, .12)"
    return "rgba(128, 128, 128, .28)", "none"


def _agent_room_html(agent: str) -> str:
    state = st.session_state.hq_agents[agent]
    status = state["status"]
    icon = STATUS_ICONS.get(status, "⚪")
    border, shadow = _room_visual(status)
    task = escape(str(state.get("task", "대기 중")))
    mission = escape(AGENT_MISSIONS[agent])
    name = escape(AGENT_DISPLAY_NAMES[agent])

    return f"""
<div style="border:1px solid {border}; box-shadow:{shadow}; border-radius:18px; padding:16px; min-height:158px; background:rgba(127,127,127,.035);">
  <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:10px;">
    <div>
      <div style="font-size:11px; opacity:.55; letter-spacing:.11em;">OFFICE / DEPARTMENT</div>
      <div style="font-size:20px; font-weight:750; margin-top:3px;">{name}</div>
    </div>
    <div style="font-size:13px; font-weight:700; white-space:nowrap;">{icon} {escape(status)}</div>
  </div>
  <div style="font-size:12px; opacity:.7; margin-top:12px; line-height:1.45;">{mission}</div>
  <div style="margin-top:12px; padding-top:10px; border-top:1px solid rgba(128,128,128,.16);">
    <div style="font-size:10px; opacity:.5; letter-spacing:.08em;">CURRENT TASK</div>
    <div style="font-size:12px; margin-top:4px; line-height:1.45;">{task}</div>
  </div>
</div>
"""


def _ceo_room_html() -> str:
    return """
<div style="border:1px solid rgba(120,150,255,.5); border-radius:18px; padding:16px; min-height:158px; background:rgba(120,150,255,.045);">
  <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:10px;">
    <div>
      <div style="font-size:11px; opacity:.55; letter-spacing:.11em;">EXECUTIVE OFFICE</div>
      <div style="font-size:20px; font-weight:750; margin-top:3px;">CEO · YOU</div>
    </div>
    <div style="font-size:13px; font-weight:700; white-space:nowrap;">👤 FINAL AUTHORITY</div>
  </div>
  <div style="font-size:12px; opacity:.7; margin-top:12px; line-height:1.45;">최종 투자 결정과 투자정책 승인을 담당합니다.</div>
  <div style="margin-top:12px; padding-top:10px; border-top:1px solid rgba(128,128,128,.16);">
    <div style="font-size:10px; opacity:.5; letter-spacing:.08em;">ROLE</div>
    <div style="font-size:12px; margin-top:4px;">보고를 받고 승인 · 보류 · 거절을 결정</div>
  </div>
</div>
"""


def _pipeline_html() -> str:
    pieces: list[str] = []
    for index, agent in enumerate(PIPELINE_ORDER):
        state = st.session_state.hq_agents[agent]
        status = state["status"]
        icon = STATUS_ICONS.get(status, "⚪")
        border, _ = _room_visual(status)
        pieces.append(
            f'<span style="border:1px solid {border}; border-radius:999px; padding:7px 10px; font-size:11px; white-space:nowrap;">'
            f'{icon} {escape(AGENT_DISPLAY_NAMES[agent])}</span>'
        )
        if index < len(PIPELINE_ORDER) - 1:
            pieces.append('<span style="opacity:.35; padding:0 2px;">→</span>')

    return (
        '<div style="border:1px solid rgba(128,128,128,.22); border-radius:16px; padding:12px; margin:4px 0 16px 0;">'
        '<div style="font-size:10px; opacity:.5; letter-spacing:.09em; margin-bottom:9px;">LIVE WORKFLOW</div>'
        '<div style="display:flex; align-items:center; gap:5px; flex-wrap:wrap;">'
        + "".join(pieces)
        + "</div></div>"
    )


def render_agent_card(slot, agent: str) -> None:
    ensure_hq_state()
    slot.markdown(_agent_room_html(agent), unsafe_allow_html=True)


def render_pipeline(slot) -> None:
    ensure_hq_state()
    slot.markdown(_pipeline_html(), unsafe_allow_html=True)


def _render_agent_office(column, agent: str, slots: dict[str, object]) -> None:
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


def render_hq_dashboard() -> dict[str, object]:
    ensure_hq_state()

    st.subheader("ASSET MANAGEMENT HQ · 2D OFFICE")
    st.caption(
        "실제 Agent 업무 상태를 사무실 형태로 표시합니다. 노란색 WORKING 부서가 현재 업무를 수행 중입니다."
    )

    slots: dict[str, object] = {}
    pipeline_slot = st.empty()
    slots["__pipeline__"] = pipeline_slot
    render_pipeline(pipeline_slot)

    executive_left, executive_right = st.columns(2)
    with executive_left:
        st.markdown(_ceo_room_html(), unsafe_allow_html=True)
        st.caption("CEO Office")
    _render_agent_office(executive_right, "CIO", slots)

    st.markdown(
        '<div style="text-align:center; opacity:.28; font-size:18px; margin:4px 0;">↓ DELEGATION ↓</div>',
        unsafe_allow_html=True,
    )

    research_left, research_right = st.columns(2)
    _render_agent_office(research_left, "Analysis", slots)
    _render_agent_office(research_right, "Portfolio", slots)

    control_left, control_right = st.columns(2)
    _render_agent_office(control_left, "Risk", slots)
    _render_agent_office(control_right, "Execution", slots)

    st.markdown(
        '<div style="text-align:center; opacity:.28; font-size:18px; margin:4px 0;">↓ REPORTING ↓</div>',
        unsafe_allow_html=True,
    )

    spacer_left, briefing_column, spacer_right = st.columns([1, 2, 1])
    _render_agent_office(briefing_column, "Briefing", slots)

    return slots


def refresh_agent_card(slots: dict[str, object], agent: str) -> None:
    slot = slots.get(agent)
    if slot is not None:
        render_agent_card(slot, agent)

    pipeline_slot = slots.get("__pipeline__")
    if pipeline_slot is not None:
        render_pipeline(pipeline_slot)


def refresh_all_agent_cards(slots: dict[str, object]) -> None:
    for agent in AGENT_ORDER:
        slot = slots.get(agent)
        if slot is not None:
            render_agent_card(slot, agent)

    pipeline_slot = slots.get("__pipeline__")
    if pipeline_slot is not None:
        render_pipeline(pipeline_slot)


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
