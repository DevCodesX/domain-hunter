"""
IP / Trademark / Existing Brand Risk Engine Package for Domain Hunter
"""

from risk_engine.models import (
    RiskLevel,
    BrandStatus,
    MatchType,
    TrademarkMatch,
    ExistingBrandMatch,
    IPRiskReport
)
from risk_engine.similarity import (
    levenshtein_distance,
    levenshtein_similarity,
    jaro_winkler_similarity,
    soundex,
    metaphone,
    calculate_comprehensive_similarity
)
from risk_engine.curated_brands import CURATED_BRANDS
from risk_engine.negative_screening import NegativeSemanticScreening
from risk_engine.providers.base import TrademarkProvider
from risk_engine.providers.uspto import USPTOProvider
from risk_engine.brand_engine import ExistingBrandEngine
from risk_engine.trademark_engine import TrademarkRiskEngine
from risk_engine.ip_decision import IPDecisionEngine
from risk_engine.known_brand_matcher import (
    BrandRiskResult,
    check_known_brand_collision,
    load_known_brands
)
from risk_engine.atom_trademark_client import (
    AtomTrademarkResult,
    AtomTrademarkClient
)

__all__ = [
    "RiskLevel",
    "BrandStatus",
    "MatchType",
    "TrademarkMatch",
    "ExistingBrandMatch",
    "IPRiskReport",
    "levenshtein_distance",
    "levenshtein_similarity",
    "jaro_winkler_similarity",
    "soundex",
    "metaphone",
    "calculate_comprehensive_similarity",
    "CURATED_BRANDS",
    "NegativeSemanticScreening",
    "TrademarkProvider",
    "USPTOProvider",
    "ExistingBrandEngine",
    "TrademarkRiskEngine",
    "IPDecisionEngine",
    "BrandRiskResult",
    "check_known_brand_collision",
    "load_known_brands",
    "AtomTrademarkResult",
    "AtomTrademarkClient"
]

