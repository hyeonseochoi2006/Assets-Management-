import type { AgentStatus } from '../types'

interface CharacterProps {
  status: AgentStatus
  label: string
  executive?: boolean
}

const statusText: Record<AgentStatus, string> = {
  IDLE: '대기',
  WORKING: '업무 중',
  DONE: '완료',
  ERROR: '문제 발생',
}

export function Character({ status, label, executive = false }: CharacterProps) {
  return (
    <div
      className={`office-character character-${status.toLowerCase()} ${executive ? 'character-executive' : ''}`}
      aria-label={`${label} ${statusText[status]}`}
    >
      <div className="character-thought" aria-hidden="true">
        {status === 'WORKING' ? '···' : status === 'DONE' ? '✓' : status === 'ERROR' ? '!' : 'Z'}
      </div>
      <div className="character-head" aria-hidden="true">
        <span className="character-hair" />
        <span className="character-eye eye-left" />
        <span className="character-eye eye-right" />
      </div>
      <div className="character-body" aria-hidden="true">
        <span className="character-arm arm-left" />
        <span className="character-arm arm-right" />
        <span className="character-torso" />
      </div>
      <div className="character-chair" aria-hidden="true" />
    </div>
  )
}
