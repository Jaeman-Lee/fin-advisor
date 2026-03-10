"""Income/Dividend investing strategy agent."""

from __future__ import annotations

from src.debate.base_agent import StrategyAgent
from src.debate.models import DebateContext, Signal, StrategyOpinion


class IncomeInvestor(StrategyAgent):
    """Evaluates based on dividend yield, payout ratio, cash flow stability."""

    name = "income-investor"
    description = "배당수익률, 현금흐름, 배당 안정성 기반 인컴 전략"

    def evaluate(self, context: DebateContext) -> StrategyOpinion:
        score = 0.0
        reasons: list[str] = []
        metrics: dict = {}
        flags: list[str] = []

        f = context.fundamentals

        # Dividend yield
        div_yield = f.get("dividend_yield")
        if div_yield is not None:
            dy_pct = div_yield * 100 if div_yield < 1 else div_yield
            metrics["dividend_yield"] = f"{dy_pct:.2f}%"
            if dy_pct > 6:
                score += 0.25
                reasons.append(f"배당수익률 {dy_pct:.1f}% — 고배당")
                if dy_pct > 12:
                    flags.append(f"배당수익률 {dy_pct:.0f}% 비정상 — 삭감 리스크")
                    score -= 0.1
            elif dy_pct > 3:
                score += 0.15
                reasons.append(f"배당수익률 {dy_pct:.1f}% — 양호")
            elif dy_pct > 0:
                score += 0.05
            else:
                score -= 0.1
                reasons.append("무배당 종목")

        # Payout ratio
        payout = f.get("payout_ratio")
        if payout is not None:
            po_pct = payout * 100 if payout < 5 else payout
            metrics["payout_ratio"] = f"{po_pct:.0f}%"
            if po_pct > 100:
                score -= 0.2
                reasons.append(f"배당성향 {po_pct:.0f}% — 이익 초과 배당 (지속불가)")
                flags.append("배당성향 100% 초과")
            elif po_pct > 80:
                score -= 0.05
                flags.append(f"배당성향 {po_pct:.0f}% 높음")
            elif 30 <= po_pct <= 60:
                score += 0.1
                reasons.append(f"배당성향 {po_pct:.0f}% — 건전")

        # Free cash flow coverage
        fcf = f.get("free_cashflow")
        if fcf is not None:
            if fcf > 0:
                score += 0.1
                metrics["fcf_positive"] = True
            else:
                score -= 0.2
                reasons.append("잉여현금흐름 음수 — 배당 재원 부족")
                flags.append("FCF 음수")

        # Profit margin stability (proxy for earnings stability)
        margin = f.get("profit_margins")
        if margin is not None:
            margin_pct = margin * 100 if margin < 1 else margin
            if margin_pct < 0:
                score -= 0.2
                flags.append("적자 기업 — 배당 삭감 위험")

        # Consecutive dividend years (if available)
        # Not always in yfinance, use as bonus

        # P&L check — if position is deeply underwater, dividend alone
        # doesn't justify holding
        pnl_pct = context.portfolio_context.get("pnl_pct")
        if pnl_pct is not None and pnl_pct < -30:
            score -= 0.15
            reasons.append(
                f"평가손 {pnl_pct:+.1f}% — 배당으로 만회 어려움"
            )

        if div_yield is None and payout is None:
            return StrategyOpinion(
                agent_name=self.name,
                signal=Signal.HOLD,
                confidence=0.15,
                rationale="배당/인컴 데이터 부족으로 판단 보류.",
            )

        score = max(-1.0, min(1.0, score))
        confidence = min(abs(score) + 0.2, 1.0)
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

        rationale = "; ".join(reasons[:3]) if reasons else "인컴 지표 중립."

        return StrategyOpinion(
            agent_name=self.name,
            signal=signal,
            confidence=round(confidence, 2),
            rationale=rationale,
            key_metrics=metrics,
            risk_flags=flags,
        )
