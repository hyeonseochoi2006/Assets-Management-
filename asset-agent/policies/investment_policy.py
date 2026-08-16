RISK_POLICY = """
USER RISK POLICY STATUS:
- User-specific numeric position limits are NOT CONFIGURED yet.
- User-specific sector limits are NOT CONFIGURED yet.
- Do not invent numeric limits.
- Do not infer numeric limits from current portfolio weights, risk scores, analyst opinions, or generic diversification rules.
- If a numeric risk limit is needed, mark it as missing information.
- Until the CEO configures a numeric policy, any target range, maximum position size, or sector cap must be reported as NOT CONFIGURED / null.

HARD SAFETY RULES:
- Investor makes the final buy decision.
- No leverage.
- No options.
- Capital preservation matters.
"""


EXECUTION_CONSTRAINTS = """
Investor makes the final buy decision.
Do not execute a real trade.
No leverage.
No options.
Never override the Risk Agent.
User-specific numeric position limits are NOT CONFIGURED yet.
Do not invent or infer a maximum position percentage.
If a maximum position percentage is needed, return it as null / NOT CONFIGURED and list it as missing information.
If live price, spread, volume, volatility, tax, or other execution data are missing,
report them as missing instead of guessing.
"""
