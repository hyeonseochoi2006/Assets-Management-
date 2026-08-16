export type AgentName =
  | 'CIO'
  | 'Analysis'
  | 'Portfolio'
  | 'Risk'
  | 'Execution'
  | 'Briefing'

export type AgentStatus = 'IDLE' | 'WORKING' | 'DONE' | 'ERROR'
export type JobStatus = 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED'

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
