import type { AgentStatus } from '../types'

interface WorkstationProps {
  status: AgentStatus
  label: string
}

export function Workstation({ status, label }: WorkstationProps) {
  const screenText =
    status === 'WORKING'
      ? 'PROCESSING'
      : status === 'DONE'
        ? 'COMPLETE'
        : status === 'ERROR'
          ? 'ERROR'
          : 'STANDBY'

  return (
    <div className={`workstation workstation-${status.toLowerCase()}`} aria-label={`${label} workstation ${screenText}`}>
      <div className="monitor">
        <div className="monitor-screen">
          <span className="monitor-dot" />
          <strong>{screenText}</strong>
          <div className="screen-lines" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
        </div>
        <div className="monitor-stand" />
      </div>
      <div className="desk-surface">
        <span className="keyboard" />
        <span className="desk-light" />
      </div>
      <div className="desk-legs" aria-hidden="true">
        <span />
        <span />
      </div>
    </div>
  )
}
