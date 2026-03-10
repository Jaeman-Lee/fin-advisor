"""Risk management agent with veto power."""

from __future__ import annotations

from src.debate.base_agent import StrategyAgent
from src.debate.models import DebateContext, Signal, StrategyOpinion


class RiskManager(StrategyAgent):
    """Evaluates portfolio risk: drawdown, concentration, volatility, loss history.

    Has VETO power: if risk is critical, escalates urgency regardless of other votes.
    """

    name = "risk-manager"
    description = "손실 제한, 분산도, 최대낙폭, 헤지 — 거부권 보유"
    _needs_fundamentals = False

    # Thresholds
    MAX_SINGLE_POSITION_PCT = 0.15  # 15% of total portfolio
    MAX_DRAWDOWN_WARN = -0.20       # -20%
    MAX_DRAWDOWN_CRITICAL = -0.40   # -40%
    VOLATILITY_HIGH = 40.0          # annualized %
    RISK_SCORE_HIGH = 0.7

    def evaluate(self, context: DebateContext) -> StrategyOpinion:
        score = 0.0  # 0 = safe, negative = risky
        reasons: list[str] = []
        metrics: dict = {}
        flags: list[str] = []

        risk = context.risk_assessment
        pf = context.portfolio_context
        ind = self._latest_indicators(context)

        # 1. Current P&L / Drawdown
        pnl_pct = pf.get("pnl_pct")
        if pnl_pct is not None:
            metrics["pnl_pct"] = f"{pnl_pct:+.1f}%"
            if pnl_pct <= self.MAX_DRAWDOWN_CRITICAL * 100:
                score -= 0.4
                reasons.append(f"심각한 손실 {pnl_pct:+.1f}% — 즉시 대응 필요")
                flags.append(f"낙폭 {pnl_pct:+.1f}%")
            elif pnl_pct <= self.MAX_DRAWDOWN_WARN * 100:
                score -= 0.2
                reasons.append(f"손실 {pnl_pct:+.1f}% — 손절 기준 검토 필요")
                flags.append(f"낙폭 {pnl_pct:+.1f}%")
            elif pnl_pct > 20:
                score += 0.1
                reasons.append(f"수익 {pnl_pct:+.1f}% — 일부 차익 실현 고려")

        # 2. Position concentration
        position_pct = pf.get("position_pct")
        if position_pct is not None:
            metrics["portfolio_weight"] = f"{position_pct:.1f}%"
            if position_pct > self.MAX_SINGLE_POSITION_PCT * 100:
                score -= 0.15
                reasons.append(
                    f"포트폴리오 비중 {position_pct:.1f}% — 과집중"
                )
                flags.append("포지션 과집중")

        # 3. Risk score (from risk_assessor)
        risk_score = risk.get("risk_score")
        if risk_score is not None:
            metrics["risk_score"] = round(risk_score, 2)
            if risk_score >= self.RISK_SCORE_HIGH:
                score -= 0.2
                reasons.append(f"리스크 점수 {risk_score:.2f} — 고위험")
                flags.append(f"고위험 (score {risk_score:.2f})")

        # 4. Volatility
        volatility = risk.get("volatility") or pf.get("volatility")
        if volatility is not None:
            metrics["volatility"] = f"{volatility:.1f}%"
            if volatility >= self.VOLATILITY_HIGH:
                score -= 0.15
                reasons.append(f"변동성 {volatility:.1f}% — 높음")
                flags.append("고변동성")

        # 5. Realized loss history (learned lessons)
        total_realized_loss = pf.get("total_realized_loss_krw", 0)
        if total_realized_loss < -2_000_000:
            score -= 0.1
            reasons.append(
                f"누적 확정 손실 {total_realized_loss:,.0f}원 — 추가 손실 회피 권고"
            )
            flags.append("누적 손실 이력")

        # 6. VIX check
        vix = pf.get("vix")
        if vix is not None and vix >= 30:
            score -= 0.15
            flags.append(f"VIX {vix:.0f}")

        # Score to signal (inverted: negative score = SELL for risk)
        score = max(-1.0, min(0.2, score))
        confidence = min(abs(score) + 0.3, 1.0)
        confidence = self._apply_data_quality_penalty(confidence, context)
        self._add_data_warnings(flags, context)

        if score <= -0.5:
            signal = Signal.STRONG_SELL
        elif score <= -0.2:
            signal = Signal.SELL
        elif score >= 0.1:
            signal = Signal.BUY
        else:
            signal = Signal.HOLD

        if not reasons:
            reasons.append("리스크 지표 정상 범위 내")

        rationale = "; ".join(reasons[:3])

        return StrategyOpinion(
            agent_name=self.name,
            signal=signal,
            confidence=round(confidence, 2),
            rationale=rationale,
            key_metrics=metrics,
            risk_flags=flags,
        )

    @property
    def has_veto(self) -> bool:
        return True
