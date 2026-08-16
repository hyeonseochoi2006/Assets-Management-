import { useEffect, useRef, useState } from 'react'

import type { AgentMap, AgentName } from '../types'
import { AgentRoom } from './AgentRoom'
import { Character } from './Character'
import { Workstation } from './Workstation'
import { WorkflowPacket, type Handoff } from './WorkflowPacket'

interface OfficeFloorProps {
  agents: AgentMap
  pipelineOrder: AgentName[]
  selectedAgent: AgentName
  onSelectAgent: (agent: AgentName) => void
}

export function OfficeFloor({ agents, pipelineOrder, selectedAgent, onSelectAgent }: OfficeFloorProps) {
  const previousAgents = useRef<AgentMap | null>(null)
  const timerRef = useRef<number | null>(null)
  const [handoff, setHandoff] = useState<Handoff | null>(null)

  useEffect(() => {
    const previous = previousAgents.current

    for (let index = 0; index < pipelineOrder.length - 1; index += 1) {
      const from = pipelineOrder[index]
      const to = pipelineOrder[index + 1]
      const activeNow = agents[from].status === 'DONE' && agents[to].status === 'WORKING'
      const activeBefore = previous
        ? previous[from].status === 'DONE' && previous[to].status === 'WORKING'
        : false

      if (activeNow && !activeBefore) {
        if (timerRef.current) window.clearTimeout(timerRef.current)
        setHandoff({ from, to, id: Date.now() })
        timerRef.current = window.setTimeout(() => setHandoff(null), 1500)
        break
      }
    }

    previousAgents.current = agents
  }, [agents, pipelineOrder])

  useEffect(
    () => () => {
      if (timerRef.current) window.clearTimeout(timerRef.current)
    },
    [],
  )

  return (
    <section className="office-stage-wrap">
      <div className="office-stage-heading">
        <div>
          <div className="eyebrow">2.5D LIVE OFFICE</div>
          <h2>Investment Operations Floor</h2>
        </div>
        <span>상태는 실제 Agent API와 동기화됩니다.</span>
      </div>

      <div className="office-floor">
        <WorkflowPacket handoff={handoff} />

        <div className="office-room ceo-visual-office office-slot-ceo">
          <div className="room-wall-glow" />
          <div className="room-header">
            <div>
              <div className="eyebrow">EXECUTIVE OFFICE</div>
              <h3>CEO · YOU</h3>
            </div>
            <span className="authority-badge">FINAL AUTHORITY</span>
          </div>
          <div className="room-scene">
            <Workstation status="IDLE" label="CEO" />
            <Character status="IDLE" label="CEO" executive />
            <div className="room-rug" />
          </div>
          <div className="room-task-summary">
            <span>ROLE</span>
            <strong>보고 확인 · 승인 · 보류 · 거절</strong>
          </div>
        </div>

        <div className="office-slot-cio">
          <AgentRoom agent="CIO" state={agents.CIO} selected={selectedAgent === 'CIO'} onSelect={onSelectAgent} />
        </div>
        <div className="office-slot-analysis">
          <AgentRoom agent="Analysis" state={agents.Analysis} selected={selectedAgent === 'Analysis'} onSelect={onSelectAgent} />
        </div>
        <div className="office-slot-portfolio">
          <AgentRoom agent="Portfolio" state={agents.Portfolio} selected={selectedAgent === 'Portfolio'} onSelect={onSelectAgent} />
        </div>
        <div className="office-slot-risk">
          <AgentRoom agent="Risk" state={agents.Risk} selected={selectedAgent === 'Risk'} onSelect={onSelectAgent} />
        </div>
        <div className="office-slot-execution">
          <AgentRoom agent="Execution" state={agents.Execution} selected={selectedAgent === 'Execution'} onSelect={onSelectAgent} />
        </div>
        <div className="office-slot-briefing">
          <AgentRoom agent="Briefing" state={agents.Briefing} selected={selectedAgent === 'Briefing'} onSelect={onSelectAgent} />
        </div>

        <div className="office-corridor corridor-vertical" aria-hidden="true" />
        <div className="office-corridor corridor-horizontal-one" aria-hidden="true" />
        <div className="office-corridor corridor-horizontal-two" aria-hidden="true" />
      </div>
    </section>
  )
}
