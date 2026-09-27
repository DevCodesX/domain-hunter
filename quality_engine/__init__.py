"""
Quality Engine Package for Domain Hunter
"""

from quality_engine.config import (
    DEFAULT_QUALITY_WEIGHTS,
    get_quality_weights,
    DEFAULT_STRATEGY_TARGETS,
    MIN_QUALITY_SCORE,
    MIN_BRANDABILITY_SCORE,
    MIN_COMMERCIAL_SCORE,
    FINAL_RESULT_COUNT,
    MAX_AI_EVAL_CANDIDATES
)
from quality_engine.feature_extractor import QualityFeatureExtractor
from quality_engine.one_word_engine import OneWordQualityEngine
from quality_engine.naming_classifier import NamingTypeClassifier
from quality_engine.generator_strategies import NamingStrategyGenerator
from quality_engine.quality_scorer import QualityScorer
from quality_engine.ai_evaluator import AIQualityEvaluator
from quality_engine.diversity_engine import DiversityEngine
from quality_engine.brand_refinement import (
    WordGlueDetector,
    AIGeneratedFeelDetector,
    CompoundNaturalnessScorer,
    BuyerClarityScorer,
    CandidateTrendFitScorer,
    FinalJudge
)

from quality_engine.buyer_intelligence import BuyerIntelligenceEngine
from quality_engine.quality_tiers import QualityTierEngine
from quality_engine.multi_engine import (
    OneWordEngine,
    InventedBrandEngine,
    SemanticBrandEngine,
    CompoundEngine,
    PrefixSuffixEngine,
    TrendEngine,
    KeywordBrandableEngine,
    MultiEngineOrchestrator,
    INITIAL_STRATEGY_QUOTAS
)
from quality_engine.evolutionary_generator import EvolutionaryGenerator
from quality_engine.invented_quality import (
    InventedQualityEvaluator,
    invented_quality_score,
    invented_subtype,
    evaluate_invented_candidate,
    get_weak_unanchored_ratio_cap
)
from quality_engine.pre_availability import (
    calculate_pre_availability_score,
    rank_and_stratify_candidates
)

__all__ = [
    "DEFAULT_QUALITY_WEIGHTS",
    "get_quality_weights",
    "DEFAULT_STRATEGY_TARGETS",
    "MIN_QUALITY_SCORE",
    "MIN_BRANDABILITY_SCORE",
    "MIN_COMMERCIAL_SCORE",
    "QualityFeatureExtractor",
    "OneWordQualityEngine",
    "NamingTypeClassifier",
    "NamingStrategyGenerator",
    "QualityScorer",
    "AIQualityEvaluator",
    "DiversityEngine",
    "WordGlueDetector",
    "AIGeneratedFeelDetector",
    "CompoundNaturalnessScorer",
    "BuyerClarityScorer",
    "CandidateTrendFitScorer",
    "FinalJudge",
    "BuyerIntelligenceEngine",
    "QualityTierEngine",
    "OneWordEngine",
    "InventedBrandEngine",
    "SemanticBrandEngine",
    "CompoundEngine",
    "PrefixSuffixEngine",
    "TrendEngine",
    "KeywordBrandableEngine",
    "MultiEngineOrchestrator",
    "INITIAL_STRATEGY_QUOTAS",
    "EvolutionaryGenerator",
    "InventedQualityEvaluator",
    "invented_quality_score",
    "invented_subtype",
    "evaluate_invented_candidate",
    "get_weak_unanchored_ratio_cap",
    "calculate_pre_availability_score",
    "rank_and_stratify_candidates"
]
