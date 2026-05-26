from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from langchain_core.messages import BaseMessage

from app.schemas.ai_usage import AIUsageTokenSource


@dataclass(frozen=True)
class AIUsageTokenEstimate:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    token_source: AIUsageTokenSource


@dataclass(frozen=True)
class AIUsageCostEstimate:
    estimated_cost: Decimal
    currency: str


class AIUsageTokenService:
    """Estimate AI token usage and cost.

    This service only calculates token/cost numbers.
    It does not call the LLM, check quota, or write database records.
    """

    APPROX_CHARS_PER_TOKEN = 4
    COST_QUANTIZE = Decimal("0.00000001")

    DEFAULT_CURRENCY = "CNY"

    # 项目内部估算价格：单位为 每 1,000,000 token 的人民币成本。
    # 后续如果要精确对账，应根据 DeepSeek 官方价格和实际模型重新调整。
    DEFAULT_PROMPT_PRICE_PER_1M_TOKENS = Decimal("2.00")
    DEFAULT_COMPLETION_PRICE_PER_1M_TOKENS = Decimal("8.00")

    MODEL_PRICE_RULES: dict[str, tuple[Decimal, Decimal]] = {
        "deepseek-v4-flash": (
            DEFAULT_PROMPT_PRICE_PER_1M_TOKENS,
            DEFAULT_COMPLETION_PRICE_PER_1M_TOKENS,
        ),
    }

    def estimate_prompt_tokens_from_messages(
        self,
        messages: list[BaseMessage] | list[dict[str, Any]] | list[Any],
    ) -> AIUsageTokenEstimate:
        text = self._messages_to_text(messages)
        prompt_tokens = self.estimate_tokens_from_text(text)

        return AIUsageTokenEstimate(
            prompt_tokens=prompt_tokens,
            completion_tokens=0,
            total_tokens=prompt_tokens,
            token_source="estimated",
        )

    def estimate_tokens_from_text(self, text: str | None) -> int:
        if not text:
            return 0

        normalized_text = str(text).strip()
        if not normalized_text:
            return 0

        return max(1, (len(normalized_text) + self.APPROX_CHARS_PER_TOKEN - 1) // self.APPROX_CHARS_PER_TOKEN)

    def build_token_usage(
        self,
        *,
        response: Any | None,
        prompt_messages: list[BaseMessage] | list[dict[str, Any]] | list[Any] | None = None,
        completion_text: str | None = None,
    ) -> AIUsageTokenEstimate:
        provider_usage = self.extract_token_usage_from_response(response)
        if provider_usage is not None:
            return provider_usage

        prompt_tokens = 0
        if prompt_messages is not None:
            prompt_tokens = self.estimate_prompt_tokens_from_messages(prompt_messages).prompt_tokens

        completion_tokens = self.estimate_tokens_from_text(completion_text)

        return AIUsageTokenEstimate(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            token_source="estimated" if prompt_tokens or completion_tokens else "none",
        )

    def extract_token_usage_from_response(self, response: Any | None) -> AIUsageTokenEstimate | None:
        if response is None:
            return None

        usage_metadata = getattr(response, "usage_metadata", None)
        usage = self._normalize_usage_dict(usage_metadata)
        if usage is not None:
            return usage

        response_metadata = getattr(response, "response_metadata", None)
        if isinstance(response_metadata, dict):
            token_usage = response_metadata.get("token_usage")
            usage = self._normalize_usage_dict(token_usage)
            if usage is not None:
                return usage

            usage = self._normalize_usage_dict(response_metadata.get("usage"))
            if usage is not None:
                return usage

        return None

    def estimate_cost(
        self,
        *,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        currency: str = DEFAULT_CURRENCY,
    ) -> AIUsageCostEstimate:
        prompt_price, completion_price = self._get_model_price_rule(model_name)

        prompt_cost = Decimal(prompt_tokens) * prompt_price / Decimal(1_000_000)
        completion_cost = Decimal(completion_tokens) * completion_price / Decimal(1_000_000)
        estimated_cost = (prompt_cost + completion_cost).quantize(
            self.COST_QUANTIZE,
            rounding=ROUND_HALF_UP,
        )

        return AIUsageCostEstimate(
            estimated_cost=estimated_cost,
            currency=currency,
        )

    def _normalize_usage_dict(self, usage: Any | None) -> AIUsageTokenEstimate | None:
        if not isinstance(usage, dict):
            return None

        prompt_tokens = self._to_non_negative_int(
            usage.get("prompt_tokens", usage.get("input_tokens", 0))
        )
        completion_tokens = self._to_non_negative_int(
            usage.get("completion_tokens", usage.get("output_tokens", 0))
        )
        total_tokens = self._to_non_negative_int(
            usage.get("total_tokens", prompt_tokens + completion_tokens)
        )

        if prompt_tokens == 0 and completion_tokens == 0 and total_tokens == 0:
            return None

        if total_tokens == 0:
            total_tokens = prompt_tokens + completion_tokens

        return AIUsageTokenEstimate(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            token_source="provider_usage",
        )

    def _messages_to_text(
        self,
        messages: list[BaseMessage] | list[dict[str, Any]] | list[Any],
    ) -> str:
        parts: list[str] = []

        for message in messages:
            if isinstance(message, BaseMessage):
                parts.append(str(message.content))
                continue

            if isinstance(message, dict):
                role = message.get("role", "")
                content = message.get("content", "")
                parts.append(f"{role}: {content}")
                continue

            content = getattr(message, "content", None)
            if content is not None:
                parts.append(str(content))
            else:
                parts.append(str(message))

        return "\n".join(parts)

    def _get_model_price_rule(self, model_name: str) -> tuple[Decimal, Decimal]:
        return self.MODEL_PRICE_RULES.get(
            model_name,
            (
                self.DEFAULT_PROMPT_PRICE_PER_1M_TOKENS,
                self.DEFAULT_COMPLETION_PRICE_PER_1M_TOKENS,
            ),
        )

    def _to_non_negative_int(self, value: Any) -> int:
        try:
            number = int(value or 0)
        except (TypeError, ValueError):
            return 0

        return max(0, number)