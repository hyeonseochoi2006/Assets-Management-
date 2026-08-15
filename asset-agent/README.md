# Asset Management Agent

Company-style structure for a personal, read-only investment decision-support system.

```text
asset-agent/
├── main.py
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

## Flow

Toss portfolio data -> Analysis -> Portfolio -> Risk -> Execution -> CIO -> Investor brief -> User decision

The system is read-only with respect to brokerage execution. It does not place, modify, or cancel orders.

## Run

```bash
python main.py PANW
```

If no ticker is supplied, the demonstration default is NVDA.
