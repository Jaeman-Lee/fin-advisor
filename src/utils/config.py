"""Central configuration for the investment advisory system."""

import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "investment.db"

# ── Asset Universe ─────────────────────────────────────────────────────────
# Stocks: major indices & blue chips
STOCK_TICKERS = [
    "^GSPC", "^IXIC", "^DJI",          # US indices
    "^KS11", "^N225", "^FTSE",          # KR, JP, UK indices
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA",  # US mega cap
    "005930.KS", "000660.KS",           # Samsung, SK Hynix
]

# Bonds: treasury yields
BOND_TICKERS = [
    "^TNX",   # 10-Year US Treasury Yield
    "^TYX",   # 30-Year US Treasury Yield
    "^FVX",   # 5-Year US Treasury Yield
    "^IRX",   # 13-Week Treasury Bill
    "TLT",    # iShares 20+ Year Treasury Bond ETF
    "SHY",    # iShares 1-3 Year Treasury Bond ETF
]

# Commodities
COMMODITY_TICKERS = [
    "GC=F",   # Gold
    "SI=F",   # Silver
    "CL=F",   # Crude Oil WTI
    "BZ=F",   # Brent Crude
    "NG=F",   # Natural Gas
    "HG=F",   # Copper
]

# Crypto
CRYPTO_TICKERS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD",
]

# FX
FX_TICKERS = [
    "EURUSD=X", "USDJPY=X", "USDKRW=X", "DX-Y.NYB",  # Dollar Index
]

ALL_TICKERS = STOCK_TICKERS + BOND_TICKERS + COMMODITY_TICKERS + CRYPTO_TICKERS + FX_TICKERS

# ── Asset Type Mapping ─────────────────────────────────────────────────────
ASSET_TYPE_MAP: dict[str, str] = {}
for t in STOCK_TICKERS:
    ASSET_TYPE_MAP[t] = "stock"
for t in BOND_TICKERS:
    ASSET_TYPE_MAP[t] = "bond"
for t in COMMODITY_TICKERS:
    ASSET_TYPE_MAP[t] = "commodity"
for t in CRYPTO_TICKERS:
    ASSET_TYPE_MAP[t] = "crypto"
for t in FX_TICKERS:
    ASSET_TYPE_MAP[t] = "fx"

# ── Theme Categories ───────────────────────────────────────────────────────
THEME_CATEGORIES = [
    "macro",        # 거시경제 (금리, 인플레이션, GDP)
    "geopolitics",  # 지정학 (전쟁, 무역분쟁, 제재)
    "sector",       # 섹터별 (AI, 반도체, 에너지, 바이오)
    "asset",        # 자산별 (주식, 채권, 원자재, 암호화폐)
    "sentiment",    # 시장 심리 (공포/탐욕, VIX)
    "technical",    # 기술적 (추세, 패턴, 지지/저항)
]

# ── Scoring Thresholds ─────────────────────────────────────────────────────
SENTIMENT_THRESHOLDS = {
    "very_negative": -0.6,
    "negative": -0.2,
    "neutral_low": -0.05,
    "neutral_high": 0.05,
    "positive": 0.2,
    "very_positive": 0.6,
}

RELEVANCE_MIN_SCORE = 0.3       # Minimum relevance to keep
DEDUP_SIMILARITY_THRESHOLD = 0.85  # Similarity threshold for deduplication

# ── Technical Indicator Defaults ───────────────────────────────────────────
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BOLLINGER_PERIOD = 20
BOLLINGER_STD = 2.0
SMA_PERIODS = [20, 50, 200]

# ── Data Collection Settings ──────────────────────────────────────────────
DEFAULT_LOOKBACK_DAYS = 365
NEWS_MAX_ITEMS_PER_QUERY = 10
MARKET_DATA_INTERVAL = "1d"     # daily OHLCV

# ── Risk Thresholds ───────────────────────────────────────────────────────
RISK_LEVELS = {
    "very_low": (0.0, 0.2),
    "low": (0.2, 0.4),
    "moderate": (0.4, 0.6),
    "high": (0.6, 0.8),
    "very_high": (0.8, 1.0),
}

# ── Portfolio Allocation Constraints ──────────────────────────────────────
ALLOCATION_BOUNDS = {
    "stock": (0.0, 0.70),
    "bond": (0.0, 0.50),
    "commodity": (0.0, 0.25),
    "crypto": (0.0, 0.15),
    "fx": (0.0, 0.10),
    "cash": (0.05, 1.0),  # minimum 5% cash
}
