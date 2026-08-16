import type { AgentMap, AgentName } from '../types'

interface WorkflowProps {
  order: AgentName[]
  agents: AgentMap
}

export function Workflow({ order, agents }: WorkflowProps) {
  return (
    <section className="workflow-panel" aria-label="Live workflow">
      <div className="eyebrow">LIVE WORKFLOW</div>
      <div className="workflow-row">
        {order.map((agent, index) => (
          <div className="workflow-step-wrap" key={agent}>
            <div className={`workflow-step status-${agents[agent].status.toLowerCase()}`}>
              <span className="status-dot" />
              <span>{agent.toUpperCase()}</span>
            </div>
            {index < order.length - 1 && <span className="workflow-arrow">→</span>}
          </div>
        ))}
      </div>
    </section>
  )
}
