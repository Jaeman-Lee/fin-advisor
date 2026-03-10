"""Value investing strategy agent."""

from __future__ import annotations

from src.debate.base_agent import StrategyAgent
from src.debate.models import DebateContext, Signal, StrategyOpinion


class ValueInvestor(StrategyAgent):
    """Evaluates based on intrinsic value: P/E, P/B, FCF, margin of safety."""

    name = "value-investor"
    description = "내재가치 대비 저평가 분석 — 버핏/그레이엄 스타일"

    def evaluate(self, context: DebateContext) -> StrategyOpinion:
        score = 0.0
        reasons: list[str] = []
        metrics: dict = {}
        flags: list[str] = []

        f = context.fundamentals

        # P/E ratio
        pe = f.get("forward_pe") or f.get("trailing_pe")
        if pe is not None:
            metrics["pe_ratio"] = round(pe, 1)
            if pe < 12:
                score += 0.3
                reasons.append(f"P/E {pe:.1f}x — 저평가 영역")
            elif pe < 20:
                score += 0.1
                reasons.append(f"P/E {pe:.1f}x — 합리적 수준")
            elif pe > 40:
                score -= 0.3
                reasons.append(f"P/E {pe:.1f}x — 고평가")
                flags.append(f"P/E {pe:.0f}x 고평가")
            elif pe > 25:
                score -= 0.1
                reasons.append(f"P/E {pe:.1f}x — 다소 높음")

        # P/B ratio
        pb = f.get("price_to_book")
        if pb is not None:
            metrics["pb_ratio"] = round(pb, 2)
            if pb < 1.0:
                score += 0.2
                reasons.append(f"P/B {pb:.2f}x — 장부가 이하")
            elif pb < 2.0:
                score += 0.05
            elif pb > 5.0:
                score -= 0.1

        # Free cash flow yield
        fcf = f.get("free_cashflow")
        market_cap = f.get("market_cap")
        if fcf and market_cap and market_cap > 0:
            fcf_yield = fcf / market_cap * 100
            metrics["fcf_yield"] = f"{fcf_yield:.1f}%"
            if fcf_yield > 8:
                score += 0.2
                reasons.append(f"FCF 수익률 {fcf_yield:.1f}% — 매력적")
            elif fcf_yield > 4:
                score += 0.1
            elif fcf_yield < 0:
                score -= 0.2
                flags.append("음의 잉여현금흐름")

        # Profit margin
        margin = f.get("profit_margins")
        if margin is not None:
            margin_pct = margin * 100 if margin < 1 else margin
            metrics["profit_margin"] = f"{margin_pct:.1f}%"
            if margin_pct > 20:
                score += 0.1
            elif margin_pct < 0:
                score -= 0.2
                flags.append("적자 기업")

        # Debt-to-equity
        de = f.get("debt_to_equity")
        if de is not None:
            metrics["debt_to_equity"] = round(de, 1)
            if de > 200:
                score -= 0.15
                flags.append(f"부채비율 {de:.0f}% 과다")
            elif de < 50:
                score += 0.1

        # 52-week range (margin of safety)
        high_52 = f.get("fifty_two_week_high")
        low_52 = f.get("fifty_two_week_low")
        ind = self._latest_indicators(context)
        close = ind.get("close")
        if close and high_52 and high_52 > 0:
            from_high = (close - high_52) / high_52 * 100
            metrics["vs_52w_high"] = f"{from_high:+.1f}%"
            if from_high < -30:
                score += 0.15
                reasons.append(f"52주 고점 대비 {from_high:+.1f}% — 안전마진 확보")

        if not f:
            return StrategyOpinion(
                agent_name=self.name,
                signal=Signal.HOLD,
                confidence=0.15,
                rationale="펀더멘탈 데이터 부족으로 판단 보류.",
                risk_flags=["데이터 부족 — 신뢰도 낮음"],
            )

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

        rationale = "; ".join(reasons[:3]) if reasons else "밸류에이션 중립."

        return StrategyOpinion(
            agent_name=self.name,
            signal=signal,
            confidence=round(confidence, 2),
            rationale=rationale,
            key_metrics=metrics,
            risk_flags=flags,
        )
