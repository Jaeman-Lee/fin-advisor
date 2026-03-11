"""Growth investing strategy agent."""

from __future__ import annotations

from src.debate.base_agent import StrategyAgent
from src.debate.models import DebateContext, Signal, StrategyOpinion


class GrowthInvestor(StrategyAgent):
    """Evaluates based on growth metrics: revenue growth, PEG, innovation."""

    name = "growth-investor"
    description = "매출 성장률, TAM, 혁신성 기반 성장주 발굴"

    def evaluate(self, context: DebateContext) -> StrategyOpinion:
        score = 0.0
        reasons: list[str] = []
        metrics: dict = {}
        flags: list[str] = []

        f = context.fundamentals

        # Revenue growth
        rev_growth = f.get("revenue_growth")
        if rev_growth is not None:
            growth_pct = rev_growth * 100 if abs(rev_growth) < 5 else rev_growth
            metrics["revenue_growth"] = f"{growth_pct:+.1f}%"
            if growth_pct > 25:
                score += 0.3
                reasons.append(f"매출 성장 {growth_pct:+.1f}% — 고성장")
            elif growth_pct > 10:
                score += 0.15
                reasons.append(f"매출 성장 {growth_pct:+.1f}% — 양호")
            elif growth_pct < 0:
                score -= 0.2
                reasons.append(f"매출 성장 {growth_pct:+.1f}% — 역성장")
                flags.append("매출 역성장")

        # Earnings growth
        earnings_growth = f.get("earnings_growth")
        if earnings_growth is not None:
            eg_pct = earnings_growth * 100 if abs(earnings_growth) < 5 else earnings_growth
            metrics["earnings_growth"] = f"{eg_pct:+.1f}%"
            if eg_pct > 30:
                score += 0.2
            elif eg_pct > 10:
                score += 0.1
            elif eg_pct < -10:
                score -= 0.15
                flags.append("이익 감소")

        # PEG ratio (P/E / Growth)
        pe = f.get("forward_pe") or f.get("trailing_pe")
        if pe and rev_growth and rev_growth > 0:
            growth_for_peg = rev_growth * 100 if rev_growth < 1 else rev_growth
            if growth_for_peg > 0:
                peg = pe / growth_for_peg
                metrics["peg_ratio"] = round(peg, 2)
                if peg < 1.0:
                    score += 0.2
                    reasons.append(f"PEG {peg:.2f} — 성장 대비 저렴")
                elif peg > 2.5:
                    score -= 0.15
                    reasons.append(f"PEG {peg:.2f} — 성장 대비 비쌈")

        # Gross margin (high margin = competitive moat)
        gross_margin = f.get("gross_margins")
        if gross_margin is not None:
            gm_pct = gross_margin * 100 if gross_margin < 1 else gross_margin
            metrics["gross_margin"] = f"{gm_pct:.1f}%"
            if gm_pct > 60:
                score += 0.1
                reasons.append(f"매출총이익률 {gm_pct:.0f}% — 강한 경쟁력")
            elif gm_pct < 20:
                score -= 0.1

        # R&D intensity (proxy for innovation)
        # Not always available, check operating_expenses or similar

        # Market cap growth potential
        market_cap = f.get("market_cap")
        if market_cap:
            metrics["market_cap"] = f"${market_cap/1e9:.1f}B"

        # Analyst target upside
        target = f.get("target_mean_price")
        ind = self._latest_indicators(context)
        close = ind.get("close")
        if target and close and close > 0:
            upside = (target - close) / close * 100
            metrics["analyst_upside"] = f"{upside:+.1f}%"
            if upside > 30:
                score += 0.15
                reasons.append(f"애널리스트 목표가 +{upside:.0f}%")
            elif upside < 0:
                score -= 0.1

        if not f:
            return StrategyOpinion(
                agent_name=self.name,
                signal=Signal.HOLD,
                confidence=0.15,
                rationale="성장 지표 데이터 부족으로 판단 보류.",
                risk_flags=["데이터 부족 — 신뢰도 낮음"],
            )

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

        rationale = "; ".join(reasons[:3]) if reasons else "성장 지표 중립."

        return StrategyOpinion(
            agent_name=self.name,
            signal=signal,
            confidence=round(confidence, 2),
            rationale=rationale,
            key_metrics=metrics,
            risk_flags=flags,
        )
