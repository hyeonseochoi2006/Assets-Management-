export type AgentName =
  | 'CIO'
  | 'Analysis'
  | 'Portfolio'
  | 'Risk'
  | 'Execution'
  | 'Briefing'

export type AgentStatus = 'IDLE' | 'WORKING' | 'DONE' | 'ERROR'
export type JobStatus = 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'INTERRUPTED'
export type DailyEscalation =
  | 'NONE'
  | 'RISK'
  | 'OPPORTUNITY'
  | 'ANALYSIS_REQUEST'
  | 'DECISION'

export type ApprovalStatus =
  | 'PENDING'
  | 'APPROVED'
  | 'DEFERRED'
  | 'REJECTED'
  | 'ACKNOWLEDGED'

export type ApprovalDecision = Exclude<ApprovalStatus, 'PENDING'>

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
  retry_of: string | null
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

export interface AuthCheckResponse {
  authenticated: true
}

export interface DailyRunSummary {
  run_id: string
  started_at: string
  completed_at: string | null
  status: JobStatus
  run_kind: 'SCAN' | 'CLOSE'
  material_change: boolean | null
  escalation: DailyEscalation | null
  ceo_action_required: boolean | null
  summary: string | null
  affected_tickers: string[]
  change_count: number
  external_event_count: number
  gate_decision: 'SKIP_AI' | 'TARGETED_REVIEW' | 'CIO_REVIEW' | null
  ai_called: boolean | null
  finding_count: number
  opportunity_count: number
  opportunity_tickers: string[]
  has_briefing: boolean
  error: string | null
}

export interface DailyHistoryResponse {
  runs: DailyRunSummary[]
}

export type DailyScheduleEventStatus = JobStatus | 'SKIPPED'

export interface DailyScheduleEvent {
  schedule_key: string
  scheduled_for: string
  timezone: string
  status: DailyScheduleEventStatus
  job_id: string | null
  reason: string | null
  created_at: string
  updated_at: string
}

export interface DailyScheduleResponse {
  enabled: boolean
  daily_time: string | null
  scan_times: string[]
  schedule_times: Array<{
    run_kind: 'SCAN' | 'CLOSE'
    time: string | null
  }>
  timezone: string | null
  misfire_grace_minutes: number
  next_run_at: string | null
  recent_events: DailyScheduleEvent[]
}

export interface ApprovalItem {
  approval_id: string
  run_id: string
  category: Exclude<DailyEscalation, 'NONE'>
  title: string
  summary: string
  reasons: string[]
  affected_tickers: string[]
  recommended_next_step: string
  briefing: string | null
  status: ApprovalStatus
  created_at: string
  decided_at: string | null
  decision_note: string | null
}

export interface ApprovalQueueResponse {
  items: ApprovalItem[]
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
