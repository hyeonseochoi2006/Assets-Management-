import type {
  ApprovalDecision,
  ApprovalItem,
  ApprovalQueueResponse,
  CreateJobResponse,
  DailyHistoryResponse,
  HealthResponse,
  HQJob,
  HQState,
} from '../types'

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      detail = typeof body?.detail === 'string' ? body.detail : JSON.stringify(body?.detail ?? body)
    } catch {
      // Keep the HTTP status text when the response is not JSON.
    }
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch('/api/v1/health', { cache: 'no-store' })
  return readJson<HealthResponse>(response)
}

export async function createJob(command: string): Promise<CreateJobResponse> {
  const response = await fetch('/api/v1/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command }),
  })
  return readJson<CreateJobResponse>(response)
}

export async function getJob(jobId: string): Promise<HQJob> {
  const response = await fetch(`/api/v1/jobs/${encodeURIComponent(jobId)}`, {
    cache: 'no-store',
  })
  return readJson<HQJob>(response)
}

export async function getHQState(): Promise<HQState> {
  const response = await fetch('/api/v1/hq/state', { cache: 'no-store' })
  return readJson<HQState>(response)
}

export async function getDailyHistory(): Promise<DailyHistoryResponse> {
  const response = await fetch('/api/v1/operations/daily/history', {
    cache: 'no-store',
  })
  return readJson<DailyHistoryResponse>(response)
}

export async function getApprovalQueue(): Promise<ApprovalQueueResponse> {
  const response = await fetch('/api/v1/approvals?limit=20', {
    cache: 'no-store',
  })
  return readJson<ApprovalQueueResponse>(response)
}

export async function decideApproval(
  approvalId: string,
  decision: ApprovalDecision,
  note?: string,
): Promise<ApprovalItem> {
  const response = await fetch(
    `/api/v1/approvals/${encodeURIComponent(approvalId)}/decision`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, note: note?.trim() || null }),
    },
  )
  return readJson<ApprovalItem>(response)
}
