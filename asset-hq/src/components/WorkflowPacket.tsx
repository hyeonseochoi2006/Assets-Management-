import type { CSSProperties } from 'react'

import type { AgentName } from '../types'

export interface Handoff {
  from: AgentName
  to: AgentName
  id: number
}

const roomPoints: Record<AgentName, { x: string; y: string }> = {
  CIO: { x: '75%', y: '14%' },
  Analysis: { x: '25%', y: '39%' },
  Portfolio: { x: '75%', y: '39%' },
  Risk: { x: '25%', y: '64%' },
  Execution: { x: '75%', y: '64%' },
  Briefing: { x: '50%', y: '88%' },
}

export function WorkflowPacket({ handoff }: { handoff: Handoff | null }) {
  if (!handoff) return null

  const from = roomPoints[handoff.from]
  const to = roomPoints[handoff.to]
  const style = {
    '--packet-from-x': from.x,
    '--packet-from-y': from.y,
    '--packet-to-x': to.x,
    '--packet-to-y': to.y,
  } as CSSProperties

  return (
    <>
      <div key={handoff.id} className="workflow-packet" style={style} aria-hidden="true">
        <span className="packet-icon">DATA</span>
      </div>
      <div className="mobile-handoff" role="status">
        업무 전달: {handoff.from.toUpperCase()} → {handoff.to.toUpperCase()}
      </div>
    </>
  )
}
