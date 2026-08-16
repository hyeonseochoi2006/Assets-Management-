import type { HQJob } from '../types'

interface ReportPanelProps {
  job: HQJob | null
}

export function ReportPanel({ job }: ReportPanelProps) {
  if (!job) {
    return (
      <section className="report-panel empty-panel">
        <div className="eyebrow">CEO REPORT</div>
        <h2>아직 도착한 보고서가 없습니다.</h2>
        <p>CEO 명령을 보내면 각 부서가 일한 뒤 이곳에 최종 결과가 도착합니다.</p>
      </section>
    )
  }

  if (job.status === 'FAILED') {
    return (
      <section className="report-panel error-panel">
        <div className="eyebrow">CEO REPORT · FAILED</div>
        <h2>업무가 중단되었습니다.</h2>
        <pre>{job.error ?? 'Unknown error'}</pre>
      </section>
    )
  }

  if (job.status !== 'COMPLETED') {
    return (
      <section className="report-panel working-panel">
        <div className="eyebrow">CEO REPORT · IN PROGRESS</div>
        <h2>{job.command}</h2>
        <p>각 부서가 순서대로 업무를 처리하고 있습니다. 완료되면 최종 보고서가 자동으로 표시됩니다.</p>
      </section>
    )
  }

  return (
    <section className="report-panel complete-panel">
      <div className="report-heading">
        <div>
          <div className="eyebrow">CEO REPORT · ARRIVED</div>
          <h2>{job.ticker ? `${job.ticker} 최종 보고` : '최종 보고'}</h2>
        </div>
        <span className="complete-chip">COMPLETED</span>
      </div>
      <pre className="report-content">{job.result ?? '결과 없음'}</pre>
      <p className="final-authority">최종 투자 결정은 CEO가 합니다. 이 시스템은 실제 주문을 실행하지 않습니다.</p>
    </section>
  )
}
