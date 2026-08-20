# Automatic Company Runtime

## Process split

The autonomous company now has two long-lived process roles that share the same
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
- show jobs, reports, approvals, schedule state, and worker health
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

## Current boundary

This step separates recurring automation from the HQ API. Manual CEO-triggered
analysis jobs can still execute from the API process. A later queue-worker phase
can move those manual jobs behind the same worker boundary if desired.

The Worker process still needs an always-on host. Codespaces sleeping will stop
both processes; deployment to an always-on service is a separate infrastructure
step.
