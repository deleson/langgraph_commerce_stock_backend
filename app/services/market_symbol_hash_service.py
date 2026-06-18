"""股票基础信息哈希服务。

哈希用于判断 Provider 返回的基础信息是否真的发生变化。它不能替代业务键匹配，
但可以避免全量同步时对 5000 多条股票记录做无意义 update。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.schemas.market_data import MarketSymbolCreate


class MarketSymbolHashService:
    """为股票基础信息生成稳定的数据指纹。"""

    def raw_hash(
        self,
        payload: dict[str, Any],
    ) -> str:
        """对 Provider 原始字段生成哈希。"""

        return self._hash_payload(payload)

    def normalized_payload(
        self,
        symbol: MarketSymbolCreate,
    ) -> dict[str, Any]:
        """提取会影响统一展示和业务判断的字段。

        同步时间、错误信息、updated_at 等运行状态不参与哈希，否则每次同步都会被
        误判为数据变化。
        """

        return {
            "symbol": symbol.symbol,
            "market": symbol.market,
            "name": symbol.name,
            "currency": symbol.currency,
            "exchange": symbol.exchange,
            "provider_symbol": symbol.provider_symbol,
            "list_status": symbol.list_status,
            "source": symbol.source,
            "is_active": symbol.is_active,
        }

    def normalized_hash(
        self,
        symbol: MarketSymbolCreate,
    ) -> str:
        """对项目统一字段生成哈希。"""

        return self._hash_payload(self.normalized_payload(symbol))

    def _hash_payload(
        self,
        payload: dict[str, Any],
    ) -> str:
        normalized_json = json.dumps(
            self._normalize_value(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(normalized_json.encode("utf-8")).hexdigest()

    def _normalize_value(
        self,
        value: Any,
    ) -> Any:
        if isinstance(value, dict):
            return {
                str(key): self._normalize_value(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            }

        if isinstance(value, list):
            return [self._normalize_value(item) for item in value]

        if isinstance(value, str):
            return value.strip()

        return value
