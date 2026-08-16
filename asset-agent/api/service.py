from threading import Lock, Thread

from ceo_desk.command_router import CEOAction, CEOCommand, route_command
from ceo_desk.hq_state import AGENT_MISSIONS
from data.portfolio_monitor import get_live_portfolio_snapshot
from departments.portfolio import run_portfolio_review
from executive.cio import run_cio_pipeline
from reporting.briefing import run_korean_ceo_brief

from api.job_store import JOB_STORE


_START_LOCK = Lock()


class ActiveJobError(RuntimeError):
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(f"Another CEO job is already active: {job_id}")


def _task_for(agent: str, subject: str) -> str:
    mission = AGENT_MISSIONS.get(agent, "업무 수행")
    return f"{subject} · {mission}"


def _help_text() -> str:
    return (
        "현재 가능한 명령:\n"
        "- PANW 분석해\n"
        "- 팔란티어 분석해\n"
        "- 내 포트폴리오 보여줘\n"
        "- 내 포트폴리오 점검해\n\n"
        "실제 주문은 실행하지 않으며 최종 투자 결정은 CEO가 합니다."
    )


def _unknown_text() -> str:
    return (
        "아직 그 지시는 정확히 분류하지 못했습니다. "
        "예: `PANW 분석해`, `내 포트폴리오 보여줘`, "
        "`내 포트폴리오 점검해`"
    )


def _run_job(job_id: str, command: CEOCommand) -> None:
    JOB_STORE.mark_running(job_id)

    try:
        if command.action == CEOAction.HELP:
            JOB_STORE.complete_job(job_id, _help_text(), "markdown")
            return

        if command.action == CEOAction.UNKNOWN:
            JOB_STORE.complete_job(job_id, _unknown_text(), "markdown")
            return

        if command.action == CEOAction.SHOW_PORTFOLIO:
            task = _task_for("Portfolio", "현재 Toss 포트폴리오 조회")
            JOB_STORE.update_agent(job_id, "Portfolio", "WORKING", task)
            snapshot = get_live_portfolio_snapshot()
            JOB_STORE.update_agent(job_id, "Portfolio", "DONE", task)
            JOB_STORE.complete_job(job_id, snapshot, "portfolio")
            return

        if command.action == CEOAction.REVIEW_PORTFOLIO:
            portfolio_task = _task_for("Portfolio", "전체 포트폴리오")
            JOB_STORE.update_agent(
                job_id,
                "Portfolio",
                "WORKING",
                portfolio_task,
            )
            snapshot = get_live_portfolio_snapshot()
            review = run_portfolio_review(snapshot)
            JOB_STORE.update_agent(job_id, "Portfolio", "DONE", portfolio_task)

            briefing_task = _task_for("Briefing", "전체 포트폴리오")
            JOB_STORE.update_agent(
                job_id,
                "Briefing",
                "WORKING",
                briefing_task,
            )
            report = run_korean_ceo_brief(
                source_report=review,
                report_type="WHOLE_PORTFOLIO_REVIEW",
                portfolio_snapshot=snapshot,
            )
            JOB_STORE.update_agent(job_id, "Briefing", "DONE", briefing_task)
            JOB_STORE.complete_job(job_id, report, "markdown")
            return

        if command.action == CEOAction.ANALYZE_COMPANY and command.ticker:
            ticker = command.ticker
            try:
                snapshot = get_live_portfolio_snapshot()
            except Exception:
                task = _task_for("Portfolio", f"{ticker} · 실제 계좌 불러오기")
                JOB_STORE.update_agent(job_id, "Portfolio", "ERROR", task)
                raise

            def status_callback(agent: str, status: str) -> None:
                JOB_STORE.update_agent(
                    job_id,
                    agent,
                    status,
                    _task_for(agent, ticker),
                )

            _, cio_report = run_cio_pipeline(
                ticker,
                portfolio_snapshot=snapshot,
                status_callback=status_callback,
            )

            briefing_task = _task_for("Briefing", ticker)
            JOB_STORE.update_agent(
                job_id,
                "Briefing",
                "WORKING",
                briefing_task,
            )
            report = run_korean_ceo_brief(
                source_report=cio_report,
                report_type="COMPANY_ANALYSIS",
                ticker=ticker,
                portfolio_snapshot=snapshot,
            )
            JOB_STORE.update_agent(job_id, "Briefing", "DONE", briefing_task)
            JOB_STORE.complete_job(job_id, report, "markdown")
            return

        JOB_STORE.complete_job(job_id, _unknown_text(), "markdown")

    except Exception as exc:
        JOB_STORE.fail_job(job_id, f"{type(exc).__name__}: {exc}")


def start_job(command_text: str) -> dict[str, object]:
    command = route_command(command_text)

    with _START_LOCK:
        active_job_id = JOB_STORE.active_job_id()
        if active_job_id is not None:
            raise ActiveJobError(active_job_id)

        job = JOB_STORE.create_job(
            command=command_text,
            action=command.action.value,
            ticker=command.ticker,
        )
        thread = Thread(
            target=_run_job,
            args=(str(job["job_id"]), command),
            daemon=True,
            name=f"asset-job-{job['job_id']}",
        )
        thread.start()

    return job
