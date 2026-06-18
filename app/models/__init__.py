"""Model 统一导出入口。

本文件集中导出所有 SQLAlchemy Model，方便业务代码引用，
也方便 Alembic 在迁移时识别完整 metadata。这里不写业务逻辑。
"""

from app.models.analysis_record import AnalysisRecord
from app.models.base import Base
from app.models.device import Device
from app.models.notification import Notification
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.models.user_preference import UserPreference
from app.models.user_session import UserSession
from app.models.watchlist_item import WatchlistItem
from app.models.market_symbol import MarketSymbol
from app.models.market_symbol_source import MarketSymbolSource
from app.models.market_candle import MarketCandle
from app.models.market_data_sync_status import MarketDataSyncStatus
from app.models.market_data_sync_log import MarketDataSyncLog
from app.models.analysis_conversation_message import AnalysisConversationMessage
from app.models.analysis_react_trace import AnalysisReactTrace
from app.models.ai_usage_log import AIUsageLog
from app.models.ai_quota_account import AIQuotaAccount
from app.models.ai_usage_summary import AIUsageSummary
from app.models.background_task import BackgroundTask
from app.models.user_memory import UserMemory
from app.models.user_profile import UserProfile
from app.models.user_memory_embedding import UserMemoryEmbedding
from app.models.daily_report import DailyReport
from app.models.quant_alert_rule import QuantAlertRule
from app.models.quant_alert_event import QuantAlertEvent
from app.models.paper_trading_account import PaperTradingAccount
from app.models.paper_trading_position import PaperTradingPosition
from app.models.paper_trading_order import PaperTradingOrder
from app.models.paper_trading_trade import PaperTradingTrade
from app.models.paper_trading_equity_snapshot import PaperTradingEquitySnapshot
from app.models.paper_trading_account_config import PaperTradingAccountConfig
from app.models.paper_trading_run import PaperTradingRun

__all__ = [
    "AnalysisRecord",
    "Base",
    "Device",
    "Notification",
    "SystemSetting",
    "User",
    "UserPreference",
    "UserSession",
    "WatchlistItem",
    "MarketSymbol",
    "MarketSymbolSource",
    "MarketCandle",
    "MarketDataSyncStatus",
    "MarketDataSyncLog",
    "AnalysisConversationMessage",
    "AnalysisReactTrace",
    "AIUsageLog",
    "AIQuotaAccount",
    "AIUsageSummary",
    "BackgroundTask",
    "UserMemory",
    "UserProfile",
    "UserMemoryEmbedding",
    "DailyReport",
    "QuantAlertRule",
    "QuantAlertEvent",
    "PaperTradingAccount",
    "PaperTradingPosition",
    "PaperTradingOrder",
    "PaperTradingTrade",
    "PaperTradingEquitySnapshot",
    "PaperTradingAccountConfig",
    "PaperTradingRun",
]
