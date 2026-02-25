#!/usr/bin/env python3
"""Korean market analysis script - KOSPI/KOSDAQ rally assessment (2026-02-24)."""

import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

pd.set_option('display.float_format', '{:.2f}'.format)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 120)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. Data Collection
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

tickers = {
    # Korean indices
    "^KS11": "KOSPI",
    "^KQ11": "KOSDAQ",
    # US indices & futures
    "^GSPC": "S&P 500",
    "^IXIC": "NASDAQ",
    "ES=F": "S&P Futures",
    "NQ=F": "NASDAQ Futures",
    # Volatility
    "^VIX": "VIX",
    # FX
    "USDKRW=X": "USD/KRW",
    # Korean major stocks
    "005930.KS": "Samsung",
    "000660.KS": "SK Hynix",
    "373220.KS": "LG Energy",
    "035420.KS": "NAVER",
    "035720.KS": "Kakao",
    "068270.KS": "Celltrion",
    "055550.KS": "Shinhan Bank",
    # Korean ETFs for sector analysis
    "069500.KS": "KODEX 200",
    "229200.KS": "KODEX KOSDAQ150",
    # Global context
    "GC=F": "Gold",
    "CL=F": "WTI Oil",
    "^TNX": "US 10Y Yield",
}

print("=" * 80)
print("  한국 시장 분석: KOSPI/KOSDAQ 신고가 돌파 시점 진입 검토")
print(f"  분석일: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 80)

# Download 1 year of data for all tickers
print("\n[데이터 수집 중...]")
data = {}
info_data = {}

for ticker, name in tickers.items():
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y")
        if len(hist) > 0:
            data[ticker] = hist
            try:
                info_data[ticker] = t.info
            except:
                info_data[ticker] = {}
            print(f"  ✓ {name} ({ticker}): {len(hist)} days")
        else:
            print(f"  ✗ {name} ({ticker}): no data")
    except Exception as e:
        print(f"  ✗ {name} ({ticker}): {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Helper Functions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def calc_returns(df):
    """Calculate various return periods."""
    if df is None or len(df) < 2:
        return {}
    close = df['Close']
    latest = close.iloc[-1]

    results = {"latest_price": latest}

    # 1D return
    if len(close) >= 2:
        results["1d_ret"] = (close.iloc[-1] / close.iloc[-2] - 1) * 100

    # 1W return
    if len(close) >= 5:
        results["1w_ret"] = (close.iloc[-1] / close.iloc[-5] - 1) * 100

    # 1M return
    if len(close) >= 21:
        results["1m_ret"] = (close.iloc[-1] / close.iloc[-21] - 1) * 100

    # 3M return
    if len(close) >= 63:
        results["3m_ret"] = (close.iloc[-1] / close.iloc[-63] - 1) * 100

    # YTD return
    ytd_start = close.loc[close.index >= "2026-01-01"]
    if len(ytd_start) > 0:
        results["ytd_ret"] = (close.iloc[-1] / ytd_start.iloc[0] - 1) * 100

    # 52-week high/low
    results["52w_high"] = close.max()
    results["52w_low"] = close.min()
    results["pct_from_52w_high"] = (latest / close.max() - 1) * 100
    results["pct_from_52w_low"] = (latest / close.min() - 1) * 100

    return results


def calc_technicals(df):
    """Calculate technical indicators."""
    if df is None or len(df) < 30:
        return {}

    close = df['Close']
    results = {}

    # RSI
    rsi = ta.rsi(close, length=14)
    if rsi is not None and len(rsi) > 0:
        results["rsi_14"] = rsi.iloc[-1]

    # MACD
    macd = ta.macd(close, fast=12, slow=26, signal=9)
    if macd is not None and len(macd) > 0:
        results["macd"] = macd.iloc[-1, 0]
        results["macd_signal"] = macd.iloc[-1, 1]
        results["macd_hist"] = macd.iloc[-1, 2]

    # Moving Averages
    for period in [20, 50, 200]:
        sma = ta.sma(close, length=period)
        if sma is not None and len(sma) > 0 and not pd.isna(sma.iloc[-1]):
            results[f"sma_{period}"] = sma.iloc[-1]
            results[f"dist_sma_{period}"] = (close.iloc[-1] / sma.iloc[-1] - 1) * 100

    # Bollinger Bands
    bb = ta.bbands(close, length=20, std=2)
    if bb is not None and len(bb) > 0:
        results["bb_upper"] = bb.iloc[-1, 0]
        results["bb_mid"] = bb.iloc[-1, 1]
        results["bb_lower"] = bb.iloc[-1, 2]
        results["bb_width"] = bb.iloc[-1, 3] if bb.shape[1] > 3 else None

    # ATR (volatility)
    atr = ta.atr(df['High'], df['Low'], close, length=14)
    if atr is not None and len(atr) > 0:
        results["atr_14"] = atr.iloc[-1]
        results["atr_pct"] = (atr.iloc[-1] / close.iloc[-1]) * 100

    # Stochastic RSI
    stoch = ta.stochrsi(close)
    if stoch is not None and len(stoch) > 0:
        results["stoch_rsi_k"] = stoch.iloc[-1, 0]
        results["stoch_rsi_d"] = stoch.iloc[-1, 1]

    return results


def format_ret(val):
    """Format return value with color indicator."""
    if val is None:
        return "N/A"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}%"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. KOSPI / KOSDAQ Analysis
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n" + "=" * 80)
print("  1. KOSPI / KOSDAQ 현황")
print("=" * 80)

for idx_ticker in ["^KS11", "^KQ11"]:
    name = tickers[idx_ticker]
    if idx_ticker not in data:
        print(f"\n  {name}: 데이터 없음")
        continue

    df = data[idx_ticker]
    rets = calc_returns(df)
    techs = calc_technicals(df)

    print(f"\n{'─' * 60}")
    print(f"  {name} ({idx_ticker})")
    print(f"{'─' * 60}")
    print(f"  현재가:      {rets.get('latest_price', 'N/A'):,.2f}")
    print(f"  52주 고가:   {rets.get('52w_high', 'N/A'):,.2f} ({format_ret(rets.get('pct_from_52w_high'))} 대비)")
    print(f"  52주 저가:   {rets.get('52w_low', 'N/A'):,.2f} ({format_ret(rets.get('pct_from_52w_low'))} 대비)")
    print()
    print(f"  수익률:")
    print(f"    1일:       {format_ret(rets.get('1d_ret'))}")
    print(f"    1주:       {format_ret(rets.get('1w_ret'))}")
    print(f"    1개월:     {format_ret(rets.get('1m_ret'))}")
    print(f"    3개월:     {format_ret(rets.get('3m_ret'))}")
    print(f"    YTD:       {format_ret(rets.get('ytd_ret'))}")
    print()
    print(f"  기술적 지표:")
    print(f"    RSI(14):        {techs.get('rsi_14', 'N/A'):.1f}" if techs.get('rsi_14') else "    RSI(14):        N/A")
    print(f"    MACD:           {techs.get('macd', 'N/A'):.2f}" if techs.get('macd') else "    MACD:           N/A")
    print(f"    MACD Signal:    {techs.get('macd_signal', 'N/A'):.2f}" if techs.get('macd_signal') else "    MACD Signal:    N/A")
    print(f"    MACD Hist:      {techs.get('macd_hist', 'N/A'):.2f}" if techs.get('macd_hist') else "    MACD Hist:      N/A")
    print(f"    Stoch RSI K:    {techs.get('stoch_rsi_k', 'N/A'):.1f}" if techs.get('stoch_rsi_k') else "    Stoch RSI K:    N/A")
    print(f"    Stoch RSI D:    {techs.get('stoch_rsi_d', 'N/A'):.1f}" if techs.get('stoch_rsi_d') else "    Stoch RSI D:    N/A")
    print()
    print(f"  이동평균 대비 이격도:")
    for period in [20, 50, 200]:
        key = f"dist_sma_{period}"
        sma_key = f"sma_{period}"
        if key in techs:
            print(f"    SMA{period}:  {techs[sma_key]:,.2f}  (이격: {format_ret(techs[key])})")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. Global Risk Sentiment
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n\n" + "=" * 80)
print("  2. 글로벌 리스크 심리 지표")
print("=" * 80)

for gbl_ticker in ["^VIX", "^GSPC", "^IXIC", "ES=F", "NQ=F", "^TNX", "GC=F", "CL=F"]:
    name = tickers[gbl_ticker]
    if gbl_ticker not in data:
        continue
    rets = calc_returns(data[gbl_ticker])
    techs = calc_technicals(data[gbl_ticker])

    rsi_str = f"RSI={techs.get('rsi_14', 'N/A'):.1f}" if techs.get('rsi_14') else "RSI=N/A"
    print(f"  {name:18s} | 현재: {rets.get('latest_price', 0):>10,.2f} | "
          f"1D: {format_ret(rets.get('1d_ret')):>8s} | "
          f"1M: {format_ret(rets.get('1m_ret')):>8s} | "
          f"3M: {format_ret(rets.get('3m_ret')):>8s} | "
          f"{rsi_str}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. USD/KRW Exchange Rate
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n\n" + "=" * 80)
print("  3. 원/달러 환율 (USD/KRW)")
print("=" * 80)

fx_ticker = "USDKRW=X"
if fx_ticker in data:
    rets = calc_returns(data[fx_ticker])
    techs = calc_technicals(data[fx_ticker])
    print(f"  현재: {rets.get('latest_price', 0):,.2f}")
    print(f"  1D: {format_ret(rets.get('1d_ret'))} | 1W: {format_ret(rets.get('1w_ret'))} | "
          f"1M: {format_ret(rets.get('1m_ret'))} | 3M: {format_ret(rets.get('3m_ret'))}")
    print(f"  52주 범위: {rets.get('52w_low', 0):,.2f} ~ {rets.get('52w_high', 0):,.2f}")
    if techs.get('rsi_14'):
        print(f"  RSI(14): {techs['rsi_14']:.1f}")
    print(f"  → 환율 하락(원화 강세) = 외국인 매수 유인 / 수출기업 이익감소")
    print(f"  → 환율 상승(원화 약세) = 외국인 매도 압력 / 수출기업 이익증가")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. Korean Major Stocks Analysis
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n\n" + "=" * 80)
print("  4. 한국 주요 종목 현황")
print("=" * 80)

kr_stocks = ["005930.KS", "000660.KS", "373220.KS", "035420.KS", "035720.KS", "068270.KS", "055550.KS"]
for kr_ticker in kr_stocks:
    name = tickers[kr_ticker]
    if kr_ticker not in data:
        continue
    rets = calc_returns(data[kr_ticker])
    techs = calc_technicals(data[kr_ticker])

    rsi_str = f"RSI={techs.get('rsi_14', 'N/A'):.1f}" if techs.get('rsi_14') else "RSI=N/A"
    dist_50 = format_ret(techs.get('dist_sma_50')) if techs.get('dist_sma_50') is not None else "N/A"

    print(f"  {name:14s} | 현재: {rets.get('latest_price', 0):>12,.0f} | "
          f"1M: {format_ret(rets.get('1m_ret')):>8s} | "
          f"3M: {format_ret(rets.get('3m_ret')):>8s} | "
          f"YTD: {format_ret(rets.get('ytd_ret')):>8s} | "
          f"52H: {format_ret(rets.get('pct_from_52w_high')):>8s} | "
          f"{rsi_str} | SMA50: {dist_50}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. Valuation Context (P/E if available)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n\n" + "=" * 80)
print("  5. 밸류에이션 참고 (yfinance info)")
print("=" * 80)

for kr_ticker in kr_stocks:
    name = tickers[kr_ticker]
    info = info_data.get(kr_ticker, {})
    pe_trailing = info.get('trailingPE', 'N/A')
    pe_forward = info.get('forwardPE', 'N/A')
    pb = info.get('priceToBook', 'N/A')
    div_yield = info.get('dividendYield', None)
    div_str = f"{div_yield*100:.2f}%" if div_yield else "N/A"
    market_cap = info.get('marketCap', None)
    cap_str = f"{market_cap/1e12:.1f}조" if market_cap else "N/A"

    print(f"  {name:14s} | PER(T): {pe_trailing:>8} | PER(F): {pe_forward:>8} | "
          f"PBR: {pb:>6} | 배당: {div_str:>6} | 시총: {cap_str}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. Market Breadth & Momentum Score
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n\n" + "=" * 80)
print("  6. 시장 모멘텀 종합 스코어")
print("=" * 80)

# Count how many KR stocks are above their 50-day and 200-day SMAs
above_sma50 = 0
above_sma200 = 0
total_checked = 0
rsi_sum = 0
rsi_count = 0

for kr_ticker in kr_stocks:
    if kr_ticker not in data:
        continue
    techs = calc_technicals(data[kr_ticker])
    total_checked += 1
    if techs.get('dist_sma_50') and techs['dist_sma_50'] > 0:
        above_sma50 += 1
    if techs.get('dist_sma_200') and techs['dist_sma_200'] > 0:
        above_sma200 += 1
    if techs.get('rsi_14'):
        rsi_sum += techs['rsi_14']
        rsi_count += 1

if total_checked > 0:
    print(f"  SMA50 상회 종목: {above_sma50}/{total_checked} ({above_sma50/total_checked*100:.0f}%)")
    print(f"  SMA200 상회 종목: {above_sma200}/{total_checked} ({above_sma200/total_checked*100:.0f}%)")
if rsi_count > 0:
    avg_rsi = rsi_sum / rsi_count
    print(f"  평균 RSI(14): {avg_rsi:.1f}")
    if avg_rsi > 70:
        print(f"  → 시장 전반적으로 과매수 영역 (주의)")
    elif avg_rsi > 60:
        print(f"  → 모멘텀 양호하나 과열 주의")
    elif avg_rsi > 40:
        print(f"  → 중립적 수준")
    else:
        print(f"  → 과매도 영역 접근")

# KOSPI specific momentum
if "^KS11" in data:
    kospi_techs = calc_technicals(data["^KS11"])
    kospi_rets = calc_returns(data["^KS11"])

    print(f"\n  KOSPI 모멘텀 진단:")

    # RSI zones
    rsi = kospi_techs.get('rsi_14', 50)
    if rsi > 70:
        print(f"    RSI {rsi:.1f}: ⚠️  과매수 영역 - 단기 조정 가능성 높음")
    elif rsi > 60:
        print(f"    RSI {rsi:.1f}: 상승 모멘텀 양호 (아직 과매수 아님)")
    elif rsi > 50:
        print(f"    RSI {rsi:.1f}: 중립~양호")
    else:
        print(f"    RSI {rsi:.1f}: 약세 모멘텀")

    # MACD
    macd_hist = kospi_techs.get('macd_hist', 0)
    if macd_hist and macd_hist > 0:
        print(f"    MACD Hist {macd_hist:.2f}: 상승 시그널 지속")
    elif macd_hist:
        print(f"    MACD Hist {macd_hist:.2f}: 하락 시그널")

    # Distance from 52w high
    dist_high = kospi_rets.get('pct_from_52w_high', -999)
    if dist_high is not None:
        if dist_high >= -1:
            print(f"    52주 신고가 부근 ({format_ret(dist_high)}): 강세장 확인, 다만 고점 매수 리스크")
        elif dist_high >= -5:
            print(f"    52주 고점 대비 {format_ret(dist_high)}: 고점 근접")
        else:
            print(f"    52주 고점 대비 {format_ret(dist_high)}: 고점 대비 상당 폭 하락")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 9. Historical context: "Buying at highs"
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n\n" + "=" * 80)
print("  7. 신고가 매수의 역사적 맥락")
print("=" * 80)

# Use longer-term KOSPI data if available
try:
    kospi_long = yf.Ticker("^KS11").history(period="5y")
    if len(kospi_long) > 200:
        close = kospi_long['Close']

        # Find all-time-high-ish moments (within 2% of rolling 252-day high)
        rolling_high = close.rolling(252).max()
        near_high = close >= rolling_high * 0.98

        # For each "near high" cluster, check forward returns
        # Sample at least 20 trading days apart
        signals = []
        last_signal_idx = -25
        for i in range(252, len(close)):
            if near_high.iloc[i] and (i - last_signal_idx >= 20):
                signals.append(i)
                last_signal_idx = i

        fwd_rets = {20: [], 60: [], 120: []}
        for sig_idx in signals:
            for horizon in fwd_rets.keys():
                if sig_idx + horizon < len(close):
                    fwd = (close.iloc[sig_idx + horizon] / close.iloc[sig_idx] - 1) * 100
                    fwd_rets[horizon].append(fwd)

        print(f"  5년간 52주 신고가 부근 매수 시그널: {len(signals)}회")
        print(f"  (52주 고점 대비 -2% 이내에서 매수한 경우의 이후 수익률)")
        print()
        for horizon, rets_list in fwd_rets.items():
            if rets_list:
                avg = np.mean(rets_list)
                median = np.median(rets_list)
                win_rate = sum(1 for r in rets_list if r > 0) / len(rets_list) * 100
                worst = min(rets_list)
                best = max(rets_list)
                print(f"    {horizon//20}개월 후: 평균 {avg:+.2f}% | 중앙값 {median:+.2f}% | "
                      f"승률 {win_rate:.0f}% | 최악 {worst:.2f}% | 최고 {best:+.2f}% (n={len(rets_list)})")
except Exception as e:
    print(f"  장기 분석 에러: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 10. Correlation check: KOSPI vs USD/KRW
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n\n" + "=" * 80)
print("  8. KOSPI-환율 상관관계 (최근 60일)")
print("=" * 80)

if "^KS11" in data and "USDKRW=X" in data:
    kospi_close = data["^KS11"]['Close'].tail(60).pct_change().dropna()
    fx_close = data["USDKRW=X"]['Close'].tail(60).pct_change().dropna()

    # Align dates
    common_idx = kospi_close.index.intersection(fx_close.index)
    if len(common_idx) > 10:
        corr = kospi_close.loc[common_idx].corr(fx_close.loc[common_idx])
        print(f"  60일 일간 수익률 상관계수: {corr:.3f}")
        if corr < -0.3:
            print(f"  → 강한 역상관: KOSPI 상승 시 원화 강세 (외국인 매수 주도 시사)")
        elif corr < 0:
            print(f"  → 약한 역상관")
        else:
            print(f"  → 양의 상관 또는 무상관 (국내 요인 주도 가능)")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 11. Volatility Analysis
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n\n" + "=" * 80)
print("  9. 변동성 분석")
print("=" * 80)

if "^KS11" in data:
    kospi_df = data["^KS11"]
    daily_ret = kospi_df['Close'].pct_change().dropna()

    vol_20d = daily_ret.tail(20).std() * np.sqrt(252) * 100
    vol_60d = daily_ret.tail(60).std() * np.sqrt(252) * 100
    vol_1y = daily_ret.std() * np.sqrt(252) * 100

    print(f"  KOSPI 연환산 변동성:")
    print(f"    20일: {vol_20d:.1f}%")
    print(f"    60일: {vol_60d:.1f}%")
    print(f"    1년:  {vol_1y:.1f}%")

    if vol_20d < vol_60d * 0.8:
        print(f"  → 최근 변동성 축소: 추세 가속 또는 변곡점 주의")
    elif vol_20d > vol_60d * 1.2:
        print(f"  → 최근 변동성 확대: 불확실성 증가")
    else:
        print(f"  → 변동성 안정적")

if "^VIX" in data:
    vix_rets = calc_returns(data["^VIX"])
    vix_level = vix_rets.get('latest_price', 0)
    print(f"\n  VIX 현재: {vix_level:.2f}")
    if vix_level < 15:
        print(f"  → 매우 낮은 공포: Complacency 주의 (역발상 관점에서 위험)")
    elif vix_level < 20:
        print(f"  → 낮은 공포: 리스크온 환경")
    elif vix_level < 25:
        print(f"  → 보통 수준")
    elif vix_level < 30:
        print(f"  → 높은 불안감: 주의 필요")
    else:
        print(f"  → 극도의 공포: 패닉 구간")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Summary Signal
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n\n" + "=" * 80)
print("  종합 시그널 매트릭스")
print("=" * 80)

signals = {}

# KOSPI momentum
if "^KS11" in data:
    kt = calc_technicals(data["^KS11"])
    kr = calc_returns(data["^KS11"])

    rsi = kt.get('rsi_14', 50)
    signals['KOSPI RSI'] = "과매수" if rsi > 70 else "양호" if rsi > 50 else "약세"

    macd_h = kt.get('macd_hist', 0)
    signals['MACD'] = "상승" if macd_h and macd_h > 0 else "하락"

    d52 = kr.get('pct_from_52w_high', -10)
    signals['52주 고점'] = "신고가 부근" if d52 and d52 >= -2 else "고점 하회"

    d200 = kt.get('dist_sma_200', 0)
    signals['SMA200 대비'] = f"상회 ({d200:+.1f}%)" if d200 and d200 > 0 else f"하회 ({d200:.1f}%)" if d200 else "N/A"

# VIX
if "^VIX" in data:
    vix = calc_returns(data["^VIX"]).get('latest_price', 20)
    signals['VIX'] = f"{vix:.1f} (낮음-리스크온)" if vix < 20 else f"{vix:.1f} (보통)" if vix < 25 else f"{vix:.1f} (높음-주의)"

# FX
if "USDKRW=X" in data:
    fx_1m = calc_returns(data["USDKRW=X"]).get('1m_ret', 0)
    if fx_1m:
        signals['USD/KRW 1M'] = f"원화 강세 ({fx_1m:+.1f}%)" if fx_1m < -1 else f"원화 약세 ({fx_1m:+.1f}%)" if fx_1m > 1 else f"횡보 ({fx_1m:+.1f}%)"

for k, v in signals.items():
    print(f"  {k:18s}: {v}")


print("\n\n" + "=" * 80)
print("  ⚠️  면책 조항 (DISCLAIMER)")
print("=" * 80)
print("""
  본 분석은 공개된 시장 데이터를 기반으로 한 참고용 정보이며,
  투자 권유나 매매 추천이 아닙니다.

  투자에 대한 최종 판단과 책임은 투자자 본인에게 있으며,
  본 자료로 인한 어떠한 투자 손실에 대해서도 책임지지 않습니다.

  과거 수익률은 미래 수익을 보장하지 않습니다.
  반드시 본인의 투자 목적, 경험, 재정 상황을 고려하여 판단하시기 바랍니다.
""")

print("=" * 80)
print("  [END OF ANALYSIS]")
print("=" * 80)
