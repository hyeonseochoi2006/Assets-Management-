export type AgentName =
  | 'CIO'
  | 'Analysis'
  | 'Portfolio'
  | 'Risk'
  | 'Execution'
  | 'Briefing'

export type AgentStatus = 'IDLE' | 'WORKING' | 'DONE' | 'ERROR'
export type JobStatus = 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED'
export type DailyEscalation =
  | 'NONE'
  | 'RISK'
  | 'OPPORTUNITY'
  | 'ANALYSIS_REQUEST'
  | 'DECISION'

export interface AgentState {
  status: AgentStatus
  task: string
  last_completed: string
}

export type AgentMap = Record<AgentName, AgentState>

export interface HQJob {
  job_id: string
  command: string
  action: string
  ticker: string | null
  status: JobStatus
  created_at: string
  started_at: string | null
  completed_at: string | null
  agents: AgentMap
  result_type: string | null
  result: string | null
  error: string | null
}

export interface CreateJobResponse extends HQJob {
  poll_path: string
  hq_state_path: string
}

export interface HQState {
  latest_job_id: string | null
  job_status: JobStatus | 'IDLE'
  command?: string
  ticker?: string | null
  pipeline_order: AgentName[]
  agents: AgentMap
}

export interface HealthResponse {
  status: string
  service: string
  mode: string
  branch: string
}

export interface DailyRunSummary {
  run_id: string
  started_at: string
  completed_at: string | null
  status: JobStatus
  material_change: boolean | null
  escalation: DailyEscalation | null
  ceo_action_required: boolean | null
  summary: string | null
  affected_tickers: string[]
  change_count: number
  finding_count: number
  opportunity_count: number
  opportunity_tickers: string[]
  has_briefing: boolean
  error: string | null
}

export interface DailyHistoryResponse {
  runs: DailyRunSummary[]
}

export const AGENT_NAMES: AgentName[] = [
  'CIO',
  'Analysis',
  'Portfolio',
  'Risk',
  'Execution',
  'Briefing',
]

export const PIPELINE_FALLBACK: AgentName[] = [
  'Analysis',
  'Portfolio',
  'Risk',
  'Execution',
  'CIO',
  'Briefing',
]
