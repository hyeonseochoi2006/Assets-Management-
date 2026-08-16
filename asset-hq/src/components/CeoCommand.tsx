import { FormEvent, useState } from 'react'

interface CeoCommandProps {
  busy: boolean
  submitting: boolean
  onSubmit: (command: string) => Promise<void> | void
}

export function CeoCommand({ busy, submitting, onSubmit }: CeoCommandProps) {
  const [command, setCommand] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const cleaned = command.trim()
    if (!cleaned || busy || submitting) return
    await onSubmit(cleaned)
    setCommand('')
  }

  return (
    <section className="command-panel">
      <div>
        <div className="eyebrow">CEO COMMAND</div>
        <h2>회사에 지시하기</h2>
        <p>예: PANW 분석해 · 내 포트폴리오 보여줘 · 내 포트폴리오 점검해</p>
      </div>
      <form onSubmit={submit} className="command-form">
        <input
          value={command}
          onChange={(event) => setCommand(event.target.value)}
          placeholder="PANW 분석해"
          disabled={busy || submitting}
          aria-label="CEO command"
        />
        <button type="submit" disabled={!command.trim() || busy || submitting}>
          {busy ? '업무 진행 중' : submitting ? '전송 중' : '지시 전송'}
        </button>
      </form>
    </section>
  )
}
