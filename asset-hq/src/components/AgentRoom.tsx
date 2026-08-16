import type { AgentName, AgentState } from '../types'

const labels: Record<AgentName, { title: string; role: string; icon: string }> = {
  CIO: { title: 'CIO', role: '부서 의견 통합 · CEO 판단자료', icon: 'C' },
  Analysis: { title: 'ANALYSIS', role: '기업 · 산업 · 재무 · 밸류에이션', icon: 'A' },
  Portfolio: { title: 'PORTFOLIO', role: '계좌 적합성 · 비중 · 집중도', icon: 'P' },
  Risk: { title: 'RISK', role: '하방 위험 · 한도 · 정책 검토', icon: 'R' },
  Execution: { title: 'EXECUTION', role: '진입 방식 · 실행 조건 검토', icon: 'E' },
  Briefing: { title: 'BRIEFING', role: '한국어 CEO 최종 보고', icon: 'B' },
}

interface AgentRoomProps {
  agent: AgentName
  state: AgentState
  selected: boolean
  onSelect: (agent: AgentName) => void
}

export function AgentRoom({ agent, state, selected, onSelect }: AgentRoomProps) {
  const label = labels[agent]

  return (
    <button
      type="button"
      className={`agent-room status-${state.status.toLowerCase()} ${selected ? 'selected' : ''}`}
      onClick={() => onSelect(agent)}
    >
      <div className="agent-room-top">
        <div className="agent-avatar" aria-hidden="true">{label.icon}</div>
        <div>
          <div className="eyebrow">OFFICE / DEPARTMENT</div>
          <h3>{label.title}</h3>
        </div>
        <div className="status-badge">
          <span className="status-dot" />
          {state.status}
        </div>
      </div>
      <p className="agent-role">{label.role}</p>
      <div className="task-box">
        <span>CURRENT TASK</span>
        <strong>{state.task || '대기 중'}</strong>
      </div>
    </button>
  )
}
