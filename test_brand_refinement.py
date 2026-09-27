"""
Test Suite: Phase 2.75 Naming Intelligence Refinement
Tests:
1. Natural Brand Quality (Product Hunt test)
2. Compound Naturalness
3. Word-Glue Detector (penalizing generic adjective+noun and verb+noun pairings)
4. AI-Generated Feel Detector (detecting synthetic X/V/Z stuffing and forced suffixes)
5. Candidate Trend Fit (confirming the identical Trend 82 bug is permanently resolved)
6. Buyer Clarity & Commercial Archetypes
7. Startup Naturalness Evaluation
8. 10-Criteria Final Judge Assessment
9. 100% Normalized Quality Weight Aggregation
10. One-Word Priority & Queue Protection
"""

import pytest
from quality_engine.brand_refinement import (
    WordGlueDetector,
    AIGeneratedFeelDetector,
    CompoundNaturalnessScorer,
    BuyerClarityScorer,
    CandidateTrendFitScorer,
    FinalJudge
)
from quality_engine.quality_scorer import QualityScorer
from quality_engine.config import get_quality_weights, DEFAULT_QUALITY_WEIGHTS


def test_weights_sum_to_one_hundred_percent():
    """Verify that the revised quality weights sum to exactly 1.0 (100%)."""
    weights = get_quality_weights()
    total = sum(weights.values())
    assert abs(total - 1.0) < 0.001, f"Weights sum to {total}, expected 1.0"
    assert "natural_brand" in weights
    assert "buyer_clarity" in weights
    assert "startup_naturalness" in weights
    assert weights["natural_brand"] == 0.12
    assert weights["brandability"] == 0.15
    assert weights["commercial"] == 0.13


def test_word_glue_detector_flags_generic_compounds():
    """Word-glue detector must flag generic adj+noun and verb+noun constructs."""
    # Test cases reported from previous run:
    # cleartether, firmclause, bindrule, stilltether, dockterm, surekeel
    for domain in ["cleartether.com", "firmclause.com", "bindrule.com", "stilltether.com", "dockterm.com", "surekeel.com"]:
        res = WordGlueDetector.detect_word_glue(domain)
        assert res["is_word_glue"] is True, f"Expected {domain} to be flagged as word-glue"
        assert res["word_glue_penalty"] >= 20, f"Expected penalty >= 20 for {domain}, got {res['word_glue_penalty']}"
        assert len(res["components"]) == 2


def test_word_glue_detector_spares_natural_brands():
    """Natural brands and clean compounds must NOT be flagged as word-glue."""
    natural_names = ["stripe.com", "coinbase.com", "ironclad.com", "cloudnest.com", "datadoor.com", "lumina.com"]
    for domain in natural_names:
        res = WordGlueDetector.detect_word_glue(domain)
        assert res["is_word_glue"] is False, f"Expected natural name {domain} NOT to be flagged as word-glue"
        assert res["word_glue_penalty"] == 0


def test_ai_generated_feel_detector():
    """Detects low-quality synthetic patterns (stuffing, forced -ix endings)."""
    # Synthetic name from last run: yuridix
    res_synthetic = AIGeneratedFeelDetector.evaluate_ai_feel("yuridix.com")
    assert res_synthetic["ai_generated_feel_score"] > 30

    # Excessive synthetic consonants
    res_stuffing = AIGeneratedFeelDetector.evaluate_ai_feel("vzxqflow.com")
    assert res_stuffing["ai_generated_feel_score"] >= 50
    assert res_stuffing["is_flagged"] is True

    # Natural Latin roots like apex, nexus, matrix should NOT be flagged
    for natural in ["apex.com", "nexus.com", "matrix.com"]:
        res_nat = AIGeneratedFeelDetector.evaluate_ai_feel(natural)
        assert res_nat["ai_generated_feel_score"] <= 30


def test_compound_naturalness_scorer():
    """Evaluates rhythm, length balance, consonant collision."""
    # Good balanced compound
    res_good = CompoundNaturalnessScorer.calculate_compound_naturalness("dataflow.com")
    assert res_good["compound_naturalness_score"] >= 80

    # Generic word glue with consonant collision (dock+term, citadel+pact)
    res_glue = CompoundNaturalnessScorer.calculate_compound_naturalness("dockterm.com")
    assert res_glue["compound_naturalness_score"] < 70


def test_candidate_trend_fit_resolves_identical_trend_82():
    """
    CRITICAL BUG FIX TEST:
    Verifies that unrelated domains receive candidate-specific trend scores,
    NOT the identical 82.0 static score.
    """
    concept = "AI Agent Automation & Autonomous Workflows"
    
    # Candidate A aligns directly with flow / agent tokens
    res_a = CandidateTrendFitScorer.calculate_trend_fit("agentflow.com", concept, concept_trend_relevance=92)
    # Candidate B is unrelated generic
    res_b = CandidateTrendFitScorer.calculate_trend_fit("drywood.com", concept, concept_trend_relevance=92)
    # Candidate C is a finance term
    res_c = CandidateTrendFitScorer.calculate_trend_fit("taxrail.com", concept, concept_trend_relevance=92)

    # Scores must NOT all be 82
    scores = [res_a["blended_trend_score"], res_b["blended_trend_score"], res_c["blended_trend_score"]]
    assert len(set(scores)) > 1, f"Trend scores are still identical: {scores}"
    assert res_a["candidate_trend_fit_score"] > res_b["candidate_trend_fit_score"]
    assert all(s != 82 or len(set(scores)) > 1 for s in scores)


def test_buyer_clarity_scorer():
    """Verify commercial buyer clarity, buyer count, industries, and startup fit."""
    res_ai = BuyerClarityScorer.evaluate_buyer_clarity("agentcore.com", market_category="AI & Technology")
    assert res_ai["buyer_clarity_score"] >= 80
    assert res_ai["buyer_count"] >= 3
    assert "AI SaaS" in res_ai["buyer_industries"]
    assert "AI Agent" in res_ai["startup_fit"]

    res_fin = BuyerClarityScorer.evaluate_buyer_clarity("vaultpay.com", market_category="Finance")
    assert res_fin["buyer_clarity_score"] >= 80
    assert "FinTech" in res_fin["buyer_industries"]


def test_final_judge_verdict():
    """FinalJudge must evaluate 10 criteria and return APPROVED or REJECTED."""
    # Strong candidate
    good_buyer = BuyerClarityScorer.evaluate_buyer_clarity("agentmesh.com", "AI & Technology")
    good_glue = WordGlueDetector.detect_word_glue("agentmesh.com")
    good_ai = AIGeneratedFeelDetector.evaluate_ai_feel("agentmesh.com")

    verdict_good = FinalJudge.evaluate(
        domain="agentmesh.com",
        quality_score=88,
        natural_brand_score=85,
        startup_naturalness_score=88,
        radio_test_score=85,
        buyer_clarity=good_buyer,
        word_glue=good_glue,
        ai_feel=good_ai,
        market_category="AI & Technology"
    )
    assert verdict_good["verdict"] == "APPROVED"
    assert verdict_good["criteria_met_count"] >= 7
    assert verdict_good["criteria"]["real_startup_plausibility"] is True

    # Bad candidate: heavy word glue, low startup naturalness
    bad_buyer = BuyerClarityScorer.evaluate_buyer_clarity("dockterm.com", "Micro-SaaS & Tooling")
    bad_glue = WordGlueDetector.detect_word_glue("dockterm.com")
    bad_ai = AIGeneratedFeelDetector.evaluate_ai_feel("dockterm.com")

    verdict_bad = FinalJudge.evaluate(
        domain="dockterm.com",
        quality_score=62,
        natural_brand_score=52,
        startup_naturalness_score=55,
        radio_test_score=70,
        buyer_clarity=bad_buyer,
        word_glue=bad_glue,
        ai_feel=bad_ai,
        market_category="Micro-SaaS & Tooling"
    )
    assert verdict_bad["verdict"] == "REJECTED"


def test_quality_scorer_penalizes_word_glue():
    """
    QualityScorer must penalize word-glue candidates (firmclause, cleartether, bindrule)
    such that genuine natural brandables score higher.
    """
    scorer = QualityScorer()

    # Domain 1: Natural Brandable (e.g. Sentry / Lumina / NovaCore)
    res_natural = scorer.score_candidate(
        domain="novacore.com",
        structural_features={"label": "novacore", "char_length": 8, "pronounceability_score": 88, "spelling_simplicity": 85, "estimated_memorability": 86},
        one_word_features={"one_word_score": 0},
        naming_type_info={"naming_type": "SEMANTIC_BRANDABLE"},
        concept="Core AI and Neural Infrastructure",
        market_category="AI & Technology"
    )

    # Domain 2: Generic Word-Glue (e.g. firmclause)
    res_glue = scorer.score_candidate(
        domain="firmclause.com",
        structural_features={"label": "firmclause", "char_length": 10, "pronounceability_score": 80, "spelling_simplicity": 75, "estimated_memorability": 70},
        one_word_features={"one_word_score": 0},
        naming_type_info={"naming_type": "COMPOUND"},
        concept="Enterprise Legal Tech",
        market_category="B2B High-CPC / Commercial Services"
    )

    assert res_natural["quality_score"] > res_glue["quality_score"], (
        f"Natural brand ({res_natural['quality_score']}) should beat word-glue ({res_glue['quality_score']})"
    )
    assert res_glue["word_glue_penalty"] >= 25
    assert res_natural["natural_brand_score"] > res_glue["natural_brand_score"]
    assert res_natural["startup_naturalness_score"] > res_glue["startup_naturalness_score"]


if __name__ == "__main__":
    pytest.main(["-v", __file__])
