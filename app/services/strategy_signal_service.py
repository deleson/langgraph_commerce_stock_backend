"""策略信号规则服务。

本服务把技术指标和数据质量报告转换成确定性的策略信号。它不是 LLM 自由判断，
也不是投资建议：所有 buy / sell / hold / observe 都来自固定规则、固定分数和
固定阈值，主要用于研究、回测、候选评分和纸面交易模拟。
"""

from app.schemas.market_data_sync import MarketDataQualityReport
from app.schemas.strategy_signal import (
    StrategySignalInputSnapshot,
    StrategySignalResponse,
    StrategyRuleResult,
)
from app.schemas.technical_indicator import (
    MacdSnapshot,
    MomentumSnapshot,
    MovingAverageSnapshot,
    RsiSnapshot,
    TechnicalIndicatorResponse,
    VolatilitySnapshot,
    VolumeFactorSnapshot,
)


class StrategySignalService:
    """根据技术指标生成可解释的策略信号。

    评分流程是“中性基准分 + 多个规则加减分 + 阈值映射信号”。这样做的好处是：
    每个分数来源都能在 rule_results 中审计，后续回测和纸面交易也能复盘依据。
    """

    # 50 分表示中性起点；各规则只做加减分，最后再限制在 0 到 100。
    # 这些常量是第一版确定性策略权重，不代表真实投资模型已经最优。
    BASE_SCORE = 50
    MAX_REASON_COUNT = 10
    MAX_RISK_COUNT = 10
    QUALITY_LIMITED_SCORE = 40
    UNAVAILABLE_SCORE = 0
    TREND_BULLISH_SCORE = 18
    TREND_BEARISH_SCORE = -18
    TREND_CONFIRM_SCORE = 5
    RSI_OVERSOLD_SCORE = 10
    RSI_OVERBOUGHT_SCORE = -12
    RSI_LOW_CONFIRM_SCORE = 5
    RSI_HIGH_RISK_SCORE = -5
    MACD_BULLISH_SCORE = 18
    MACD_BEARISH_SCORE = -18
    MACD_HISTOGRAM_CONFIRM_SCORE = 4
    MOMENTUM_BULLISH_SCORE = 12
    MOMENTUM_BEARISH_SCORE = -12
    MOMENTUM_CONFIRM_SCORE = 4
    VOLATILITY_LOW_SCORE = 3
    VOLATILITY_HIGH_RISK_SCORE = -12
    VOLATILITY_EXTREME_RISK_SCORE = -5
    EXTREME_ANNUALIZED_VOLATILITY = 0.6
    VOLUME_EXPANDING_SCORE = 6
    VOLUME_SHRINKING_RISK_SCORE = -6
    VOLUME_EXTREME_EXPANDING_SCORE = 3
    VOLUME_EXTREME_SHRINKING_RISK_SCORE = -3
    HIGH_VOLUME_RATIO = 2.0
    LOW_VOLUME_RATIO = 0.5

    def generate_signal(
        self,
        *,
        technical_indicators: TechnicalIndicatorResponse,
        data_quality: MarketDataQualityReport | None = None,
        include_detail: bool = True,
    ) -> StrategySignalResponse:
        """生成策略信号响应。

        先执行数据质量门控：无数据或硬错误直接 unavailable；数据不足或过旧只给
        observe。数据可用时再计算趋势、RSI、MACD、动量、波动率和成交量规则。
        """

        quality_rule = self._build_data_quality_rule(data_quality)
        reasons = self._build_initial_reasons(technical_indicators)
        risks = self._build_initial_risks(
            technical_indicators=technical_indicators,
            data_quality=data_quality,
        )

        if quality_rule is not None:
            reasons.append(quality_rule.reason)
            risks.extend(quality_rule.warnings)

        if self._is_data_unavailable(data_quality):
            return StrategySignalResponse(
                symbol=technical_indicators.symbol,
                market=technical_indicators.market,
                timeframe=technical_indicators.timeframe,
                adjust_type=technical_indicators.adjust_type,
                source=technical_indicators.source,
                status="unavailable",
                signal=None,
                strength=None,
                score=self.UNAVAILABLE_SCORE,
                summary=self._build_unavailable_summary(
                    technical_indicators=technical_indicators,
                    data_quality=data_quality,
                ),
                reasons=self._limit_text_list(reasons, limit=self.MAX_REASON_COUNT),
                risks=self._limit_text_list(risks, limit=self.MAX_RISK_COUNT),
                rule_results=self._build_rule_results(
                    quality_rule=quality_rule,
                    include_detail=include_detail,
                ),
                input_snapshot=self._build_input_snapshot(
                    technical_indicators=technical_indicators,
                    data_quality=data_quality,
                    include_detail=include_detail,
                ),
            )

        if self._is_data_quality_limited(data_quality):
            return StrategySignalResponse(
                symbol=technical_indicators.symbol,
                market=technical_indicators.market,
                timeframe=technical_indicators.timeframe,
                adjust_type=technical_indicators.adjust_type,
                source=technical_indicators.source,
                status="available",
                signal="observe",
                strength="weak",
                score=self.QUALITY_LIMITED_SCORE,
                summary=self._build_quality_limited_summary(
                    technical_indicators=technical_indicators,
                    data_quality=data_quality,
                ),
                reasons=self._limit_text_list(reasons, limit=self.MAX_REASON_COUNT),
                risks=self._limit_text_list(risks, limit=self.MAX_RISK_COUNT),
                rule_results=self._build_rule_results(
                    quality_rule=quality_rule,
                    include_detail=include_detail,
                ),
                input_snapshot=self._build_input_snapshot(
                    technical_indicators=technical_indicators,
                    data_quality=data_quality,
                    include_detail=include_detail,
                ),
            )

        trend_rule = self._build_trend_rule(
            technical_indicators.summary.moving_average
        )
        rsi_rule = self._build_rsi_rule(technical_indicators.summary.rsi)
        macd_rule = self._build_macd_rule(technical_indicators.summary.macd)
        momentum_rule = self._build_momentum_rule(
            technical_indicators.summary.momentum
        )
        volatility_rule = self._build_volatility_rule(
            technical_indicators.summary.volatility
        )
        volume_rule = self._build_volume_rule(
            technical_indicators.summary.volume_factor
        )

        # 总分只由固定规则得出，没有 LLM 参与。这样回测、候选评分和纸面交易
        # 每一次信号都能通过 rule_results 追溯到具体指标。
        score = self._clamp_score(
            self.BASE_SCORE
            + trend_rule.score_delta
            + rsi_rule.score_delta
            + macd_rule.score_delta
            + momentum_rule.score_delta
            + volatility_rule.score_delta
            + volume_rule.score_delta
        )
        signal = self._signal_from_score(score)
        strength = self._strength_from_score(score)

        reasons.append(trend_rule.reason)
        reasons.append(rsi_rule.reason)
        reasons.append(macd_rule.reason)
        reasons.append(momentum_rule.reason)
        reasons.append(volatility_rule.reason)
        reasons.append(volume_rule.reason)
        risks.extend(trend_rule.warnings)
        risks.extend(rsi_rule.warnings)
        risks.extend(macd_rule.warnings)
        risks.extend(momentum_rule.warnings)
        risks.extend(volatility_rule.warnings)
        risks.extend(volume_rule.warnings)

        return StrategySignalResponse(
            symbol=technical_indicators.symbol,
            market=technical_indicators.market,
            timeframe=technical_indicators.timeframe,
            adjust_type=technical_indicators.adjust_type,
            source=technical_indicators.source,
            status="available",
            signal=signal,
            strength=strength,
            score=score,
            summary=self._build_baseline_summary(technical_indicators),
            reasons=self._limit_text_list(reasons, limit=self.MAX_REASON_COUNT),
            risks=self._limit_text_list(risks, limit=self.MAX_RISK_COUNT),
            rule_results=self._build_rule_results(
                quality_rule=quality_rule,
                trend_rule=trend_rule,
                rsi_rule=rsi_rule,
                macd_rule=macd_rule,
                momentum_rule=momentum_rule,
                volatility_rule=volatility_rule,
                volume_rule=volume_rule,
                include_detail=include_detail,
            ),
            input_snapshot=self._build_input_snapshot(
                technical_indicators=technical_indicators,
                data_quality=data_quality,
                include_detail=include_detail,
            ),
        )

    def _is_data_unavailable(
        self,
        data_quality: MarketDataQualityReport | None,
    ) -> bool:
        if data_quality is None:
            return False

        return data_quality.is_empty or bool(data_quality.errors)

    def _is_data_quality_limited(
        self,
        data_quality: MarketDataQualityReport | None,
    ) -> bool:
        if data_quality is None:
            return False

        return (not data_quality.is_enough) or data_quality.is_stale

    def _build_data_quality_rule(
        self,
        data_quality: MarketDataQualityReport | None,
    ) -> StrategyRuleResult | None:
        """构建数据质量规则。

        数据质量是所有策略规则之前的安全门：空数据和硬错误不能生成信号；
        数量不足或过旧只能观察，避免系统在数据基础不可靠时给出强信号。
        """

        if data_quality is None:
            return StrategyRuleResult(
                rule_name="data_quality",
                direction="neutral",
                score_delta=0,
                reason="当前未传入数据质量报告，暂不根据数据质量调整策略信号。",
                warnings=["缺少数据质量报告，策略信号可信度需要谨慎看待。"],
            )

        if data_quality.is_empty:
            return StrategyRuleResult(
                rule_name="data_quality",
                direction="invalid",
                score_delta=-100,
                reason="当前没有可用 K 线数据，无法生成策略信号。",
                warnings=data_quality.errors or ["K 线数据为空。"],
            )

        if data_quality.errors:
            return StrategyRuleResult(
                rule_name="data_quality",
                direction="invalid",
                score_delta=-100,
                reason="当前 K 线数据存在硬错误，无法生成策略信号。",
                warnings=data_quality.errors,
            )

        if not data_quality.is_enough:
            return StrategyRuleResult(
                rule_name="data_quality",
                direction="risk",
                score_delta=-10,
                reason="当前 K 线数量不足，策略信号只能作为观察参考。",
                warnings=data_quality.warnings or ["K 线数量不足。"],
            )

        if data_quality.is_stale:
            return StrategyRuleResult(
                rule_name="data_quality",
                direction="risk",
                score_delta=-10,
                reason="当前 K 线数据可能过旧，策略信号只能作为观察参考。",
                warnings=data_quality.warnings or ["K 线数据可能过旧。"],
            )

        return StrategyRuleResult(
            rule_name="data_quality",
            direction="neutral",
            score_delta=0,
            reason=f"当前 K 线数据质量可用，共 {data_quality.candle_count} 根。",
            warnings=data_quality.warnings,
        )

    def _build_unavailable_summary(
        self,
        *,
        technical_indicators: TechnicalIndicatorResponse,
        data_quality: MarketDataQualityReport | None,
    ) -> str:
        if data_quality is None:
            return (
                f"{technical_indicators.market}:{technical_indicators.symbol} "
                "当前缺少数据质量报告，无法确认策略信号可靠性。"
            )

        if data_quality.is_empty:
            return (
                f"{technical_indicators.market}:{technical_indicators.symbol} "
                "当前没有可用 K 线数据，暂无法生成策略信号。"
            )

        return (
            f"{technical_indicators.market}:{technical_indicators.symbol} "
            "当前 K 线数据存在错误，暂无法生成策略信号。"
        )

    def _build_quality_limited_summary(
        self,
        *,
        technical_indicators: TechnicalIndicatorResponse,
        data_quality: MarketDataQualityReport | None,
    ) -> str:
        if data_quality is None:
            return self._build_baseline_summary(technical_indicators)

        if not data_quality.is_enough:
            return (
                f"{technical_indicators.market}:{technical_indicators.symbol} "
                f"当前 K 线数量为 {data_quality.candle_count}，数据不足，策略信号仅建议观察。"
            )

        if data_quality.is_stale:
            return (
                f"{technical_indicators.market}:{technical_indicators.symbol} "
                "当前 K 线数据可能过旧，策略信号仅建议观察。"
            )

        return self._build_baseline_summary(technical_indicators)

    def _build_rule_results(
        self,
        *,
        quality_rule: StrategyRuleResult | None,
        trend_rule: StrategyRuleResult | None = None,
        rsi_rule: StrategyRuleResult | None = None,
        macd_rule: StrategyRuleResult | None = None,
        momentum_rule: StrategyRuleResult | None = None,
        volatility_rule: StrategyRuleResult | None = None,
        volume_rule: StrategyRuleResult | None = None,
        include_detail: bool,
    ) -> list[StrategyRuleResult]:
        if not include_detail:
            return []

        results: list[StrategyRuleResult] = []

        if quality_rule is not None:
            results.append(quality_rule)

        if trend_rule is not None:
            results.append(trend_rule)

        if rsi_rule is not None:
            results.append(rsi_rule)

        if macd_rule is not None:
            results.append(macd_rule)

        if momentum_rule is not None:
            results.append(momentum_rule)

        if volatility_rule is not None:
            results.append(volatility_rule)

        if volume_rule is not None:
            results.append(volume_rule)

        return results

    def _build_trend_rule(
        self,
        moving_average: MovingAverageSnapshot,
    ) -> StrategyRuleResult:
        """构建均线趋势规则。

        多头排列加分，空头排列扣分；MA5/MA20 与 EMA12/EMA26 只是确认项，
        用来降低单一均线标签带来的误判风险。
        """

        score_delta = 0
        warnings: list[str] = []

        if moving_average.trend == "bullish":
            score_delta += self.TREND_BULLISH_SCORE
            direction = "bullish"
            reason = "均线趋势偏多，当前价格结构表现出一定上行动能。"
        elif moving_average.trend == "bearish":
            score_delta += self.TREND_BEARISH_SCORE
            direction = "bearish"
            reason = "均线趋势偏空，当前价格结构表现出一定下行压力。"
        else:
            direction = "neutral"
            reason = "均线趋势暂时中性，尚未形成明确方向。"

        confirm_delta = self._calculate_trend_confirmation_score(moving_average)
        score_delta += confirm_delta

        if confirm_delta > 0:
            reason += " MA5 高于 MA20 且 EMA12 高于 EMA26，短期趋势得到一定确认。"
        elif confirm_delta < 0:
            reason += " MA5 低于 MA20 且 EMA12 低于 EMA26，短期弱势得到一定确认。"
        elif self._has_missing_trend_confirmation_values(moving_average):
            warnings.append("部分均线数据缺失，趋势确认分未完全计算。")

        return StrategyRuleResult(
            rule_name="trend",
            direction=direction,
            score_delta=score_delta,
            reason=reason,
            warnings=warnings,
        )

    def _build_rsi_rule(
        self,
        rsi: RsiSnapshot,
    ) -> StrategyRuleResult:
        """构建 RSI 规则。

        RSI 超卖会适度加分，表示可能存在修复机会；RSI 超买会扣分，
        表示追高风险上升。超卖不直接等于买入，因为弱势股票也可能长期低 RSI。
        """

        score_delta = 0
        warnings: list[str] = []

        if rsi.status == "oversold":
            score_delta += self.RSI_OVERSOLD_SCORE
            direction = "bullish"
            reason = "RSI 处于超卖区域，价格短期可能存在修复机会，但不代表一定反弹。"
        elif rsi.status == "overbought":
            score_delta += self.RSI_OVERBOUGHT_SCORE
            direction = "risk"
            reason = "RSI 处于超买区域，短期追高风险上升。"
        else:
            direction = "neutral"
            reason = "RSI 当前处于中性区域，暂未给出明显超买或超卖信号。"

        if rsi.rsi12 is None:
            warnings.append("RSI12 数据缺失，无法进行中周期 RSI 强弱确认。")
        elif rsi.rsi12 <= 30:
            score_delta += self.RSI_LOW_CONFIRM_SCORE
            direction = "bullish"
            reason += f" RSI12={rsi.rsi12:.2f}，处于明显低位。"
        elif rsi.rsi12 >= 70:
            score_delta += self.RSI_HIGH_RISK_SCORE
            direction = "risk"
            reason += f" RSI12={rsi.rsi12:.2f}，处于明显过热区域。"

        if self._has_missing_rsi_values(rsi):
            warnings.append("部分 RSI 数据缺失，RSI 规则可信度需要谨慎看待。")

        return StrategyRuleResult(
            rule_name="rsi",
            direction=direction,
            score_delta=score_delta,
            reason=reason,
            warnings=self._limit_text_list(warnings, limit=5),
        )

    def _build_macd_rule(
        self,
        macd: MacdSnapshot,
    ) -> StrategyRuleResult:
        """构建 MACD 动能规则。

        MACD 用 DIF、DEA 和柱体观察趋势动能。多头动能加分，空头动能扣分；
        histogram 作为额外确认项，避免只看 DIF/DEA 标签。
        """

        score_delta = 0
        warnings: list[str] = []

        if macd.signal == "bullish":
            score_delta += self.MACD_BULLISH_SCORE
            direction = "bullish"
            reason = "MACD 当前为多头信号，趋势动能偏强。"
        elif macd.signal == "bearish":
            score_delta += self.MACD_BEARISH_SCORE
            direction = "bearish"
            reason = "MACD 当前为空头信号，趋势动能偏弱。"
        else:
            direction = "neutral"
            reason = "MACD 当前为中性信号，趋势动能暂不明显。"

        if macd.histogram is None:
            warnings.append("MACD histogram 数据缺失，无法进行柱状图动能确认。")
        elif macd.histogram > 0:
            score_delta += self.MACD_HISTOGRAM_CONFIRM_SCORE
            if direction == "neutral":
                direction = "bullish"
            reason += f" histogram={macd.histogram:.4f}，柱状图为正，动能有一定支持。"
        elif macd.histogram < 0:
            score_delta -= self.MACD_HISTOGRAM_CONFIRM_SCORE
            if direction == "neutral":
                direction = "bearish"
            reason += f" histogram={macd.histogram:.4f}，柱状图为负，动能偏弱。"

        if self._has_missing_macd_values(macd):
            warnings.append("部分 MACD 数据缺失，MACD 规则可信度需要谨慎看待。")

        return StrategyRuleResult(
            rule_name="macd",
            direction=direction,
            score_delta=score_delta,
            reason=reason,
            warnings=self._limit_text_list(warnings, limit=5),
        )

    def _build_momentum_rule(
        self,
        momentum: MomentumSnapshot,
    ) -> StrategyRuleResult:
        """构建价格动量规则。

        动量规则比较最新价格和历史窗口价格的差值。中短期动量一致时额外加减分，
        但它仍然只是策略总分中的一个维度。
        """

        score_delta = 0
        warnings: list[str] = []

        if momentum.direction == "bullish":
            score_delta += self.MOMENTUM_BULLISH_SCORE
            direction = "bullish"
            reason = "动量方向偏多，近期价格变化速度支持上行动能。"
        elif momentum.direction == "bearish":
            score_delta += self.MOMENTUM_BEARISH_SCORE
            direction = "bearish"
            reason = "动量方向偏空，近期价格变化速度显示下行压力。"
        else:
            direction = "neutral"
            reason = "动量方向暂时中性，近期价格变化速度不明显。"

        if self._has_missing_momentum_confirmation_values(momentum):
            warnings.append("部分动量数据缺失，无法完整确认中短期动量一致性。")
        elif momentum.momentum_20 > 0 and momentum.momentum_10 > 0:
            score_delta += self.MOMENTUM_CONFIRM_SCORE
            direction = "bullish"
            reason += " momentum_10 和 momentum_20 均为正，中短期动量一致偏多。"
        elif momentum.momentum_20 < 0 and momentum.momentum_10 < 0:
            score_delta -= self.MOMENTUM_CONFIRM_SCORE
            direction = "bearish"
            reason += " momentum_10 和 momentum_20 均为负，中短期动量一致偏弱。"

        if self._has_missing_momentum_values(momentum):
            warnings.append("部分动量数据缺失，动量规则可信度需要谨慎看待。")

        return StrategyRuleResult(
            rule_name="momentum",
            direction=direction,
            score_delta=score_delta,
            reason=reason,
            warnings=self._limit_text_list(warnings, limit=5),
        )

    def _build_volatility_rule(
        self,
        volatility: VolatilitySnapshot,
    ) -> StrategyRuleResult:
        """构建波动率风险规则。

        低波动小幅加分，高波动和极端波动扣分。这里的目标不是预测涨跌，
        而是把历史波动风险纳入策略评分。
        """

        score_delta = 0
        warnings: list[str] = []

        if volatility.level == "low":
            score_delta += self.VOLATILITY_LOW_SCORE
            direction = "neutral"
            reason = "当前波动率较低，价格波动相对可控。"
        elif volatility.level == "high":
            score_delta += self.VOLATILITY_HIGH_RISK_SCORE
            direction = "risk"
            reason = "当前波动率较高，价格波动风险上升。"
        else:
            direction = "neutral"
            reason = "当前波动率处于中等水平，暂不对策略信号做明显调整。"

        if volatility.annualized_volatility is None:
            warnings.append("年化波动率数据缺失，无法确认是否存在极端波动风险。")
        elif volatility.annualized_volatility >= self.EXTREME_ANNUALIZED_VOLATILITY:
            score_delta += self.VOLATILITY_EXTREME_RISK_SCORE
            direction = "risk"
            reason += (
                f" 年化波动率为 {volatility.annualized_volatility:.2f}，"
                "已经达到较高风险区间。"
            )

        if self._has_missing_volatility_values(volatility):
            warnings.append("部分波动率数据缺失，波动率规则可信度需要谨慎看待。")

        return StrategyRuleResult(
            rule_name="volatility",
            direction=direction,
            score_delta=score_delta,
            reason=reason,
            warnings=self._limit_text_list(warnings, limit=5),
        )

    def _build_volume_rule(
        self,
        volume_factor: VolumeFactorSnapshot,
    ) -> StrategyRuleResult:
        """构建成交量确认规则。

        放量表示市场参与度提升，缩量表示确认度不足。成交量只做辅助确认，
        不单独决定买卖方向。
        """

        score_delta = 0
        warnings: list[str] = []

        if volume_factor.status == "expanding":
            score_delta += self.VOLUME_EXPANDING_SCORE
            direction = "bullish"
            reason = "成交量处于放量状态，市场参与度上升，对当前策略信号形成一定确认。"
        elif volume_factor.status == "shrinking":
            score_delta += self.VOLUME_SHRINKING_RISK_SCORE
            direction = "risk"
            reason = "成交量处于缩量状态，市场参与度下降，当前策略信号确认度不足。"
        else:
            direction = "neutral"
            reason = "成交量处于正常状态，暂不对策略信号做明显调整。"

        if volume_factor.volume_ratio is None:
            warnings.append("成交量比例 volume_ratio 缺失，无法判断是否明显放量或缩量。")
        elif volume_factor.volume_ratio >= self.HIGH_VOLUME_RATIO:
            score_delta += self.VOLUME_EXTREME_EXPANDING_SCORE
            direction = "bullish"
            reason += f" volume_ratio={volume_factor.volume_ratio:.2f}，明显高于中期均量。"
        elif volume_factor.volume_ratio <= self.LOW_VOLUME_RATIO:
            score_delta += self.VOLUME_EXTREME_SHRINKING_RISK_SCORE
            direction = "risk"
            reason += f" volume_ratio={volume_factor.volume_ratio:.2f}，明显低于中期均量。"

        if self._has_missing_volume_values(volume_factor):
            warnings.append("部分成交量因子数据缺失，成交量规则可信度需要谨慎看待。")

        return StrategyRuleResult(
            rule_name="volume",
            direction=direction,
            score_delta=score_delta,
            reason=reason,
            warnings=self._limit_text_list(warnings, limit=5),
        )

    def _has_missing_volume_values(
        self,
        volume_factor: VolumeFactorSnapshot,
    ) -> bool:
        return any(
            value is None
            for value in (
                volume_factor.volume_ma5,
                volume_factor.volume_ma20,
                volume_factor.volume_ratio,
            )
        )

    def _has_missing_volatility_values(
        self,
        volatility: VolatilitySnapshot,
    ) -> bool:
        return any(
            value is None
            for value in (
                volatility.daily_return_std,
                volatility.annualized_volatility,
            )
        )

    def _has_missing_momentum_confirmation_values(
        self,
        momentum: MomentumSnapshot,
    ) -> bool:
        return momentum.momentum_10 is None or momentum.momentum_20 is None

    def _has_missing_momentum_values(
        self,
        momentum: MomentumSnapshot,
    ) -> bool:
        return any(
            value is None
            for value in (
                momentum.momentum_5,
                momentum.momentum_10,
                momentum.momentum_20,
            )
        )

    def _has_missing_macd_values(
        self,
        macd: MacdSnapshot,
    ) -> bool:
        return any(
            value is None
            for value in (
                macd.dif,
                macd.dea,
                macd.histogram,
            )
        )

    def _has_missing_rsi_values(
        self,
        rsi: RsiSnapshot,
    ) -> bool:
        return any(
            value is None
            for value in (
                rsi.rsi6,
                rsi.rsi12,
                rsi.rsi24,
            )
        )

    def _calculate_trend_confirmation_score(
        self,
        moving_average: MovingAverageSnapshot,
    ) -> int:
        """计算趋势确认分。

        只有 MA 和 EMA 同向时才给确认分；缺少任一关键值时返回 0，
        避免样本不足时放大趋势信号。
        """

        if self._has_missing_trend_confirmation_values(moving_average):
            return 0

        if (
                moving_average.ma5 > moving_average.ma20
                and moving_average.ema12 > moving_average.ema26
        ):
            return self.TREND_CONFIRM_SCORE

        if (
                moving_average.ma5 < moving_average.ma20
                and moving_average.ema12 < moving_average.ema26
        ):
            return -self.TREND_CONFIRM_SCORE

        return 0

    def _has_missing_trend_confirmation_values(
        self,
        moving_average: MovingAverageSnapshot,
    ) -> bool:
        return any(
            value is None
            for value in (
                moving_average.ma5,
                moving_average.ma20,
                moving_average.ema12,
                moving_average.ema26,
            )
        )


    def _build_input_snapshot(
        self,
        *,
        technical_indicators: TechnicalIndicatorResponse,
        data_quality: MarketDataQualityReport | None,
        include_detail: bool,
    ) -> StrategySignalInputSnapshot:
        return StrategySignalInputSnapshot(
            technical_indicators=technical_indicators if include_detail else None,
            data_quality=data_quality if include_detail else None,
        )

    def _build_baseline_summary(
        self,
        technical_indicators: TechnicalIndicatorResponse,
    ) -> str:
        trend = technical_indicators.summary.moving_average.trend
        rsi_status = technical_indicators.summary.rsi.status
        macd_signal = technical_indicators.summary.macd.signal
        momentum_direction = technical_indicators.summary.momentum.direction
        volatility_level = technical_indicators.summary.volatility.level
        volume_status = technical_indicators.summary.volume_factor.status
        return (
            f"{technical_indicators.market}:{technical_indicators.symbol} "
            f"当前已根据数据质量、均线趋势、RSI、MACD、动量、波动率和成交量生成策略信号，"
            f"均线趋势为 {trend}，RSI 状态为 {rsi_status}，"
            f"MACD 信号为 {macd_signal}，动量方向为 {momentum_direction}，"
            f"波动率等级为 {volatility_level}，成交量状态为 {volume_status}。"
        )

    def _build_initial_reasons(
        self,
        technical_indicators: TechnicalIndicatorResponse,
    ) -> list[str]:
        reasons = [
            *technical_indicators.summary.interpretation,
            f"当前技术指标基于 {technical_indicators.candle_count} 根 K 线计算。",
        ]

        return self._limit_text_list(reasons, limit=self.MAX_REASON_COUNT)

    def _build_initial_risks(
        self,
        *,
        technical_indicators: TechnicalIndicatorResponse,
        data_quality: MarketDataQualityReport | None,
    ) -> list[str]:
        risks = [
            *technical_indicators.summary.warnings,
            "当前策略信号已接入趋势、RSI、MACD、动量、波动率和成交量规则，后续仍会继续优化综合评分权重。",
        ]

        if data_quality is None:
            risks.append("当前未传入数据质量报告，后续步骤会加入数据质量门控。")
        else:
            risks.extend(data_quality.warnings)
            risks.extend(data_quality.errors)

        return self._limit_text_list(risks, limit=self.MAX_RISK_COUNT)

    def _limit_text_list(
        self,
        values: list[str],
        *,
        limit: int,
    ) -> list[str]:
        """限制 reasons / risks 数量并去重。

        API 响应需要保留关键解释，但不能无限堆叠文本；限制数量可以保证前端展示
        和后台任务结果都保持可读。
        """

        result: list[str] = []
        seen: set[str] = set()

        for value in values:
            text = str(value).strip()
            if not text or text in seen:
                continue

            seen.add(text)
            result.append(text[:300])

            if len(result) >= limit:
                break

        return result

    def _clamp_score(
        self,
        score: int,
    ) -> int:
        return max(0, min(100, score))

    def _signal_from_score(
        self,
        score: int,
    ) -> str:
        """把 0-100 总分映射为策略信号。

        高分区间偏 buy，低分区间偏 sell，中间区间保持 hold / observe。
        observe 表示需要继续观察，不等于系统建议用户真实交易。
        """

        if score >= 65:
            return "buy"

        if score >= 55:
            return "observe"

        if score >= 45:
            return "hold"

        if score >= 35:
            return "observe"

        return "sell"

    def _strength_from_score(
        self,
        score: int,
    ) -> str:
        """根据分数距离中性区间的程度生成强弱标签。"""

        if score >= 75 or score < 25:
            return "strong"

        if score >= 55 or score < 45:
            return "medium"

        return "weak"


