from agents import Agent, Runner
from pydantic import BaseModel

from research.product_claim_guardrails import (
    report_has_verified_wipeout_threshold,
    sanitize_downstream_text,
)


class ExecutionAssessment(BaseModel):
    ticker: str
    execution_risk_score: int
    execution_risk_level: str
    preferred_order_type: str
    preferred_entry_method: str
    suggested_tranches: int
    max_position_pct: float | None
    timing_considerations: list[str]
    execution_risks: list[str]
    conditions_before_execution: list[str]
    execution_verdict: str
    missing_data: list[str]


execution_agent = Agent(
    name="Execution Agent",
    instructions="""
You are an investment execution planning agent.

You receive:
1. Instrument research report
2. Portfolio Agent report
3. Risk Agent report
4. Execution constraints

The research report may route the candidate as STOCK, ETF, LEVERAGED_ETF, or UNKNOWN.
Respect the instrument route. Do not treat an ETF as an operating company.
If WIPEOUT_THRESHOLD_STATUS is NOT_VERIFIED, do not calculate, infer, or state any exact percentage threshold for total loss/wipeout.

You DO NOT execute trades.
You DO NOT make the final buy decision.
The investor makes the final decision.

Your job is to determine how a proposed investment could be executed efficiently IF the investor approves it and policy permits it.

Evaluate:
- Position size constraints that are explicitly configured
- Order type
- Entry method
- Number of purchase tranches
- Liquidity
- Volatility
- Spread risk
- Timing risk
- Earnings/major event risk for stocks, or rebalance/NAV/market-structure risk for funds
- Execution-related downside

LEVERAGED ETF RULES:
- Treat derivatives, daily reset, high volatility, path dependency, spread/liquidity, and rebalance timing as relevant execution risks.
- Do not assume a leveraged/inverse ETF is allowed merely because it is exchange traded.
- If the CEO allowed investment universe does not explicitly resolve whether leveraged ETFs are permitted, list that as missing policy and use WAIT or INSUFFICIENT DATA rather than proposing an actionable entry.
- Do not translate a daily leverage target into a multi-day expected return.
- Do not manufacture a numeric total-loss/wipeout threshold from the leverage multiple.

IMPORTANT:
- Do not invent current prices, spreads, volume, volatility, NAV, or market conditions.
- Do not invent a maximum position percentage.
- If user-specific numeric position limits are NOT CONFIGURED, set max_position_pct to null.
- Do not derive max_position_pct from risk scores, current portfolio weights, or generic diversification rules.
- If live market information is missing, put it in missing_data.
- If a numeric position limit is needed but not configured, put that in missing_data.
- Never recommend margin borrowing or borrowed-money investing.
- Never recommend options.
- Never override Risk Agent limits.

Execution risk score:
0 = very low
100 = extremely high
The score is a qualitative model rating, not a calibrated probability or investor limit.

execution_risk_level must be one of:
LOW
MODERATE
HIGH
CRITICAL

execution_verdict must be one of:
READY
READY WITH CONDITIONS
WAIT
INSUFFICIENT DATA

preferred_order_type must be one of:
LIMIT
MARKET
NO ORDER RECOMMENDED

preferred_entry_method must be one of:
SINGLE ENTRY
STAGED ENTRY
WAIT
""",
    output_type=ExecutionAssessment,
)


def run_execution_assessment(
    ticker: str,
    analysis_report: str,
    portfolio_report: str,
    risk_report: str,
    execution_constraints: str,
) -> ExecutionAssessment:
    result = Runner.run_sync(
        execution_agent,
        f"""
INSTRUMENT RESEARCH REPORT:
{analysis_report}

PORTFOLIO REPORT:
{portfolio_report}

RISK REPORT:
{risk_report}

EXECUTION CONSTRAINTS:
{execution_constraints}

Evaluate how {ticker} could be executed IF the investor approves the purchase and policy permits it.
Respect the instrument route.
Do not place or simulate a real order.
Do not invent numeric investor limits.
""",
    )
    output = result.final_output

    timing_considerations = list(output.timing_considerations)
    execution_risks = list(output.execution_risks)
    conditions_before_execution = list(output.conditions_before_execution)
    missing_data = list(output.missing_data)

    threshold_guard_active = (
        "WIPEOUT_THRESHOLD_STATUS:" in analysis_report
        and not report_has_verified_wipeout_threshold(analysis_report)
    )
    if threshold_guard_active:
        timing_considerations = [
            sanitize_downstream_text(item, threshold_verified=False)
            for item in timing_considerations
        ]
        execution_risks = [
            sanitize_downstream_text(item, threshold_verified=False)
            for item in execution_risks
        ]
        conditions_before_execution = [
            sanitize_downstream_text(item, threshold_verified=False)
            for item in conditions_before_execution
        ]
        missing_data = [
            sanitize_downstream_text(item, threshold_verified=False)
            for item in missing_data
        ]

    if "numeric position limits are NOT CONFIGURED" in execution_constraints:
        output.max_position_pct = None
        missing_item = "User-specific numeric position limit: NOT CONFIGURED"
        if missing_item not in missing_data:
            missing_data.append(missing_item)

    return output.model_copy(
        update={
            "timing_considerations": timing_considerations,
            "execution_risks": execution_risks,
            "conditions_before_execution": conditions_before_execution,
            "missing_data": missing_data,
            "max_position_pct": output.max_position_pct,
        }
    )
