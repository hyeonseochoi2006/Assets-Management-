import { useCallback, useEffect, useMemo, useState } from 'react'

import { decideApproval, getApprovalQueue } from '../api/hqApi'
import type { ApprovalDecision, ApprovalItem } from '../types'

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

function categoryLabel(category: ApprovalItem['category']): string {
  switch (category) {
    case 'RISK':
      return '위험'
    case 'OPPORTUNITY':
      return '기회'
    case 'ANALYSIS_REQUEST':
      return '추가 분석'
    case 'DECISION':
      return '결정'
  }
}

function decisionLabel(status: ApprovalItem['status']): string {
  switch (status) {
    case 'PENDING':
      return '대기'
    case 'APPROVED':
      return '승인'
    case 'DEFERRED':
      return '보류'
    case 'REJECTED':
      return '거절'
    case 'ACKNOWLEDGED':
      return '확인 완료'
  }
}

export function ApprovalQueuePanel() {
  const [items, setItems] = useState<ApprovalItem[]>([])
  const [loading, setLoading] = useState(true)
  const [actingId, setActingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notes, setNotes] = useState<Record<string, string>>({})

  const load = useCallback(async () => {
    try {
      const response = await getApprovalQueue()
      setItems(response.items)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'CEO Inbox를 불러오지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(), 15000)
    return () => window.clearInterval(timer)
  }, [load])

  const pending = useMemo(() => items.filter((item) => item.status === 'PENDING'), [items])
  const resolved = useMemo(() => items.filter((item) => item.status !== 'PENDING').slice(0, 5), [items])

  const decide = async (item: ApprovalItem, decision: ApprovalDecision) => {
    setActingId(item.approval_id)
    try {
      await decideApproval(item.approval_id, decision, notes[item.approval_id])
      setNotes((current) => ({ ...current, [item.approval_id]: '' }))
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'CEO 결정을 기록하지 못했습니다.')
    } finally {
      setActingId(null)
    }
  }

  return (
    <section className="approval-panel">
      <div className="approval-heading">
        <div>
          <div className="eyebrow">CEO DECISION INBOX</div>
          <h2>APPROVAL QUEUE</h2>
          <p>회사가 CEO 판단이 필요하다고 올린 안건만 표시합니다.</p>
        </div>
        <div className="approval-count">대기 {pending.length}</div>
      </div>

      <div className="approval-safety-note">
        여기서 승인해도 실제 매수·매도 주문은 실행되지 않습니다. 현재 v1은 CEO 의사결정 기록만 저장합니다.
      </div>

      {error && <div className="approval-error">{error}</div>}
      {loading && items.length === 0 && <div className="approval-empty">CEO Inbox 확인 중...</div>}
      {!loading && pending.length === 0 && (
        <div className="approval-empty">현재 CEO 결정이 필요한 안건이 없습니다.</div>
      )}

      <div className="approval-list">
        {pending.map((item) => {
          const busy = actingId === item.approval_id
          const isRisk = item.category === 'RISK'
          return (
            <article className={`approval-card category-${item.category.toLowerCase()}`} key={item.approval_id}>
              <div className="approval-card-top">
                <div>
                  <span className="approval-category">{categoryLabel(item.category)}</span>
                  <h3>{item.title}</h3>
                </div>
                <time>{formatTime(item.created_at)}</time>
              </div>

              <p className="approval-summary">{item.summary}</p>

              {item.affected_tickers.length > 0 && (
                <div className="approval-tickers">관련 종목 · {item.affected_tickers.join(', ')}</div>
              )}

              {item.reasons.length > 0 && (
                <div className="approval-reasons">
                  <strong>왜 올라왔나</strong>
                  <ul>
                    {item.reasons.map((reason, index) => <li key={`${item.approval_id}-${index}`}>{reason}</li>)}
                  </ul>
                </div>
              )}

              <div className="approval-next-step">
                <span>제안된 다음 행동</span>
                <strong>{item.recommended_next_step || '별도 제안 없음'}</strong>
              </div>

              {item.briefing && (
                <details className="approval-briefing">
                  <summary>CEO 보고서 보기</summary>
                  <pre>{item.briefing}</pre>
                </details>
              )}

              <input
                className="approval-note-input"
                value={notes[item.approval_id] ?? ''}
                onChange={(event) => setNotes((current) => ({
                  ...current,
                  [item.approval_id]: event.target.value,
                }))}
                placeholder="CEO 메모 (선택)"
                maxLength={1000}
                disabled={busy}
              />

              <div className="approval-actions">
                {isRisk ? (
                  <button type="button" className="primary" disabled={busy} onClick={() => void decide(item, 'ACKNOWLEDGED')}>
                    확인
                  </button>
                ) : (
                  <button type="button" className="primary" disabled={busy} onClick={() => void decide(item, 'APPROVED')}>
                    승인
                  </button>
                )}
                <button type="button" disabled={busy} onClick={() => void decide(item, 'DEFERRED')}>보류</button>
                {!isRisk && (
                  <button type="button" className="danger" disabled={busy} onClick={() => void decide(item, 'REJECTED')}>
                    거절
                  </button>
                )}
              </div>
            </article>
          )
        })}
      </div>

      {resolved.length > 0 && (
        <div className="approval-history">
          <div className="approval-history-title">최근 CEO 처리 기록</div>
          {resolved.map((item) => (
            <div className="approval-history-row" key={item.approval_id}>
              <div>
                <strong>{item.title}</strong>
                <span>{categoryLabel(item.category)} · {formatTime(item.decided_at ?? item.created_at)}</span>
              </div>
              <b className={`decision-${item.status.toLowerCase()}`}>{decisionLabel(item.status)}</b>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
