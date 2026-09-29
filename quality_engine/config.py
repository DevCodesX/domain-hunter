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
# MULTI-MODEL QUALITY EVALUATION CONFIGURATION
# =========================================================================
# Role/model selection is resolved against the existing ModelRouter task profiles.
# Environment variables can override role provider/model only when the pair is present
# in the router's configured profiles.
DEFAULT_MULTI_MODEL_EVALUATION: Dict[str, Any] = {
    "enabled": os.getenv("MULTI_MODEL_EVALUATION_ENABLED", "true").lower() == "true",
    "stage1_pool_size": int(os.getenv("MULTI_MODEL_STAGE1_POOL", "50")),
    "arbiter_pool_size": int(os.getenv("MULTI_MODEL_ARBITER_POOL", "20")),
    "judge_batch_size": int(os.getenv("MULTI_MODEL_JUDGE_BATCH_SIZE", "5")),
    "request_timeout_seconds": float(os.getenv("MULTI_MODEL_TIMEOUT_SECONDS", "25")),
    "judge_max_retries": int(os.getenv("MULTI_MODEL_MAX_RETRIES", "1")),
    "disagreement_threshold": float(os.getenv("MULTI_MODEL_DISAGREEMENT_THRESHOLD", "22")),
    "disagreement_penalty_factor": float(os.getenv("MULTI_MODEL_DISAGREEMENT_PENALTY", "0.35")),
    "missing_judge_penalty": float(os.getenv("MULTI_MODEL_MISSING_JUDGE_PENALTY", "6")),
    "min_consensus_confidence": float(os.getenv("MULTI_MODEL_MIN_CONFIDENCE", "55")),
    "arbiter_review_min_score": float(os.getenv("MULTI_MODEL_ARBITER_REVIEW_MIN_SCORE", "60")),
    "exploration_ratio": float(os.getenv("MULTI_MODEL_EXPLORATION_RATIO", "0.10")),
    "invented_ai_blend": float(os.getenv("MULTI_MODEL_INVENTED_AI_BLEND", "0.35")),
    "non_invented_ai_blend": float(os.getenv("MULTI_MODEL_NON_INVENTED_AI_BLEND", "0.45")),
    "semantic_ai_blend": float(os.getenv("MULTI_MODEL_SEMANTIC_AI_BLEND", "0.25")),
    "commercial_ai_blend": float(os.getenv("MULTI_MODEL_COMMERCIAL_AI_BLEND", "0.35")),
    "red_team_penalty_factor": float(os.getenv("MULTI_MODEL_RED_TEAM_PENALTY", "0.20")),
    "red_team_low_score": float(os.getenv("MULTI_MODEL_RED_TEAM_LOW_SCORE", "55")),
    "final_quality_floor": float(os.getenv("MULTI_MODEL_FINAL_QUALITY_FLOOR", "68")),
    "final_brand_floor": float(os.getenv("MULTI_MODEL_FINAL_BRAND_FLOOR", "60")),
    "final_commercial_floor": float(os.getenv("MULTI_MODEL_FINAL_COMMERCIAL_FLOOR", "58")),
    "final_linguistic_floor": float(os.getenv("MULTI_MODEL_FINAL_LINGUISTIC_FLOOR", "60")),
    "unanchored_final_ceiling": float(os.getenv("MULTI_MODEL_UNANCHORED_CEILING", "64")),
    "weak_final_ceiling": float(os.getenv("MULTI_MODEL_WEAK_CEILING", "72")),
    "unanchored_commercial_ceiling": float(os.getenv("MULTI_MODEL_UNANCHORED_COMMERCIAL_CEILING", "58")),
    "weak_commercial_ceiling": float(os.getenv("MULTI_MODEL_WEAK_COMMERCIAL_CEILING", "68")),
    "deterministic_severe_phonetic_ceiling": float(os.getenv("MULTI_MODEL_SEVERE_PHONETIC_CEILING", "59")),
    "short_meaningless_max_length": int(os.getenv("MULTI_MODEL_SHORT_MEANINGLESS_MAX_LENGTH", "7")),
    "short_meaningless_semantic_max": float(os.getenv("MULTI_MODEL_SHORT_MEANINGLESS_SEMANTIC_MAX", "50")),
    "short_meaningless_commercial_max": float(os.getenv("MULTI_MODEL_SHORT_MEANINGLESS_COMMERCIAL_MAX", "60")),
    "gibberish_likely_threshold": float(os.getenv("MULTI_MODEL_GIBBERISH_LIKELY_THRESHOLD", "70")),
    "gibberish_strong_coined_max": float(os.getenv("MULTI_MODEL_GIBBERISH_STRONG_MAX", "20")),
    "gibberish_acceptable_max": float(os.getenv("MULTI_MODEL_GIBBERISH_ACCEPTABLE_MAX", "40")),
    "diversity_penalty_cap": float(os.getenv("MULTI_MODEL_DIVERSITY_PENALTY_CAP", "8")),
    "final_rank_weights": {
        "deterministic": 0.27,
        "linguistic": 0.11,
        "brand": 0.13,
        "commercial": 0.13,
        "buyer": 0.09,
        "semantic": 0.08,
        "atom": 0.06,
        "learning": 0.07,
        "pattern_diversity": 0.06,
    },
    "role_task_map": {
        "linguistic": "quality_evaluator",
        "brand": "brandability",
        "commercial": "commercial_evaluator",
        "red_team": "quality_evaluator",
        "arbiter": "final_judge",
    },
    "linguistic": {"enabled": True, "temperature": 0.1, "max_tokens": 2200},
    "brand": {"enabled": True, "temperature": 0.2, "max_tokens": 2200},
    "commercial": {"enabled": True, "temperature": 0.2, "max_tokens": 2200},
    "red_team": {"enabled": True, "temperature": 0.1, "max_tokens": 2200},
    "arbiter": {"enabled": True, "temperature": 0.1, "max_tokens": 1800},
    "arbiter_enabled": True,
    "role_profile_index": {
        "linguistic": 2,
        "brand": 0,
        "commercial": 0,
        "red_team": 1,
        "arbiter": 1,
    },
}
def get_multi_model_evaluation_config() -> Dict[str, Any]:
    cfg = json.loads(json.dumps(DEFAULT_MULTI_MODEL_EVALUATION))
    return cfg

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
