import { useCallback, useEffect, useState } from 'react'

import { createJob, getHQState, getJob } from '../api/hqApi'
import type { HQJob, HQState } from '../types'

export function useJobStatus() {
  const [job, setJob] = useState<HQJob | null>(null)
  const [hqState, setHqState] = useState<HQState | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refreshHQ = useCallback(async () => {
    try {
      const state = await getHQState()
      setHqState(state)
      if (state.latest_job_id) {
        const latestJob = await getJob(state.latest_job_id)
        setJob(latestJob)
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    }
  }, [])

  useEffect(() => {
    void refreshHQ()
  }, [refreshHQ])

  useEffect(() => {
    if (!job || (job.status !== 'QUEUED' && job.status !== 'RUNNING')) {
      return
    }

    const timer = window.setInterval(async () => {
      try {
        const next = await getJob(job.job_id)
        setJob(next)
        setHqState((previous) =>
          previous
            ? {
                ...previous,
                latest_job_id: next.job_id,
                job_status: next.status,
                command: next.command,
                ticker: next.ticker,
                agents: next.agents,
              }
            : previous,
        )
        if (next.status === 'COMPLETED' || next.status === 'FAILED') {
          window.clearInterval(timer)
        }
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : String(exc))
      }
    }, 1000)

    return () => window.clearInterval(timer)
  }, [job?.job_id, job?.status])

  const start = useCallback(async (command: string) => {
    const cleaned = command.trim()
    if (!cleaned) return

    setSubmitting(true)
    setError(null)
    try {
      const created = await createJob(cleaned)
      setJob(created)
      setHqState((previous) =>
        previous
          ? {
              ...previous,
              latest_job_id: created.job_id,
              job_status: created.status,
              command: created.command,
              ticker: created.ticker,
              agents: created.agents,
            }
          : previous,
      )
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setSubmitting(false)
    }
  }, [])

  return {
    job,
    hqState,
    submitting,
    error,
    start,
    refreshHQ,
  }
}
