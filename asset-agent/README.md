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
