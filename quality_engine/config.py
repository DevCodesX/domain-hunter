"""
Domain Hunter - Quality Engine Configuration
Configurable weights, thresholds, targets, and parameters.
All settings can be customized via environment variables or modified here.
"""

import os
import json
from typing import Dict, Any, List, Tuple, Optional, Set

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
        "deterministic": 0.25,
        "linguistic": 0.11,
        "brand": 0.13,
        "commercial": 0.13,
        "buyer": 0.09,
        "semantic": 0.08,
        "atom": float(os.getenv("ATOM_RANK_WEIGHT", "0.12")),
        "learning": 0.07,
        "pattern_diversity": 0.05,
    },
    "role_task_map": {
        "linguistic": "linguistic_judge",
        "brand": "brand_judge",
        "commercial": "commercial_judge",
        "red_team": "red_team",
        "arbiter": "consensus_arbiter",
    },
    "linguistic": {"enabled": True, "temperature": 0.1, "max_tokens": 2200},
    "brand": {"enabled": True, "temperature": 0.2, "max_tokens": 2200},
    "commercial": {"enabled": True, "temperature": 0.2, "max_tokens": 2200},
    "red_team": {"enabled": True, "temperature": 0.1, "max_tokens": 2200},
    "arbiter": {"enabled": True, "temperature": 0.1, "max_tokens": 1800},
    "arbiter_enabled": True,
    "role_profile_index": {
        "linguistic": 0,
        "brand": 0,
        "commercial": 0,
        "red_team": 0,
        "arbiter": 0,
    },
}
def get_multi_model_evaluation_config() -> Dict[str, Any]:
    cfg = json.loads(json.dumps(DEFAULT_MULTI_MODEL_EVALUATION))
    return cfg

def get_atom_config() -> Dict[str, Any]:
    return {
        "enabled": os.getenv("ATOM_ENABLED", "true").lower() == "true",
        "required_for_final": os.getenv("ATOM_REQUIRED_FOR_FINAL", "true").lower() == "true",
        "api_token": os.getenv("ATOM_API_TOKEN", os.getenv("ATOM_API_KEY", "")).strip(),
        "user_id": os.getenv("ATOM_USER_ID", "").strip(),
        "endpoint": os.getenv("ATOM_APPRAISAL_URL", "https://www.atom.com/api/marketplace/domain-appraisal"),
        "max_appraisals_per_run": int(os.getenv("ATOM_MAX_APPRAISALS_PER_RUN", "10")),
        "cache_ttl_hours": int(os.getenv("ATOM_CACHE_TTL_HOURS", "24")),
        "min_domain_score": float(os.getenv("ATOM_MIN_DOMAIN_SCORE", "8.0")),
        "tier_a_min_score": float(os.getenv("ATOM_TIER_A_MIN_DOMAIN_SCORE", "8.5")),
        "review_range_min": float(os.getenv("ATOM_REVIEW_RANGE_MIN", "7.0")),
        "rank_weight": float(os.getenv("ATOM_RANK_WEIGHT", "0.12")),
    }

# =========================================================================
# 2. NAMING STRATEGY CANDIDATE TARGETS (SINGLE SOURCE OF TRUTH)
# =========================================================================
# Authoritative baseline quotas (Total = 1950, INVENTED <= 18% max cap)
CANONICAL_STRATEGY_QUOTAS: Dict[str, int] = {
    "ONE_WORD": 350,
    "COMPOUND": 350,
    "SEMANTIC": 350,
    "INVENTED": 270,
    "PREFIX_SUFFIX": 210,
    "TREND": 210,
    "KEYWORD_BRANDABLE": 210,
}

# Aliases for backwards compatibility with legacy naming strategy keys
DEFAULT_STRATEGY_TARGETS: Dict[str, int] = {
    "ONE_WORD": CANONICAL_STRATEGY_QUOTAS["ONE_WORD"],
    "COMPOUND": CANONICAL_STRATEGY_QUOTAS["COMPOUND"],
    "INVENTED": CANONICAL_STRATEGY_QUOTAS["INVENTED"],
    "SEMANTIC": CANONICAL_STRATEGY_QUOTAS["SEMANTIC"],
    "SEMANTIC_BRANDABLE": CANONICAL_STRATEGY_QUOTAS["SEMANTIC"],
    "KEYWORD_BRANDABLE": CANONICAL_STRATEGY_QUOTAS["KEYWORD_BRANDABLE"],
    "TREND": CANONICAL_STRATEGY_QUOTAS["TREND"],
    "TREND_BASED": CANONICAL_STRATEGY_QUOTAS["TREND"],
    "PREFIX_SUFFIX": CANONICAL_STRATEGY_QUOTAS["PREFIX_SUFFIX"],
}

INVENTED_GENERATION_DEFAULTS: Dict[str, Any] = {
    "baseline_ratio": 0.14,
    "max_ratio": 0.18,
    "exploration_ratio_max": 0.10,
    "anchored_ratio_target": 0.90,
}

INVENTED_BRANDABILITY_DEFAULTS: Dict[str, float] = {
    "anchor_factor_strong": 1.00,
    "anchor_factor_moderate": 0.88,
    "anchor_factor_weak": 0.72,
    "anchor_factor_unanchored": 0.58,
}

COMMERCIAL_CALIBRATION_DEFAULTS: Dict[str, float] = {
    "invented_neutral_baseline": 48.0,
    "short_length_max_bonus": 6.0,
}

TREND_CALIBRATION_DEFAULTS: Dict[str, float] = {
    "invented_unanchored_cap": 40.0,
}

INVENTED_FINAL_GATES_DEFAULTS: Dict[str, str] = {
    "tier_a_requires": "STRONG",
    "tier_b_requires": "MODERATE",
    "weak_action": "WATCHLIST",
    "unanchored_action": "WATCHLIST",
    "extremely_weak_action": "REJECT",
}

QUALITY_CEILINGS_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "UNANCHORED": {
        "max_brandability": 68.0,
        "max_commercial_score": 55.0,
        "max_semantic_relevance": 38.0,
        "max_trend_score": 40.0,
        "max_overall_quality": 58.0,
        "max_selection_score": 58.0,
        "allowed_tiers": ["WATCHLIST"],
    },
    "WEAK": {
        "max_brandability": 74.0,
        "max_commercial_score": 65.0,
        "max_semantic_relevance": 50.0,
        "max_trend_score": 50.0,
        "max_overall_quality": 66.0,
        "max_selection_score": 66.0,
        "allowed_tiers": ["TIER_B", "WATCHLIST"],
    },
    "MODERATE": {
        "max_brandability": 84.0,
        "max_commercial_score": 80.0,
        "max_semantic_relevance": 75.0,
        "max_trend_score": 75.0,
        "max_overall_quality": 80.0,
        "max_selection_score": 80.0,
        "allowed_tiers": ["TIER_B", "WATCHLIST"],
    },
    "STRONG": {
        "max_brandability": 98.0,
        "max_commercial_score": 98.0,
        "max_semantic_relevance": 98.0,
        "max_trend_score": 98.0,
        "max_overall_quality": 98.0,
        "max_selection_score": 98.0,
        "allowed_tiers": ["TIER_A", "TIER_B", "WATCHLIST"],
    },
}

COMPOUND_QUALITY_DEFAULTS: Dict[str, Any] = {
    "contradictory_modifiers": [
        "low", "down", "less", "off", "sub", "under", "slow", "cold",
        "dull", "drop", "lost", "late", "zero", "nil", "void", "bad", "pale"
    ],
    "contradictory_penalty": 36.0,
    "max_contradictory_naturalness": 45.0,
    "max_contradictory_commercial": 50.0,
    "max_contradictory_overall": 60.0,
}


def load_yaml_config_safe() -> Dict[str, Any]:
    """Safely loads invented_quality_weights.yaml if pyyaml is installed."""
    yaml_path = os.path.join(MODULE_DIR, "config", "invented_quality_weights.yaml")
    try:
        import yaml
        if os.path.isfile(yaml_path):
            with open(yaml_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except Exception:
        pass
    return {}


def get_invented_generation_config() -> Dict[str, Any]:
    cfg = load_yaml_config_safe().get("invented_generation", {})
    return {**INVENTED_GENERATION_DEFAULTS, **cfg}


def get_invented_brandability_config() -> Dict[str, float]:
    cfg = load_yaml_config_safe().get("invented_brandability", {})
    return {**INVENTED_BRANDABILITY_DEFAULTS, **cfg}


def get_commercial_calibration_config() -> Dict[str, float]:
    cfg = load_yaml_config_safe().get("commercial_calibration", {})
    return {**COMMERCIAL_CALIBRATION_DEFAULTS, **cfg}


def get_trend_calibration_config() -> Dict[str, float]:
    cfg = load_yaml_config_safe().get("trend_calibration", {})
    return {**TREND_CALIBRATION_DEFAULTS, **cfg}


def get_invented_final_gates_config() -> Dict[str, str]:
    cfg = load_yaml_config_safe().get("invented_final_gates", {})
    return {**INVENTED_FINAL_GATES_DEFAULTS, **cfg}


def get_quality_ceilings_config() -> Dict[str, Dict[str, Any]]:
    cfg = load_yaml_config_safe().get("quality_ceilings", {})
    merged = {}
    for tier, defaults in QUALITY_CEILINGS_DEFAULTS.items():
        tier_cfg = cfg.get(tier, {})
        merged[tier] = {**defaults, **tier_cfg}
    return merged


def get_compound_quality_config() -> Dict[str, Any]:
    cfg = load_yaml_config_safe().get("compound_quality", {})
    return {**COMPOUND_QUALITY_DEFAULTS, **cfg}


def validate_strategy_quotas(quotas: Dict[str, int], target_total: int = 1950) -> Tuple[bool, List[str]]:
    """
    Validates generation quotas:
    - All strategy quotas are >= 0
    - Total sum equals target_total
    - INVENTED quota does not exceed max_ratio (default 18%)
    - No NaN/negative numbers
    """
    errors = []
    inv_cfg = get_invented_generation_config()
    max_inv_ratio = float(inv_cfg.get("max_ratio", 0.18))
    max_inv_allowed = int(round(target_total * max_inv_ratio))

    total = sum(quotas.values())
    if total != target_total:
        errors.append(f"Total normalized quota ({total}) does not equal target_total ({target_total})")

    for strat, count in quotas.items():
        if count < 0:
            errors.append(f"Strategy {strat} has negative quota: {count}")

    inv_count = quotas.get("INVENTED", 0)
    if inv_count > max_inv_allowed:
        errors.append(
            f"INVENTED quota ({inv_count}) exceeds max configured ratio {max_inv_ratio:.1%} ({max_inv_allowed})"
        )

    return (len(errors) == 0, errors)


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
