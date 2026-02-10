"""Butterfly effect causal chain detection.

Identifies cascading cause-effect relationships between events and their
potential market impact, e.g.:
  Fed rate hike → USD strengthens → EM currencies weaken → EM equities sell off
"""

import logging
from typing import NamedTuple

from src.database.operations import DatabaseOperations

logger = logging.getLogger(__name__)


class CausalLink(NamedTuple):
    cause: str
    effect: str
    mechanism: str
    strength: float  # 0.0 to 1.0


# Pre-defined causal templates (common financial causal chains)
CAUSAL_TEMPLATES: list[list[CausalLink]] = [
    # Rate hike chain
    [
        CausalLink("Fed raises interest rates", "USD strengthens",
                   "Higher rates attract capital inflows", 0.8),
        CausalLink("USD strengthens", "Emerging market currencies weaken",
                   "Capital outflows from EM to USD assets", 0.7),
        CausalLink("EM currencies weaken", "EM equities decline",
                   "Foreign investors sell EM assets, import costs rise", 0.6),
        CausalLink("EM equities decline", "Global risk sentiment deteriorates",
                   "Contagion effect and risk-off positioning", 0.5),
    ],
    # Oil shock chain
    [
        CausalLink("Middle East conflict escalates", "Oil supply disrupted",
                   "Strait of Hormuz/pipeline risk", 0.7),
        CausalLink("Oil supply disrupted", "Oil prices surge",
                   "Supply-demand imbalance", 0.85),
        CausalLink("Oil prices surge", "Inflation expectations rise",
                   "Energy costs feed through to CPI", 0.7),
        CausalLink("Inflation expectations rise", "Bond yields spike",
                   "Market prices in tighter monetary policy", 0.65),
        CausalLink("Bond yields spike", "Growth stocks sold off",
                   "Higher discount rates reduce present value of future earnings", 0.6),
    ],
    # AI capex chain
    [
        CausalLink("AI capex accelerates", "Semiconductor demand surges",
                   "GPU/HBM demand from hyperscalers", 0.85),
        CausalLink("Semiconductor demand surges", "Chip stocks rally",
                   "Revenue/earnings growth expectations", 0.8),
        CausalLink("Chip stocks rally", "Power/energy demand increases",
                   "Data centers require massive electricity", 0.7),
        CausalLink("Power/energy demand increases", "Utility and energy stocks benefit",
                   "Infrastructure buildout demand", 0.65),
    ],
    # Crypto cascade
    [
        CausalLink("Bitcoin breaks all-time high", "Crypto market sentiment euphoric",
                   "FOMO and media attention", 0.75),
        CausalLink("Crypto market sentiment euphoric", "Altcoins surge",
                   "Rotation from BTC to higher-beta altcoins", 0.7),
        CausalLink("Altcoins surge", "Regulatory scrutiny increases",
                   "Rapid price appreciation draws regulator attention", 0.5),
        CausalLink("Regulatory scrutiny increases", "Market correction occurs",
                   "Uncertainty and potential restrictions", 0.55),
    ],
    # Trade war chain
    [
        CausalLink("US imposes new tariffs on China", "Supply chain disrupted",
                   "Import costs rise, sourcing shifts needed", 0.75),
        CausalLink("Supply chain disrupted", "Tech hardware costs increase",
                   "Components and assembly affected", 0.7),
        CausalLink("Tech hardware costs increase", "Consumer electronics margins squeezed",
                   "Higher COGS, potential price increases", 0.65),
        CausalLink("Consumer electronics margins squeezed", "Tech sector rotation",
                   "Investors shift to software/services from hardware", 0.5),
    ],
    # Yield curve inversion chain
    [
        CausalLink("Yield curve inverts", "Recession expectations rise",
                   "Historical correlation between inversion and recession", 0.7),
        CausalLink("Recession expectations rise", "Consumer spending contracts",
                   "Precautionary savings increase", 0.6),
        CausalLink("Consumer spending contracts", "Corporate earnings decline",
                   "Revenue shortfall across consumer sectors", 0.65),
        CausalLink("Corporate earnings decline", "Equity market declines",
                   "Earnings-driven selloff", 0.7),
        CausalLink("Equity market declines", "Safe haven assets rally",
                   "Flight to quality: gold, treasuries, USD", 0.75),
    ],
]

# Keywords that trigger specific chain templates
CHAIN_TRIGGER_KEYWORDS: dict[int, list[str]] = {
    0: ["rate hike", "fed raise", "interest rate increase", "hawkish", "tightening"],
    1: ["oil shock", "middle east", "oil supply", "opec cut", "strait of hormuz"],
    2: ["ai capex", "ai spending", "gpu demand", "data center", "ai infrastructure"],
    3: ["bitcoin ath", "crypto rally", "bitcoin high", "crypto surge"],
    4: ["tariff", "trade war", "trade restriction", "import duty"],
    5: ["yield curve invert", "inverted yield", "2y10y", "recession signal"],
}


def detect_chains(text: str) -> list[int]:
    """Detect which causal chain templates are triggered by the text.

    Returns list of chain template indices.
    """
    text_lower = text.lower()
    triggered = []
    for idx, keywords in CHAIN_TRIGGER_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            triggered.append(idx)
    return triggered


def build_chain_from_template(template_idx: int) -> list[CausalLink]:
    """Get the causal chain for a template index."""
    if 0 <= template_idx < len(CAUSAL_TEMPLATES):
        return CAUSAL_TEMPLATES[template_idx]
    return []


def store_detected_chains(db: DatabaseOperations, text: str,
                          evidence_id: int | None = None) -> list[int]:
    """Detect and store butterfly chains triggered by the given text.

    Args:
        db: Database operations instance.
        text: Text to analyze for chain triggers.
        evidence_id: Optional processed_data ID for evidence linking.

    Returns:
        List of created chain IDs.
    """
    triggered = detect_chains(text)
    chain_ids: list[int] = []

    for idx in triggered:
        template = build_chain_from_template(idx)
        if not template:
            continue

        # Compute chain confidence (product of link strengths)
        confidence = 1.0
        for link in template:
            confidence *= link.strength

        chain_id = db.create_butterfly_chain(
            name=f"Chain: {template[0].cause}",
            trigger_event=template[0].cause,
            description=f"{template[0].cause} → ... → {template[-1].effect}",
            final_impact=template[-1].effect,
            confidence=round(confidence, 3),
        )

        for i, link in enumerate(template):
            db.add_chain_link(
                chain_id=chain_id,
                seq_order=i + 1,
                cause=link.cause,
                effect=link.effect,
                mechanism=link.mechanism,
                strength=link.strength,
                evidence_id=evidence_id,
            )

        chain_ids.append(chain_id)
        logger.info(f"Created butterfly chain: {template[0].cause} → {template[-1].effect} "
                     f"(confidence={confidence:.3f})")

    return chain_ids
