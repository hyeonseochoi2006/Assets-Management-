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
