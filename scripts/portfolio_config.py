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
    "GOOGL": {"shares": 3, "avg_price": 307.61, "buy_date": "2026-02-20"},
    "AMZN":  {"shares": 4, "avg_price": 205.59, "buy_date": "2026-02-20"},
    "MSFT":  {"shares": 2, "avg_price": 399.69, "buy_date": "2026-02-20"},
}

HELD_TICKERS = list(POSITIONS.keys())  # ["GOOGL", "AMZN", "MSFT"]
MARKET_TICKERS = ["^GSPC", "^VIX"]

# ──────────────────────────────────────────────────────────────
# Full Portfolio — 전체 보유 자산 (2026-02-25 기준)
# ──────────────────────────────────────────────────────────────

ALL_POSITIONS = {
    # US Stocks
    "GOOGL":    {"shares": 3,  "avg_price": 307.61,  "currency": "USD", "strategy": "US빅테크과매도", "buy_date": "2026-02-20"},
    "AMZN":     {"shares": 4,  "avg_price": 205.59,  "currency": "USD", "strategy": "US빅테크과매도", "buy_date": "2026-02-20"},
    "MSFT":     {"shares": 2,  "avg_price": 399.69,  "currency": "USD", "strategy": "US빅테크과매도", "buy_date": "2026-02-20"},
    # ACRE: 2026-02-25 전량 손절 (15주, $8.69→$5.09, -41.4%, -$54.00)
    "BRK-B":    {"shares": 6,  "avg_price": 502.03,  "currency": "USD", "strategy": "가치투자", "buy_date": "2025-01-01"},
    # Korean Stocks
    "451800.KS": {"shares": 18, "avg_price": 5350,   "currency": "KRW", "strategy": "리츠/배당", "buy_date": "2025-01-01", "name": "한화리츠"},
}

# Non-stock assets
GOLD_POSITION = {"qty_grams": 18, "avg_price_krw": 227431, "currency": "KRW"}
CASH_BALANCES = {"USD": 3604.59, "KRW": 7046698}

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
}

WATCHLIST_TICKERS = list(WATCHLIST.keys())

TOTAL_CAPITAL = 6151.00       # US빅테크과매도 전략 예산 (USD)
INVESTED = 2544.94            # 1차 트랜치 실투자 (USD)
REMAINING = 3604.59           # 잔여 USD 현금

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
