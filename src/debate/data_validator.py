"""Data validation layer to prevent hallucination in agent evaluations.

Validates fundamentals, market data, and context completeness before
agents consume data. Ensures no fabricated defaults or stale data
silently enters the decision pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Reasonable bounds for financial metrics.
# Values outside these ranges are flagged as suspect (likely data error).
METRIC_BOUNDS: dict[str, tuple[float | None, float | None]] = {
    "forward_pe": (-500, 2000),
    "trailing_pe": (-500, 2000),
    "price_to_book": (-100, 500),
    "profit_margins": (-10, 1.0),       # -1000% to 100%
    "gross_margins": (-5, 1.0),
    "revenue_growth": (-1.0, 50.0),     # -100% to 5000%
    "earnings_growth": (-10.0, 100.0),
    "dividend_yield": (0, 1.0),         # 0 to 100%
    "payout_ratio": (-5, 10.0),
    "debt_to_equity": (-500, 5000),
    "free_cashflow": (-1e12, 1e12),
    "market_cap": (0, 20e12),           # max ~$20T
}

# Minimum number of fundamentals to consider data "usable"
MIN_FUNDAMENTALS_COUNT = 3


@dataclass
class DataQuality:
    """Tracks data completeness and reliability for a context."""

    completeness: float = 0.0           # 0.0-1.0, fraction of expected fields present
    available_fields: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)    # bounds violations, stale data
    suspect_fields: list[str] = field(default_factory=list)  # out-of-bounds values
    data_age_days: int | None = None    # how old is the market data

    @property
    def is_sufficient(self) -> bool:
        """Whether there's enough data for a meaningful evaluation."""
        return len(self.available_fields) >= MIN_FUNDAMENTALS_COUNT

    @property
    def confidence_penalty(self) -> float:
        """Confidence reduction factor based on data quality.

        Returns a multiplier (0.3-1.0) to apply to agent confidence.
        - 1.0 = full data, no penalty
        - 0.3 = minimal data, heavy penalty
        """
        if not self.is_sufficient:
            return 0.3

        penalty = 1.0

        # Penalize for missing data (up to 0.3 reduction)
        penalty -= (1.0 - self.completeness) * 0.3

        # Penalize for suspect values (0.05 each, max 0.2)
        penalty -= min(len(self.suspect_fields) * 0.05, 0.2)

        # Penalize for stale data (> 3 days old)
        if self.data_age_days is not None and self.data_age_days > 3:
            penalty -= min(self.data_age_days * 0.02, 0.15)

        return max(0.3, penalty)


def validate_fundamentals(raw: dict) -> tuple[dict, list[str]]:
    """Validate and sanitize fundamentals data from yfinance.

    Args:
        raw: Dict from yfinance info with metric keys.

    Returns:
        Tuple of (cleaned_data, warnings).
        - cleaned_data: Same dict but with out-of-bounds values set to None.
        - warnings: List of warning messages for flagged values.
    """
    if not raw:
        return {}, ["펀더멘탈 데이터 없음"]

    cleaned = dict(raw)
    warnings = []

    for key, value in raw.items():
        if value is None:
            continue

        if not isinstance(value, (int, float)):
            continue

        bounds = METRIC_BOUNDS.get(key)
        if bounds is None:
            continue

        lo, hi = bounds
        if lo is not None and value < lo:
            warnings.append(
                f"{key}={value} 이상값 (하한 {lo}). 데이터 오류 가능성 — 제외됨."
            )
            cleaned[key] = None
        elif hi is not None and value > hi:
            warnings.append(
                f"{key}={value} 이상값 (상한 {hi}). 데이터 오류 가능성 — 제외됨."
            )
            cleaned[key] = None

    return cleaned, warnings


def assess_data_quality(
    fundamentals: dict,
    market_data: list[dict],
    macro_snapshot: list[dict] | None = None,
) -> DataQuality:
    """Assess overall data quality for a debate context.

    Args:
        fundamentals: Validated fundamentals dict.
        market_data: List of OHLCV + indicator dicts.
        macro_snapshot: Optional macro data.

    Returns:
        DataQuality instance with completeness metrics.
    """
    dq = DataQuality()

    # ── Fundamentals completeness ──
    expected_fundamental_keys = [
        "forward_pe", "trailing_pe", "price_to_book", "market_cap",
        "free_cashflow", "profit_margins", "gross_margins",
        "revenue_growth", "earnings_growth", "dividend_yield",
        "debt_to_equity",
    ]
    for key in expected_fundamental_keys:
        val = fundamentals.get(key)
        if val is not None:
            dq.available_fields.append(key)
        else:
            dq.missing_fields.append(key)

    total_expected = len(expected_fundamental_keys)
    dq.completeness = len(dq.available_fields) / total_expected if total_expected else 0.0

    # ── Market data freshness ──
    if market_data:
        latest_date_str = market_data[-1].get("date") or market_data[-1].get("trade_date", "")
        if latest_date_str:
            try:
                latest_date = datetime.strptime(latest_date_str[:10], "%Y-%m-%d")
                age = (datetime.now() - latest_date).days
                dq.data_age_days = age
                if age > 7:
                    dq.warnings.append(
                        f"시장 데이터가 {age}일 전 것입니다. 실시간 판단에 부적합할 수 있습니다."
                    )
                elif age > 3:
                    dq.warnings.append(
                        f"시장 데이터가 {age}일 전입니다. 주말/휴일이 아니라면 갱신이 필요합니다."
                    )
            except (ValueError, TypeError):
                dq.warnings.append("시장 데이터 날짜를 파싱할 수 없습니다.")

        # Check for critical indicators
        latest = market_data[-1]
        for indicator in ["rsi_14", "macd", "sma_20"]:
            if latest.get(indicator) is None:
                dq.missing_fields.append(f"indicator:{indicator}")
    else:
        dq.warnings.append("시장 데이터(OHLCV) 없음 — 기술적 분석 불가.")

    # ── Macro data ──
    if macro_snapshot is not None and len(macro_snapshot) == 0:
        dq.missing_fields.append("macro_snapshot")

    # ── Insufficient data warning ──
    if not dq.is_sufficient:
        dq.warnings.append(
            f"사용 가능한 펀더멘탈 지표가 {len(dq.available_fields)}개뿐입니다. "
            f"최소 {MIN_FUNDAMENTALS_COUNT}개 이상 필요합니다."
        )

    return dq


def verify_agent_metrics(
    claimed_metrics: dict,
    context_fundamentals: dict,
    context_indicators: dict,
    tolerance: float = 0.01,
) -> list[str]:
    """Verify that agent-claimed metrics match actual context data.

    This is the moderator's fact-checking tool. Compares what agents
    report in key_metrics against the actual data they were given.

    Args:
        claimed_metrics: Agent's key_metrics dict.
        context_fundamentals: Original fundamentals from context.
        context_indicators: Latest indicators from context.
        tolerance: Allowed relative difference for numeric values.

    Returns:
        List of discrepancy descriptions. Empty = no issues.
    """
    discrepancies = []

    # Map agent metric names to context source fields
    metric_sources = {
        "pe_ratio": [("forward_pe", context_fundamentals), ("trailing_pe", context_fundamentals)],
        "pb_ratio": [("price_to_book", context_fundamentals)],
        "rsi_14": [("rsi_14", context_indicators)],
        "macd": [("macd", context_indicators)],
        "macd_signal": [("macd_signal", context_indicators)],
        "dividend_yield": [("dividend_yield", context_fundamentals)],
        "revenue_growth": [("revenue_growth", context_fundamentals)],
    }

    for metric_name, sources in metric_sources.items():
        claimed = claimed_metrics.get(metric_name)
        if claimed is None:
            continue

        # Extract numeric value from formatted strings
        claimed_num = _extract_numeric(claimed)
        if claimed_num is None:
            continue

        matched = False
        for source_key, source_dict in sources:
            source_val = source_dict.get(source_key)
            if source_val is None:
                continue

            source_num = float(source_val)
            # Handle percentage conversion (fundamentals store as 0.xx, agents may use xx%)
            if abs(source_num) < 1 and abs(claimed_num) >= 1:
                source_num *= 100
            elif abs(source_num) >= 1 and abs(claimed_num) < 1:
                claimed_num *= 100

            if source_num == 0:
                matched = claimed_num == 0
            else:
                rel_diff = abs(claimed_num - source_num) / abs(source_num)
                matched = rel_diff <= tolerance

            if matched:
                break

        if not matched and sources:
            # Check if there's any source data to compare against
            has_source = any(s_dict.get(s_key) is not None for s_key, s_dict in sources)
            if has_source:
                discrepancies.append(
                    f"지표 불일치: {metric_name}={claimed} — 원본 데이터와 일치하지 않음"
                )

    return discrepancies


def _extract_numeric(value) -> float | None:
    """Extract numeric value from various formats (123, '12.3%', '$1,234', etc.)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("$", "").replace("원", "").replace(
            "%", ""
        ).replace("+", "").strip()
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None
    return None
