import asyncio

from app.graphs.nodes import (
    analyze_with_llm_node_async,
    calculate_indicators_node,
    load_market_data_node,
)


async def main() -> None:
    state = {
        "user_id": 1,
        "symbol": "AAPL",
        "market": "US",
        "analysis_type": "stock_basic",
        "risk_preference": "balanced",
    }
    state.update(load_market_data_node(state))
    state.update(calculate_indicators_node(state))
    state.update(await analyze_with_llm_node_async(state))
    print(state["result"].model_dump())


asyncio.run(main())