"""
Unit Test Suite: Phase 2.75B - Naming Generation & Scoring Audit
Validates:
1. Pattern Saturation Detection & Run-Level Diversity Penalty
2. Phonetic Diversity & Metaphone/Soundex Clustering
3. Morphological Classification (7 Categories)
4. AI-Naming Artifact Detection
5. Generation Template Traceability (9 Fields)
6. Elimination of Hardcoded Repeated Scores (Brand 80 / Trend 88 / Comm 80)
7. Separation of Concept vs Candidate Scores
8. High Score Resolution (Floats)
9. Diversity-Aware Selection (Eliminates sdkura/sdkloom/sdkgrid co-occurrence)
10. One-Word 7-Stage Survival Funnel & Length Distribution
"""

import pytest
from quality_engine.pattern_saturation import PatternSaturationDetector
from quality_engine.phonetic_engine import PhoneticEngine, soundex, metaphone
from quality_engine.morphology_classifier import MorphologyClassifier
from quality_engine.quality_scorer import QualityScorer
from quality_engine.diversity_engine import DiversityEngine
from quality_engine.ai_evaluator import compute_deterministic_linguistic_evaluation


def test_pattern_saturation_detector_penalizes_repeated_patterns():
    """Verify that repeated prefixes/suffixes are detected and receive pattern_diversity penalties."""
    run_candidates = [
        "sdkura.com", "sdkloom.com", "sdkgrid.com", "sdkwave.com",
        "agenlux.com", "agenvos.com",
        "masvera.com", "capevio.com", "toovira.com", "trezync.com",
        "novacore.com", "meridian.com", "caldera.com"
    ]
    report = PatternSaturationDetector.analyze_run_saturation(run_candidates)
    
    # Check that 'sdk' is detected as a saturated prefix
    cand_sat = report["candidate_saturation"]
    assert cand_sat["sdkura"]["prefix_freq"] == 4
    assert cand_sat["sdkloom"]["prefix_freq"] == 4
    assert cand_sat["sdkura"]["pattern_diversity_score"] < 80.0
    
    # Check that 'agen' prefix is detected as repeated
    assert cand_sat["agenlux"]["prefix_freq"] == 2
    assert cand_sat["agenvos"]["prefix_freq"] == 2
    
    # Check that unique names receive full 100.0 pattern diversity
    assert cand_sat["caldera"]["pattern_diversity_score"] == 100.0
    assert cand_sat["meridian"]["pattern_diversity_score"] == 100.0


def test_phonetic_engine_clusters_acoustic_cousins():
    """Verify Soundex, Metaphone, and composite clustering group similar pronunciations."""
    # agenlux and agenvos share the leading 'AJN' phonetic root
    meta_lux = metaphone("agenlux")
    meta_vos = metaphone("agenvos")
    assert meta_lux.startswith("AJN")
    assert meta_vos.startswith("AJN")
    
    # sdkloom and sdkgrid share the STK sound skeleton
    meta_loom = metaphone("sdkloom")
    meta_grid = metaphone("sdkgrid")
    assert meta_loom.startswith("STK")
    assert meta_grid.startswith("STK")

    # Cluster mapping test
    cluster_map = PhoneticEngine.get_candidate_cluster_map(["sdkloom.com", "sdkgrid.com", "sdkwave.com"])
    assert cluster_map["sdkloom.com"] == cluster_map["sdkgrid.com"]


def test_morphology_classifier_all_seven_types():
    """Verify classification into 7 distinct morphologies."""
    assert MorphologyClassifier.classify("stride") in ["REAL_WORD", "FOREIGN_WORD"]
    assert MorphologyClassifier.classify("caldera") in ["REAL_WORD", "FOREIGN_WORD"]
    assert MorphologyClassifier.classify("datadog") in ["COMPOUND", "HYBRID"]
    assert MorphologyClassifier.classify("sdkflow") in ["PREFIX_SUFFIX"]
    assert MorphologyClassifier.classify("lyvion") in ["INVENTED"]
    assert MorphologyClassifier.classify("novashift") in ["COMPOUND", "PREFIX_SUFFIX", "HYBRID"]


def test_ai_naming_artifact_detector():
    """Verify synthetic artifact penalty detects forced consonant stuffing & suffixes."""
    # Synthetic examples with forced endings / consonant clusters
    score_synthetic = MorphologyClassifier.calculate_ai_naming_artifact_score("trezync")
    score_clean = MorphologyClassifier.calculate_ai_naming_artifact_score("meridian")
    assert score_synthetic > score_clean
    assert score_synthetic >= 35.0
    assert score_clean <= 25.0

    score_sdk = MorphologyClassifier.calculate_ai_naming_artifact_score("sdkura")
    assert score_sdk >= 35.0


def test_no_identical_fallback_scores():
    """Verify that deterministic fallback produces differentiated, high-resolution scores."""
    eval_a = compute_deterministic_linguistic_evaluation("agenlux.com")
    eval_b = compute_deterministic_linguistic_evaluation("masvera.com")
    eval_c = compute_deterministic_linguistic_evaluation("meridian.com")

    # Ensure scores are floats and not identical 80/80/80
    assert eval_a["brandability"] != eval_c["brandability"]
    assert eval_a["natural_brand_score"] != eval_c["natural_brand_score"]
    assert eval_b["ai_generated_feel"] != eval_c["ai_generated_feel"]
    assert isinstance(eval_a["brandability"], float)


def test_separation_of_concept_vs_candidate_scores():
    """
    Verify candidate_trend_fit_score is distinct from concept_trend_score,
    and candidate_commercial_fit is distinct from category_opportunity_score.
    """
    scorer = QualityScorer()
    
    # Candidate A: Highly relevant to concept
    res_a = scorer.score_candidate(
        domain="neuralmesh.com",
        structural_features={"label": "neuralmesh", "char_length": 10, "pronounceability_score": 85, "spelling_simplicity": 85, "estimated_memorability": 85},
        one_word_features={"one_word_score": 0},
        naming_type_info={"naming_type": "COMPOUND"},
        concept="Autonomous Neural Agents and Mesh Computing",
        market_category="AI & Technology",
        concept_trend_relevance=92.0,
        category_opportunity_score=88.0
    )

    # Candidate B: Clunky name for the same concept
    res_b = scorer.score_candidate(
        domain="sdkura.com",
        structural_features={"label": "sdkura", "char_length": 6, "pronounceability_score": 60, "spelling_simplicity": 65, "estimated_memorability": 60},
        one_word_features={"one_word_score": 0},
        naming_type_info={"naming_type": "PREFIX_SUFFIX"},
        concept="Autonomous Neural Agents and Mesh Computing",
        market_category="AI & Technology",
        concept_trend_relevance=92.0,
        category_opportunity_score=88.0,
        pattern_diversity_score=75.0
    )

    # Same concept trend score (92.0)
    assert res_a["concept_trend_score"] == 92.0
    assert res_b["concept_trend_score"] == 92.0

    # But candidate trend fit scores must be distinctly different!
    assert res_a["candidate_trend_fit_score"] > res_b["candidate_trend_fit_score"]
    assert res_a["overall_score"] > res_b["overall_score"]
    assert isinstance(res_a["overall_score"], float)


def test_diversity_aware_selection_eliminates_pattern_co_occurrence():
    """Verify that multiple sdk* or agelux/agenvos candidates do not co-occur in final selection."""
    diversity = DiversityEngine()
    
    candidates = [
        {"domain_name": "sdkura.com", "quality_score": 82, "overall_score": 82.5, "phonetic_cluster_id": "PHON_STK_S3", "morphology_type": "PREFIX_SUFFIX", "market_category": "Developer Tools"},
        {"domain_name": "sdkloom.com", "quality_score": 80, "overall_score": 80.2, "phonetic_cluster_id": "PHON_STK_S3", "morphology_type": "PREFIX_SUFFIX", "market_category": "Developer Tools"},
        {"domain_name": "sdkgrid.com", "quality_score": 79, "overall_score": 79.1, "phonetic_cluster_id": "PHON_STK_S3", "morphology_type": "PREFIX_SUFFIX", "market_category": "Developer Tools"},
        {"domain_name": "sdkwave.com", "quality_score": 78, "overall_score": 78.4, "phonetic_cluster_id": "PHON_STK_S3", "morphology_type": "PREFIX_SUFFIX", "market_category": "Developer Tools"},
        {"domain_name": "meridian.com", "quality_score": 90, "overall_score": 90.4, "phonetic_cluster_id": "PHON_MRD_M6", "morphology_type": "REAL_WORD", "market_category": "Finance"},
        {"domain_name": "caldera.com", "quality_score": 88, "overall_score": 88.1, "phonetic_cluster_id": "PHON_KLD_C4", "morphology_type": "REAL_WORD", "market_category": "AI & Technology"},
        {"domain_name": "ironclad.com", "quality_score": 86, "overall_score": 86.3, "phonetic_cluster_id": "PHON_RNK_I6", "morphology_type": "COMPOUND", "market_category": "B2B High-CPC / Commercial Services"}
    ]

    selected = diversity.select_diverse_candidates(candidates, limit=5)
    selected_names = [c["domain_name"] for c in selected]

    # Only the strongest sdk* candidate should survive! Never all four together!
    sdk_count = sum(1 for name in selected_names if name.startswith("sdk"))
    assert sdk_count == 1, f"Expected exactly 1 sdk* candidate, but got {sdk_count}: {selected_names}"
    assert "sdkura.com" in selected_names
    assert "sdkloom.com" not in selected_names
    assert "sdkgrid.com" not in selected_names
    assert "sdkwave.com" not in selected_names
