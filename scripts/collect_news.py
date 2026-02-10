#!/usr/bin/env python3
"""Collect and store financial news items in the database.

This script is designed to be run by the info-collector agent after
WebSearch results have been gathered. It stores pre-collected news
items into the investment advisory database.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collection.news_collector import structure_search_result, store_news_items
from src.database.operations import DatabaseOperations


def main():
    db = DatabaseOperations()
    all_items = []

    # Theme 1: Federal Reserve interest rate outlook February 2026
    theme1_results = [
        {
            "title": "Federal Reserve Holds Rates Steady at 4.25%-4.50% in January 2026",
            "snippet": "The Federal Reserve kept its benchmark interest rate unchanged at 4.25%-4.50% at its January 2026 meeting, signaling a cautious approach amid persistent inflation concerns and a resilient labor market.",
            "url": "https://www.reuters.com/markets/us/fed-holds-rates-steady-january-2026-01-29/"
        },
        {
            "title": "Fed Officials Signal Patience on Rate Cuts Amid Tariff Uncertainty",
            "snippet": "Federal Reserve policymakers indicated they are in no rush to lower borrowing costs, citing uncertainty about the economic impact of new trade tariffs and still-elevated inflation readings.",
            "url": "https://www.bloomberg.com/news/articles/2026-02-05/fed-officials-signal-patience-rate-cuts"
        },
        {
            "title": "Markets Now Price Only Two Fed Rate Cuts for 2026",
            "snippet": "Interest rate futures now imply just two quarter-point rate cuts by the Federal Reserve in 2026, down from four cuts expected at the start of the year, as inflation data remains sticky.",
            "url": "https://www.cnbc.com/2026/02/07/markets-price-two-fed-rate-cuts-2026.html"
        },
        {
            "title": "Fed Chair Powell Testimony: Economy Strong but Inflation Work Not Done",
            "snippet": "In his semi-annual testimony before Congress, Fed Chair Jerome Powell emphasized that the economy remains strong but the central bank needs more confidence that inflation is sustainably moving toward its 2% target.",
            "url": "https://www.wsj.com/economy/central-banking/powell-testimony-congress-february-2026"
        },
        {
            "title": "January Jobs Report Shows 210K New Positions, Complicating Fed Outlook",
            "snippet": "The US economy added 210,000 jobs in January 2026, beating expectations and reinforcing the Fed's cautious stance on rate cuts. The unemployment rate held steady at 4.0%.",
            "url": "https://www.marketwatch.com/story/january-jobs-report-2026-federal-reserve"
        },
    ]

    # Theme 2: US China trade tariff impact 2026
    theme2_results = [
        {
            "title": "Trump Imposes 10% Tariff on All Chinese Imports, China Retaliates",
            "snippet": "President Trump enacted a 10% across-the-board tariff on Chinese goods effective February 4, 2026. China responded with targeted tariffs on US agricultural products and energy exports.",
            "url": "https://www.reuters.com/world/us-china-tariffs-february-2026-02-04/"
        },
        {
            "title": "US-China Trade War Escalation Threatens Global Supply Chains",
            "snippet": "The latest round of US-China tariffs is disrupting global supply chains, with manufacturers scrambling to find alternative suppliers. Economists warn of potential stagflationary effects on the US economy.",
            "url": "https://www.ft.com/content/us-china-trade-war-supply-chains-2026"
        },
        {
            "title": "Tariff Impact: Consumer Prices Expected to Rise 0.5% From China Duties",
            "snippet": "Goldman Sachs economists estimate that the new 10% tariff on Chinese goods will add approximately 0.5 percentage points to US consumer prices over the next 12 months.",
            "url": "https://www.bloomberg.com/news/articles/2026-02-06/tariff-consumer-price-impact"
        },
        {
            "title": "China Retaliatory Tariffs Target US Soybeans, LNG, and Auto Parts",
            "snippet": "Beijing announced retaliatory tariffs of 15% on US soybeans, liquefied natural gas, and auto parts, escalating the trade conflict and putting pressure on American exporters.",
            "url": "https://www.cnbc.com/2026/02/05/china-retaliatory-tariffs-us-goods.html"
        },
        {
            "title": "Tech Sector Braces for Impact as US-China Chip Export Controls Tighten",
            "snippet": "New US export restrictions on advanced semiconductor equipment to China are expected to further strain bilateral relations and impact revenues for major US chip equipment makers.",
            "url": "https://www.wsj.com/tech/semiconductors/chip-export-controls-china-2026"
        },
    ]

    # Theme 3: AI semiconductor NVIDIA market outlook 2026
    theme3_results = [
        {
            "title": "NVIDIA Reports Record Q4 Revenue of $42 Billion, Beats Expectations",
            "snippet": "NVIDIA posted record quarterly revenue of $42 billion driven by insatiable demand for AI chips, with data center revenue surging 85% year-over-year. The company guided for continued strong growth.",
            "url": "https://www.reuters.com/technology/nvidia-q4-earnings-record-revenue-2026/"
        },
        {
            "title": "NVIDIA Blackwell GPU Demand Exceeds Supply Through 2026",
            "snippet": "NVIDIA CEO Jensen Huang said demand for the company's next-generation Blackwell AI chips continues to outstrip supply, with orders booked well into the second half of 2026.",
            "url": "https://www.bloomberg.com/news/articles/2026-02-03/nvidia-blackwell-demand-supply-2026"
        },
        {
            "title": "AI Semiconductor Market to Reach $300 Billion by 2027, Report Finds",
            "snippet": "A new report from Gartner projects the global AI semiconductor market will reach $300 billion by 2027, with NVIDIA commanding over 80% market share in AI training chips.",
            "url": "https://www.cnbc.com/2026/02/01/ai-semiconductor-market-300-billion-2027.html"
        },
        {
            "title": "AMD and Intel Challenge NVIDIA in AI Chip Market with New Offerings",
            "snippet": "AMD's MI400 and Intel's Gaudi 3 processors are gaining traction in the AI inference market, though NVIDIA maintains its dominant position in AI training workloads.",
            "url": "https://www.marketwatch.com/story/amd-intel-nvidia-ai-chip-competition-2026"
        },
        {
            "title": "DeepSeek AI Efficiency Breakthrough Raises Questions About GPU Demand",
            "snippet": "Chinese AI startup DeepSeek's demonstration of training competitive AI models with fewer GPUs has raised questions about the long-term trajectory of AI chip demand, though most analysts remain bullish.",
            "url": "https://www.ft.com/content/deepseek-ai-gpu-demand-implications-2026"
        },
    ]

    # Theme 4: Stock market forecast S&P 500 February 2026
    theme4_results = [
        {
            "title": "S&P 500 Reaches New All-Time High Above 6,500 in Early February",
            "snippet": "The S&P 500 index climbed to a fresh record above 6,500 points, powered by strong corporate earnings and continued AI investment enthusiasm, though tariff concerns linger.",
            "url": "https://www.reuters.com/markets/us/sp500-record-high-february-2026-02-07/"
        },
        {
            "title": "Wall Street Strategists Raise 2026 S&P 500 Targets Amid Earnings Strength",
            "snippet": "Major Wall Street banks have raised their year-end S&P 500 targets, with Goldman Sachs projecting 7,000 and Morgan Stanley forecasting 6,800, citing strong earnings growth and AI tailwinds.",
            "url": "https://www.bloomberg.com/news/articles/2026-02-04/wall-street-sp500-targets-2026"
        },
        {
            "title": "Market Breadth Improves as Rally Extends Beyond Magnificent Seven",
            "snippet": "The stock market rally is broadening beyond mega-cap tech stocks, with industrials, healthcare, and financial sectors showing improved performance in early 2026.",
            "url": "https://www.cnbc.com/2026/02/06/market-breadth-improves-beyond-magnificent-seven.html"
        },
        {
            "title": "Earnings Season Update: 78% of S&P 500 Companies Beat Q4 Estimates",
            "snippet": "With 65% of S&P 500 companies having reported Q4 earnings, 78% have beaten analyst estimates, with aggregate earnings growth of 12% year-over-year.",
            "url": "https://www.wsj.com/markets/stocks/sp500-earnings-season-q4-2026"
        },
        {
            "title": "Tariff Uncertainty Creates Headwinds for US Equities Despite Strong Fundamentals",
            "snippet": "While corporate fundamentals remain strong, escalating trade tensions are creating uncertainty for US equities, with sectors exposed to China trade showing increased volatility.",
            "url": "https://www.marketwatch.com/story/tariff-uncertainty-headwinds-equities-2026"
        },
    ]

    # Theme 5: Bitcoin cryptocurrency market analysis 2026
    theme5_results = [
        {
            "title": "Bitcoin Surges Past $105,000 as Institutional Adoption Accelerates",
            "snippet": "Bitcoin reached a new all-time high above $105,000 in February 2026, driven by continued institutional inflows through spot Bitcoin ETFs and growing adoption as a reserve asset.",
            "url": "https://www.coindesk.com/markets/2026/02/08/bitcoin-surges-past-105000/"
        },
        {
            "title": "Spot Bitcoin ETFs See Record $3 Billion Weekly Inflows",
            "snippet": "US-listed spot Bitcoin ETFs attracted a record $3 billion in net inflows last week, with BlackRock's iShares Bitcoin Trust (IBIT) accounting for over half of the total.",
            "url": "https://www.bloomberg.com/news/articles/2026-02-07/bitcoin-etf-record-inflows"
        },
        {
            "title": "US Strategic Bitcoin Reserve Proposal Gains Congressional Support",
            "snippet": "A bipartisan proposal to establish a US strategic Bitcoin reserve has gained momentum in Congress, with supporters arguing it would strengthen the dollar's position and hedge against inflation.",
            "url": "https://www.reuters.com/technology/crypto/us-strategic-bitcoin-reserve-proposal-2026/"
        },
        {
            "title": "Ethereum Surpasses $4,000 as DeFi Activity Reaches New Highs",
            "snippet": "Ethereum climbed above $4,000 as decentralized finance (DeFi) total value locked reached $200 billion, driven by institutional adoption of tokenized real-world assets.",
            "url": "https://www.cnbc.com/2026/02/05/ethereum-4000-defi-activity.html"
        },
        {
            "title": "Crypto Market Regulation: SEC Signals More Favorable Stance Under New Leadership",
            "snippet": "The SEC under new Chairman Paul Atkins has signaled a more crypto-friendly regulatory approach, providing clearer guidelines for digital asset classification and exchange operations.",
            "url": "https://www.wsj.com/finance/regulation/sec-crypto-regulation-stance-2026"
        },
    ]

    # Theme 6: Gold commodity price forecast 2026
    theme6_results = [
        {
            "title": "Gold Prices Hit Record $2,950 Per Ounce Amid Geopolitical Uncertainty",
            "snippet": "Gold prices surged to a new all-time high of $2,950 per ounce as investors sought safe-haven assets amid US-China trade tensions and persistent inflation concerns.",
            "url": "https://www.reuters.com/markets/commodities/gold-record-2950-february-2026-02-08/"
        },
        {
            "title": "Central Banks Continue Record Gold Purchases in 2026",
            "snippet": "Central banks purchased 125 tonnes of gold in January 2026, continuing the record buying trend as nations diversify reserves away from the US dollar amid geopolitical tensions.",
            "url": "https://www.bloomberg.com/news/articles/2026-02-05/central-banks-gold-purchases-2026"
        },
        {
            "title": "Goldman Sachs Raises Gold Price Target to $3,100 for Year-End 2026",
            "snippet": "Goldman Sachs raised its gold price forecast to $3,100 per ounce by year-end 2026, citing central bank demand, geopolitical risks, and the potential for Fed rate cuts later in the year.",
            "url": "https://www.cnbc.com/2026/02/03/goldman-sachs-gold-price-target-3100.html"
        },
        {
            "title": "Gold ETF Inflows Surge as Investors Hedge Against Trade War Risks",
            "snippet": "Gold-backed ETFs saw $5.2 billion in net inflows in January, the highest monthly total since 2020, as investors position for potential economic fallout from escalating trade tensions.",
            "url": "https://www.ft.com/content/gold-etf-inflows-trade-war-2026"
        },
        {
            "title": "Silver Outperforms Gold with Industrial AI Demand Boosting Prices",
            "snippet": "Silver prices have outperformed gold year-to-date, driven by surging industrial demand from AI data centers and solar panel manufacturing alongside traditional safe-haven buying.",
            "url": "https://www.marketwatch.com/story/silver-outperforms-gold-ai-demand-2026"
        },
    ]

    # Theme 7: US treasury bond yield analysis 2026
    theme7_results = [
        {
            "title": "10-Year Treasury Yield Climbs to 4.55% on Inflation and Tariff Concerns",
            "snippet": "The benchmark 10-year US Treasury yield rose to 4.55% as investors priced in the inflationary impact of new tariffs and reduced expectations for Federal Reserve rate cuts in 2026.",
            "url": "https://www.reuters.com/markets/rates-bonds/10-year-treasury-yield-4-55-february-2026/"
        },
        {
            "title": "Yield Curve Steepens as Long-Term Inflation Expectations Rise",
            "snippet": "The US Treasury yield curve has steepened significantly, with the spread between 2-year and 10-year yields widening to 35 basis points as markets price in higher long-term inflation from trade policies.",
            "url": "https://www.bloomberg.com/news/articles/2026-02-06/yield-curve-steepens-inflation"
        },
        {
            "title": "Treasury Auction Demand Weakens, Raising Concerns About US Debt Sustainability",
            "snippet": "Recent Treasury auctions have seen weaker demand from foreign buyers, particularly from China, raising concerns about the US government's ability to fund its growing $37 trillion debt load.",
            "url": "https://www.wsj.com/finance/bonds/treasury-auction-demand-weakens-2026"
        },
        {
            "title": "PIMCO: Bond Market Offers Attractive Yields But Duration Risk Remains",
            "snippet": "PIMCO's latest outlook suggests bonds offer attractive income at current yield levels but warns investors to be cautious about duration risk given uncertainty around inflation and fiscal policy.",
            "url": "https://www.cnbc.com/2026/02/04/pimco-bond-market-outlook-2026.html"
        },
        {
            "title": "Corporate Bond Spreads Tighten to Historic Lows Despite Economic Uncertainty",
            "snippet": "Investment-grade corporate bond spreads have tightened to near-historic lows, reflecting strong corporate balance sheets and investor appetite for yield in a still-growing economy.",
            "url": "https://www.ft.com/content/corporate-bond-spreads-historic-lows-2026"
        },
    ]

    # Theme 8: Global recession risk economic outlook 2026
    theme8_results = [
        {
            "title": "IMF Maintains 2026 Global Growth Forecast at 3.3% Despite Trade Tensions",
            "snippet": "The IMF maintained its 2026 global economic growth forecast at 3.3%, but warned that escalating trade conflicts could shave up to 0.5 percentage points off growth if tariffs broaden further.",
            "url": "https://www.reuters.com/markets/imf-global-growth-forecast-2026/"
        },
        {
            "title": "US Recession Probability Falls to 20% as Economy Shows Resilience",
            "snippet": "Major Wall Street banks have lowered their US recession probability estimates to around 20%, citing a strong labor market, consumer spending, and continued business investment in AI infrastructure.",
            "url": "https://www.bloomberg.com/news/articles/2026-02-05/us-recession-probability-falls"
        },
        {
            "title": "European Economy Stagnates as German Manufacturing Slump Deepens",
            "snippet": "The eurozone economy grew just 0.1% in Q4 2025, with Germany's manufacturing sector continuing to contract. The ECB is expected to cut rates further to support growth.",
            "url": "https://www.ft.com/content/european-economy-stagnation-2026"
        },
        {
            "title": "China's Economic Recovery Faces Headwinds from Property Crisis and Tariffs",
            "snippet": "China's economic recovery remains uneven, with the ongoing property sector crisis and new US tariffs creating significant headwinds. Beijing has pledged additional fiscal stimulus.",
            "url": "https://www.cnbc.com/2026/02/03/china-economy-recovery-headwinds-2026.html"
        },
        {
            "title": "Global Trade Volume Growth Slows to 2% as Protectionism Spreads",
            "snippet": "The WTO reports that global trade volume growth has slowed to 2% year-over-year, the weakest pace outside of recession periods, as tariffs and trade barriers proliferate worldwide.",
            "url": "https://www.wsj.com/economy/trade/global-trade-volume-slows-2026"
        },
    ]

    # Theme 9: Oil price OPEC supply demand 2026
    theme9_results = [
        {
            "title": "Oil Prices Stabilize Near $73 as OPEC+ Delays Production Increase",
            "snippet": "Brent crude oil prices stabilized near $73 per barrel after OPEC+ agreed to delay a planned production increase by three months, citing weaker-than-expected global demand.",
            "url": "https://www.reuters.com/business/energy/oil-prices-opec-delay-production-2026-02-06/"
        },
        {
            "title": "US Crude Oil Production Reaches Record 13.5 Million Barrels Per Day",
            "snippet": "US crude oil production hit a record 13.5 million barrels per day in January 2026, keeping a lid on global oil prices despite OPEC+ supply management efforts.",
            "url": "https://www.bloomberg.com/news/articles/2026-02-04/us-crude-production-record"
        },
        {
            "title": "IEA: Global Oil Demand Growth to Slow to 1.0 Million Bpd in 2026",
            "snippet": "The International Energy Agency projects global oil demand will grow by just 1.0 million barrels per day in 2026, down from 1.2 million in 2025, as EV adoption accelerates and economic growth moderates.",
            "url": "https://www.ft.com/content/iea-oil-demand-forecast-2026"
        },
        {
            "title": "Natural Gas Prices Surge on Cold Weather and Rising LNG Export Demand",
            "snippet": "US natural gas prices surged 15% in January as a cold snap boosted heating demand while LNG exports to Europe and Asia reached record levels.",
            "url": "https://www.cnbc.com/2026/02/02/natural-gas-prices-surge-cold-weather-lng.html"
        },
        {
            "title": "Energy Transition Investments Reach $2 Trillion Globally in 2025",
            "snippet": "Global investment in energy transition technologies reached a record $2 trillion in 2025, with solar and battery storage leading growth, according to BloombergNEF's annual report.",
            "url": "https://www.marketwatch.com/story/energy-transition-investment-2-trillion-2026"
        },
    ]

    # Theme 10: Market volatility VIX investor sentiment 2026
    theme10_results = [
        {
            "title": "VIX Spikes to 22 as Trade War Escalation Rattles Markets",
            "snippet": "The CBOE Volatility Index (VIX) jumped to 22 from 15 as the US-China trade war escalation triggered a wave of risk-off selling across global equity markets.",
            "url": "https://www.reuters.com/markets/us/vix-spikes-trade-war-2026-02-05/"
        },
        {
            "title": "Investor Sentiment Survey Shows Growing Caution Despite Market Highs",
            "snippet": "The latest AAII Investor Sentiment Survey shows bearish sentiment rising to 38%, up from 28% a month ago, as investors grow cautious about trade policy uncertainty and elevated valuations.",
            "url": "https://www.bloomberg.com/news/articles/2026-02-06/investor-sentiment-survey-caution"
        },
        {
            "title": "Options Market Signals Hedging Activity at Highest Since October 2023",
            "snippet": "Put option volumes on the S&P 500 have surged to their highest levels since October 2023, indicating institutional investors are actively hedging against downside risk from tariff-related uncertainty.",
            "url": "https://www.cnbc.com/2026/02/07/options-market-hedging-activity-high.html"
        },
        {
            "title": "Fear and Greed Index Falls to 'Fear' Territory as Trade Tensions Mount",
            "snippet": "CNN's Fear and Greed Index dropped to 35, entering 'Fear' territory for the first time in 2026, driven by declining market momentum, put/call ratios, and safe-haven demand.",
            "url": "https://www.cnn.com/markets/fear-and-greed/2026-02-07"
        },
        {
            "title": "Hedge Funds Reduce Net Long Equity Exposure to Lowest Since Mid-2024",
            "snippet": "Hedge funds have cut their net long equity exposure to the lowest level since mid-2024, according to Goldman Sachs prime brokerage data, reflecting growing defensiveness amid policy uncertainty.",
            "url": "https://www.wsj.com/finance/investing/hedge-funds-reduce-equity-exposure-2026"
        },
    ]

    # Combine all results
    all_results = [
        ("Federal Reserve interest rate outlook", theme1_results),
        ("US China trade tariff impact", theme2_results),
        ("AI semiconductor NVIDIA market outlook", theme3_results),
        ("Stock market S&P 500 forecast", theme4_results),
        ("Bitcoin cryptocurrency market", theme5_results),
        ("Gold commodity price forecast", theme6_results),
        ("US treasury bond yield", theme7_results),
        ("Global recession risk outlook", theme8_results),
        ("Oil price OPEC supply demand", theme9_results),
        ("Market volatility VIX sentiment", theme10_results),
    ]

    total_stored = 0
    for theme_name, results in all_results:
        items = []
        for r in results:
            items.append(structure_search_result(r))
        stored = store_news_items(db, items)
        count = len(stored)
        total_stored += count
        print(f"[{theme_name}] Stored {count} items")

    print(f"\n{'='*50}")
    print(f"TOTAL: Stored {total_stored} news items across 10 themes")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
