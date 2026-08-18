import type { HQJob } from '../types'

interface ReportPanelProps {
  job: HQJob | null
  retrying: boolean
  onRetry: () => Promise<void> | void
}

export function ReportPanel({ job, retrying, onRetry }: ReportPanelProps) {
  if (!job) {
    return (
      <section className="report-panel empty-panel">
        <div className="eyebrow">CEO REPORT</div>
        <h2>아직 도착한 보고서가 없습니다.</h2>
        <p>CEO 명령을 보내면 각 부서가 일한 뒤 이곳에 최종 결과가 도착합니다.</p>
      </section>
    )
  }

  if (job.status === 'FAILED' || job.status === 'INTERRUPTED') {
    const interrupted = job.status === 'INTERRUPTED'
    return (
      <section className="report-panel error-panel">
        <div className="eyebrow">CEO REPORT · {job.status}</div>
        <h2>{interrupted ? '서버 재시작으로 업무가 중단되었습니다.' : '업무 처리 중 오류가 발생했습니다.'}</h2>
        <pre>{job.error ?? 'Unknown error'}</pre>
        <p>기존 기록은 보존됩니다. 재실행하면 연결된 새 작업이 생성됩니다.</p>
        <button type="button" onClick={() => void onRetry()} disabled={retrying}>
          {retrying ? '재실행 준비 중' : '안전하게 다시 실행'}
        </button>
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
