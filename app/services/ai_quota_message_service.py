from app.schemas.ai_usage import AIUsageFeature


class AIQuotaMessageService:
    """Build user-facing Chinese messages for AI quota blocked scenarios.

    This service does not check quota, does not write database, and does not call LLM.
    It only converts quota blocked reasons into product-friendly Chinese messages.
    """

    FEATURE_DISPLAY_NAMES: dict[AIUsageFeature, str] = {
        "stock_analysis": "个股 AI 分析",
        "react_reason": "ReAct 追问推理",
        "react_final_answer": "ReAct 最终回答",
        "candidate_ai_explanation": "AI 候选解释",
    }

    def build_short_reason(self, reason: str | None) -> str:
        clean_reason = str(reason or "").strip()
        if clean_reason:
            return clean_reason

        return "当前 AI 额度不足。"

    def build_feature_name(self, feature: AIUsageFeature) -> str:
        return self.FEATURE_DISPLAY_NAMES.get(feature, "AI 功能")

    def build_stock_analysis_blocked_summary(self, reason: str | None) -> str:
        short_reason = self.build_short_reason(reason)
        return (
            "当前 AI 分析额度不足，本次没有继续调用大模型生成完整个股分析。"
            f"系统记录到的原因是：{short_reason}"
        )

    def build_stock_analysis_blocked_key_points(self, reason: str | None) -> list[str]:
        short_reason = self.build_short_reason(reason)
        return [
            "系统已在调用 DeepSeek 前完成额度检查，并主动停止本次 AI 生成。",
            f"本次停止原因：{short_reason}",
            "行情、技术指标、策略信号、回测和候选评分等确定性能力不受本次 AI 额度影响。",
        ]

    def build_stock_analysis_blocked_suggestion(self) -> str:
        return (
            "建议稍后重新发起 AI 分析，或先查看行情数据、技术指标、策略信号、"
            "历史回测和候选评分等确定性结果。也可以通过 AI Usage 接口查看当前额度。"
        )

    def build_stock_analysis_blocked_warnings(self) -> list[str]:
        return [
            "本次结果是 AI 额度不足时的系统降级提示，不是完整 AI 分析结论。",
            "系统没有继续调用 DeepSeek，因此不会产生新的 AI 分析判断。",
            "以上内容仅供研究参考，不构成投资建议。",
        ]

    def build_react_blocked_answer(
        self,
        *,
        feature: AIUsageFeature,
        reason: str | None,
    ) -> str:
        feature_name = self.build_feature_name(feature)
        short_reason = self.build_short_reason(reason)

        return (
            f"当前 {feature_name} 的 AI 调用额度不足，本次没有继续调用大模型生成新的追问内容。"
            f"系统记录到的原因是：{short_reason}。"
            "你可以稍后再试，或者先查看已有分析记录、行情数据、技术指标、"
            "回测结果和候选评分等确定性信息。"
            "以上内容仅供研究参考，不构成投资建议。"
        )

    def build_candidate_ai_blocked_fallback_reason(self, reason: str | None) -> str:
        short_reason = self.build_short_reason(reason)
        return (
            "当前 AI 候选解释额度不足，系统没有继续调用 DeepSeek。"
            f"额度原因：{short_reason}。"
            "本次可以继续返回基于确定性候选评分生成的降级解释，"
            "但不会生成新的 AI 扩展解释。"
        )