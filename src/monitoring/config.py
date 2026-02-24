"""Split-buy strategy configuration and monitoring thresholds."""

from dataclasses import dataclass
from datetime import date


@dataclass
class TrancheConfig:
    tranche: int
    budget: float
    allocations: dict[str, int]  # ticker -> quantity
    triggers: list[str]          # human-readable trigger descriptions
    deadline: date | None = None


@dataclass
class SplitBuyStrategy:
    name: str
    total_budget: float
    tickers: list[str]
    target_ratios: dict[str, float]   # ticker -> ratio (0-1)
    tranches: list[TrancheConfig]


# Active strategy definition
ACTIVE_STRATEGY = SplitBuyStrategy(
    name="US빅테크과매도",
    total_budget=6151.0,
    tickers=["GOOGL", "AMZN", "MSFT"],
    target_ratios={"GOOGL": 0.40, "AMZN": 0.30, "MSFT": 0.30},
    tranches=[
        TrancheConfig(
            tranche=1,
            budget=2525.0,
            allocations={"GOOGL": 3, "AMZN": 4, "MSFT": 2},
            triggers=["RSI 31~32 과매도"],
        ),
        TrancheConfig(
            tranche=2,
            budget=1820.0,
            allocations={"GOOGL": 3, "AMZN": 3, "MSFT": 1},
            triggers=[
                "평균 매수가 대비 5% 하락",
                "2주 경과 (2026-03-06)",
                "RSI 45 회복",
            ],
            deadline=date(2026, 3, 6),
        ),
        TrancheConfig(
            tranche=3,
            budget=1820.0,
            allocations={"GOOGL": 2, "AMZN": 3, "MSFT": 1},
            triggers=[
                "MACD 골든크로스",
                "4주 경과 (2026-03-20)",
                "SMA20 탈환",
            ],
            deadline=date(2026, 3, 20),
        ),
    ],
)
