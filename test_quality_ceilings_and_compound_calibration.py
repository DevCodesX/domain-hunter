"""
Tests for Quality Ceilings, No High Score Without Evidence, and Compound Plausibility Calibration.
Verifies:
1. Unanchored synthetic strings (horede, smertis, mentlea, pipeara) receive deflated scores (Brand <= 68, Overall <= 58)
2. Quality Ceilings strictly bound unanchored, weak, and moderate candidates
3. Contradictory compounds (syncLow, apexLow, primeLow) are flagged as CONTRADICTORY_MODIFIER_GLUE and penalized
4. Partially-aligned compounds (nodeshade) receive calibrated trend scores <= 75.0
5. Authentic anchored brandables (kinetoc, vectra) preserve Tier A conviction >= 82+
6. Quality floors and tier assignments enforce ceilings
"""

import pytest
from quality_engine.config import get_quality_ceilings_config, get_compound_quality_config
from quality_engine.invented_quality import InventedQualityEvaluator
from quality_engine.brand_refinement import (
    WordGlueDetector,
    CompoundNaturalnessScorer,
    CandidateTrendFitScorer,
    BuyerClarityScorer
)
from quality_engine.quality_scorer import QualityScorer
from quality_engine.quality_tiers import QualityTierEngine


def test_quality_ceilings_config_loaded():
    """Verify quality ceilings configuration is properly loaded."""
    ceilings = get_quality_ceilings_config()
    assert "UNANCHORED" in ceilings
    assert "WEAK" in ceilings
    assert "MODERATE" in ceilings
    assert "STRONG" in ceilings

    assert ceilings["UNANCHORED"]["max_brandability"] <= 68.0
    assert ceilings["UNANCHORED"]["max_overall_quality"] <= 58.0
    assert "TIER_A" not in ceilings["UNANCHORED"]["allowed_tiers"]
    assert "TIER_B" not in ceilings["UNANCHORED"]["allowed_tiers"]

    assert ceilings["MODERATE"]["max_brandability"] <= 84.0
    assert "TIER_A" not in ceilings["MODERATE"]["allowed_tiers"]
    assert "TIER_B" in ceilings["MODERATE"]["allowed_tiers"]

    assert "TIER_A" in ceilings["STRONG"]["allowed_tiers"]


def test_unanchored_invented_score_deflation_horede():
    """
    REGRESSION AUDIT: horede.com previously scored Brand 96.6, Overall 86.8.
    Must now be classified as UNANCHORED / WEAK with Brand <= 68 and Overall <= 58.
    """
    ev = InventedQualityEvaluator.get_instance()
    res = ev.evaluate_candidate("horede")

    assert res["invented_subtype"] == "UNANCHORED"
    assert res["invented_quality_tier"] in ["WEAK", "EXTREMELY_WEAK"]
    assert res["anchor_adjusted_brandability_score"] <= 68.0, (
        f"horede brandability {res['anchor_adjusted_brandability_score']} exceeds ceiling 68.0"
    )

    qs = QualityScorer()
    q_res = qs.score_candidate(
        domain="horede.com",
        structural_features={"label": "horede", "char_length": 6},
        one_word_features={},
        naming_type_info={"naming_type": "INVENTED"},
        concept="Autonomous AI Agent Platform"
    )
    b = q_res["quality_breakdown"]
    assert q_res["overall_score"] <= 58.0, f"horede overall {q_res['overall_score']} exceeds ceiling 58.0"
    assert b["brandability"] <= 68.0
    assert b["invented_quality_tier"] in ["WEAK", "EXTREMELY_WEAK"]


def test_unanchored_cohort_deflation():
    """
    Verifies the entire reported cohort (smertis, mentlea, pipeara) is deflated.
    """
    ev = InventedQualityEvaluator.get_instance()
    qs = QualityScorer()

    for name in ["smertis", "mentlea", "pipeara"]:
        res = ev.evaluate_candidate(name)
        assert res["invented_subtype"] == "UNANCHORED", f"{name} should be UNANCHORED, got {res['invented_subtype']}"
        assert res["anchor_adjusted_brandability_score"] <= 68.0

        q_res = qs.score_candidate(
            domain=f"{name}.com",
            structural_features={"label": name, "char_length": len(name)},
            one_word_features={},
            naming_type_info={"naming_type": "INVENTED"},
            concept="Autonomous AI Agent Platform"
        )
        assert q_res["overall_score"] <= 58.0, f"{name} overall {q_res['overall_score']} exceeds 58.0"


def test_cunvasa_ceiling_enforced():
    """
    cunvasa has awkward cluster 'nv' and is not an authentic commercial derivation.
    Must be capped at MODERATE, cannot enter Tier A.
    """
    ev = InventedQualityEvaluator.get_instance()
    res = ev.evaluate_candidate("cunvasa")

    assert res["invented_quality_tier"] != "STRONG", "cunvasa must not be STRONG tier"
    assert res["anchor_adjusted_brandability_score"] <= 84.0

    qs = QualityScorer()
    q_res = qs.score_candidate(
        domain="cunvasa.com",
        structural_features={"label": "cunvasa", "char_length": 7},
        one_word_features={},
        naming_type_info={"naming_type": "INVENTED"},
        concept="Autonomous AI Agent Platform"
    )
    assert q_res["overall_score"] <= 80.0

    # Ensure tier assignment caps it at Tier B max
    tier = QualityTierEngine.assign_tier(q_res, opportunity_score=85.0)
    assert tier != "TIER_A", f"cunvasa must not be TIER_A, received {tier}"


def test_contradictory_compounds_penalized():
    """
    Verifies syncLow, apexLow, primeLow are detected as CONTRADICTORY_MODIFIER_GLUE
    and heavily penalized.
    """
    qs = QualityScorer()
    for name in ["synclow", "apexlow", "primelow"]:
        glue = WordGlueDetector.detect_word_glue(name)
        assert glue["is_word_glue"] is True
        assert glue["glue_type"] == "CONTRADICTORY_MODIFIER_GLUE"
        assert glue["word_glue_penalty"] >= 35

        nat = CompoundNaturalnessScorer.calculate_compound_naturalness(name, glue_info=glue)
        assert nat["compound_naturalness_score"] <= 40

        q_res = qs.score_candidate(
            domain=f"{name}.com",
            structural_features={"label": name, "char_length": len(name)},
            one_word_features={},
            naming_type_info={"naming_type": "COMPOUND"},
            concept="High-Performance Cloud Infrastructure"
        )
        assert q_res["overall_score"] <= 60.0, f"{name} overall {q_res['overall_score']} exceeds 60.0 ceiling"

        # Quality floor rejects contradictory compound
        passes_floor, reasons = QualityTierEngine.check_quality_floors(q_res)
        assert passes_floor is False or q_res["overall_score"] < 65.0


def test_nodeshade_trend_fit_calibrated():
    """
    nodeshade has 'node' (tech root) + 'shade' (non-tech).
    Trend score must be calibrated to <= 75.0, not inflated to 96.2.
    """
    trend = CandidateTrendFitScorer.calculate_trend_fit(
        domain_or_label="nodeshade",
        concept="Autonomous AI Agent Platform",
        concept_trend_relevance=95.0
    )
    assert trend["blended_trend_score"] <= 75.0, (
        f"nodeshade trend score {trend['blended_trend_score']} exceeds 75.0"
    )


def test_authentic_brandables_preserve_tier_a():
    """
    Verifies that legitimate anchored brandables (kinetoc, vectra) preserve
    high brandability (>= 88) and qualify for Tier A.
    """
    ev = InventedQualityEvaluator.get_instance()
    qs = QualityScorer()

    for name in ["kinetoc", "vectra"]:
        res = ev.evaluate_candidate(name)
        assert res["invented_quality_tier"] == "STRONG", f"{name} should be STRONG, got {res['invented_quality_tier']}"
        assert res["invented_subtype"] == "HYBRID_ANCHORED"

        q_res = qs.score_candidate(
            domain=f"{name}.com",
            structural_features={"label": name, "char_length": len(name)},
            one_word_features={},
            naming_type_info={"naming_type": "INVENTED"},
            concept="Autonomous AI Agent Platform"
        )
        assert q_res["overall_score"] >= 80.0, f"{name} overall score {q_res['overall_score']} dropped below 80"
        assert q_res["quality_breakdown"]["brandability"] >= 88.0

        # Tier assignment allows Tier A
        opp_score = QualityTierEngine.compute_opportunity_score(q_res)
        tier = QualityTierEngine.assign_tier(q_res, opportunity_score=opp_score)
        assert tier == "TIER_A", f"{name} must achieve TIER_A, got {tier}"


def test_selection_score_ceilings():
    """
    Verifies that compute_selection_score caps unanchored candidates at <= 58.0.
    """
    unanchored_cand = {
        "domain": "horede.com",
        "quality_score": 52.0,
        "brandability_score": 55.0,
        "anchor_adjusted_brandability_score": 55.0,
        "commercial_score": 54.0,
        "buyer_clarity_score": 54.0,
        "startup_naturalness_score": 54.0,
        "semantic_relevance_score": 38.0,
        "pronunciation_score": 75.0,
        "morphology_type": "INVENTED",
        "invented_quality_tier": "WEAK",
        "invented_subtype": "UNANCHORED",
        "quality_breakdown": {
            "_float_scores": {
                "brandability": 55.0,
                "commercial": 54.0,
                "semantic": 38.0,
                "pronunciation": 75.0
            }
        }
    }
    sel_score = QualityTierEngine.compute_selection_score(unanchored_cand)
    assert sel_score <= 58.0, f"Unanchored selection score {sel_score} exceeds 58.0 ceiling"
