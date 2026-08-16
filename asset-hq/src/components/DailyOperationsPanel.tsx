import { useCallback, useEffect, useState } from 'react'

import { getDailyHistory } from '../api/hqApi'
import type { DailyRunSummary } from '../types'

function formatTime(value: string | null): string {
  if (!value) return '아직 없음'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('ko-KR', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function statusLabel(run: DailyRunSummary): string {
  if (run.status === 'FAILED') return '확인 필요'
  if (run.status === 'RUNNING' || run.status === 'QUEUED') return '업무 중'
  if (run.ceo_action_required) return 'CEO 확인 필요'
  return '정상 완료'
}

function escalationLabel(run: DailyRunSummary): string {
  switch (run.escalation) {
    case 'RISK':
      return '위험'
    case 'OPPORTUNITY':
      return '기회'
    case 'ANALYSIS_REQUEST':
      return '추가 분석'
    case 'DECISION':
      return '결정 필요'
    case 'NONE':
      return '없음'
    default:
      return '판단 전'
  }
}

export function DailyOperationsPanel() {
  const [runs, setRuns] = useState<DailyRunSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const response = await getDailyHistory()
      setRuns(response.runs)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Daily Operations 기록을 불러오지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(), 15000)
    return () => window.clearInterval(timer)
  }, [load])

  const latest = runs[0]

  return (
    <section className="daily-operations-panel">
      <div className="daily-operations-heading">
        <div>
          <div className="eyebrow">AUTONOMOUS COMPANY STATUS</div>
          <h2>DAILY OPERATIONS</h2>
          <p>회사가 스스로 수행한 최근 업무와 CEO 호출 여부입니다.</p>
        </div>
        <button type="button" className="daily-refresh" onClick={() => void load()} disabled={loading}>
          {loading ? '확인 중' : '새로고침'}
        </button>
      </div>

      {error && <div className="daily-error">{error}</div>}

      {!latest && !loading ? (
        <div className="daily-empty">아직 Daily Operations 실행 기록이 없습니다.</div>
      ) : latest ? (
        <>
          <div className="daily-latest-grid">
            <div className="daily-metric">
              <span>마지막 실행</span>
              <strong>{formatTime(latest.completed_at ?? latest.started_at)}</strong>
            </div>
            <div className="daily-metric">
              <span>상태</span>
              <strong className={`daily-run-status status-${latest.status.toLowerCase()}`}>
                {statusLabel(latest)}
              </strong>
            </div>
            <div className="daily-metric">
              <span>CIO 에스컬레이션</span>
              <strong>{escalationLabel(latest)}</strong>
            </div>
            <div className="daily-metric">
              <span>CEO 행동</span>
              <strong>{latest.ceo_action_required ? '필요' : latest.ceo_action_required === false ? '필요 없음' : '판단 전'}</strong>
            </div>
          </div>

          <div className="daily-summary-box">
            <span>오늘 결론</span>
            <strong>{latest.summary ?? latest.error ?? '업무 결과를 정리하는 중입니다.'}</strong>
            <div className="daily-summary-meta">
              <span>포트폴리오 변화 {latest.change_count}</span>
              <span>중요 Finding {latest.finding_count}</span>
              <span>기회 후보 {latest.opportunity_count}</span>
              {latest.opportunity_tickers.length > 0 && (
                <span>후보 {latest.opportunity_tickers.join(', ')}</span>
              )}
              {latest.affected_tickers.length > 0 && (
                <span>CEO 관련 종목 {latest.affected_tickers.join(', ')}</span>
              )}
            </div>
          </div>
        </>
      ) : null}

      {runs.length > 0 && (
        <div className="daily-history">
          <div className="daily-history-title">최근 실행 기록</div>
          {runs.map((run) => (
            <div className="daily-history-row" key={run.run_id}>
              <div>
                <strong>{formatTime(run.completed_at ?? run.started_at)}</strong>
                <span>{run.summary ?? run.error ?? '처리 중'}</span>
                {run.opportunity_count > 0 && (
                  <span>Research candidates: {run.opportunity_tickers.join(', ')}</span>
                )}
              </div>
              <div className="daily-history-right">
                <span>{escalationLabel(run)}</span>
                <b className={`status-${run.status.toLowerCase()}`}>{statusLabel(run)}</b>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
