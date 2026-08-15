RISK_POLICY = """
USER RISK POLICY STATUS:
- User-specific numeric position limits are NOT CONFIGURED yet.
- User-specific sector limits are NOT CONFIGURED yet.
- Do not invent numeric limits.
- If a numeric risk limit is needed, mark it as missing information.

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
If live price, spread, volume, volatility, tax, or other execution data are missing,
report them as missing instead of guessing.
"""
