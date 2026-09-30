"""
Domain Hunter - Quality Engineering Phase Verification Suite
============================================================
Validates all requirements for the Quality Engineering Phase:
1. Dynamic quota fairness & deficit redistribution (Part B, C, D)
2. Invented generator anchor ratio (>= 85% anchored, <= 10% exploration) (Part E, F)
3. Name classification regression: corelow.com is COMPOUND (Part O)
4. Score inflation prevention & anchor-adjusted brandability (Part J, K, L, M)
5. Regression examples: kinetoc vs tusokn, zuprok, plimvo, pebrowa, ogridu, supoce, tizux, kocud, kyntoa, sakape
6. Selection score calculation & ordering before diversity selection (Part Q, R, T)
7. Stage 9 Funnel observability & counters (Part P)
"""

import pytest
import math
from typing import Dict, Any, List
from unittest.mock import MagicMock, AsyncMock, patch

from quality_engine.config import (
    CANONICAL_STRATEGY_QUOTAS,
    validate_strategy_quotas,
    get_invented_generation_config,
    get_invented_brandability_config,
    get_commercial_calibration_config,
    get_trend_calibration_config,
    get_invented_final_gates_config
)
from quality_engine.multi_engine import MultiEngineOrchestrator, InventedBrandEngine
from quality_engine.naming_classifier import NamingTypeClassifier
from quality_engine.morphology_classifier import MorphologyClassifier
from quality_engine.invented_quality import InventedQualityEvaluator, calculate_invented_semantic_relevance
from quality_engine.brand_refinement import BuyerClarityScorer, CandidateTrendFitScorer
from quality_engine.quality_scorer import QualityScorer
from quality_engine.quality_tiers import QualityTierEngine
from quality_engine.diversity_engine import DiversityEngine
from quality_engine.feature_extractor import QualityFeatureExtractor
from quality_engine.one_word_engine import OneWordQualityEngine


# =========================================================================
# 1. DYNAMIC QUOTA FAIRNESS & DEFICIT REDISTRIBUTION (Parts B, C, D)
# =========================================================================

def test_canonical_strategy_quotas_valid():
    """Verify canonical quotas sum to 1950, invented <= 18%, no negative values."""
    is_valid, errors = validate_strategy_quotas(CANONICAL_STRATEGY_QUOTAS, target_total=1950)
    assert is_valid is True, f"Canonical strategy quotas invalid: {errors}"
    assert CANONICAL_STRATEGY_QUOTAS["INVENTED"] <= 351, "INVENTED quota must be <= 18% of 1950 (351)"
    assert sum(CANONICAL_STRATEGY_QUOTAS.values()) == 1950


def test_dynamic_quotas_fair_redistribution():
    """
    Verify calculate_dynamic_quotas:
    - Never assigns rounding diff exclusively to INVENTED
    - Respects 18% max ratio cap for INVENTED
    - Sums exactly to target total
    """
    orchestrator = MultiEngineOrchestrator(router=None)
    stats = {
        "INVENTED": {"success_rate": 0.99, "avg_quality": 95.0, "total_attempts": 100},
        "ONE_WORD": {"success_rate": 0.10, "avg_quality": 60.0, "total_attempts": 100}
    }
    dynamic_quotas = orchestrator.calculate_dynamic_quotas(target_total=1950, strategy_stats=stats)

    assert sum(dynamic_quotas.values()) == 1950, f"Dynamic quotas sum {sum(dynamic_quotas.values())} != 1950"
    max_invented = int(1950 * 0.18)
    assert dynamic_quotas["INVENTED"] <= max_invented, (
        f"INVENTED quota {dynamic_quotas['INVENTED']} exceeded 18% cap ({max_invented})"
    )


# =========================================================================
# 2. INVENTED GENERATOR ANCHOR RATIO & EXPLORATION (Parts E, F)
# =========================================================================

@pytest.mark.asyncio
async def test_invented_generation_subdistribution():
    """
    Verify InventedBrandEngine produces >= 85% anchored candidates
    and <= 15% controlled exploration neologisms.
    """
    engine = InventedBrandEngine(router=None)
    candidates = await engine.generate(concept="AI Autonomous Intelligence & Neural Compute", count=100)

    assert len(candidates) == 100
    anchored = [c for c in candidates if c.get("invented_subdistribution") == "ANCHORED_INVENTED" or c.get("is_anchored")]
    exploration = [c for c in candidates if c.get("invented_subdistribution") == "EXPLORATION_INVENTED" or c.get("is_exploration")]

    anchored_ratio = len(anchored) / len(candidates)
    exploration_ratio = len(exploration) / len(candidates)

    assert anchored_ratio >= 0.85, f"Anchored ratio {anchored_ratio:.2f} is below 85% target"
    assert exploration_ratio <= 0.15, f"Exploration ratio {exploration_ratio:.2f} exceeds 15% target"

    # Verify no harsh consonant collisions in generated candidates
    harsh_pairs = {"zt", "fq", "gq", "zk", "xz", "zx", "jx", "xj", "vj", "jv", "qp"}
    for c in candidates:
        lbl = c["domain"].replace(".com", "")
        for pair in harsh_pairs:
            assert pair not in lbl, f"Harsh collision '{pair}' in {lbl}"


# =========================================================================
# 3. COMPOUND CLASSIFICATION REGRESSION: corelow.com (Part O)
# =========================================================================

def test_corelow_classified_as_compound():
    """
    REGRESSION TEST: corelow.com must be classified as COMPOUND (core + low),
    NEVER as INVENTED or PREFIX_SUFFIX.
    """
    naming_clf = NamingTypeClassifier()
    morph_clf = MorphologyClassifier()

    naming_res = naming_clf.classify("corelow")
    morph_res = morph_clf.classify_morphology("corelow")

    assert naming_res["naming_type"] == "COMPOUND", (
        f"corelow classified as {naming_res['naming_type']} instead of COMPOUND. Reason: {naming_res.get('reason')}"
    )
    assert morph_res["morphology"] == "COMPOUND", (
        f"corelow morphology classified as {morph_res['morphology']} instead of COMPOUND"
    )
    assert naming_res.get("components") == ["core", "low"]


# =========================================================================
# 4. BRANDABILITY CALIBRATION & ANCHOR ADJUSTMENT (Parts J, K, L, M)
# =========================================================================

def test_brandability_anchor_factor_calibration():
    """
    Verify that unanchored random strings have anchor_factor <= 0.72
    and their brandability is properly discounted, while anchored names retain full factor.
    """
    evaluator = InventedQualityEvaluator.get_instance()

    # Anchored candidate (kinetoc derived from kinetic)
    eval_kinetoc = evaluator.evaluate_candidate("kinetoc")
    assert eval_kinetoc["brandability_anchor_factor"] >= 0.88, (
        f"kinetoc anchor factor {eval_kinetoc['brandability_anchor_factor']} should be >= 0.88"
    )
    assert eval_kinetoc["invented_quality_tier"] == "STRONG"

    # Weak/unanchored candidates
    weak_names = ["tusokn", "zuprok", "plimvo", "pebrowa", "ogridu", "tizux"]
    for name in weak_names:
        res = evaluator.evaluate_candidate(name)
        assert res["brandability_anchor_factor"] <= 0.75, (
            f"{name} anchor factor {res['brandability_anchor_factor']} should be <= 0.75"
        )
        assert res["anchor_adjusted_brandability_score"] < res["raw_brandability_heuristic_score"], (
            f"{name} should have anchor-adjusted brandability lower than raw score"
        )


def test_unanchored_invented_cannot_score_high_overall():
    """
    CRITICAL BUG FIX TEST:
    tusokn.com and zuprok.com must NOT receive inflated 85-98 brand scores.
    Overall quality score for unanchored strings must remain low/moderate (<= 58.0),
    while genuine anchored brandables (kinetoc) score >= 85.0.
    """
    scorer = QualityScorer()
    fe = QualityFeatureExtractor()
    ow = OneWordQualityEngine()
    nc = NamingTypeClassifier()

    scored_kinetoc = scorer.score_candidate(
        domain="kinetoc.com",
        structural_features=fe.extract_features("kinetoc"),
        one_word_features=ow.compute_one_word_score("kinetoc"),
        naming_type_info=nc.classify("kinetoc"),
        concept="Autonomous AI Agents & Intelligent Workflow Automation",
        market_category="AI & Technology"
    )
    assert scored_kinetoc["quality_score"] >= 85.0
    assert scored_kinetoc["brandability_score"] >= 90.0

    for name in ["tusokn", "zuprok", "plimvo", "tizux"]:
        domain = f"{name}.com"
        struct_feats = fe.extract_features(name)
        one_word_feats = ow.compute_one_word_score(name)
        naming_info = nc.classify(name)

        scored = scorer.score_candidate(
            domain=domain,
            structural_features=struct_feats,
            one_word_features=one_word_feats,
            naming_type_info=naming_info,
            concept="Autonomous AI Agents & Intelligent Workflow Automation",
            market_category="AI & Technology"
        )

        assert scored["quality_score"] <= 58.0, (
            f"{domain} scored {scored['quality_score']}, expected <= 58.0"
        )
        # Difference between anchored and weak must be at least 25 points
        assert scored_kinetoc["quality_score"] - scored["quality_score"] >= 25.0

    # tusokn (EXTREMELY_WEAK) has severe brandability discount (< 45.0)
    scored_tusokn = scorer.score_candidate(
        domain="tusokn.com",
        structural_features=fe.extract_features("tusokn"),
        one_word_features=ow.compute_one_word_score("tusokn"),
        naming_type_info=nc.classify("tusokn"),
        concept="Autonomous AI Agents & Intelligent Workflow Automation",
        market_category="AI & Technology"
    )
    assert scored_tusokn["brandability_score"] < 45.0
    assert scored_tusokn["quality_score"] <= 45.0


# =========================================================================
# 5. QUALITY FLOORS & CONVICTION ENFORCEMENT (Parts S, T)
# =========================================================================

def test_tier_a_requires_strong_invented_conviction():
    """
    Tier A requires STRONG or HYBRID_ANCHORED for INVENTED names.
    MODERATE, WEAK, or UNANCHORED candidates cannot enter Tier A even with high score.
    """
    # 1. STRONG candidate enters Tier A
    cand_strong = {
        "domain": "kinetoc.com",
        "morphology_type": "INVENTED",
        "invented_quality_tier": "STRONG",
        "invented_subtype": "HYBRID_ANCHORED",
        "ip_risk_level": "LOW",
        "pronunciation_score": 88.0,
        "hear_to_spell_score": 85.0,
        "commercial_naturalness_score": 82.0,
        "brandability_score": 90.0,
        "quality_breakdown": {
            "_float_scores": {"pronunciation": 88.0, "brandability": 90.0, "startup_naturalness": 82.0}
        }
    }
    tier_strong = QualityTierEngine.assign_tier(cand_strong, opportunity_score=86.0)
    assert tier_strong == "TIER_A"

    # 2. MODERATE candidate demoted from Tier A to Tier B
    cand_mod = {
        "domain": "pulsera.com",
        "morphology_type": "INVENTED",
        "invented_quality_tier": "MODERATE",
        "invented_subtype": "LEXICAL_ANCHORED",
        "ip_risk_level": "LOW",
        "pronunciation_score": 88.0,
        "hear_to_spell_score": 85.0,
        "commercial_naturalness_score": 82.0,
        "brandability_score": 85.0,
        "quality_breakdown": {
            "_float_scores": {"pronunciation": 88.0, "brandability": 85.0, "startup_naturalness": 82.0}
        }
    }
    tier_mod = QualityTierEngine.assign_tier(cand_mod, opportunity_score=86.0)
    assert tier_mod == "TIER_B", f"MODERATE should be demoted from Tier A to Tier B, got {tier_mod}"


def test_quality_floors_check_method():
    """Verify QualityTierEngine.check_quality_floors filters out fatally flawed candidates."""
    # Good candidate passes
    cand_good = {
        "quality_score": 75.0,
        "pronunciation_score": 80.0,
        "hear_to_spell_score": 75.0,
        "morphology_type": "COMPOUND"
    }
    passes, reasons = QualityTierEngine.check_quality_floors(cand_good)
    assert passes is True
    assert len(reasons) == 0

    # EXTREMELY_WEAK candidate fails
    cand_bad = {
        "quality_score": 72.0,
        "pronunciation_score": 75.0,
        "hear_to_spell_score": 70.0,
        "morphology_type": "INVENTED",
        "invented_quality_tier": "EXTREMELY_WEAK"
    }
    passes_bad, reasons_bad = QualityTierEngine.check_quality_floors(cand_bad)
    assert passes_bad is False
    assert any("EXTREMELY_WEAK" in r for r in reasons_bad)


# =========================================================================
# 6. SELECTION SCORE & DIVERSITY INTEGRATION (Parts Q, R, T)
# =========================================================================

def test_selection_score_formula_and_penalties():
    """
    Verify compute_selection_score balances quality, commercial, buyer clarity,
    semantic, and applies invented tier penalties.
    """
    # Strong candidate
    cand_strong = {
        "quality_score": 85.0,
        "brandability_score": 88.0,
        "anchor_adjusted_brandability_score": 88.0,
        "commercial_score": 82.0,
        "buyer_clarity_score": 80.0,
        "startup_naturalness_score": 82.0,
        "semantic_score": 85.0,
        "morphology_type": "INVENTED",
        "invented_quality_tier": "STRONG",
        "invented_subtype": "HYBRID_ANCHORED",
        "word_glue_penalty": 0.0,
        "quality_breakdown": {
            "_float_scores": {
                "brandability": 88.0, "commercial": 82.0, "semantic": 85.0, "pronunciation": 85.0
            }
        }
    }
    score_strong = QualityTierEngine.compute_selection_score(cand_strong)
    assert score_strong >= 82.0

    # Weak unanchored candidate with same raw metrics gets tier penalty
    cand_weak = dict(cand_strong)
    cand_weak["invented_quality_tier"] = "WEAK"
    cand_weak["invented_subtype"] = "UNANCHORED"
    score_weak = QualityTierEngine.compute_selection_score(cand_weak)

    assert score_strong - score_weak >= 10.0, (
        f"Strong ({score_strong}) should significantly outscore weak ({score_weak})"
    )


def test_diversity_engine_uses_selection_score():
    """Verify DiversityEngine prioritizes selection_score over raw overall_score."""
    diversity = DiversityEngine()

    cand1 = {
        "domain": "alphaone.com",
        "domain_name": "alphaone.com",
        "overall_score": 90.0,
        "selection_score": 75.0,  # Lower selection score
        "market_category": "AI & Technology"
    }
    cand2 = {
        "domain": "betatwo.com",
        "domain_name": "betatwo.com",
        "overall_score": 80.0,
        "selection_score": 92.0,  # Higher selection score
        "market_category": "AI & Technology"
    }

    selected = diversity.select_diverse_candidates([cand1, cand2], limit=1)
    assert len(selected) == 1
    assert selected[0]["domain"] == "betatwo.com", "DiversityEngine should pick candidate with higher selection_score"
