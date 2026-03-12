"""Shared portfolio configuration and trigger engine.

Contains position data, split-buy trigger logic, and utilities
for the 2-track monitoring system (quick_scan + daily_analysis).
"""

import sys
from dataclasses import dataclass, field
from datetime import date, datetime

# ──────────────────────────────────────────────────────────────
# Portfolio Constants
# ──────────────────────────────────────────────────────────────

# Split-Buy Strategy positions (actively monitored with triggers)
POSITIONS = {
    "GOOGL": {"shares": 10, "avg_price": 305.16,   "buy_date": "2026-02-20"},
    "AMZN":  {"shares": 19, "avg_price": 209.3873, "buy_date": "2026-02-20"},
    "MSFT":  {"shares": 10, "avg_price": 404.09,   "buy_date": "2026-02-20"},
}

HELD_TICKERS = list(POSITIONS.keys())  # ["GOOGL", "AMZN", "MSFT"]
MARKET_TICKERS = ["^GSPC", "^VIX"]

# ──────────────────────────────────────────────────────────────
# Full Portfolio — 전체 보유 자산 (2026-02-25 기준)
# ──────────────────────────────────────────────────────────────

ALL_POSITIONS = {
    # US Stocks
    "GOOGL":    {"shares": 10, "avg_price": 305.16,   "currency": "USD", "strategy": "US빅테크과매도", "buy_date": "2026-02-20"},
    "AMZN":     {"shares": 19, "avg_price": 209.3873, "currency": "USD", "strategy": "US빅테크과매도", "buy_date": "2026-02-20"},
    "MSFT":     {"shares": 10, "avg_price": 404.09,   "currency": "USD", "strategy": "US빅테크과매도", "buy_date": "2026-02-20"},
    # ACRE: 2026-02-25 전량 손절 (15주, $8.69→$5.09, -41.4%, -$54.00)
    # PLTR: 기매도 (확정손실 -1,278,045원, -12.7%)
    # SHY: 2026-03-11 매수 미체결 — 보유 없음
    "BRK-B":    {"shares": 6,  "avg_price": 502.03,  "currency": "USD", "strategy": "가치투자",   "buy_date": "2025-01-01"},
    "V":        {"shares": 2,  "avg_price": 314.02,  "currency": "USD", "strategy": "결제인프라",  "buy_date": "2026-03-11"},
    "META":     {"shares": 1,  "avg_price": 657.35,  "currency": "USD", "strategy": "AI광고플랫폼", "buy_date": "2026-03-11"},
    # 한화리츠(451800.KS): 2026-03-03 매도 (18주, 5350원→5000원, -6.5%)
    # KORU: 2026-03-05 전량 매도 (8주, $453.50→$452.30, -0.27%, -$9.60)
    # KR Stocks
    "000660.KS": {"shares": 27, "avg_price": 991000, "currency": "KRW", "strategy": "장투", "buy_date": "2026-03-05"},
}

# Non-stock assets
GOLD_POSITION = {"qty_grams": 18, "avg_price_krw": 227431, "currency": "KRW"}
CASH_BALANCES = {"USD": 3682.00, "KRW": 0}  # 2026-03-12 실제 잔고

# 월급 입금 (매월 21일 영업일, 200만원)
MONTHLY_INCOME = {"day": 21, "amount_krw": 2_000_000, "note": "급여 입금 → 투자 집행일"}

ALL_TICKERS = list(ALL_POSITIONS.keys())

# ──────────────────────────────────────────────────────────────
# Watchlist — 관심종목 (보유하지 않지만 모니터링 + 투자 조언)
# ──────────────────────────────────────────────────────────────

WATCHLIST = {
    "SOL-USD": {
        "name": "Solana",
        "thesis": "Firedancer/Alpenglow 업그레이드 + ETF 생태계 + DeFi TVL 선두",
        "entry_conditions": {
            "rsi_above": 45,            # RSI 45 이상 회복 시
            "macd_golden_cross": True,   # MACD 골든크로스
            "regulatory_clear": True,    # SEC 규제 리스크 완화
        },
        "risk_factors": ["SEC 증권 분류", "집단소송", "고베타 80%+ 드로다운", "네트워크 장애 이력"],
        "added_date": "2026-02-25",
        "notes": "RSI 반등 + MACD 크로스 + 규제 완화 확인 전까지 관망",
    },
    "BITX": {
        "name": "2x Bitcoin Strategy ETF (Volatility Shares)",
        "thesis": "비트코인 2배 레버리지 ETF — 전쟁/인플레 헤지 + 크립토 상승 사이클",
        "entry_conditions": {
            "rsi_above": 40,            # RSI 40 이상 회복 시
            "macd_golden_cross": True,   # MACD 골든크로스
            "btc_above_sma20": True,    # BTC 가격 > SMA20
        },
        "risk_factors": ["2배 레버리지 decay", "크립토 변동성 극대", "전쟁 장기화 시 리스크자산 급락", "ETF 구조 리스크"],
        "added_date": "2026-03-03",
        "notes": "이란-미국 전쟁 중 크립토 헤지 수단 검토. 레버리지 특성상 단기 트레이딩 적합.",
    },
    # V: 2026-03-11 매수 완료 (2주 @$314.02) → ALL_POSITIONS으로 이동
    "JPM": {
        "name": "JP Morgan Chase",
        "thesis": "미국 최대 은행. P/E 14.4x (섹터 42% 할인), 순현금 $262B. 딥밸류 + 배당 수익",
        "entry_conditions": {
            "rsi_below": 40,            # RSI 40 이하 과매도 구간
            "macd_golden_cross": True,   # MACD 골든크로스 전환 대기 (현재 데드크로스)
        },
        "risk_factors": ["EPS -3.6%", "MACD 데드크로스", "경기침체 시 대출 부실"],
        "target_shares": 2,
        "target_amount_usd": 580,
        "added_date": "2026-03-11",
        "notes": "RSI 36 + 볼린저 8% 극단적 과매도. MACD 골든크로스 전환 시 진입. 금융 밸류 2순위.",
    },
    "VZ": {
        "name": "Verizon Communications",
        "thesis": "통신 방어주 + 고배당 (~6%). P/E 12.5x, GM 59%. 경기방어 + 인컴 목적",
        "entry_conditions": {
            "rsi_below": 50,            # RSI 50 이하 풀백 대기 (현재 69 과매수)
        },
        "risk_factors": ["EPS -53.3%", "Net Debt/EBITDA 3.3x", "성장성 부재"],
        "target_shares": 10,
        "target_amount_usd": 510,
        "added_date": "2026-03-11",
        "notes": "현재 RSI 69 과매수 → 풀백 대기. 통신 섹터 = 빅테크와 저상관 분산 효과.",
    },
}

WATCHLIST_TICKERS = list(WATCHLIST.keys())

INVESTED = 4500.68            # US빅테크 1차 $2,544.94 + 2차 $1,955.74
REMAINING = 3682.00           # 2026-03-12 실제 USD 잔고

# ──────────────────────────────────────────────────────────────
# Tranche 2 Triggers (any one fires → execute 2nd buy)
# ──────────────────────────────────────────────────────────────

TRANCHE_2_TRIGGERS = {
    "price_drop_pct": 5.0,           # any held stock drops 5%+ from buy price
    "time_target": "2026-03-06",     # 2 weeks elapsed
    "rsi_threshold": 45,             # RSI >= 45 recovery
    "rsi_min_stocks": 2,             # at least 2 stocks meet RSI threshold
}

TRANCHE_2_TRADES = {
    "GOOGL": 3,
    "AMZN":  3,
    "MSFT":  1,
}

# ──────────────────────────────────────────────────────────────
# Tranche 3 Triggers (any one fires → execute 3rd buy)
# ──────────────────────────────────────────────────────────────

TRANCHE_3_TRIGGERS = {
    "macd_cross_min_stocks": 2,      # MACD golden cross in 2+ stocks
    "time_target": "2026-03-20",     # 4 weeks elapsed
    "sma20_min_stocks": 2,           # close > SMA20 in 2+ stocks
}

TRANCHE_3_TRADES = {
    "GOOGL": 2,
    "AMZN":  3,
    "MSFT":  1,
}

# ──────────────────────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────────────────────


@dataclass
class TriggerResult:
    """Result of a single trigger check."""
    name: str           # e.g. "price_drop_5pct", "time_elapsed", "rsi_recovery"
    fired: bool | None  # True=fired, False=not fired, None=skipped/unavailable
    details: str        # human-readable description
    data: dict = field(default_factory=dict)


@dataclass
class TrancheCheckResult:
    """Aggregated result for a tranche's trigger checks."""
    tranche: int
    any_fired: bool
    triggers: list[TriggerResult] = field(default_factory=list)
    summary: str = ""


# ──────────────────────────────────────────────────────────────
# Trigger Functions
# ──────────────────────────────────────────────────────────────


def check_price_drop_trigger(
    current_prices: dict[str, float],
    positions: dict[str, dict] = POSITIONS,
    pct: float = 5.0,
) -> TriggerResult:
    """Check if any held stock has dropped >= pct% from buy price."""
    dropped = {}
    max_drop_pct = 0.0
    for ticker, pos in positions.items():
        price = current_prices.get(ticker)
        if price is None:
            continue
        change_pct = (price - pos["avg_price"]) / pos["avg_price"] * 100
        if change_pct <= -pct:
            dropped[ticker] = change_pct
        if abs(min(change_pct, 0)) > abs(max_drop_pct):
            max_drop_pct = change_pct

    fired = len(dropped) >= 1
    if fired:
        tickers_str = ", ".join(f"{t} ({v:+.1f}%)" for t, v in dropped.items())
        details = f"FIRED: {tickers_str} dropped >= {pct}%"
    else:
        details = f"Not fired (max drop: {max_drop_pct:+.1f}%)"

    return TriggerResult(
        name="price_drop_5pct",
        fired=fired,
        details=details,
        data={"dropped_tickers": dropped, "max_drop_pct": max_drop_pct, "threshold": pct},
    )


def check_time_elapsed_trigger(target_date: str) -> TriggerResult:
    """Check if today >= target_date."""
    today = date.today()
    target = date.fromisoformat(target_date)
    days_remaining = (target - today).days
    fired = today >= target

    if fired:
        details = f"FIRED: target date {target_date} reached ({-days_remaining}d past)"
    else:
        details = f"Not fired ({days_remaining}d remaining until {target_date})"

    return TriggerResult(
        name="time_elapsed",
        fired=fired,
        details=details,
        data={"target_date": target_date, "days_remaining": days_remaining},
    )


def check_rsi_recovery_trigger(
    rsi_values: dict[str, float | None],
    threshold: float = 45.0,
    min_stocks: int = 2,
) -> TriggerResult:
    """Check if RSI >= threshold for at least min_stocks held tickers."""
    if not rsi_values or all(v is None for v in rsi_values.values()):
        return TriggerResult(
            name="rsi_recovery",
            fired=None,
            details="Skipped: RSI data unavailable",
            data={},
        )

    recovered = {}
    for ticker, rsi in rsi_values.items():
        if rsi is not None and rsi >= threshold:
            recovered[ticker] = rsi

    fired = len(recovered) >= min_stocks
    all_rsi_str = ", ".join(
        f"{t}: {v:.1f}" if v is not None else f"{t}: N/A"
        for t, v in rsi_values.items()
    )

    if fired:
        details = f"FIRED: {len(recovered)}/{min_stocks} stocks RSI >= {threshold} ({all_rsi_str})"
    else:
        details = f"Not fired: {len(recovered)}/{min_stocks} stocks RSI >= {threshold} ({all_rsi_str})"

    return TriggerResult(
        name="rsi_recovery",
        fired=fired,
        details=details,
        data={"recovered_tickers": recovered, "all_rsi": dict(rsi_values),
              "threshold": threshold, "min_stocks": min_stocks},
    )


def check_macd_golden_cross_trigger(
    macd_data: dict[str, dict],
    min_stocks: int = 2,
) -> TriggerResult:
    """Check for MACD golden cross (MACD crosses above signal line).

    macd_data: {ticker: {"macd": float, "signal": float, "prev_macd": float, "prev_signal": float}}
    Golden cross: prev_macd <= prev_signal AND current macd > signal
    """
    if not macd_data or all(v is None for v in macd_data.values()):
        return TriggerResult(
            name="macd_golden_cross",
            fired=None,
            details="Skipped: MACD data unavailable",
            data={},
        )

    crossed = {}
    for ticker, d in macd_data.items():
        if d is None:
            continue
        macd = d.get("macd")
        signal = d.get("signal")
        prev_macd = d.get("prev_macd")
        prev_signal = d.get("prev_signal")
        if any(v is None for v in (macd, signal, prev_macd, prev_signal)):
            continue
        if prev_macd <= prev_signal and macd > signal:
            crossed[ticker] = {"macd": macd, "signal": signal}

    fired = len(crossed) >= min_stocks
    if fired:
        tickers_str = ", ".join(crossed.keys())
        details = f"FIRED: {len(crossed)}/{min_stocks} stocks MACD golden cross ({tickers_str})"
    else:
        details = f"Not fired: {len(crossed)}/{min_stocks} stocks MACD golden cross"

    return TriggerResult(
        name="macd_golden_cross",
        fired=fired,
        details=details,
        data={"crossed_tickers": crossed, "min_stocks": min_stocks},
    )


def check_sma20_recapture_trigger(
    price_sma_data: dict[str, dict],
    min_stocks: int = 2,
) -> TriggerResult:
    """Check if close > SMA20 for at least min_stocks.

    price_sma_data: {ticker: {"close": float, "sma_20": float}}
    """
    if not price_sma_data or all(v is None for v in price_sma_data.values()):
        return TriggerResult(
            name="sma20_recapture",
            fired=None,
            details="Skipped: SMA20 data unavailable",
            data={},
        )

    above = {}
    for ticker, d in price_sma_data.items():
        if d is None:
            continue
        close = d.get("close")
        sma_20 = d.get("sma_20")
        if close is not None and sma_20 is not None and close > sma_20:
            above[ticker] = {"close": close, "sma_20": sma_20}

    fired = len(above) >= min_stocks
    if fired:
        tickers_str = ", ".join(above.keys())
        details = f"FIRED: {len(above)}/{min_stocks} stocks above SMA20 ({tickers_str})"
    else:
        details = f"Not fired: {len(above)}/{min_stocks} stocks above SMA20"

    return TriggerResult(
        name="sma20_recapture",
        fired=fired,
        details=details,
        data={"above_sma20": above, "min_stocks": min_stocks},
    )


# ──────────────────────────────────────────────────────────────
# Tranche Check Aggregators
# ──────────────────────────────────────────────────────────────


def check_tranche_2_triggers(
    prices: dict[str, float],
    rsi_values: dict[str, float | None] | None = None,
    today_date: date | None = None,
) -> TrancheCheckResult:
    """Check all Tranche 2 triggers. Returns aggregated result.

    For quick_scan, pass rsi_values=None to skip RSI check.
    """
    triggers = []

    # 1. Price drop trigger
    triggers.append(check_price_drop_trigger(prices, POSITIONS, TRANCHE_2_TRIGGERS["price_drop_pct"]))

    # 2. Time elapsed trigger
    triggers.append(check_time_elapsed_trigger(TRANCHE_2_TRIGGERS["time_target"]))

    # 3. RSI recovery trigger (skipped if rsi_values is None)
    if rsi_values is not None:
        triggers.append(check_rsi_recovery_trigger(
            rsi_values,
            TRANCHE_2_TRIGGERS["rsi_threshold"],
            TRANCHE_2_TRIGGERS["rsi_min_stocks"],
        ))

    any_fired = any(t.fired is True for t in triggers)
    fired_names = [t.name for t in triggers if t.fired is True]
    if any_fired:
        summary = f"TRANCHE 2 TRIGGERED by: {', '.join(fired_names)}"
    else:
        summary = "Tranche 2: no triggers fired"

    return TrancheCheckResult(
        tranche=2,
        any_fired=any_fired,
        triggers=triggers,
        summary=summary,
    )


def check_tranche_3_triggers(
    prices: dict[str, float] | None = None,
    macd_data: dict[str, dict] | None = None,
    sma_data: dict[str, dict] | None = None,
    today_date: date | None = None,
) -> TrancheCheckResult:
    """Check all Tranche 3 triggers. Returns aggregated result.

    For quick_scan, pass macd_data=None and sma_data=None to skip technical checks.
    """
    triggers = []

    # 1. MACD golden cross trigger
    if macd_data is not None:
        triggers.append(check_macd_golden_cross_trigger(
            macd_data, TRANCHE_3_TRIGGERS["macd_cross_min_stocks"]
        ))

    # 2. Time elapsed trigger
    triggers.append(check_time_elapsed_trigger(TRANCHE_3_TRIGGERS["time_target"]))

    # 3. SMA20 recapture trigger
    if sma_data is not None:
        triggers.append(check_sma20_recapture_trigger(
            sma_data, TRANCHE_3_TRIGGERS["sma20_min_stocks"]
        ))

    any_fired = any(t.fired is True for t in triggers)
    fired_names = [t.name for t in triggers if t.fired is True]
    if any_fired:
        summary = f"TRANCHE 3 TRIGGERED by: {', '.join(fired_names)}"
    else:
        summary = "Tranche 3: no triggers fired"

    return TrancheCheckResult(
        tranche=3,
        any_fired=any_fired,
        triggers=triggers,
        summary=summary,
    )


# ──────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────


def compute_pnl(
    positions: dict[str, dict],
    current_prices: dict[str, float],
) -> list[dict]:
    """Compute P&L for each position and total.

    Returns list of dicts with: ticker, shares, avg_price, current_price,
    cost, market_value, pnl, pnl_pct
    """
    results = []
    total_cost = 0.0
    total_value = 0.0

    for ticker, pos in positions.items():
        price = current_prices.get(ticker)
        if price is None:
            continue
        shares = pos["shares"]
        avg = pos["avg_price"]
        cost = shares * avg
        value = shares * price
        pnl = value - cost
        pnl_pct = (pnl / cost) * 100 if cost > 0 else 0.0

        results.append({
            "ticker": ticker,
            "shares": shares,
            "avg_price": avg,
            "current_price": price,
            "cost": cost,
            "market_value": value,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
        })
        total_cost += cost
        total_value += value

    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost) * 100 if total_cost > 0 else 0.0
    results.append({
        "ticker": "TOTAL",
        "shares": sum(p["shares"] for p in positions.values()),
        "avg_price": None,
        "current_price": None,
        "cost": total_cost,
        "market_value": total_value,
        "pnl": total_pnl,
        "pnl_pct": total_pnl_pct,
    })

    return results


class Colors:
    """ANSI terminal color codes with disable support."""

    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    _enabled = True

    @classmethod
    def disable(cls):
        cls.BOLD = ""
        cls.RED = ""
        cls.GREEN = ""
        cls.YELLOW = ""
        cls.CYAN = ""
        cls.DIM = ""
        cls.RESET = ""
        cls._enabled = False

    @classmethod
    def is_enabled(cls) -> bool:
        return cls._enabled

    @classmethod
    def colorize(cls, text: str, color: str) -> str:
        """Apply color to text if colors enabled."""
        if cls._enabled:
            return f"{color}{text}{cls.RESET}"
        return text

    @classmethod
    def pnl_color(cls, value: float) -> str:
        """Return color code for P&L value (green=positive, red=negative)."""
        if value > 0:
            return cls.GREEN
        elif value < 0:
            return cls.RED
        return cls.DIM
