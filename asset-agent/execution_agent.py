from pydantic import BaseModel
from agents import Agent, Runner


class ExecutionAssessment(BaseModel):
    ticker: str
    execution_risk_score: int
    execution_risk_level: str
    preferred_order_type: str
    preferred_entry_method: str
    suggested_tranches: int
    max_position_pct: float
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
                                                        1. Analysis Agent report
                                                        2. Portfolio Agent report
                                                        3. Risk Agent report
                                                        4. Execution constraints

                                                        You DO NOT execute trades.

                                                        You DO NOT make the final buy decision.

                                                        The investor makes the final decision.

                                                        Your job is to determine how a proposed investment
                                                        could be executed efficiently IF the investor approves it.

                                                        Evaluate:

                                                        - Position size constraints
                                                        - Order type
                                                        - Entry method
                                                        - Number of purchase tranches
                                                        - Liquidity
                                                        - Volatility
                                                        - Spread risk
                                                        - Timing risk
                                                        - Earnings or major event risk
                                                        - Execution-related downside

                                                        IMPORTANT:

                                                        Do not invent current prices, spreads, volume,
                                                        volatility, or market conditions.

                                                        If live market information is missing,
                                                        put it in missing_data.

                                                        Never recommend leverage.

                                                        Never recommend options.

                                                        Never override Risk Agent limits.

                                                        Execution risk score:

                                                        0 = very low
                                                        100 = extremely high

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
                                                            )analysis_report = """
                                                            Ticker: NVDA

                                                            Business Quality: 9/10
                                                            Growth: 9/10
                                                            Financial Strength: 9/10
                                                            Valuation: 6/10

                                                            Confidence: 83/100

                                                            Main risks:
                                                            High valuation,
                                                            customer concentration,
                                                            competition,
                                                            AI capital-spending slowdown.
                                                            """


    portfolio_report = """
                                                            Ticker: NVDA

                                                            Current Weight: 5.0%
                                                            Target Weight Range: 3.0% - 7.5%
                                                            Maximum Weight: 15.0%

                                                            Portfolio Fit Score: 78/100

                                                            Technology exposure is already substantial.
                                                            """


                                                            risk_report = """
                                                            Risk Verdict:
                                                            PASS WITH LIMITS

                                                            Rules:

                                                            Maintain NVDA within 3.0% - 7.5%.

                                                            Do not increase above 7.5%
                                                            without additional review.

                                                            Keep total technology exposure
                                                            below 50%.

                                                            No leverage.

                                                            No options.
                                                            """


                                                            execution_constraints = """
                                                            Investor makes final buy decision.

                                                            No leverage.
                                                            No options.

                                                            Capital preservation is important.

                                                            Live price and market microstructure
                                                            data are currently not supplied.
                                                            """


                                                            result = Runner.run_sync(
                                                                execution_agent,
                                                                    f"""
                                                                    ANALYSIS REPORT:

                                                                    {analysis_report}


                                                                    PORTFOLIO REPORT:

                                                                    {portfolio_report}


                                                                    RISK REPORT:

                                                                    {risk_report}


                                                                    EXECUTION CONSTRAINTS:

                                                                    {execution_constraints}


                                                                    Evaluate how NVDA could be executed
                                                                    IF the investor approves the purchase.
                                                                    """,
                                                                    )


                                                                    print(result.final_output.model_dump_json(indent=2))