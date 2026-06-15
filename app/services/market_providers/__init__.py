"""行情 Provider 统一导出口。

外部代码只从这个包导入 Provider，避免直接依赖具体文件路径。新增行情源时，
需要在这里导出，MarketDataSyncService 才能按配置选择对应适配器。
"""

from app.services.market_providers.baostock import BaoStockProvider
from app.services.market_providers.base import MarketDataProvider
from app.services.market_providers.mock import MockMarketDataProvider
from app.services.market_providers.tushare import TushareProvider

__all__ = [
    "BaoStockProvider",
    "MarketDataProvider",
    "MockMarketDataProvider",
    "TushareProvider",
]
