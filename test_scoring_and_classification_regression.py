"""
Automated Regression Test Suite (Requirements 1-15)
Verifies:
A. Two different domains do not automatically receive the same score.
B. Concept score is not copied to candidate score.
C. Naming strategy is not automatically equal to naming type.
D. Failed scoring does not receive a high default score.
E. Invented names are classified as INVENTED/COINED when appropriate (not COMPOUND).
F. Real dictionary words are classified correctly.
G. IP NOT_CHECKED is not displayed as IP LOW.
H. Diversity filtering detects repeated naming patterns and retains strongest representative.
"""

import pytest
import statistics
from quality_engine.quality_scorer import QualityScorer
from quality_engine.feature_extractor import QualityFeatureExtractor
from quality_engine.one_word_engine import OneWordQualityEngine
from quality_engine.naming_classifier import NamingTypeClassifier
from quality_engine.pattern_saturation import PatternSaturationDetector
from quality_engine.diversity_engine import DiversityEngine
from quality_engine.brand_refinement import CandidateTrendFitScorer, BuyerClarityScorer
from risk_engine.models import RiskLevel, IPRiskReport
from risk_engine.ip_decision import IPDecisionEngine
from risk_engine.trademark_engine import TrademarkRiskEngine


# =========================================================================
# TEST A: Two different domains do not automatically receive the same score
# =========================================================================
def test_regression_two_different_domains_do_not_receive_identical_scores():
    qs = QualityScorer()
    fe = QualityFeatureExtractor()
    owe = OneWordQualityEngine()
    nc = NamingTypeClassifier()

    problem_domains = [
        "nefqi.com", "woztu.com", "jipna.com", "guvni.com",
        "toovira.com", "capevio.com", "masvera.com", "agenvos.com",
        "fybris.com", "lomdex.com", "kispem.com", "plidoc.com"
    ]

    scored = {}
    for d in problem_domains:
        lbl = d.replace(".com", "")
        sf = fe.extract_features(lbl)
        ow = owe.compute_one_word_score(lbl)
        nt = nc.classify(lbl)
        res = qs.score_candidate(d, structural_features=sf, one_word_features=ow, naming_type_info=nt)
        scored[d] = res

    # 1. Verify brandability scores are differentiated
    brand_scores = [round(scored[d]["brandability_score"], 2) for d in problem_domains]
    unique_brands = len(set(brand_scores))
    assert unique_brands >= 10, f"Expected distinct brand scores, got only {unique_brands} unique in {brand_scores}"

    # 2. Verify candidate trend fit scores are differentiated
    trend_scores = [round(scored[d]["candidate_trend_fit_score"], 2) for d in problem_domains]
    unique_trends = len(set(trend_scores))
    assert unique_trends >= 10, f"Expected distinct trend scores, got only {unique_trends} unique in {trend_scores}"

    # 3. Verify commercial fit scores are differentiated
    comm_scores = [round(scored[d]["candidate_commercial_fit"], 2) for d in problem_domains]
    unique_comms = len(set(comm_scores))
    assert unique_comms >= 10, f"Expected distinct commercial scores, got only {unique_comms} unique in {comm_scores}"

    # 4. Verify overall scores are differentiated with healthy standard deviation
    overall_scores = [round(scored[d]["overall_score"], 3) for d in problem_domains]
    assert len(set(overall_scores)) == len(problem_domains), f"Overall scores contain duplicates: {overall_scores}"
    assert statistics.stdev(overall_scores) > 1.5, f"Standard deviation too low: {statistics.stdev(overall_scores)}"

    # 5. Verify none of the previous hardcoded artifact clusters appear
    old_identical_clusters = {92.51, 80.61, 90.61, 80.0, 88.0, 90.1, 76.51, 88.48}
    for d in problem_domains:
        b = round(scored[d]["brandability_score"], 2)
        t = round(scored[d]["trend_score"], 2)
        c = round(scored[d]["commercial_score"], 2)
        assert (b, t, c) != (92.51, 80.61, 90.61), f"{d} still has old 92.51/80.61/90.61 cluster"
        assert (b, t, c) != (80.0, 88.0, 80.0), f"{d} still has old 80/88/80 cluster"
        assert (b, t, c) != (90.1, 76.51, 88.48), f"{d} still has old 90.1/76.51/88.48 cluster"


# =========================================================================
# TEST B: Concept score is not copied to candidate score
# =========================================================================
def test_regression_concept_score_not_copied_to_candidate_score():
    concept_macro_trend = 88.0
    concept = "AI Agents & Autonomous Workflows"

    # Candidate A: strong AI agent match
    res_a = CandidateTrendFitScorer.calculate_trend_fit(
        domain_or_label="agentflow.com",
        concept=concept,
        concept_trend_relevance=concept_macro_trend
    )

    # Candidate B: unrelated short invented name
    res_b = CandidateTrendFitScorer.calculate_trend_fit(
        domain_or_label="woztu.com",
        concept=concept,
        concept_trend_relevance=concept_macro_trend
    )

    # Concept score is strictly preserved as macro context
    assert res_a["concept_trend_score"] == 88.0
    assert res_b["concept_trend_score"] == 88.0

    # Candidate trend fit is candidate-dependent and NOT copied from concept
    assert res_a["candidate_trend_fit_score"] != concept_macro_trend
    assert res_b["candidate_trend_fit_score"] != concept_macro_trend
    assert res_a["candidate_trend_fit_score"] > res_b["candidate_trend_fit_score"] + 15.0


# =========================================================================
# TEST C: Naming strategy is not automatically equal to naming type
# =========================================================================
def test_regression_naming_strategy_not_automatically_equal_to_naming_type():
    classifier = NamingTypeClassifier()

    # Domain was produced by a "COMPOUND" strategy generator, but linguistically it's INVENTED
    gen_strategy = "COMPOUND"
    classified_woztu = classifier.classify("woztu.com")
    classified_jipna = classifier.classify("jipna.com")

    assert classified_woztu["naming_type"] == "INVENTED"
    assert classified_jipna["naming_type"] == "INVENTED"
    assert gen_strategy != classified_woztu["naming_type"]
    assert gen_strategy != classified_jipna["naming_type"]


# =========================================================================
# TEST D: Failed scoring does not receive a high default score
# =========================================================================
def test_regression_failed_scoring_does_not_receive_high_default_score():
    qs = QualityScorer()
    fe = QualityFeatureExtractor()
    owe = OneWordQualityEngine()
    nc = NamingTypeClassifier()

    d = "badexample.com"
    sf = fe.extract_features("badexample")
    ow = owe.compute_one_word_score("badexample")
    nt = nc.classify("badexample")

    # Simulate failed AI evaluation
    failed_ai_eval = {
        "status": "SCORING_FAILED",
        "evaluation_status": "SCORING_FAILED",
        "reason": "Model API rate limit or JSON schema failure."
    }

    res = qs.score_candidate(
        d,
        structural_features=sf,
        one_word_features=ow,
        naming_type_info=nt,
        ai_evaluation=failed_ai_eval
    )

    # Must be explicitly marked as failed and never receive high default scores (80, 88, 90)
    assert res["status"] == "SCORING_FAILED"
    assert res["quality_score"] == 0
    assert res["overall_score"] == 0.0
    assert res["brandability_score"] == 0.0
    assert res["trend_score"] == 0.0
    assert res["commercial_score"] == 0.0


# =========================================================================
# TEST E: Invented names are classified as INVENTED/COINED (not COMPOUND)
# =========================================================================
def test_regression_invented_names_classified_as_invented():
    classifier = NamingTypeClassifier()

    invented_examples = [
        "nefqi.com", "woztu.com", "jipna.com", "guvni.com",
        "fybris.com", "lomdex.com", "kispem.com", "plidoc.com",
        "nyspel.com", "feskop.com"
    ]

    for d in invented_examples:
        res = classifier.classify(d)
        assert res["naming_type"] == "INVENTED", f"{d} falsely classified as {res['naming_type']}"
        assert res["subtype"] == "INVENTED_ONE_WORD"
        assert res["naming_type"] != "COMPOUND"


# =========================================================================
# TEST F: Real dictionary words are classified correctly
# =========================================================================
def test_regression_real_dictionary_words_classified_correctly():
    classifier = NamingTypeClassifier()

    real_words = ["beacon.com", "cloud.com", "vault.com", "forge.com", "summit.com", "pulse.com"]
    for d in real_words:
        res = classifier.classify(d)
        assert res["naming_type"] == "ONE_WORD", f"{d} not classified as ONE_WORD: {res}"
        assert res["subtype"] == "REAL_ONE_WORD"
        assert res["linguistic_type"] == "REAL_WORD"


# =========================================================================
# TEST G: IP NOT_CHECKED is not displayed as IP LOW
# =========================================================================
def test_regression_ip_not_checked_not_displayed_as_low():
    # 1. Static factory creates explicit NOT_CHECKED report
    report = TrademarkRiskEngine.create_not_checked_report("unscreened.com")
    assert report.ip_risk_level == RiskLevel.NOT_CHECKED
    assert report.ip_check_status == "NOT_CHECKED"
    assert report.ip_risk_level != RiskLevel.LOW

    # 2. Decision engine maintains NOT_CHECKED distinction
    explanation = IPDecisionEngine.build_candidate_explanation(
        domain="unscreened.com",
        quality_score=85,
        quality_breakdown={"commercial": 85},
        naming_type="INVENTED",
        structural_features={"pronounceability_score": 85},
        one_word_features={},
        ip_risk=report
    )

    assert explanation["ip_risk"]["level"] == "NOT_CHECKED"
    assert explanation["ip_risk"]["check_status"] == "NOT_CHECKED"
    assert any("NOT_CHECKED" in r for r in explanation["reasons"])


# =========================================================================
# TEST H: Diversity filtering detects repeated naming patterns
# =========================================================================
def test_regression_diversity_filtering_detects_repeated_naming_patterns():
    # Detect prefix / template repetition in sdk* and agen* clusters
    pool = [
        "agenlux.com", "agenvos.com",
        "sdkura.com", "sdkgrid.com", "sdkloom.com", "sdkwave.com",
        "caldera.com", "meridian.com", "quantumflow.com"
    ]

    analysis = PatternSaturationDetector.analyze_run_saturation(pool)
    cand_sat = analysis["candidate_saturation"]

    # Repetition is detected
    assert cand_sat["sdkura"]["prefix_freq"] == 4
    assert cand_sat["agenlux"]["prefix_freq"] == 2
    assert cand_sat["sdkura"]["pattern_diversity_score"] < 80.0
    assert cand_sat["caldera"]["pattern_diversity_score"] == 100.0

    # Diversity engine retains the strongest representative
    diversity_engine = DiversityEngine()
    candidates = [
        {"domain_name": "agenlux.com", "quality_score": 88, "overall_score": 88.5, "phonetic_cluster_id": "PHON_AJN_LKS", "morphology_type": "INVENTED", "market_category": "AI & Technology"},
        {"domain_name": "agenvos.com", "quality_score": 82, "overall_score": 82.1, "phonetic_cluster_id": "PHON_AJN_VS", "morphology_type": "INVENTED", "market_category": "AI & Technology"},
        {"domain_name": "caldera.com", "quality_score": 92, "overall_score": 92.4, "phonetic_cluster_id": "PHON_KLD_C4", "morphology_type": "ONE_WORD", "market_category": "AI & Technology"}
    ]

    selected = diversity_engine.select_diverse_candidates(candidates, limit=2)
    selected_names = [c["domain_name"] for c in selected]

    # Strongest agen* representative kept, but not multiple low-variety copies
    assert "caldera.com" in selected_names
    assert "agenlux.com" in selected_names
    assert "agenvos.com" not in selected_names
