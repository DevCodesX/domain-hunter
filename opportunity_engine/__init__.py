"""
Phase 2.5: Opportunity & Semantic Expansion Engine Package
"""

from opportunity_engine.config import (
    MARKET_CATEGORIES,
    DEFAULT_CATEGORY_ALLOCATION,
    MAX_CATEGORY_CONCENTRATION,
    ENABLE_MULTILINGUAL,
    get_category_allocations
)
from opportunity_engine.semantic_roots import (
    SEMANTIC_ROOT_LIBRARY,
    get_roots_for_category,
    find_semantic_cluster
)
from opportunity_engine.multilingual_engine import (
    MultilingualEngine,
    MULTILINGUAL_DICTIONARY
)
from opportunity_engine.radio_scorer import RadioTestScorer
from opportunity_engine.category_fit import CategoryFitScorer, OpportunityScorer
from opportunity_engine.concept_discovery import ConceptDiscoveryEngine
from opportunity_engine.matrix_generator import MatrixOpportunityGenerator

__all__ = [
    "MARKET_CATEGORIES",
    "MAX_CATEGORY_CONCENTRATION",
    "ENABLE_MULTILINGUAL",
    "get_category_allocations",
    "SEMANTIC_ROOT_LIBRARY",
    "get_roots_for_category",
    "find_semantic_cluster",
    "MultilingualEngine",
    "MULTILINGUAL_DICTIONARY",
    "RadioTestScorer",
    "CategoryFitScorer",
    "OpportunityScorer",
    "ConceptDiscoveryEngine",
    "MatrixOpportunityGenerator"
]
