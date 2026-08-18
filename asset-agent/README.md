# Asset Management Agent

Company-style personal, read-only investment decision-support system.

```text
asset-agent/
├── main.py
├── ceo_desk/
│   ├── app.py
│   └── command_router.py
├── executive/
│   └── cio.py
├── departments/
│   ├── analysis.py
│   ├── portfolio.py
│   ├── risk.py
│   └── execution.py
├── data/
│   ├── toss_client.py
│   └── portfolio_monitor.py
├── policies/
│   └── investment_policy.py
├── reporting/
│   └── briefing.py
└── requirements.txt
```

## Company flow

CEO Desk -> CIO -> Analysis -> Portfolio -> Risk -> Execution -> CIO Brief -> CEO decision

Live portfolio data comes from Toss Securities Open API in read-only mode.
The system does not place, modify, or cancel brokerage orders.

## CEO Desk

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the CEO Desk:

```bash
python -m streamlit run ceo_desk/app.py
```

## FastAPI HQ

The HQ API requires a server-side Bearer token containing at least 32
characters. Do not commit this value or expose it through frontend environment
variables.

```bash
export ASSET_API_TOKEN="your-generated-32-character-or-longer-token"
python -m uvicorn api.app:app --host 127.0.0.1 --port 8000
```

Only the health endpoint is public:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

All portfolio, job, Daily Operations, HQ state, and CEO approval endpoints
require the token:

```bash
curl \
  -H "Authorization: Bearer $ASSET_API_TOKEN" \
  http://127.0.0.1:8000/api/v1/hq/state
```

HQ jobs and completed reports are stored in `runtime/operations.db`, so they
remain available after an API restart. A running job sends a lease heartbeat.
If the server stops and the lease expires, the job and its linked Daily
Operations run become `INTERRUPTED` instead of remaining falsely `RUNNING`.
The HQ then offers a deliberate retry that creates a new linked job; it never
resumes silently, duplicates an approval intentionally, or places a trade.

Runtime storage can be moved outside the repository when deploying:

```bash
export ASSET_RUNTIME_DIR="/durable/private/path"
```

### Automatic Daily Operations schedule

The scheduler is disabled by default to prevent unexpected API usage. Enable
it only after selecting an explicit local time and IANA timezone:

```bash
export ASSET_DAILY_SCHEDULE_ENABLED="true"
export ASSET_DAILY_TIME="08:00"
export ASSET_TIMEZONE="America/Vancouver"
export ASSET_DAILY_MISFIRE_GRACE_MINUTES="120"
```

Exactly one automatic Daily Operations job can be created per local calendar
date. If the server returns within the grace window, it performs one catch-up
run. If it returns later, that date is recorded as `SKIPPED` and no analysis
cost is incurred. CEO commands already in progress take priority; the
scheduler retries until the grace window closes. Schedule state is available
through the authenticated `/api/v1/operations/daily/schedule` endpoint.

The scheduler runs only while the API server is running. Codespaces can sleep,
so production-grade daily execution requires an always-on server and durable
`ASSET_RUNTIME_DIR`. The scheduler never places, modifies, or cancels trades.

Install development dependencies and run the authentication tests:

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Examples inside the chat interface:

```text
PANW 분석해
팔란티어 분석해
내 포트폴리오 보여줘
내 포트폴리오 점검해
```

## Terminal fallback

The original command-line entry point remains available:

```bash
python main.py PANW
```
