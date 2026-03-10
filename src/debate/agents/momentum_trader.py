"""Momentum/Technical trading strategy agent."""

from __future__ import annotations

from src.debate.base_agent import StrategyAgent
from src.debate.models import DebateContext, Signal, StrategyOpinion


class MomentumTrader(StrategyAgent):
    """Evaluates based on technical indicators: RSI, MACD, SMA, Bollinger."""

    name = "momentum-trader"
    description = "추세 추종, 기술적 지표 기반 매매 판단"
    _needs_fundamentals = False

    def evaluate(self, context: DebateContext) -> StrategyOpinion:
        ind = self._latest_indicators(context)
        if not ind or ind.get("close") is None:
            return StrategyOpinion(
                agent_name=self.name,
                signal=Signal.HOLD,
                confidence=0.1,
                rationale="기술적 지표 데이터 부족으로 판단 보류.",
            )

        score = 0.0  # -1.0 (bearish) to +1.0 (bullish)
        reasons: list[str] = []
        metrics: dict = {}
        flags: list[str] = []

        # RSI
        rsi = ind.get("rsi_14")
        if rsi is not None:
            metrics["rsi_14"] = round(rsi, 1)
            if rsi <= 30:
                score += 0.3
                reasons.append(f"RSI {rsi:.1f} 과매도 → 반등 가능")
            elif rsi <= 45:
                score += 0.1
                reasons.append(f"RSI {rsi:.1f} 회복 초기")
            elif rsi >= 70:
                score -= 0.3
                reasons.append(f"RSI {rsi:.1f} 과매수 → 조정 가능")
                flags.append("RSI 과매수")
            elif rsi >= 55:
                score += 0.1
                reasons.append(f"RSI {rsi:.1f} 건전한 상승 구간")

        # MACD
        macd = ind.get("macd")
        macd_signal = ind.get("macd_signal")
        macd_hist = ind.get("macd_hist")
        if macd is not None and macd_signal is not None:
            metrics["macd"] = round(macd, 3)
            metrics["macd_signal"] = round(macd_signal, 3)
            if macd_hist is not None:
                metrics["macd_hist"] = round(macd_hist, 3)
            if macd > macd_signal:
                score += 0.2
                reasons.append("MACD 강세 크로스")
            else:
                score -= 0.2
                reasons.append("MACD 약세 구간")

        # SMA alignment
        close = ind.get("close")
        sma_20 = ind.get("sma_20")
        sma_50 = ind.get("sma_50")
        sma_200 = ind.get("sma_200")
        if close and sma_200:
            pct_from_200 = (close - sma_200) / sma_200 * 100
            metrics["vs_sma200"] = f"{pct_from_200:+.1f}%"
            if close > sma_200:
                score += 0.15
            else:
                score -= 0.15
                flags.append(f"SMA200 하회 ({pct_from_200:+.1f}%)")
        if close and sma_50 and sma_200:
            if sma_50 > sma_200:
                score += 0.1
                reasons.append("골든크로스 상태")
            elif sma_50 < sma_200:
                score -= 0.1
                reasons.append("데드크로스 상태")

        # Bollinger Bands
        bb_upper = ind.get("bb_upper")
        bb_lower = ind.get("bb_lower")
        if close and bb_upper and bb_lower:
            if close <= bb_lower:
                score += 0.15
                reasons.append("볼린저 하단 이탈 → 반등 기대")
            elif close >= bb_upper:
                score -= 0.1
                reasons.append("볼린저 상단 접근 → 과열")

        # Score to signal
        score = max(-1.0, min(1.0, score))
        confidence = min(abs(score) + 0.2, 1.0)
        confidence = self._apply_data_quality_penalty(confidence, context)
        self._add_data_warnings(flags, context)

        if score >= 0.5:
            signal = Signal.STRONG_BUY
        elif score >= 0.15:
            signal = Signal.BUY
        elif score <= -0.5:
            signal = Signal.STRONG_SELL
        elif score <= -0.15:
            signal = Signal.SELL
        else:
            signal = Signal.HOLD

        rationale = "; ".join(reasons[:3]) if reasons else "기술적 신호 중립."

        return StrategyOpinion(
            agent_name=self.name,
            signal=signal,
            confidence=round(confidence, 2),
            rationale=rationale,
            key_metrics=metrics,
            risk_flags=flags,
        )
