"""Macro-economic strategy agent."""

from __future__ import annotations

from src.debate.base_agent import StrategyAgent
from src.debate.models import DebateContext, Signal, StrategyOpinion


class MacroStrategist(StrategyAgent):
    """Evaluates based on macro-economic conditions: rates, inflation, FX, VIX."""

    name = "macro-strategist"
    description = "금리, 경기 사이클, 환율, 매크로 데이터 기반 전략"
    _needs_fundamentals = False

    def evaluate(self, context: DebateContext) -> StrategyOpinion:
        score = 0.0
        reasons: list[str] = []
        metrics: dict = {}
        flags: list[str] = []

        macro = {
            item.get("series_id", item.get("name", "")): item.get("value")
            for item in context.macro_snapshot
            if item.get("value") is not None
        }

        # Fed Funds Rate
        dff = macro.get("DFF")
        if dff is not None:
            metrics["fed_funds"] = dff
            if dff <= 3.0:
                score += 0.2
                reasons.append(f"기준금리 {dff}% — 완화적 환경")
            elif dff >= 5.0:
                score -= 0.2
                reasons.append(f"기준금리 {dff}% — 긴축적 환경")
                flags.append("고금리 환경")
            else:
                reasons.append(f"기준금리 {dff}% — 중립")

        # Yield curve (10Y-2Y spread)
        t10y2y = macro.get("T10Y2Y")
        if t10y2y is not None:
            metrics["yield_spread_10y2y"] = t10y2y
            if t10y2y < 0:
                score -= 0.2
                reasons.append(f"수익률 곡선 역전 ({t10y2y:.2f}%) — 경기 침체 신호")
                flags.append("수익률 곡선 역전")
            elif t10y2y > 0.5:
                score += 0.1
                reasons.append(f"수익률 곡선 정상화 ({t10y2y:.2f}%)")

        # CPI / Inflation expectations
        t5yie = macro.get("T5YIE")
        if t5yie is not None:
            metrics["inflation_5y_exp"] = t5yie
            if t5yie > 3.0:
                score -= 0.15
                reasons.append(f"인플레 기대 {t5yie:.1f}% — 고인플레")
                flags.append("인플레이션 우려")
            elif t5yie < 2.0:
                score += 0.1

        # Unemployment
        unrate = macro.get("UNRATE")
        if unrate is not None:
            metrics["unemployment"] = unrate
            if unrate > 5.0:
                score -= 0.15
                reasons.append(f"실업률 {unrate}% — 노동시장 약화")
                flags.append("고실업률")
            elif unrate < 4.0:
                score += 0.1
                reasons.append(f"실업률 {unrate}% — 고용 건전")

        # Consumer sentiment
        umcsent = macro.get("UMCSENT")
        if umcsent is not None:
            metrics["consumer_sentiment"] = umcsent
            if umcsent < 60:
                score -= 0.1
                reasons.append(f"소비자 심리 {umcsent} — 비관적")
            elif umcsent > 80:
                score += 0.1

        # VIX (from market_data or portfolio_context)
        vix = context.portfolio_context.get("vix")
        if vix is not None:
            metrics["vix"] = vix
            if vix >= 30:
                score -= 0.2
                reasons.append(f"VIX {vix:.1f} — 공포 구간")
                flags.append(f"VIX {vix:.0f} 고변동성")
            elif vix >= 20:
                score -= 0.05
            elif vix < 15:
                score += 0.1
                reasons.append(f"VIX {vix:.1f} — 안정적")

        # Asset-specific: currency impact
        currency = context.portfolio_context.get("currency", "USD")
        usdkrw = context.portfolio_context.get("usdkrw")
        if currency == "KRW" and usdkrw is not None:
            metrics["usdkrw"] = usdkrw
            if usdkrw > 1400:
                score -= 0.05
                reasons.append(f"원화 약세 ({usdkrw:.0f}) — 외국인 매도 압력")

        # Score to signal
        score = max(-1.0, min(1.0, score))
        confidence = min(abs(score) + 0.25, 1.0)
        confidence = self._apply_data_quality_penalty(confidence, context)
        self._add_data_warnings(flags, context)

        if score >= 0.4:
            signal = Signal.STRONG_BUY
        elif score >= 0.1:
            signal = Signal.BUY
        elif score <= -0.4:
            signal = Signal.STRONG_SELL
        elif score <= -0.1:
            signal = Signal.SELL
        else:
            signal = Signal.HOLD

        rationale = "; ".join(reasons[:3]) if reasons else "매크로 데이터 부족."

        return StrategyOpinion(
            agent_name=self.name,
            signal=signal,
            confidence=round(confidence, 2),
            rationale=rationale,
            key_metrics=metrics,
            risk_flags=flags,
        )
