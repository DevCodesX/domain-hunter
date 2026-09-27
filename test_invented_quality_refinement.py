"""
Phase 1 (Revised) Test Suite: INVENTED Candidate Quality Refinement via Multi-Signal Anchoring
=============================================================================================
Tests:
1. Regression fixture test using exact sample set: tusokn, zuprok, plimvo, pebrowa, kinetoc, bivorn
   - Asserts relative ordering (kinetoc clearly outranks unanchored candidates)
   - Asserts kinetoc is NOT UNANCHORED (HYBRID/LEXICAL_ANCHORED)
   - Asserts tusokn, zuprok, plimvo, pebrowa are UNANCHORED, and bivorn is not STRONG
2. Independent proximity scores: lexical_proximity_score, phonetic_proximity_score, semantic_anchor_score
   stored independently and not collapsed/averaged into a single real_word_proximity value.
3. Coincidental match resistance: single edit-distance match to obscure/rare word does not produce STRONG anchor.
4. Vowel ending bonus cap: maximum contribution <= configured cap (3 points).
5. Length score gating: ideal 6-char length cannot alone rescue an unpronounceable gibberish candidate.
6. Soft penalty tiers: STRONG, MODERATE, WEAK, EXTREMELY_WEAK treated distinctly, only EXTREMELY_WEAK excluded from Tier A/B.
7. weak_unanchored_invented_ratio_cap enforced ONLY on UNANCHORED+weak brandability, STRONG anchored candidates never capped.
8. Reuse confirmation: Soundex, Metaphone, and PhoneticEngine utilities are called/reused, not reimplemented.
9. Full suite regression integrity.
"""

import pytest
from unittest.mock import patch, MagicMock
from quality_engine.invented_quality import (
    InventedQualityEvaluator,
    invented_quality_score,
    invented_subtype,
    evaluate_invented_candidate,
    get_weak_unanchored_ratio_cap
)
from quality_engine.quality_scorer import QualityScorer
from quality_engine.quality_tiers import QualityTierEngine
from quality_engine.feature_extractor import QualityFeatureExtractor
from quality_engine.one_word_engine import OneWordQualityEngine
from quality_engine.naming_classifier import NamingTypeClassifier
import quality_engine.phonetic_engine as pe_module


# =========================================================================
# TEST 1: Regression Fixture Test (tusokn, zuprok, plimvo, pebrowa, kinetoc, bivorn)
# =========================================================================
def test_1_regression_fixture_invented_relative_ordering_and_subtypes():
    """
    Regression fixture test using exact sample set:
    tusokn, zuprok, plimvo, pebrowa, kinetoc, bivorn.
    Asserts relative ordering: kinetoc outranks all unanchored candidates.
    Asserts subtypes: kinetoc != UNANCHORED, others == UNANCHORED (and bivorn not STRONG).
    """
    score_kinetoc = invented_quality_score("kinetoc")
    score_tusokn = invented_quality_score("tusokn")
    score_zuprok = invented_quality_score("zuprok")
    score_plimvo = invented_quality_score("plimvo")
    score_pebrowa = invented_quality_score("pebrowa")
    score_bivorn = invented_quality_score("bivorn")

    # 1. Assert relative ordering: kinetoc clearly outranks unanchored gibberish
    assert score_kinetoc > score_tusokn, f"kinetoc ({score_kinetoc}) should outrank tusokn ({score_tusokn})"
    assert score_kinetoc > score_zuprok, f"kinetoc ({score_kinetoc}) should outrank zuprok ({score_zuprok})"
    assert score_kinetoc > score_plimvo, f"kinetoc ({score_kinetoc}) should outrank plimvo ({score_plimvo})"
    assert score_kinetoc > score_pebrowa, f"kinetoc ({score_kinetoc}) should outrank pebrowa ({score_pebrowa})"
    assert score_kinetoc > score_bivorn, f"kinetoc ({score_kinetoc}) should outrank bivorn ({score_bivorn})"

    # Assert significant separation (at least 15 points between kinetoc and gibberish)
    assert score_kinetoc - score_tusokn >= 15.0, "kinetoc should have strong point separation from tusokn"
    assert score_kinetoc - score_zuprok >= 15.0, "kinetoc should have strong point separation from zuprok"

    # 2. Subtype classifications
    sub_kinetoc = invented_subtype("kinetoc")
    sub_tusokn = invented_subtype("tusokn")
    sub_zuprok = invented_subtype("zuprok")
    sub_plimvo = invented_subtype("plimvo")
    sub_pebrowa = invented_subtype("pebrowa")
    eval_bivorn = evaluate_invented_candidate("bivorn")

    assert sub_kinetoc != "UNANCHORED", f"kinetoc should be anchored, got {sub_kinetoc}"
    assert sub_kinetoc in ["LEXICAL_ANCHORED", "HYBRID_ANCHORED"], f"kinetoc should be anchored, got {sub_kinetoc}"
    assert sub_tusokn == "UNANCHORED", f"tusokn should be UNANCHORED, got {sub_tusokn}"
    assert sub_zuprok == "UNANCHORED", f"zuprok should be UNANCHORED, got {sub_zuprok}"
    assert sub_plimvo == "UNANCHORED", f"plimvo should be UNANCHORED, got {sub_plimvo}"
    assert sub_pebrowa == "UNANCHORED", f"pebrowa should be UNANCHORED, got {sub_pebrowa}"

    # bivorn allowed some tolerance if weak anchor present, but must NOT be STRONG
    assert eval_bivorn["invented_quality_tier"] != "STRONG", f"bivorn must not be STRONG, got {eval_bivorn['invented_quality_tier']}"


# =========================================================================
# TEST 2: Independent Proximity Fields (Not Collapsed / Averaged)
# =========================================================================
def test_2_independent_proximity_scores_stored_separately():
    """
    Asserts lexical_proximity_score, phonetic_proximity_score, and semantic_anchor_score
    are stored as distinct, independent fields and NOT collapsed into a single real_word_proximity field.
    """
    evaluator = InventedQualityEvaluator.get_instance()
    res = evaluator.evaluate_candidate("kinetoc")

    # Verify separate existence
    assert "lexical_proximity_score" in res, "Missing lexical_proximity_score"
    assert "phonetic_proximity_score" in res, "Missing phonetic_proximity_score"
    assert "semantic_anchor_score" in res, "Missing semantic_anchor_score"

    # Verify distinct anchor lists
    assert "lexical_anchors" in res
    assert "phonetic_anchors" in res
    assert "semantic_anchors" in res
    assert "anchor_frequency" in res

    # Verify there is NO single 'real_word_proximity' field
    assert "real_word_proximity" not in res, "real_word_proximity should NOT exist as a collapsed field"

    # Verify independence in QualityScorer integration
    qs = QualityScorer()
    fe = QualityFeatureExtractor()
    owe = OneWordQualityEngine()
    nc = NamingTypeClassifier()

    sf = fe.extract_features("kinetoc")
    ow = owe.compute_one_word_score("kinetoc")
    nt = nc.classify("kinetoc")
    score_res = qs.score_candidate("kinetoc.com", structural_features=sf, one_word_features=ow, naming_type_info=nt)

    assert "lexical_proximity_score" in score_res
    assert "phonetic_proximity_score" in score_res
    assert "semantic_anchor_score" in score_res
    assert "real_word_proximity" not in score_res
    assert score_res["invented_subtype"] in ["HYBRID_ANCHORED", "LEXICAL_ANCHORED"]


# =========================================================================
# TEST 3: Resistance to Coincidental Matches (Single Rare Word Match)
# =========================================================================
def test_3_single_coincidental_match_to_rare_word_not_strong():
    """
    Constructs a synthetic candidate with ONE coincidental edit-distance match to a rare/obscure word.
    Verifies that top-3-5 anchors and anchor_frequency logic down-weights isolated, low-frequency matches
    so it does NOT produce a STRONG anchored classification.
    """
    evaluator = InventedQualityEvaluator.get_instance()

    # Synthetic obscure test candidate
    with patch.object(evaluator, "compute_lexical_proximity") as mock_lex:
        # Mock single match to obscure word with Zipf frequency 1.2
        mock_lex.return_value = (
            55.0,
            [{"word": "obscurite", "distance": 1, "similarity": 82.0, "anchor_frequency": 1.2}]
        )
        with patch.object(evaluator, "compute_phonetic_proximity") as mock_phon:
            mock_phon.return_value = (20.0, [])

            res = evaluator.evaluate_candidate("syncoinc")

            # Must NOT be STRONG
            assert res["invented_quality_tier"] != "STRONG", "Single rare match must NOT be classified as STRONG"
            # Semantic anchor score should be low due to low anchor frequency
            assert res["semantic_anchor_score"] < 40.0, f"Expected low semantic score for rare word, got {res['semantic_anchor_score']}"


# =========================================================================
# TEST 4: Vowel Ending Bonus Cap (Max 3 Points)
# =========================================================================
def test_4_vowel_ending_bonus_max_contribution():
    """
    Verifies that vowel_ending_bonus cannot exceed the configured cap (max 3 points)
    regardless of input name.
    """
    evaluator = InventedQualityEvaluator.get_instance()

    # Vowel-ending candidate
    _, sub_vowel = evaluator.compute_brandability_subscores("kineto")
    assert sub_vowel["vowel_ending_bonus"] <= 3.0, f"Vowel bonus exceeded 3.0: {sub_vowel['vowel_ending_bonus']}"
    assert sub_vowel["vowel_ending_bonus"] > 0.0

    # Consonant-ending candidate
    _, sub_cons = evaluator.compute_brandability_subscores("kinetoc")
    assert sub_cons["vowel_ending_bonus"] == 0.0


# =========================================================================
# TEST 5: Length Score Gating (Cannot Rescue Fundamentally Weak Candidate)
# =========================================================================
def test_5_length_score_cannot_alone_rescue_gibberish():
    """
    Constructs a synthetic 6-character candidate with terrible pronunciation and unnatural clusters.
    Verifies that despite 'ideal' length 6, the overall brandability and quality score stay low (< 40).
    """
    evaluator = InventedQualityEvaluator.get_instance()

    # Synthetic 6-char unpronounceable gibberish with zero vowels and bad clusters
    gibberish_6 = "zkxptw"
    res = evaluator.evaluate_candidate(gibberish_6)

    assert len(gibberish_6) == 6
    # Gated length score should be severely reduced
    assert res["brandability_subscores"]["length_score"] < res["brandability_subscores"]["raw_length_score"]
    # Brandability and overall score must remain low
    assert res["brandability_heuristic_score"] < 40.0, f"Expected brandability < 40, got {res['brandability_heuristic_score']}"
    assert res["invented_quality_tier"] == "EXTREMELY_WEAK"
    assert res["invented_subtype"] == "UNANCHORED"


# =========================================================================
# TEST 6: Soft Penalty Tiers (STRONG, MODERATE, WEAK, EXTREMELY_WEAK)
# =========================================================================
def test_6_soft_penalty_tiers_distinct_and_gating():
    """
    Verifies all four penalty tiers are distinct (not binary accept/reject),
    and only EXTREMELY_WEAK gets excluded from Tier A/B.
    """
    # 1. STRONG example (kinetoc: anchored + high brandability)
    eval_strong = evaluate_invented_candidate("kinetoc")
    assert eval_strong["invented_quality_tier"] == "STRONG"
    assert eval_strong["invented_penalty"] == 0.0

    # 2. WEAK example (zuprok or pebrowa: unanchored but decent phonetics)
    eval_weak = evaluate_invented_candidate("zuprok")
    assert eval_weak["invented_quality_tier"] == "WEAK"
    assert eval_weak["invented_penalty"] > eval_strong["invented_penalty"]

    # 3. EXTREMELY_WEAK example (tusokn: unanchored + severe cluster penalty)
    eval_ext_weak = evaluate_invented_candidate("tusokn")
    assert eval_ext_weak["invented_quality_tier"] == "EXTREMELY_WEAK"
    assert eval_ext_weak["invented_penalty"] > eval_weak["invented_penalty"]

    # Verify Tier Gate behavior in QualityTierEngine
    # Candidate with high opportunity score but EXTREMELY_WEAK tier is gated to TIER_C (Watchlist)
    cand_ext_weak = {
        "domain": "tusokn.com",
        "morphology_type": "INVENTED",
        "invented_quality_tier": "EXTREMELY_WEAK",
        "invented_subtype": "UNANCHORED",
        "brandability_heuristic_score": 35.0,
        "ip_risk_level": "LOW"
    }
    tier_ext_weak = QualityTierEngine.assign_tier(cand_ext_weak, opportunity_score=86.0)
    assert tier_ext_weak == "TIER_C", f"EXTREMELY_WEAK should be excluded from Tier A/B, got {tier_ext_weak}"

    # STRONG candidate with high opportunity score enters TIER_A
    cand_strong = {
        "domain": "kinetoc.com",
        "morphology_type": "INVENTED",
        "invented_quality_tier": "STRONG",
        "invented_subtype": "HYBRID_ANCHORED",
        "brandability_heuristic_score": 94.0,
        "ip_risk_level": "LOW"
    }
    tier_strong = QualityTierEngine.assign_tier(cand_strong, opportunity_score=86.0)
    assert tier_strong == "TIER_A", f"STRONG should enter Tier A, got {tier_strong}"

    # WEAK candidate with moderate opportunity score (76.0) is still eligible for TIER_B
    cand_weak = {
        "domain": "zuprok.com",
        "morphology_type": "INVENTED",
        "invented_quality_tier": "WEAK",
        "invented_subtype": "UNANCHORED",
        "brandability_heuristic_score": 75.0,
        "ip_risk_level": "LOW"
    }
    tier_weak = QualityTierEngine.assign_tier(cand_weak, opportunity_score=76.0)
    assert tier_weak == "TIER_B", f"WEAK should still be eligible on merit for Tier B, got {tier_weak}"


# =========================================================================
# TEST 7: weak_unanchored_invented_ratio_cap Enforcement
# =========================================================================
def test_7_weak_unanchored_invented_ratio_cap_only_on_unanchored_subset():
    """
    Verifies weak_unanchored_invented_ratio_cap is enforced ONLY on UNANCHORED+weak brandability
    candidates, and STRONG anchored candidates are NEVER capped even if numerous.
    """
    # Create synthetic candidate set: 5 STRONG anchored + 5 WEAK unanchored
    candidates = []

    # 5 STRONG anchored candidates
    for i in range(5):
        candidates.append({
            "domain": f"stronganchored{i}.com",
            "domain_name": f"stronganchored{i}.com",
            "morphology_type": "INVENTED",
            "invented_quality_tier": "STRONG",
            "invented_subtype": "HYBRID_ANCHORED",
            "brandability_heuristic_score": 92.0,
            "quality_score": 88,
            "overall_score": 88.0,
            "ip_risk_level": "LOW",
            "availability_status": "AVAILABLE_STANDARD"
        })

    # 5 WEAK unanchored candidates
    for i in range(5):
        candidates.append({
            "domain": f"weakunanchored{i}.com",
            "domain_name": f"weakunanchored{i}.com",
            "morphology_type": "INVENTED",
            "invented_quality_tier": "WEAK",
            "invented_subtype": "UNANCHORED",
            "brandability_heuristic_score": 60.0,
            "quality_score": 84,  # High raw score to qualify for Tier A/B before ratio cap
            "overall_score": 84.0,
            "ip_risk_level": "LOW",
            "availability_status": "AVAILABLE_STANDARD"
        })

    # Total 10 candidates. Ratio cap is 15% (0.15).
    # Allowed weak unanchored in Tier A+B = int(10 * 0.15) = 1.
    res = QualityTierEngine.organize_tiers(candidates)
    tier_a = res["tier_a"]
    tier_b = res["tier_b"]
    all_ab = tier_a + tier_b

    # All 5 STRONG anchored candidates must remain in Tier A/B!
    strong_in_ab = [c for c in all_ab if c.get("invented_quality_tier") == "STRONG"]
    assert len(strong_in_ab) == 5, f"All 5 STRONG anchored candidates must remain, got {len(strong_in_ab)}"

    # Weak unanchored in Tier A/B must NOT exceed ratio cap
    weak_in_ab = [c for c in all_ab if c.get("invented_quality_tier") == "WEAK"]
    cap = get_weak_unanchored_ratio_cap()
    max_allowed = int(len(all_ab) * cap)
    assert len(weak_in_ab) <= max_allowed, f"Weak unanchored in Tier A/B ({len(weak_in_ab)}) exceeded cap {max_allowed}"


# =========================================================================
# TEST 8: Reuse of Existing Soundex/Metaphone & Phonetic Clustering Utilities
# =========================================================================
def test_8_reusing_existing_soundex_metaphone_and_phonetic_engine():
    """
    Confirms existing Soundex, Metaphone, and PhoneticEngine utilities
    are called/reused directly rather than parallel implementations existing.
    """
    with patch("quality_engine.invented_quality.metaphone", wraps=pe_module.metaphone) as mock_meta, \
         patch("quality_engine.invented_quality.soundex", wraps=pe_module.soundex) as mock_snd, \
         patch.object(pe_module.PhoneticEngine, "get_composite_phonetic_key", wraps=pe_module.PhoneticEngine.get_composite_phonetic_key) as mock_key:

        evaluator = InventedQualityEvaluator.get_instance()
        evaluator.evaluate_candidate("kinetoc")

        assert mock_meta.called, "Existing metaphone function must be invoked"
        assert mock_snd.called, "Existing soundex function must be invoked"
        assert mock_key.called, "Existing PhoneticEngine.get_composite_phonetic_key must be invoked"


# =========================================================================
# TEST 9: QualityScorer Integration Consistency
# =========================================================================
def test_9_quality_scorer_invented_integration():
    """
    Tests that QualityScorer populates all Phase 1 fields for INVENTED candidates,
    while leaving them None/empty for non-invented candidates (e.g. ONE_WORD).
    """
    qs = QualityScorer()
    fe = QualityFeatureExtractor()
    owe = OneWordQualityEngine()
    nc = NamingTypeClassifier()

    # 1. INVENTED domain
    d_inv = "kinetoc.com"
    sf = fe.extract_features("kinetoc")
    ow = owe.compute_one_word_score("kinetoc")
    nt = nc.classify("kinetoc")
    res_inv = qs.score_candidate(d_inv, structural_features=sf, one_word_features=ow, naming_type_info=nt, morphology_type="INVENTED")

    assert res_inv["morphology_type"] == "INVENTED"
    assert res_inv["invented_subtype"] in ["HYBRID_ANCHORED", "LEXICAL_ANCHORED"]
    assert res_inv["invented_quality_tier"] == "STRONG"
    assert res_inv["lexical_proximity_score"] is not None
    assert res_inv["phonetic_proximity_score"] is not None
    assert res_inv["semantic_anchor_score"] is not None
    assert res_inv["brandability_heuristic_score"] is not None

    # 2. REAL_WORD domain
    d_word = "cloud.com"
    sf_w = fe.extract_features("cloud")
    ow_w = owe.compute_one_word_score("cloud")
    nt_w = nc.classify("cloud")
    res_word = qs.score_candidate(d_word, structural_features=sf_w, one_word_features=ow_w, naming_type_info=nt_w, morphology_type="REAL_WORD")

    assert res_word["morphology_type"] == "REAL_WORD"
    assert res_word["invented_subtype"] is None
