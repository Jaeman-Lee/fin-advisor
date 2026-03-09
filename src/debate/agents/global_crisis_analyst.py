"""Global crisis & geopolitical risk analyst agent."""

from __future__ import annotations

from src.debate.base_agent import StrategyAgent
from src.debate.models import DebateContext, Signal, StrategyOpinion


class GlobalCrisisAnalyst(StrategyAgent):
    """Evaluates geopolitical risks, war, trade wars, sanctions, supply chain
    disruptions, and their impact on individual holdings.

    Analyzes:
    - VIX level (fear gauge)
    - Gold price surge (safe-haven demand)
    - Oil price shocks (energy supply disruption)
    - USD strength / DXY (flight to safety)
    - KRW weakness (EM stress indicator)
    - Treasury yields (flight to quality)
    - Cross-asset correlation breakdown
    - Sentiment data for geopolitical keywords
    """

    name = "global-crisis-analyst"
    description = "전쟁, 무역분쟁, 제재, 공급망 위기, 지정학 리스크 전문 분석"

    # Thresholds
    VIX_ELEVATED = 25.0
    VIX_CRISIS = 30.0
    VIX_EXTREME = 40.0
    GOLD_SURGE_PCT = 2.0       # daily gold move suggesting safe-haven rush
    OIL_SPIKE_PCT = 5.0        # daily oil spike (supply shock signal)
    USDKRW_STRESS = 1400       # KRW stress level
    USDKRW_CRISIS = 1450       # KRW crisis level
    DXY_STRONG = 105.0         # Strong dollar (flight to safety)

    # Geopolitical keywords in sentiment data
    CRISIS_KEYWORDS = [
        "war", "전쟁", "invasion", "침공", "missile", "미사일",
        "tariff", "관세", "sanction", "제재", "trade war", "무역전쟁",
        "pandemic", "팬데믹", "outbreak", "supply chain", "공급망",
        "crisis", "위기", "conflict", "분쟁", "nuclear", "핵",
        "default", "디폴트", "sovereign", "geopolit", "지정학",
        "coup", "embargo", "blockade", "봉쇄", "martial law", "계엄",
        "escalat", "확전", "retaliat", "보복",
    ]

    def evaluate(self, context: DebateContext) -> StrategyOpinion:
        score = 0.0  # negative = crisis risk, positive = calm
        reasons: list[str] = []
        metrics: dict = {}
        flags: list[str] = []

        # ── 1. VIX Analysis (primary fear gauge) ──
        vix = self._get_vix(context)
        if vix is not None:
            metrics["vix"] = round(vix, 1)
            if vix >= self.VIX_EXTREME:
                score -= 0.5
                reasons.append(f"VIX {vix:.1f} — 극단적 공포, 시장 패닉 수준")
                flags.append(f"VIX {vix:.0f} EXTREME")
            elif vix >= self.VIX_CRISIS:
                score -= 0.35
                reasons.append(f"VIX {vix:.1f} — 위기 수준, 헤지 필수")
                flags.append(f"VIX {vix:.0f} CRISIS")
            elif vix >= self.VIX_ELEVATED:
                score -= 0.2
                reasons.append(f"VIX {vix:.1f} — 경계 구간, 변동성 확대")
                flags.append(f"VIX {vix:.0f} elevated")
            else:
                score += 0.1
                reasons.append(f"VIX {vix:.1f} — 안정적")

        # ── 2. Gold (safe-haven demand) ──
        gold_chg = self._get_asset_change(context, "GC=F")
        if gold_chg is not None:
            metrics["gold_change"] = f"{gold_chg:+.1f}%"
            if gold_chg > self.GOLD_SURGE_PCT:
                score -= 0.15
                reasons.append(f"금 {gold_chg:+.1f}% 급등 — 안전자산 수요 급증")
                flags.append("금 가격 급등")
            elif gold_chg > 1.0:
                score -= 0.05

        # ── 3. Oil (supply shock indicator) ──
        oil_chg = self._get_asset_change(context, "CL=F")
        if oil_chg is not None:
            metrics["oil_change"] = f"{oil_chg:+.1f}%"
            if abs(oil_chg) > self.OIL_SPIKE_PCT:
                score -= 0.15
                reasons.append(f"유가 {oil_chg:+.1f}% 급변 — 에너지 공급 충격 우려")
                flags.append("유가 급변")
            elif oil_chg > 3.0:
                score -= 0.05

        # ── 4. USD/KRW (EM & Korea stress) ──
        usdkrw = self._get_usdkrw(context)
        if usdkrw is not None:
            metrics["usdkrw"] = round(usdkrw, 1)
            if usdkrw >= self.USDKRW_CRISIS:
                score -= 0.2
                reasons.append(f"USD/KRW {usdkrw:.0f} — 원화 위기 수준, 외국인 이탈 가속")
                flags.append(f"원화 위기 ({usdkrw:.0f})")
            elif usdkrw >= self.USDKRW_STRESS:
                score -= 0.1
                reasons.append(f"USD/KRW {usdkrw:.0f} — 원화 약세, EM 스트레스")
                flags.append(f"원화 약세 ({usdkrw:.0f})")

        # ── 5. DXY / Dollar Index (flight to safety) ──
        dxy = self._get_latest_close(context, "DX-Y.NYB")
        if dxy is not None:
            metrics["dxy"] = round(dxy, 1)
            if dxy >= self.DXY_STRONG:
                score -= 0.1
                reasons.append(f"달러인덱스 {dxy:.1f} — 강달러, 안전자산 선호")
                flags.append("강달러")

        # ── 6. Treasury (flight to quality) ──
        tnx_chg = self._get_asset_change(context, "^TNX")
        if tnx_chg is not None:
            metrics["us10y_change"] = f"{tnx_chg:+.1f}%"
            if tnx_chg < -3.0:
                score -= 0.1
                reasons.append(f"미 10년물 금리 {tnx_chg:+.1f}% 급락 — 채권으로 자금 이동")
                flags.append("채권 피신")

        # ── 7. Sentiment: geopolitical keyword density ──
        geo_score, geo_count, geo_topics = self._analyze_geopolitical_sentiment(context)
        if geo_count > 0:
            metrics["geo_news_count"] = geo_count
            metrics["geo_sentiment_avg"] = round(geo_score, 2)
            if geo_count >= 5:
                score -= 0.2
                topic_str = ", ".join(geo_topics[:3])
                reasons.append(f"지정학 뉴스 {geo_count}건 감지 ({topic_str}) — 위험 고조")
                flags.append(f"지정학 뉴스 {geo_count}건")
            elif geo_count >= 2:
                score -= 0.1
                reasons.append(f"지정학 뉴스 {geo_count}건 — 주시 필요")

        # ── 8. Ticker-specific crisis exposure ──
        ticker_crisis_adj = self._assess_ticker_crisis_exposure(
            context.ticker, flags
        )
        score += ticker_crisis_adj
        if ticker_crisis_adj < -0.1:
            reasons.append(f"{context.ticker} 지정학 노출도 높음")

        # ── Score → Signal ──
        score = max(-1.0, min(0.5, score))
        confidence = min(abs(score) + 0.25, 1.0)

        if score >= 0.3:
            signal = Signal.BUY
            reasons.insert(0, "글로벌 위기 리스크 낮음 — 위험자산 우호적")
        elif score >= 0.0:
            signal = Signal.HOLD
        elif score >= -0.2:
            signal = Signal.HOLD
            if not any("경계" in r or "주시" in r for r in reasons):
                reasons.append("글로벌 리스크 소폭 상승 — 모니터링 강화")
        elif score >= -0.4:
            signal = Signal.SELL
            reasons.insert(0, "글로벌 위기 리스크 상승 — 방어적 포지션 권고")
        else:
            signal = Signal.STRONG_SELL
            reasons.insert(0, "글로벌 위기 심각 — 즉시 리스크 축소 권고")

        rationale = "; ".join(reasons[:4]) if reasons else "글로벌 위기 데이터 부족."

        return StrategyOpinion(
            agent_name=self.name,
            signal=signal,
            confidence=round(confidence, 2),
            rationale=rationale,
            key_metrics=metrics,
            risk_flags=flags,
        )

    # ── Helper methods ──

    def _get_vix(self, context: DebateContext) -> float | None:
        """Get VIX from global_market_data, portfolio_context, or macro_snapshot."""
        # global_market_data (most reliable, from DB)
        if context.global_market_data:
            vix_entry = context.global_market_data.get("vix", {})
            if vix_entry.get("close") is not None:
                return float(vix_entry["close"])

        vix = context.portfolio_context.get("vix")
        if vix is not None:
            return float(vix)
        for item in context.macro_snapshot:
            name = item.get("series_id", item.get("name", ""))
            if "VIX" in name.upper() or "VIXCLS" in name.upper():
                val = item.get("value")
                if val is not None:
                    return float(val)
        return None

    def _get_usdkrw(self, context: DebateContext) -> float | None:
        """Get USD/KRW from global_market_data, portfolio_context, or macro_snapshot."""
        if context.global_market_data:
            krw_entry = context.global_market_data.get("usdkrw", {})
            if krw_entry.get("close") is not None:
                return float(krw_entry["close"])

        usdkrw = context.portfolio_context.get("usdkrw")
        if usdkrw is not None:
            return float(usdkrw)
        for item in context.macro_snapshot:
            name = item.get("series_id", item.get("name", ""))
            if "DEXKOUS" in name:
                val = item.get("value")
                if val is not None:
                    return float(val)
        return None

    def _get_asset_change(self, context: DebateContext, ticker: str) -> float | None:
        """Get recent % change for an asset from global_market_data or market_data."""
        # Check global_market_data first (populated by context_builder)
        key_map = {"GC=F": "gold", "CL=F": "oil", "^TNX": "us10y",
                    "DX-Y.NYB": "dxy", "USDKRW=X": "usdkrw", "^VIX": "vix"}
        gkey = key_map.get(ticker)
        if gkey and context.global_market_data:
            entry = context.global_market_data.get(gkey, {})
            chg = entry.get("change_pct")
            if chg is not None:
                return float(chg)

        # Fallback: if the debate is about this ticker, use market_data
        if context.ticker == ticker and len(context.market_data) >= 2:
            curr = context.market_data[-1].get("close")
            prev = context.market_data[-2].get("close")
            if curr and prev and prev > 0:
                return (curr - prev) / prev * 100
        return None

    def _get_latest_close(self, context: DebateContext, ticker: str) -> float | None:
        """Get latest close for an asset from global_market_data or market_data."""
        key_map = {"GC=F": "gold", "CL=F": "oil", "^TNX": "us10y",
                    "DX-Y.NYB": "dxy", "USDKRW=X": "usdkrw", "^VIX": "vix"}
        gkey = key_map.get(ticker)
        if gkey and context.global_market_data:
            entry = context.global_market_data.get(gkey, {})
            close = entry.get("close")
            if close is not None:
                return float(close)

        if context.ticker == ticker and context.market_data:
            return context.market_data[-1].get("close")
        return None

    def _analyze_geopolitical_sentiment(
        self, context: DebateContext
    ) -> tuple[float, int, list[str]]:
        """Scan sentiment_data for geopolitical crisis keywords.

        Returns (avg_sentiment, count, matched_topics).
        """
        geo_items = []
        topics = set()
        for item in context.sentiment_data:
            title = (item.get("title") or "").lower()
            for kw in self.CRISIS_KEYWORDS:
                if kw.lower() in title:
                    geo_items.append(item)
                    topics.add(kw)
                    break

        if not geo_items:
            return 0.0, 0, []

        avg_sent = sum(
            item.get("sentiment_score", 0) for item in geo_items
        ) / len(geo_items)
        return avg_sent, len(geo_items), sorted(topics)

    def _assess_ticker_crisis_exposure(
        self, ticker: str, current_flags: list[str]
    ) -> float:
        """Assess how exposed a specific ticker is to global crisis factors.

        Returns adjustment score (negative = more exposed).
        """
        adjustment = 0.0

        # Defense/military related tickers benefit from crisis
        defense_tickers = {"LMT", "RTX", "NOC", "GD", "BA"}
        if ticker in defense_tickers:
            adjustment += 0.1

        # Energy tickers: volatile during crisis
        energy_tickers = {"XOM", "CVX", "COP", "SLB"}
        if ticker in energy_tickers and any("유가" in f for f in current_flags):
            adjustment -= 0.1

        # Korean tickers: exposed to Korea-specific geopolitical risk
        kr_tickers = {"000660.KS", "005930.KS", "^KS11"}
        if ticker in kr_tickers:
            adjustment -= 0.1
            if any("원화" in f for f in current_flags):
                adjustment -= 0.1  # double exposure

        # Tech (global supply chain dependency)
        tech_tickers = {"GOOGL", "AMZN", "MSFT", "AAPL", "NVDA", "PLTR", "TSLA"}
        if ticker in tech_tickers:
            if any("공급망" in f or "제재" in f for f in current_flags):
                adjustment -= 0.1

        # Safe-haven / value tickers
        safe_tickers = {"BRK-B", "GC=F", "TLT"}
        if ticker in safe_tickers:
            adjustment += 0.1

        return adjustment
