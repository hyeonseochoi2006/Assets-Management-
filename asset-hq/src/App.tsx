import { useEffect, useState } from 'react'

import { getHealth } from './api/hqApi'
import { ApprovalQueuePanel } from './components/ApprovalQueuePanel'
import { CeoCommand } from './components/CeoCommand'
import { DailyOperationsPanel } from './components/DailyOperationsPanel'
import { LoginGate } from './components/LoginGate'
import { OfficeFloor } from './components/OfficeFloor'
import { ReportPanel } from './components/ReportPanel'
import { Workflow } from './components/Workflow'
import { OfficeWorld } from './3d/OfficeWorld'
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

type HQView = '3d' | 'dashboard'

function HQApplication() {
  const { job, hqState, submitting, error, start } = useJobStatus()
  const [selectedAgent, setSelectedAgent] = useState<AgentName>('CIO')
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthError, setHealthError] = useState(false)
  const [view, setView] = useState<HQView>('3d')

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
          <p>CEO 명령과 회사의 자율 Daily Operations를 실제 AI 부서가 처리합니다.</p>
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
        <div className="view-switcher" role="group" aria-label="HQ view">
          <button type="button" className={view === '3d' ? 'active' : ''} onClick={() => setView('3d')}>
            3D HQ
          </button>
          <button type="button" className={view === 'dashboard' ? 'active' : ''} onClick={() => setView('dashboard')}>
            Dashboard
          </button>
        </div>

        <Workflow order={pipelineOrder} agents={agents} />
        <DailyOperationsPanel />
        <ApprovalQueuePanel />

        {view === '3d' ? (
          <OfficeWorld
            agents={agents}
            pipelineOrder={pipelineOrder}
            selectedAgent={selectedAgent}
            onSelectAgent={setSelectedAgent}
          />
        ) : (
          <OfficeFloor
            agents={agents}
            pipelineOrder={pipelineOrder}
            selectedAgent={selectedAgent}
            onSelectAgent={setSelectedAgent}
          />
        )}

        <section className="office-inspector-row">
          <aside className="inspector-panel">
            <div className="eyebrow">AGENT INSPECTOR</div>
            <div className="inspector-heading">
              <h2>{selectedAgent.toUpperCase()}</h2>
              <div className={`inspector-status status-${selected.status.toLowerCase()}`}>
                <span className="status-dot" /> {selected.status}
              </div>
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

          <div className="office-guide-panel">
            <div className="eyebrow">HOW TO READ THE OFFICE</div>
            <div className="guide-items">
              <span><i className="guide-dot idle" /> IDLE · 대기</span>
              <span><i className="guide-dot working" /> WORKING · 실제 업무 중</span>
              <span><i className="guide-dot done" /> DONE · 완료</span>
              <span><i className="guide-dot error" /> ERROR · 확인 필요</span>
            </div>
            <p>3D 직원 또는 아래 직원 이름을 누르면 Inspector에서 현재 업무를 확인할 수 있습니다.</p>
          </div>
        </section>

        <CeoCommand busy={busy} submitting={submitting} onSubmit={start} />
        <ReportPanel job={job} />
      </main>
    </div>
  )
}

export default function App() {
  return (
    <LoginGate>
      <HQApplication />
    </LoginGate>
  )
}
