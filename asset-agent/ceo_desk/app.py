import os
import subprocess
import sys
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ceo_desk.command_router import CEOAction, route_command
from data.portfolio_monitor import get_live_portfolio_snapshot
from departments.portfolio import run_portfolio_review
from executive.cio import run_cio_pipeline


st.set_page_config(
    page_title="Asset Management CEO Desk",
    page_icon="📊",
    layout="wide",
)


def _runtime_branch() -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        branch = result.stdout.strip()
        if branch:
            return branch
    except Exception:
        pass
    return os.getenv("ASSET_BRANCH", "unknown") or "unknown"


def _runtime_mode(branch: str) -> str:
    return "PRODUCTION" if branch == "main" else "DEVELOPMENT"


def _load_portfolio() -> str:
    try:
        return get_live_portfolio_snapshot()
    except Exception as exc:
        return (
            "LIVE PORTFOLIO UNAVAILABLE\n"
            f"Reason: {type(exc).__name__}: {exc}\n"
            "The investment agents must treat portfolio information as missing."
        )


def _snapshot_value(snapshot: str, label: str) -> str:
    prefix = f"{label}:"
    for line in snapshot.splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return "UNAVAILABLE"


def _portfolio_snapshot() -> str:
    if "portfolio_snapshot" not in st.session_state:
        st.session_state.portfolio_snapshot = _load_portfolio()
    return st.session_state.portfolio_snapshot


def _reset_portfolio() -> None:
    st.session_state.portfolio_snapshot = _load_portfolio()


def _help_text() -> str:
    return """### CEO Desk에서 지금 할 수 있는 일

- `PANW 분석해`
- `팔란티어 분석해`
- `내 포트폴리오 보여줘`
- `내 포트폴리오 점검해`

종목 분석은 **Analysis → Portfolio → Risk → Execution → CIO** 순서로 진행됩니다.
실제 주문은 실행하지 않으며 최종 투자 결정은 CEO가 합니다.
"""


def _render_message(message: dict[str, str]) -> None:
    with st.chat_message(message["role"]):
        if message.get("kind") == "portfolio":
            st.code(message["content"], language=None)
        else:
            st.markdown(message["content"])


branch = _runtime_branch()
mode = _runtime_mode(branch)
snapshot = _portfolio_snapshot()

st.title("ASSET MANAGEMENT — CEO DESK")
if mode == "PRODUCTION":
    st.success("PRODUCTION · main — 실제 사용용 안정 버전")
else:
    st.warning(f"DEV MODE · {branch} — 개발/실험용 버전")
st.caption("CEO가 자연어로 지시하면 CIO와 각 투자 부서가 업무를 수행합니다.")

market_value = _snapshot_value(snapshot, "Market Value")
profit_loss = _snapshot_value(snapshot, "Profit/Loss")

metric_left, metric_right = st.columns(2)
with metric_left:
    st.metric("Portfolio Market Value", market_value)
with metric_right:
    st.metric("Portfolio P/L", profit_loss)

with st.sidebar:
    st.header("CEO Control")
    st.write(f"**Mode:** {mode}")
    st.write(f"**Branch:** `{branch}`")
    st.caption("Brokerage connection: Toss Securities / Read-only")

    if st.button("포트폴리오 새로고침", width="stretch"):
        _reset_portfolio()
        st.rerun()

    with st.expander("Live Portfolio", expanded=True):
        st.code(_portfolio_snapshot(), language=None)

    st.divider()
    st.caption("Supported now")
    st.write("• 회사 분석")
    st.write("• 실제 포트폴리오 조회")
    st.write("• 전체 포트폴리오 점검")
    st.write("• CIO 최종 보고")
    st.caption("No brokerage orders are created, modified, or cancelled.")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "kind": "markdown",
            "content": (
                "CEO Desk 준비 완료. 예: **`PANW 분석해`**, "
                "**`내 포트폴리오 보여줘`**, **`내 포트폴리오 점검해`**"
            ),
        }
    ]

for chat_message in st.session_state.messages:
    _render_message(chat_message)

prompt = st.chat_input("CEO 지시를 입력하세요. 예: PANW 분석해")

if prompt:
    user_message = {"role": "user", "kind": "markdown", "content": prompt}
    st.session_state.messages.append(user_message)
    _render_message(user_message)

    command = route_command(prompt)
    current_snapshot = _portfolio_snapshot()

    with st.chat_message("assistant"):
        try:
            if command.action == CEOAction.SHOW_PORTFOLIO:
                response = current_snapshot
                kind = "portfolio"
                st.code(response, language=None)

            elif command.action == CEOAction.REVIEW_PORTFOLIO:
                with st.spinner("Portfolio 부서가 실제 계좌를 점검하는 중입니다..."):
                    review = run_portfolio_review(current_snapshot)
                response = (
                    f"### PORTFOLIO CEO REVIEW\n\n{review}\n\n"
                    "**FINAL DECISION: CEO REQUIRED**"
                )
                kind = "markdown"
                st.markdown(response)

            elif command.action == CEOAction.ANALYZE_COMPANY and command.ticker:
                ticker = command.ticker
                with st.spinner(
                    f"{ticker}: Analysis → Portfolio → Risk → Execution → CIO 진행 중..."
                ):
                    _, cio_report = run_cio_pipeline(
                        ticker,
                        portfolio_snapshot=current_snapshot,
                    )
                response = (
                    f"### CEO BRIEF — {ticker}\n\n"
                    f"{cio_report}\n\n"
                    "---\n**FINAL DECISION: CEO REQUIRED**"
                )
                kind = "markdown"
                st.markdown(response)

            elif command.action == CEOAction.HELP:
                response = _help_text()
                kind = "markdown"
                st.markdown(response)

            else:
                response = (
                    "아직 그 지시는 정확히 분류하지 못했습니다.\n\n"
                    "예를 들어 **`PANW 분석해`**, **`팔란티어 분석해`**, "
                    "**`내 포트폴리오 보여줘`**, **`내 포트폴리오 점검해`**처럼 입력해 주세요."
                )
                kind = "markdown"
                st.markdown(response)

        except Exception as exc:
            response = (
                "### CEO Desk 작업 실패\n\n"
                f"`{type(exc).__name__}`: {exc}\n\n"
                "주문은 실행되지 않았습니다. 연결 정보 또는 Agent 실행 상태를 확인해 주세요."
            )
            kind = "markdown"
            st.error(response)

    st.session_state.messages.append(
        {"role": "assistant", "kind": kind, "content": response}
    )
