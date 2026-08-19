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

### Deterministic portfolio change policy

Daily Operations converts portfolio snapshot differences into standard change
events. Each event is classified as `QUIET`, `WATCH`, or `MATERIAL` and receives
a deterministic `event_id` so reprocessing the same two snapshots does not
create a new identity. These levels route operational attention only; they are
not trading signals, loss limits, or buy/sell decisions.

The initial screening defaults are configurable:

```bash
export ASSET_CHANGE_PRICE_WATCH_PCT="3"
export ASSET_CHANGE_PRICE_MATERIAL_PCT="7"
export ASSET_CHANGE_WEIGHT_WATCH_POINTS="2"
export ASSET_CHANGE_WEIGHT_MATERIAL_POINTS="5"
export ASSET_CHANGE_QUANTITY_MATERIAL_PCT="25"
export ASSET_CHANGE_VALUE_WATCH_PCT="5"
export ASSET_CHANGE_VALUE_MATERIAL_PCT="10"
```

Missing variables use the defaults above. Invalid numbers or a material
threshold lower than its watch threshold fail closed instead of silently
changing the routing policy. Adding/removing a holding is always classified as
`MATERIAL`; a currency change is `WATCH` because it may indicate an identity or
data-quality issue.

The first external change-intelligence collector checks official SEC EDGAR
filings for exact, Toss-resolved U.S. stock positions. It uses deterministic
comparison only; no AI is needed to discover a filing. Configure the SEC
required identifying User-Agent before enabling requests:

```bash
export ASSET_SEC_USER_AGENT="Asset Agent your-email@example.com"
```

Without that variable, Daily Operations records `NOT_CONFIGURED`, sends no SEC
request, and does not falsely report "no change." The first successful check
stores a baseline and produces no alerts for old filings. Later checks create a
deduplicated `FILING_FOUND` event only for a newly observed accession number.
Important periodic/current report forms such as 10-K, 10-Q, 8-K, 20-F, 40-F,
and 6-K are routed as `WATCH`; other forms are stored as `QUIET`. Form type alone
does not prove that earnings changed, so this collector does not manufacture an
`EARNINGS_CHANGED` claim.

The collector uses SEC JSON endpoints with a conservative maximum of five
requests per second, stores official archive URLs as evidence, and treats an
HTTP, format, or identity failure as `UNAVAILABLE` or `UNSUPPORTED` rather than
"no change." Company IR and licensed news sources remain explicitly
`NOT_CONFIGURED`; the application does not guess IR pages or scrape article
bodies.

Portfolio snapshots are validated before comparison. A different account,
duplicate/blank symbol, non-finite number, negative holding value, or weight
above 100% blocks comparison and produces a data-quality event instead of a
false investment event. Missing numeric fields and a suddenly empty portfolio
are retained as warnings. A blocked snapshot remains attached to its run for
audit but is never promoted to the next comparison baseline.

Raw price, value, weight, quantity, and currency events remain available for
audit, while `symbol_summaries` presents one primary event per symbol so a
single market move is not counted as several independent developments. Events
are stored in the SQLite `change_events` ledger with `event_id` as the primary
key; reprocessing the same event updates its seen count instead of inserting a
duplicate.

A holding that disappears is first recorded as
`HOLDING_MISSING_UNCONFIRMED` (`WATCH`). It becomes `HOLDING_REMOVED`
(`MATERIAL`) only when it remains absent in a second consecutive snapshot. A
reappearance clears the pending confirmation. This confirmation is an
operational portfolio observation, not proof of a trade placed by this system.
A reappearance after only one missing snapshot is treated as a closed transient
data gap, not as a newly added holding.

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
