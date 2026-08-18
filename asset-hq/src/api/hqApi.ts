import type {
  ApprovalDecision,
  ApprovalItem,
  ApprovalQueueResponse,
  CreateJobResponse,
  DailyHistoryResponse,
  HealthResponse,
  HQJob,
  HQState,
  AuthCheckResponse,
} from '../types'

const API_TOKEN_STORAGE_KEY = 'asset-hq-api-token'
export const AUTH_EXPIRED_EVENT = 'asset-hq-auth-expired'

export function getStoredApiToken(): string | null {
  return window.sessionStorage.getItem(API_TOKEN_STORAGE_KEY)
}

export function clearStoredApiToken(): void {
  window.sessionStorage.removeItem(API_TOKEN_STORAGE_KEY)
}

function notifyAuthenticationExpired(): void {
  clearStoredApiToken()
  window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
}

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

async function authorizedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
  tokenOverride?: string,
): Promise<Response> {
  const token = tokenOverride ?? getStoredApiToken()
  if (!token) {
    notifyAuthenticationExpired()
    throw new Error('CEO 인증이 필요합니다.')
  }

  const headers = new Headers(init.headers)
  headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(input, { ...init, headers })

  if (response.status === 401) {
    notifyAuthenticationExpired()
  }
  return response
}

export async function authenticate(apiToken: string): Promise<AuthCheckResponse> {
  const cleanedToken = apiToken.trim()
  if (!cleanedToken) {
    throw new Error('API 토큰을 입력하세요.')
  }

  const response = await authorizedFetch(
    '/api/v1/auth/check',
    { cache: 'no-store' },
    cleanedToken,
  )
  const result = await readJson<AuthCheckResponse>(response)
  window.sessionStorage.setItem(API_TOKEN_STORAGE_KEY, cleanedToken)
  return result
}

export async function checkAuthentication(): Promise<AuthCheckResponse> {
  const response = await authorizedFetch('/api/v1/auth/check', {
    cache: 'no-store',
  })
  return readJson<AuthCheckResponse>(response)
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch('/api/v1/health', { cache: 'no-store' })
  return readJson<HealthResponse>(response)
}

export async function createJob(command: string): Promise<CreateJobResponse> {
  const response = await authorizedFetch('/api/v1/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command }),
  })
  return readJson<CreateJobResponse>(response)
}

export async function getJob(jobId: string): Promise<HQJob> {
  const response = await authorizedFetch(`/api/v1/jobs/${encodeURIComponent(jobId)}`, {
    cache: 'no-store',
  })
  return readJson<HQJob>(response)
}

export async function getHQState(): Promise<HQState> {
  const response = await authorizedFetch('/api/v1/hq/state', { cache: 'no-store' })
  return readJson<HQState>(response)
}

export async function getDailyHistory(): Promise<DailyHistoryResponse> {
  const response = await authorizedFetch('/api/v1/operations/daily/history', {
    cache: 'no-store',
  })
  return readJson<DailyHistoryResponse>(response)
}

export async function getApprovalQueue(): Promise<ApprovalQueueResponse> {
  const response = await authorizedFetch('/api/v1/approvals?limit=20', {
    cache: 'no-store',
  })
  return readJson<ApprovalQueueResponse>(response)
}

export async function decideApproval(
  approvalId: string,
  decision: ApprovalDecision,
  note?: string,
): Promise<ApprovalItem> {
  const response = await authorizedFetch(
    `/api/v1/approvals/${encodeURIComponent(approvalId)}/decision`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, note: note?.trim() || null }),
    },
  )
  return readJson<ApprovalItem>(response)
}
