"""
Domain Hunter - Quality Engine Configuration
Configurable weights, thresholds, targets, and parameters.
All settings can be customized via environment variables or modified here.
"""

import os
import json
from typing import Dict, Any, List

MODULE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(MODULE_DIR, "data")


def _load_json_config(filename: str, default: Any) -> Any:
    path = os.path.join(DATA_DIR, filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

# =========================================================================
# 1. QUALITY SCORING WEIGHTS (MUST SUM TO 1.0 - PHASE 2.75 REVISED)
# =========================================================================
DEFAULT_QUALITY_WEIGHTS: Dict[str, float] = {
    "natural_brand": 0.12,          # Genuinely natural brand vs artificial word glue (Product Hunt test)
    "brandability": 0.15,           # Overall brand power, catchiness, organic appeal
    "memorability": 0.10,           # Ease of recall, stickiness
    "pronunciation": 0.08,          # Phonetic flow, ease of verbal speech
    "simplicity": 0.07,             # Visual clarity, clean spelling (Radio test)
    "commercial": 0.13,             # Commercial market potential & industry fit
    "buyer_clarity": 0.08,          # Clarity of realistic commercial buyer archetype
    "startup_naturalness": 0.08,    # Plausibility as real US startup / software company
    "trend": 0.07,                  # Candidate-specific trend & opportunity fit (NOT static 82)
    "semantic": 0.05,               # Semantic clarity & category resonance
    "distinctiveness": 0.07         # Uniqueness vs generic synthetic patterns
}

def get_quality_weights() -> Dict[str, float]:
    """Load quality weights from environment if defined as JSON, else use defaults."""
    env_val = os.getenv("QUALITY_WEIGHTS")
    if env_val:
        try:
            parsed = json.loads(env_val)
            # Verify sum is approximately 1.0
            total = sum(parsed.values())
            if 0.98 <= total <= 1.02:
                return parsed
        except Exception:
            pass
    return DEFAULT_QUALITY_WEIGHTS.copy()


QUALITY_IMPROVEMENTS = _load_json_config("quality_improvements.json", {})
PHONOTACTIC_NGRAMS = _load_json_config("phonotactic_ngrams.json", {})

# =========================================================================
# 2. NAMING STRATEGY CANDIDATE TARGETS
# =========================================================================
DEFAULT_STRATEGY_TARGETS: Dict[str, int] = {
    "ONE_WORD": int(os.getenv("TARGET_ONE_WORD", "300")),
    "INVENTED": int(os.getenv("TARGET_INVENTED", "280")),
    "SEMANTIC": int(os.getenv("TARGET_SEMANTIC", "350")),
    "COMPOUND": int(os.getenv("TARGET_COMPOUND", "300")),
    "PREFIX_SUFFIX": int(os.getenv("TARGET_PREFIX_SUFFIX", "200")),
    "TREND": int(os.getenv("TARGET_TREND", "200")),
    "KEYWORD_BRANDABLE": int(os.getenv("TARGET_KEYWORD_BRANDABLE", "200")),
    "SEMANTIC_BRANDABLE": int(os.getenv("TARGET_SEMANTIC_BRANDABLE", "350")),
    "TREND_BASED": int(os.getenv("TARGET_TREND_BASED", "200")),
}

# =========================================================================
# 3. QUALITY THRESHOLDS & BOUNDARIES
# =========================================================================
MIN_QUALITY_SCORE: int = int(os.getenv("MIN_QUALITY_SCORE", "70"))
MIN_BRANDABILITY_SCORE: int = int(os.getenv("MIN_BRANDABILITY_SCORE", "65"))
MIN_COMMERCIAL_SCORE: int = int(os.getenv("MIN_COMMERCIAL_SCORE", "65"))

MAX_CANDIDATE_LENGTH: int = int(
    os.getenv(
        "MAX_CANDIDATE_LENGTH",
        str(QUALITY_IMPROVEMENTS.get("compound_constraints", {}).get("max_candidate_length", 12))
    )
)
MIN_CANDIDATE_LENGTH: int = int(os.getenv("MIN_CANDIDATE_LENGTH", "3"))
MAX_COMPOUND_ROOTS: int = int(
    os.getenv(
        "MAX_COMPOUND_ROOTS",
        str(QUALITY_IMPROVEMENTS.get("compound_constraints", {}).get("max_roots_per_compound", 2))
    )
)

# =========================================================================
# 4. PIPELINE EXECUTION & BATCHING
# =========================================================================
MAX_LLM_EVAL_BATCH_SIZE: int = int(os.getenv("MAX_LLM_EVAL_BATCH_SIZE", "25"))
MAX_AI_EVAL_CANDIDATES: int = int(os.getenv("MAX_AI_EVAL_CANDIDATES", "80"))
FINAL_RESULT_COUNT: int = int(os.getenv("FINAL_RESULT_COUNT", "15"))

# Diversity settings
EMBEDDING_SIMILARITY_THRESHOLD: float = float(os.getenv("EMBEDDING_SIMILARITY_THRESHOLD", "0.78"))
DIVERSITY_CLUSTER_THRESHOLD: float = float(os.getenv("DIVERSITY_CLUSTER_THRESHOLD", "0.75"))

# Trademark screening threshold
TRADEMARK_RISK_THRESHOLD: float = float(os.getenv("TRADEMARK_RISK_THRESHOLD", "0.65"))

# =========================================================================
# 5. QUALITY IMPROVEMENT DATASETS
# =========================================================================
CLICHE_SUFFIX_ROOTS: List[str] = list(QUALITY_IMPROVEMENTS.get("cliche_suffix_roots", []))
CLICHE_BASE_PENALTY: float = float(QUALITY_IMPROVEMENTS.get("cliche_penalties", {}).get("base_penalty", 18.0))
CLICHE_REPEAT_PENALTY_STEP: float = float(QUALITY_IMPROVEMENTS.get("cliche_penalties", {}).get("repeat_penalty_step", 5.0))

KNOWN_PREFIXES: List[str] = list(QUALITY_IMPROVEMENTS.get("known_prefixes", []))
KNOWN_SUFFIXES: List[str] = list(QUALITY_IMPROVEMENTS.get("known_suffixes", []))
RECOGNIZED_SEMANTIC_ROOTS: List[str] = list(QUALITY_IMPROVEMENTS.get("recognized_semantic_roots", []))

SEMANTIC_ROOT_BONUS: float = float(QUALITY_IMPROVEMENTS.get("semantic_root_bonus", {}).get("bonus_points", 8.0))
PURE_INVENTED_PENALTY: float = float(QUALITY_IMPROVEMENTS.get("semantic_root_bonus", {}).get("pure_invented_penalty", 6.0))
PURE_INVENTED_TIER_A_MIN_PRONOUNCEABILITY: float = float(
    QUALITY_IMPROVEMENTS.get("semantic_root_bonus", {}).get("pure_invented_tier_a_min_pronounceability", 82.0)
)
PURE_INVENTED_TIER_A_MIN_MEMORABILITY: float = float(
    QUALITY_IMPROVEMENTS.get("semantic_root_bonus", {}).get("pure_invented_tier_a_min_memorability", 80.0)
)
PURE_INVENTED_TIER_B_MIN_PRONOUNCEABILITY: float = float(
    QUALITY_IMPROVEMENTS.get("semantic_root_bonus", {}).get("pure_invented_tier_b_min_pronounceability", 74.0)
)
PURE_INVENTED_TIER_B_MIN_MEMORABILITY: float = float(
    QUALITY_IMPROVEMENTS.get("semantic_root_bonus", {}).get("pure_invented_tier_b_min_memorability", 72.0)
)

FINAL_ROOT_CAP_TIER_A: int = int(QUALITY_IMPROVEMENTS.get("final_affix_caps", {}).get("tier_a_per_root", 1))
FINAL_ROOT_CAP_TIER_AB: int = int(QUALITY_IMPROVEMENTS.get("final_affix_caps", {}).get("tier_ab_per_root", 2))

PHONOTACTIC_MINIMUM_AVERAGE_SCORE: float = float(PHONOTACTIC_NGRAMS.get("minimum_average_score", 0.56))
PHONOTACTIC_MINIMUM_WEAKEST_SCORE: float = float(PHONOTACTIC_NGRAMS.get("minimum_weakest_score", 0.2))
PHONOTACTIC_BAD_BIGRAMS: Dict[str, float] = dict(PHONOTACTIC_NGRAMS.get("bad_bigrams", {}))
PHONOTACTIC_BAD_TRIGRAMS: Dict[str, float] = dict(PHONOTACTIC_NGRAMS.get("bad_trigrams", {}))
