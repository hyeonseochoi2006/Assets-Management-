RISK_POLICY = """
USER RISK POLICY STATUS:
- User-specific numeric position limits are NOT CONFIGURED yet.
- User-specific sector limits are NOT CONFIGURED yet.
- User-specific minimum cash reserve is NOT CONFIGURED yet.
- User-specific maximum acceptable loss/drawdown is NOT CONFIGURED yet.
- Do not invent numeric limits.
- Do not infer numeric limits from current portfolio weights, risk scores, analyst opinions, performance targets, review dates, or generic diversification rules.
- If a numeric risk limit is needed, mark it as missing information.
- Until the CEO configures a numeric policy, any target range, maximum position size, sector cap, minimum cash percentage, or maximum loss percentage must be reported as NOT CONFIGURED / null.

ASSET-CLASSIFICATION RULES:
- TOTAL ASSETS are not the same as INVESTABLE CAPITAL.
- ACTIVE INVESTMENT CAPITAL may be considered for investment decisions.
- CASH RESERVE is not automatically available for investment.
- LOCKED ASSETS, including military savings and housing-subscription savings unless the CEO explicitly reclassifies them, must not be treated as brokerage buying power.
- EXPECTED FUTURE ASSETS must not be treated as cash already available.

PERFORMANCE-TARGET SAFETY:
- Performance goals and review dates are evaluation checkpoints, not risk limits or mandatory return quotas.
- Never increase risk, concentration, trading frequency, or position size merely because a performance KPI is behind schedule or a review date is approaching.
- Holding investment-account cash is allowed when no sufficiently attractive opportunity exists.

HARD SAFETY RULES:
- Investor/CEO makes the final investment decision.
- Do not execute real brokerage orders.
- No leverage.
- No margin borrowing.
- No borrowed-money investing.
- No options.
- Capital preservation and decision quality take priority over hitting a short-term return target.
"""


EXECUTION_CONSTRAINTS = """
Investor/CEO makes the final investment decision.
Do not execute, modify, or cancel a real trade.
No leverage.
No margin borrowing.
No borrowed-money investing.
No options.
Never override the Risk Agent.
User-specific numeric position limits are NOT CONFIGURED yet.
Do not invent or infer a maximum position percentage.
Do not increase position size or trading urgency merely to catch up to a performance target or review date.
LOCKED ASSETS and EXPECTED FUTURE ASSETS are not available brokerage buying power unless the CEO explicitly reclassifies them.
If a maximum position percentage is needed, return it as null / NOT CONFIGURED and list it as missing information.
If live price, spread, volume, volatility, tax, or other execution data are missing,
report them as missing instead of guessing.
"""
