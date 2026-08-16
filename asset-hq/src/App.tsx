import { useEffect, useState } from 'react'

import { getHealth } from './api/hqApi'
import { AgentRoom } from './components/AgentRoom'
import { CeoCommand } from './components/CeoCommand'
import { ReportPanel } from './components/ReportPanel'
import { Workflow } from './components/Workflow'
import { useJobStatus } from './hooks/useJobStatus'
import type { AgentMap, AgentName, HealthResponse } from './types'
import { PIPELINE_FALLBACK } from './types'

const EMPTY_AGENTS: AgentMap = {
  CIO: { status: 'IDLE', task: '대기 중', last_completed: '아직 완료된 업무 없음' },
  Analysis: { status: 'IDLE', task: '대기 중', last_completed: '아직 완료된 업무 없음' },
  Portfolio: { status: 'IDLE', task: '대기 중', last_completed: '아직 완료된 업무 없음' },
  Risk: { status: 'IDLE', task: '대기 중', last_completed: '아직 완료된 업무 없음' },
  Execution: { status: 'IDLE', task: '대기 중', last_completed: '아직 완료된 업무 없음' },
  Briefing: { status: 'IDLE', task: '대기 중', last_completed: '아직 완료된 업무 없음' },
}

export default function App() {
  const { job, hqState, submitting, error, start } = useJobStatus()
  const [selectedAgent, setSelectedAgent] = useState<AgentName>('CIO')
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthError, setHealthError] = useState(false)

  useEffect(() => {
    getHealth()
      .then((value) => {
        setHealth(value)
        setHealthError(false)
      })
      .catch(() => setHealthError(true))
  }, [])

  const agents = job?.agents ?? hqState?.agents ?? EMPTY_AGENTS
  const pipelineOrder = hqState?.pipeline_order ?? PIPELINE_FALLBACK
  const busy = job?.status === 'QUEUED' || job?.status === 'RUNNING'
  const selected = agents[selectedAgent]

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">PRIVATE INVESTMENT OPERATING SYSTEM</div>
          <h1>ASSET MANAGEMENT HQ</h1>
          <p>CEO 명령을 실제 AI 부서가 순서대로 처리합니다.</p>
        </div>
        <div className="system-status">
          <span className={`connection-dot ${healthError ? 'offline' : health ? 'online' : 'checking'}`} />
          <div>
            <strong>{healthError ? 'API OFFLINE' : health ? 'HQ ONLINE' : 'CHECKING'}</strong>
            <span>{health ? `${health.mode} · ${health.branch}` : 'FastAPI connection'}</span>
          </div>
        </div>
      </header>

      {(error || healthError) && (
        <div className="alert-bar">
          {error ?? 'FastAPI에 연결할 수 없습니다. API 서버 상태를 확인하세요.'}
        </div>
      )}

      <main>
        <Workflow order={pipelineOrder} agents={agents} />

        <section className="executive-floor">
          <div className="ceo-office">
            <div className="ceo-office-top">
              <div className="ceo-avatar">CEO</div>
              <div>
                <div className="eyebrow">EXECUTIVE OFFICE</div>
                <h3>CEO · YOU</h3>
              </div>
              <span className="authority-badge">FINAL AUTHORITY</span>
            </div>
            <p>투자정책을 승인하고 모든 최종 투자 결정을 내립니다.</p>
            <div className="task-box">
              <span>ROLE</span>
              <strong>보고 확인 · 승인 · 보류 · 거절</strong>
            </div>
          </div>
          <AgentRoom agent="CIO" state={agents.CIO} selected={selectedAgent === 'CIO'} onSelect={setSelectedAgent} />
        </section>

        <div className="floor-divider"><span>DELEGATION</span></div>

        <section className="department-grid">
          <AgentRoom agent="Analysis" state={agents.Analysis} selected={selectedAgent === 'Analysis'} onSelect={setSelectedAgent} />
          <AgentRoom agent="Portfolio" state={agents.Portfolio} selected={selectedAgent === 'Portfolio'} onSelect={setSelectedAgent} />
          <AgentRoom agent="Risk" state={agents.Risk} selected={selectedAgent === 'Risk'} onSelect={setSelectedAgent} />
          <AgentRoom agent="Execution" state={agents.Execution} selected={selectedAgent === 'Execution'} onSelect={setSelectedAgent} />
        </section>

        <div className="floor-divider"><span>REPORTING</span></div>

        <section className="briefing-floor">
          <AgentRoom agent="Briefing" state={agents.Briefing} selected={selectedAgent === 'Briefing'} onSelect={setSelectedAgent} />
          <aside className="inspector-panel">
            <div className="eyebrow">AGENT INSPECTOR</div>
            <h2>{selectedAgent.toUpperCase()}</h2>
            <div className={`inspector-status status-${selected.status.toLowerCase()}`}>
              <span className="status-dot" /> {selected.status}
            </div>
            <dl>
              <div>
                <dt>현재 업무</dt>
                <dd>{selected.task}</dd>
              </div>
              <div>
                <dt>최근 완료</dt>
                <dd>{selected.last_completed}</dd>
              </div>
            </dl>
          </aside>
        </section>

        <CeoCommand busy={busy} submitting={submitting} onSubmit={start} />
        <ReportPanel job={job} />
      </main>
    </div>
  )
}
