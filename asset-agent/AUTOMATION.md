# Automatic Company Runtime

## Process split

The autonomous company has two long-lived process roles that share the same
`operations.db` database.

```text
Asset HQ / Browser
        |
        v
   FastAPI HQ
        |
        v
operations.db <---- Asset Worker
                     |
                     v
                 Scheduler
                     |
                     v
             Daily Operations
```

### FastAPI HQ

Responsibilities:

- authenticate the CEO
- show jobs, reports, approvals, schedule state, worker health, and workflow checkpoints
- accept CEO commands and approval decisions
- never own the recurring scheduler
- never place, modify, or cancel brokerage orders

Start it with:

```bash
export ASSET_API_TOKEN="your-generated-32-character-or-longer-token"
python -m uvicorn api.app:app --host 127.0.0.1 --port 8000
```

### Asset Worker

Responsibilities:

- own the recurring Daily Scheduler
- recover expired automatic work leases
- auto-resume interrupted scheduled SCAN/CLOSE jobs from durable checkpoints
- run scheduled SCAN/CLOSE jobs
- publish a durable heartbeat and scheduler snapshot into `operations.db`
- stop safely on SIGINT/SIGTERM
- refuse to become a second live scheduler worker while another lease is valid

Start it separately with:

```bash
python worker.py
```

The API and Worker must point to the same durable runtime directory:

```bash
export ASSET_RUNTIME_DIR="/durable/private/path"
```

## Durable workflow checkpoints

Daily Operations persists these checkpoints in `operations.db`:

```text
SNAPSHOT_READY
      ↓
DATA_READY
      ↓
MONITORING_READY
      ↓
CIO_READY
      ↓
BRIEFING_READY
      ↓
APPROVAL_READY
```

`SNAPSHOT_READY` freezes the exact Toss portfolio observation and the exact
reference snapshots used for comparison. A process restart therefore does not
fetch a newer portfolio and accidentally count the restart as another market
observation.

`DATA_READY` freezes deterministic portfolio changes, official-source checks,
the change-event ledger result, and the AI analysis gate. `MONITORING_READY`,
`CIO_READY`, and `BRIEFING_READY` persist expensive AI outputs so a restart does
not spend tokens again for work that already completed. `APPROVAL_READY`
preserves whether a CEO approval request was created.

Each checkpoint stores status, payload, timestamps, attempt count, and error.
The authenticated HQ API exposes checkpoint state through:

```text
GET /api/v1/operations/daily/latest
GET /api/v1/operations/daily/{run_id}/checkpoints
```

## Crash recovery behavior

When the automatic Worker starts:

1. expired job leases become `INTERRUPTED`;
2. only scheduled SYSTEM Daily jobs with a real `schedule_key` are eligible for automatic resume;
3. manual CEO jobs and manually triggered Daily validation jobs are not silently resumed;
4. the same Daily `run_id` is reopened and its `resume_count` is incremented;
5. completed checkpoints are reused;
6. the first incomplete checkpoint is retried;
7. if the Daily run had already completed and only the outer job record was interrupted, the job record is repaired without repeating analysis.

Official SEC ingestion is also run-aware. A filing first stored by a Daily run
is returned again when that same run resumes after a crash, but it is not
reported again to genuinely later runs. This closes the failure window where a
filing could otherwise be durably stored and then disappear from the resumed
workflow before its checkpoint was written.

Automatic recovery does not turn software exceptions into infinite retries. A
normal caught exception becomes `FAILED`; automatic checkpoint resume is for
process interruption / expired leases. Bounded retry/backoff for external APIs
is a separate resilience step.

## Schedule configuration

The automatic worker reads the existing schedule variables:

```bash
export ASSET_DAILY_SCHEDULE_ENABLED="true"
export ASSET_DAILY_SCAN_TIMES="08:30,12:30"
export ASSET_DAILY_TIME="17:30"
export ASSET_TIMEZONE="America/New_York"
export ASSET_DAILY_MISFIRE_GRACE_MINUTES="120"
```

The scheduler remains disabled unless explicitly enabled.

## Worker health

The Worker stores a lease and heartbeat in the shared database. The authenticated
HQ API exposes it at:

```text
GET /api/v1/worker/status
```

The Daily schedule endpoint also includes the Worker state:

```text
GET /api/v1/operations/daily/schedule
```

Important states:

- `RUNNING`: live Worker lease and recent heartbeat
- `STALE`: database says RUNNING but the lease expired
- `STOPPED`: Worker shut down deliberately or after an error
- `NOT_STARTED`: no Worker has registered yet

Only one live scheduler Worker may hold the lease. A replacement Worker may take
over after the previous lease expires.

## Automated smoke checks

`.github/workflows/automation-smoke.yml` compiles the automation modules and
runs focused tests for:

- Worker lease / heartbeat ownership
- scheduler idempotency
- durable checkpoints
- interrupted scheduled-job recovery
- checkpoint-based Daily Runner resume
- resume-safe external filing ingestion
- autonomous company operating-policy invariants

## Current boundary

Recurring automation is separated from the HQ API and scheduled Daily work can
resume from durable checkpoints. Manual CEO-triggered analysis jobs can still
execute from the API process. A later queue-worker phase can move those manual
jobs behind the same worker boundary if desired.

The Worker process still needs an always-on host. Codespaces sleeping will stop
both processes; deployment to an always-on service is a separate infrastructure
step.
