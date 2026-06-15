from __future__ import annotations

"""量化提醒规则触发判定服务。

本文件只做确定性规则判断：
根据已准备好的行情、技术指标、数据质量和策略信号，
判断用户配置的提醒规则是否被触发。

它不写数据库、不创建通知、不处理去重；这些由 QuantAlertScanService 负责。
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from app.models.quant_alert_rule import QuantAlertRule
from app.schemas.quant_alert import (
    QuantAlertEventCreate,
    QuantAlertRuleStatus,
    QuantAlertRuleType,
    QuantAlertSeverity,
    QuantAlertTriggerDirection,
    QuantAlertTriggerSnapshot,
)
from app.services.quant_alert_data_service import QuantAlertDataContext, QuantAlertDataItem


@dataclass(slots=True)
class QuantAlertTriggeredCandidate:
    """一条“准备创建提醒事件”的候选结果。"""

    rule: QuantAlertRule
    data_item: QuantAlertDataItem
    event_payload: QuantAlertEventCreate
    cooldown_minutes: int
    enabled_notification: bool = True


@dataclass(slots=True)
class QuantAlertTriggerEvaluationItem:
    symbol: str
    market: str
    checked_rule_count: int = 0
    triggered_candidates: list[QuantAlertTriggeredCandidate] = field(default_factory=list)
    skipped_reason: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class QuantAlertTriggerEvaluationResult:
    items: list[QuantAlertTriggerEvaluationItem]
    triggered_candidates: list[QuantAlertTriggeredCandidate]
    checked_rule_count: int = 0
    warnings: list[str] = field(default_factory=list)


class QuantAlertTriggerService:
    """对准备好的扫描数据执行确定性提醒规则判定。

    这个 Service 只回答“是否触发”，不负责落库和通知。
    这样规则计算可以独立测试，也可以避免数据库副作用混入纯判断逻辑。
    """

    DEFAULT_STRATEGY_SIGNALS = {"buy", "sell"}
    DEFAULT_STRONG_STRATEGY_SIGNALS = {"buy", "sell"}
    DEFAULT_STRONG_STRENGTHS = {"strong"}
    DEFAULT_DATA_QUALITY_REASONS = {
        "no_data",
        "insufficient_data",
        "stale_data",
        "data_error",
    }
    DEFAULT_VOLUME_SPIKE_THRESHOLD = Decimal("2.0")
    PRICE_CHANGE_ABSOLUTE_CONFIG_KEY = "use_absolute"

    def evaluate_context(
        self,
        *,
        user_id: int,
        context: QuantAlertDataContext,
        rules: list[QuantAlertRule],
        triggered_at: datetime | None = None,
    ) -> QuantAlertTriggerEvaluationResult:
        """评估一次扫描上下文中的所有股票和规则。"""

        triggered_at = triggered_at or datetime.now(UTC)
        warnings = list(context.warnings)
        items: list[QuantAlertTriggerEvaluationItem] = []
        all_candidates: list[QuantAlertTriggeredCandidate] = []
        checked_rule_count = 0

        active_rules = [rule for rule in rules if self._is_active_rule(rule)]

        for data_item in context.items:
            matched_rules = [
                rule for rule in active_rules if self._rule_matches_item(rule, data_item)
            ]
            checked_rule_count += len(matched_rules)

            evaluation_item = self.evaluate_item(
                user_id=user_id,
                data_item=data_item,
                rules=matched_rules,
                triggered_at=triggered_at,
            )

            items.append(evaluation_item)
            all_candidates.extend(evaluation_item.triggered_candidates)
            warnings.extend(evaluation_item.warnings)

        return QuantAlertTriggerEvaluationResult(
            items=items,
            triggered_candidates=all_candidates,
            checked_rule_count=checked_rule_count,
            warnings=self._deduplicate_messages(warnings),
        )

    def evaluate_item(
        self,
        *,
        user_id: int,
        data_item: QuantAlertDataItem,
        rules: list[QuantAlertRule],
        triggered_at: datetime,
    ) -> QuantAlertTriggerEvaluationItem:
        if data_item.overview is None:
            return QuantAlertTriggerEvaluationItem(
                symbol=data_item.symbol,
                market=data_item.market,
                checked_rule_count=0,
                skipped_reason="no_market_overview",
                warnings=data_item.warnings + data_item.errors,
            )

        triggered_candidates: list[QuantAlertTriggeredCandidate] = []

        for rule in rules:
            candidate = self._evaluate_one_rule(
                user_id=user_id,
                data_item=data_item,
                rule=rule,
                triggered_at=triggered_at,
            )
            if candidate is not None:
                triggered_candidates.append(candidate)

        return QuantAlertTriggerEvaluationItem(
            symbol=data_item.symbol,
            market=data_item.market,
            checked_rule_count=len(rules),
            triggered_candidates=triggered_candidates,
            warnings=self._deduplicate_messages(data_item.warnings + data_item.errors),
        )

    def _evaluate_one_rule(
        self,
        *,
        user_id: int,
        data_item: QuantAlertDataItem,
        rule: QuantAlertRule,
        triggered_at: datetime,
    ) -> QuantAlertTriggeredCandidate | None:
        """根据 rule_type 分发到具体规则判断函数。

        当前支持策略信号、强策略信号、策略分数阈值、价格涨跌幅、
        成交量放大和数据质量提醒。
        """

        rule_type = self._parse_rule_type(rule.rule_type)

        if rule_type == QuantAlertRuleType.STRATEGY_SIGNAL:
            return self._evaluate_strategy_signal_rule(user_id, data_item, rule, triggered_at)

        if rule_type == QuantAlertRuleType.STRONG_STRATEGY_SIGNAL:
            return self._evaluate_strong_strategy_signal_rule(user_id, data_item, rule, triggered_at)

        if rule_type == QuantAlertRuleType.STRATEGY_SCORE_THRESHOLD:
            return self._evaluate_strategy_score_threshold_rule(user_id, data_item, rule, triggered_at)

        if rule_type == QuantAlertRuleType.PRICE_CHANGE:
            return self._evaluate_price_change_rule(user_id, data_item, rule, triggered_at)

        if rule_type == QuantAlertRuleType.VOLUME_SPIKE:
            return self._evaluate_volume_spike_rule(user_id, data_item, rule, triggered_at)

        if rule_type == QuantAlertRuleType.DATA_QUALITY:
            return self._evaluate_data_quality_rule(user_id, data_item, rule, triggered_at)

        return None

    def _evaluate_strategy_signal_rule(
        self,
        user_id: int,
        data_item: QuantAlertDataItem,
        rule: QuantAlertRule,
        triggered_at: datetime,
    ) -> QuantAlertTriggeredCandidate | None:
        signal = data_item.strategy_signal
        if signal is None or signal.status != "available" or signal.signal is None:
            return None

        target_signals = set(
            self._get_config_list(rule, "signals", self.DEFAULT_STRATEGY_SIGNALS)
        )
        if signal.signal not in target_signals:
            return None

        return self._build_candidate(
            user_id=user_id,
            data_item=data_item,
            rule=rule,
            triggered_at=triggered_at,
            trigger_value=signal.signal,
            data_quality_reason=None,
        )

    def _evaluate_strong_strategy_signal_rule(
        self,
        user_id: int,
        data_item: QuantAlertDataItem,
        rule: QuantAlertRule,
        triggered_at: datetime,
    ) -> QuantAlertTriggeredCandidate | None:
        signal = data_item.strategy_signal
        if signal is None or signal.status != "available" or signal.signal is None:
            return None

        target_signals = set(
            self._get_config_list(rule, "signals", self.DEFAULT_STRONG_STRATEGY_SIGNALS)
        )
        target_strengths = set(
            self._get_config_list(rule, "strengths", self.DEFAULT_STRONG_STRENGTHS)
        )

        if signal.signal not in target_signals:
            return None

        if signal.strength not in target_strengths:
            return None

        return self._build_candidate(
            user_id=user_id,
            data_item=data_item,
            rule=rule,
            triggered_at=triggered_at,
            trigger_value=f"{signal.signal}:{signal.strength}",
            data_quality_reason=None,
        )

    def _evaluate_strategy_score_threshold_rule(
        self,
        user_id: int,
        data_item: QuantAlertDataItem,
        rule: QuantAlertRule,
        triggered_at: datetime,
    ) -> QuantAlertTriggeredCandidate | None:
        signal = data_item.strategy_signal
        if signal is None or signal.status != "available":
            return None

        if not self._compare_number(
            value=Decimal(signal.score),
            threshold=rule.threshold_value,
            direction=rule.trigger_direction,
        ):
            return None

        return self._build_candidate(
            user_id=user_id,
            data_item=data_item,
            rule=rule,
            triggered_at=triggered_at,
            trigger_value=signal.score,
            data_quality_reason=None,
        )

    def _evaluate_price_change_rule(
        self,
        user_id: int,
        data_item: QuantAlertDataItem,
        rule: QuantAlertRule,
        triggered_at: datetime,
    ) -> QuantAlertTriggeredCandidate | None:
        quote = data_item.quote
        if quote is None:
            return None

        price_change = Decimal(str(quote.price_change_percent))
        if bool((rule.rule_config or {}).get(self.PRICE_CHANGE_ABSOLUTE_CONFIG_KEY)):
            price_change = abs(price_change)

        if not self._compare_number(
            value=price_change,
            threshold=rule.threshold_value,
            direction=rule.trigger_direction,
        ):
            return None

        return self._build_candidate(
            user_id=user_id,
            data_item=data_item,
            rule=rule,
            triggered_at=triggered_at,
            trigger_value=price_change,
            data_quality_reason=None,
        )

    def _evaluate_volume_spike_rule(
        self,
        user_id: int,
        data_item: QuantAlertDataItem,
        rule: QuantAlertRule,
        triggered_at: datetime,
    ) -> QuantAlertTriggeredCandidate | None:
        technical_indicators = data_item.technical_indicators
        if technical_indicators is None:
            return None

        volume_ratio = technical_indicators.summary.volume_factor.volume_ratio
        if volume_ratio is None:
            return None

        threshold = rule.threshold_value or self.DEFAULT_VOLUME_SPIKE_THRESHOLD
        direction = rule.trigger_direction or QuantAlertTriggerDirection.ABOVE

        if not self._compare_number(
            value=Decimal(str(volume_ratio)),
            threshold=threshold,
            direction=direction,
        ):
            return None

        return self._build_candidate(
            user_id=user_id,
            data_item=data_item,
            rule=rule,
            triggered_at=triggered_at,
            trigger_value=volume_ratio,
            data_quality_reason=None,
        )

    def _evaluate_data_quality_rule(
        self,
        user_id: int,
        data_item: QuantAlertDataItem,
        rule: QuantAlertRule,
        triggered_at: datetime,
    ) -> QuantAlertTriggeredCandidate | None:
        reason = self._get_data_quality_reason(data_item)
        if reason is None:
            return None

        target_reasons = set(
            self._get_config_list(
                rule,
                "reasons",
                self.DEFAULT_DATA_QUALITY_REASONS,
            )
        )
        if reason not in target_reasons:
            return None

        return self._build_candidate(
            user_id=user_id,
            data_item=data_item,
            rule=rule,
            triggered_at=triggered_at,
            trigger_value=reason,
            data_quality_reason=reason,
        )

    def _build_candidate(
        self,
        *,
        user_id: int,
        data_item: QuantAlertDataItem,
        rule: QuantAlertRule,
        triggered_at: datetime,
        trigger_value,
        data_quality_reason: str | None,
    ) -> QuantAlertTriggeredCandidate:
        rule_type = self._parse_rule_type(rule.rule_type)
        event_date = triggered_at.date()
        snapshot = self._build_trigger_snapshot(
            data_item=data_item,
            rule=rule,
            trigger_value=trigger_value,
            data_quality_reason=data_quality_reason,
        )

        payload = QuantAlertEventCreate(
            user_id=user_id,
            rule_id=rule.id,
            rule_type=rule_type,
            symbol=data_item.symbol,
            market=data_item.market,
            title=self._build_title(rule_type, data_item),
            message=self._build_message(rule_type, data_item, snapshot),
            severity=self._parse_severity(rule.severity),
            event_date=event_date,
            triggered_at=triggered_at,
            dedup_key=self._build_dedup_key(
                user_id=user_id,
                rule=rule,
                data_item=data_item,
                event_date=event_date,
            ),
            trigger_snapshot=snapshot,
        )

        return QuantAlertTriggeredCandidate(
            rule=rule,
            data_item=data_item,
            event_payload=payload,
            cooldown_minutes=rule.cooldown_minutes,
            enabled_notification=rule.enabled_notification,
        )

    def _build_trigger_snapshot(
        self,
        *,
        data_item: QuantAlertDataItem,
        rule: QuantAlertRule,
        trigger_value,
        data_quality_reason: str | None,
    ) -> QuantAlertTriggerSnapshot:
        signal = data_item.strategy_signal
        quote = data_item.quote
        technical_indicators = data_item.technical_indicators

        volume_ratio = None
        if technical_indicators is not None:
            volume_ratio = technical_indicators.summary.volume_factor.volume_ratio

        return QuantAlertTriggerSnapshot(
            rule_type=self._parse_rule_type(rule.rule_type),
            symbol=data_item.symbol,
            market=data_item.market,
            trigger_value=trigger_value,
            threshold_value=rule.threshold_value,
            trigger_direction=rule.trigger_direction,
            strategy_signal=signal.signal if signal else None,
            strategy_strength=signal.strength if signal else None,
            strategy_score=signal.score if signal else None,
            price_change_percent=quote.price_change_percent if quote else None,
            volume_ratio=volume_ratio,
            data_quality_status=data_quality_reason,
            data_quality_reason=data_quality_reason,
            source_payload={
                "rule_id": rule.id,
                "rule_name": rule.name,
                "enabled_notification": rule.enabled_notification,
                "cooldown_minutes": rule.cooldown_minutes,
            },
        )

    def _build_title(
        self,
        rule_type: QuantAlertRuleType,
        data_item: QuantAlertDataItem,
    ) -> str:
        return f"{data_item.market}:{data_item.symbol} 触发 {rule_type.value} 提醒"

    def _build_message(
        self,
        rule_type: QuantAlertRuleType,
        data_item: QuantAlertDataItem,
        snapshot: QuantAlertTriggerSnapshot,
    ) -> str:
        return (
            f"{data_item.market}:{data_item.symbol} 触发 {rule_type.value} 量化提醒。"
            f"触发值：{snapshot.trigger_value}。"
            "该提醒仅作为研究线索，不构成买卖建议。"
        )

    def _build_dedup_key(
        self,
        *,
        user_id: int,
        rule: QuantAlertRule,
        data_item: QuantAlertDataItem,
        event_date: date,
    ) -> str:
        return (
            f"{user_id}:"
            f"{rule.id}:"
            f"{rule.rule_type}:"
            f"{data_item.market}:"
            f"{data_item.symbol}:"
            f"{event_date.isoformat()}"
        )

    def _get_data_quality_reason(self, data_item: QuantAlertDataItem) -> str | None:
        data_quality = data_item.data_quality
        if data_quality is None:
            return "data_error"

        if data_quality.is_empty:
            return "no_data"

        if data_quality.errors:
            return "data_error"

        if not data_quality.is_enough:
            return "insufficient_data"

        if data_quality.is_stale:
            return "stale_data"

        return None

    def _compare_number(
        self,
        *,
        value: Decimal,
        threshold: Decimal | None,
        direction: str | None,
    ) -> bool:
        if threshold is None or direction is None:
            return False

        threshold_value = self._to_decimal(threshold)
        direction_value = str(direction)

        if direction_value == QuantAlertTriggerDirection.ABOVE:
            return value >= threshold_value

        if direction_value == QuantAlertTriggerDirection.BELOW:
            return value <= threshold_value

        if direction_value == QuantAlertTriggerDirection.EQUAL:
            return value == threshold_value

        return False

    def _rule_matches_item(
        self,
        rule: QuantAlertRule,
        data_item: QuantAlertDataItem,
    ) -> bool:
        rule_market = self._normalize_optional_text(rule.market)
        rule_symbol = self._normalize_optional_text(rule.symbol)

        if rule_market is not None and rule_market != self._normalize_text(data_item.market):
            return False

        if rule_symbol is not None and rule_symbol != self._normalize_text(data_item.symbol):
            return False

        return True

    def _is_active_rule(self, rule: QuantAlertRule) -> bool:
        return str(rule.status) == QuantAlertRuleStatus.ACTIVE

    def _get_config_list(
        self,
        rule: QuantAlertRule,
        key: str,
        default_values: set[str],
    ) -> list[str]:
        raw_values = (rule.rule_config or {}).get(key)
        if not isinstance(raw_values, list):
            return sorted(default_values)

        values = [
            str(item).strip().lower()
            for item in raw_values
            if str(item).strip()
        ]

        return values or sorted(default_values)

    def _parse_rule_type(self, value: str) -> QuantAlertRuleType:
        return QuantAlertRuleType(str(value))

    def _parse_severity(self, value: str) -> QuantAlertSeverity:
        return QuantAlertSeverity(str(value))

    def _to_decimal(self, value) -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0")

    def _normalize_optional_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = self._normalize_text(value)
        return normalized or None

    def _normalize_text(self, value: str | None) -> str:
        return (value or "").strip().upper()

    def _deduplicate_messages(self, messages: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []

        for message in messages:
            normalized = str(message).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)

        return result
