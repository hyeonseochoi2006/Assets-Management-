import { type FormEvent, type ReactNode, useEffect, useState } from 'react'

import {
  AUTH_EXPIRED_EVENT,
  authenticate,
  checkAuthentication,
  clearStoredApiToken,
  getStoredApiToken,
} from '../api/hqApi'

type AuthState = 'checking' | 'authenticated' | 'signed-out'

interface LoginGateProps {
  children: ReactNode
}

export function LoginGate({ children }: LoginGateProps) {
  const [authState, setAuthState] = useState<AuthState>('checking')
  const [token, setToken] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    const handleExpired = () => {
      setAuthState('signed-out')
      setToken('')
      setError('인증이 만료되었거나 토큰이 올바르지 않습니다.')
    }
    window.addEventListener(AUTH_EXPIRED_EVENT, handleExpired)

    if (!getStoredApiToken()) {
      setAuthState('signed-out')
    } else {
      checkAuthentication()
        .then(() => {
          setAuthState('authenticated')
          setError(null)
        })
        .catch(() => setAuthState('signed-out'))
    }

    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handleExpired)
  }, [])

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await authenticate(token)
      setToken('')
      setAuthState('authenticated')
    } catch {
      setError('토큰을 확인할 수 없습니다. Codespaces Secret 설정을 확인하세요.')
    } finally {
      setSubmitting(false)
    }
  }

  const signOut = () => {
    clearStoredApiToken()
    setAuthState('signed-out')
    setToken('')
    setError(null)
  }

  if (authState === 'checking') {
    return (
      <main className="login-shell" aria-live="polite">
        <div className="login-card">
          <div className="login-lock" aria-hidden="true">HQ</div>
          <div className="eyebrow">PRIVATE INVESTMENT OPERATING SYSTEM</div>
          <h1>CEO 인증 확인 중</h1>
          <p>보호된 HQ 세션을 확인하고 있습니다.</p>
        </div>
      </main>
    )
  }

  if (authState === 'signed-out') {
    return (
      <main className="login-shell">
        <form className="login-card" onSubmit={submit}>
          <div className="login-lock" aria-hidden="true">HQ</div>
          <div className="eyebrow">AUTHORIZED CEO ACCESS ONLY</div>
          <h1>Asset Management HQ</h1>
          <p>Codespaces Secret에 등록한 API 토큰을 입력하세요.</p>

          <label className="login-field">
            <span>API TOKEN</span>
            <input
              type="password"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              autoComplete="current-password"
              autoFocus
              minLength={32}
              required
              disabled={submitting}
            />
          </label>

          {error && <div className="login-error" role="alert">{error}</div>}

          <button type="submit" className="login-submit" disabled={submitting || token.trim().length < 32}>
            {submitting ? '인증 확인 중' : 'HQ 입장'}
          </button>
          <small>토큰은 현재 브라우저 탭의 세션 저장소에만 보관됩니다.</small>
        </form>
      </main>
    )
  }

  return (
    <>
      <button type="button" className="session-sign-out" onClick={signOut}>
        CEO 로그아웃
      </button>
      {children}
    </>
  )
}
