"""
Comprehensive Automated Test Suite for:
PHASE 1: Quality Engine
PHASE 2: IP / Trademark / Existing Brand Risk Engine

Tests all 16 required capabilities:
1. One-word classification
2. Dictionary detection
3. Syllable extraction
4. Pronunciation scoring
5. Structural filtering
6. Naming strategy classification
7. Quality score calculation
8. Hard vs soft filtering
9. String similarity
10. Phonetic similarity
11. Trademark risk classification
12. Existing brand classification
13. Diversity selection
14. Malformed LLM JSON recovery
15. Provider failure fallback
16. Pipeline continuation after individual candidate failure
"""

import pytest
import asyncio
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

# Phase 1 imports
from quality_engine import (
    QualityFeatureExtractor,
    OneWordQualityEngine,
    NamingTypeClassifier,
    NamingStrategyGenerator,
    QualityScorer,
    AIQualityEvaluator,
    DiversityEngine,
    DEFAULT_QUALITY_WEIGHTS
)

# Phase 2 imports
from risk_engine import (
    TrademarkRiskEngine,
    ExistingBrandEngine,
    NegativeSemanticScreening,
    IPDecisionEngine,
    RiskLevel,
    BrandStatus,
    levenshtein_distance,
    levenshtein_similarity,
    jaro_winkler_similarity,
    soundex,
    metaphone,
    calculate_comprehensive_similarity,
    check_known_brand_collision,
    BrandRiskResult,
    AtomTrademarkClient,
    AtomTrademarkResult
)


from router import ModelRouter

# =========================================================================
# 1. One-Word Classification Test
# =========================================================================
def test_one_word_classification():
    engine = OneWordQualityEngine()
    
    res_real = engine.compute_one_word_score("stride")
    assert res_real["is_one_word"] is True
    assert res_real["word_length"] == 6
    assert res_real["one_word_score"] > 50

    res_compound = engine.compute_one_word_score("cloudnest")
    # 'cloudnest' is a compound, not a single dictionary word
    assert res_compound["is_dictionary_word"] is False or not res_compound["is_one_word"]

    res_gibberish = engine.compute_one_word_score("xqzlyv")
    assert res_gibberish["is_one_word"] is False

# =========================================================================
# 2. Dictionary Detection Test
# =========================================================================
def test_dictionary_detection():
    engine = OneWordQualityEngine()
    
    is_dict, score = engine.is_dictionary_word("beacon")
    assert is_dict is True
    assert score >= 2.5

    is_dict_false, score_false = engine.is_dictionary_word("asdfjklzxcv")
    assert is_dict_false is False
    assert score_false <= 1.0

# =========================================================================
# 3. Syllable Extraction Test
# =========================================================================
def test_syllable_extraction():
    fe = QualityFeatureExtractor()
    assert fe.count_syllables("cloud") == 1
    assert fe.count_syllables("beacon") == 2
    assert fe.count_syllables("autonomous") >= 3
    assert fe.count_syllables("flow") == 1

# =========================================================================
# 4. Pronunciation Scoring Test
# =========================================================================
def test_pronunciation_scoring():
    fe = QualityFeatureExtractor()
    
    # Smooth alternating consonant-vowel word
    pron_good = fe.compute_pronounceability_score("velora")
    assert pron_good >= 80.0

    # Awkward / unpronounceable sequence
    pron_bad = fe.compute_pronounceability_score("xqzlyv")
    assert pron_bad < 30.0

    assert pron_good > pron_bad

# =========================================================================
# 5. Structural Filtering Test
# =========================================================================
def test_structural_filtering():
    fe = QualityFeatureExtractor()
    
    features = fe.extract_features("peakflow.com")
    assert features["char_length"] == 8
    assert features["syllable_count"] == 2
    assert features["vowel_consonant_ratio"] > 0.3
    assert features["passes_hard_filter"] is True
    assert features["spelling_simplicity"] >= 70.0

# =========================================================================
# 6. Naming Strategy Classification Test
# =========================================================================
def test_naming_strategy_classification():
    classifier = NamingTypeClassifier()
    
    c_one = classifier.classify("beacon.com")
    assert c_one["naming_type"] == "ONE_WORD"

    c_prefix = classifier.classify("getpulse.com")
    assert c_prefix["naming_type"] == "PREFIX_SUFFIX"

    c_compound = classifier.classify("cloudnest.com")
    assert c_compound["naming_type"] in ["COMPOUND", "TWO_WORD"]

    c_random = classifier.classify("aaaaaaaa.com")
    assert c_random["naming_type"] == "RANDOM"

# =========================================================================
# 7. Quality Score Calculation Test
# =========================================================================
def test_quality_score_calculation():
    scorer = QualityScorer()
    fe = QualityFeatureExtractor()
    one_engine = OneWordQualityEngine(fe)
    classifier = NamingTypeClassifier(one_engine)

    domain = "peakflow.com"
    struct = fe.extract_features(domain)
    one_eval = one_engine.compute_one_word_score(domain)
    naming = classifier.classify(domain)

    res = scorer.score_candidate(
        domain=domain,
        structural_features=struct,
        one_word_features=one_eval,
        naming_type_info=naming,
        concept="High performance analytics"
    )

    assert "quality_score" in res
    assert 50 <= res["quality_score"] <= 100
    bd = res["quality_breakdown"]
    assert "brandability" in bd
    assert "memorability" in bd
    assert "commercial" in bd
    assert "trend" in bd
    assert "simplicity" in bd

# =========================================================================
# 8. Hard vs Soft Filtering Test
# =========================================================================
def test_hard_vs_soft_filtering():
    fe = QualityFeatureExtractor()

    # Hard rejects
    pass_mash, reason_mash = fe.evaluate_hard_filters("xqzlyv")
    assert pass_mash is False
    assert "pronunciation" in reason_mash or "unpronounceable" in reason_mash or "vowels" in reason_mash

    pass_novowel, reason_novowel = fe.evaluate_hard_filters("bcdfgh")
    assert pass_novowel is False
    assert "no_vowels" in reason_novowel

    pass_rep, reason_rep = fe.evaluate_hard_filters("aaaaaaaa")
    assert pass_rep is False

    pass_digits, reason_digits = fe.evaluate_hard_filters("random123brand")
    assert pass_digits is False

    # Soft scoring: Meaningful 12-letter domain passes hard filter
    pass_long, _ = fe.evaluate_hard_filters("cybercommand")
    assert pass_long is True

# =========================================================================
# 9. String Similarity Test
# =========================================================================
def test_string_similarity():
    sim_identical = levenshtein_similarity("cloudora", "cloudora")
    assert sim_identical == 1.0

    sim_typo = levenshtein_similarity("cloudora", "claudora")
    assert sim_typo >= 0.85

    jw_sim = jaro_winkler_similarity("cloudora", "claudora")
    assert jw_sim >= 0.88

# =========================================================================
# 10. Phonetic Similarity Test
# =========================================================================
def test_phonetic_similarity():
    # Soundex checks
    assert soundex("Smith") == soundex("Smythe")
    
    # Metaphone checks
    meta_cloud = metaphone("cloudora")
    meta_claud = metaphone("claudora")
    # 'cloudora' -> KLTR, 'claudora' -> KLTR
    assert meta_cloud == meta_claud

    comp = calculate_comprehensive_similarity("cloudora", "claudora")
    assert comp["is_phonetic_match"] is True
    assert comp["composite_similarity"] >= 0.85

# =========================================================================
# 11. Trademark Risk Classification Test
# =========================================================================
@pytest.mark.asyncio
async def test_trademark_risk_classification():
    engine = TrademarkRiskEngine()

    # Apple is a famous brand -> Critical Risk
    report_critical = await engine.screen_candidate("apple.com")
    assert report_critical.ip_risk_level == RiskLevel.CRITICAL
    assert report_critical.ip_risk_score >= 80
    assert report_critical.decision == "REJECT"

    # Clean invented domain -> Low Risk
    report_low = await engine.screen_candidate("uniqueneuralmesh99.com")
    assert report_low.ip_risk_level == RiskLevel.LOW
    assert report_low.decision == "PASS"

# =========================================================================
# 12. Existing Brand Classification Test
# =========================================================================
def test_existing_brand_classification():
    brand_engine = ExistingBrandEngine()

    matches = brand_engine.analyze_domain("stripe")
    assert len(matches) > 0
    assert matches[0].brand_status == BrandStatus.FAMOUS_BRAND
    assert matches[0].confidence >= 0.9

    matches_compound = brand_engine.analyze_domain("getstripe")
    assert len(matches_compound) > 0
    assert any(m.brand_name == "stripe" for m in matches_compound)

# =========================================================================
# 13. Diversity Selection Test
# =========================================================================
def test_diversity_selection():
    diversity = DiversityEngine()

    candidates = [
        {"domain": "agentflow.com", "domain_name": "agentflow.com", "quality_score": 92, "naming_type": "COMPOUND"},
        {"domain": "agentforge.com", "domain_name": "agentforge.com", "quality_score": 91, "naming_type": "COMPOUND"},
        {"domain": "flowagent.com", "domain_name": "flowagent.com", "quality_score": 90, "naming_type": "COMPOUND"},
        {"domain": "beacon.com", "domain_name": "beacon.com", "quality_score": 89, "naming_type": "ONE_WORD"},
        {"domain": "velora.com", "domain_name": "velora.com", "quality_score": 88, "naming_type": "INVENTED"},
        {"domain": "stride.com", "domain_name": "stride.com", "quality_score": 87, "naming_type": "ONE_WORD"}
    ]

    selected = diversity.select_diverse_candidates(candidates, limit=4)
    selected_domains = [x["domain"] for x in selected]

    # Must select diverse types and not all 3 agent variants
    assert len(selected) <= 4
    agent_count = sum(1 for d in selected_domains if "agent" in d)
    assert agent_count <= 2

# =========================================================================
# 14. Malformed LLM JSON Recovery Test
# =========================================================================
def test_malformed_llm_json_recovery():
    router = ModelRouter()

    # Case 1: Markdown wrapped JSON
    text1 = "```json\n{\"brandability\": 90, \"memorability\": 88}\n```"
    parsed1 = router.extract_json_safe(text1)
    assert parsed1["brandability"] == 90

    # Case 2: Extra conversational leading/trailing text
    text2 = "Here is the requested output:\n{\"domain\": \"stride.com\", \"score\": 95}\nHope this helps!"
    parsed2 = router.extract_json_safe(text2)
    assert parsed2["domain"] == "stride.com"
    assert parsed2["score"] == 95

# =========================================================================
# 15. Provider Failure Fallback Test
# =========================================================================
@pytest.mark.asyncio
async def test_provider_failure_fallback():
    router = ModelRouter()
    
    # Mock primary provider failing, secondary succeeding
    call_counts = {"primary": 0, "fallback": 0}

    async def mock_req(provider, model, prompt, temp, tokens, req_id, attempt):
        if provider == "xkiro":
            call_counts["primary"] += 1
            raise Exception("503 Service Unavailable")
        elif provider == "nvidia":
            call_counts["fallback"] += 1
            return "{\"success\": true}"
        return "{}"

    with patch.object(router, '_make_request', side_effect=mock_req):
        res = await router.execute_task_json("domain_generation", "test prompt", max_retries=1)
        assert res.get("success") is True
        assert call_counts["primary"] >= 1
        assert call_counts["fallback"] >= 1

# =========================================================================
# 16. Pipeline Continuation After Candidate Failure Test
# =========================================================================
@pytest.mark.asyncio
async def test_pipeline_continuation_after_candidate_failure():
    # If one candidate throws a processing/screening error, pipeline must continue
    engine = TrademarkRiskEngine()

    # Intentionally test bad / extreme candidate inputs
    candidates = ["validbrand.com", None, "", "anothergoodbrand.com"]
    passed_reports = []

    for c in candidates:
        try:
            if not c:
                continue
            rep = await engine.screen_candidate(c)
            passed_reports.append(rep)
        except Exception as e:
            # Candidate error isolated
            pass

    assert len(passed_reports) == 2
    assert passed_reports[0].domain == "validbrand.com"
    assert passed_reports[1].domain == "anothergoodbrand.com"


# =========================================================================
# PHASE 1: BRAND & TRADEMARK COLLISION DETECTION TESTS (Tasks A, B, C, D)
# =========================================================================

def test_brand_collision_critical_same_vertical():
    """1. 'citadelpact' + category=finance -> CRITICAL risk level."""
    res = check_known_brand_collision("citadelpact.com", category="finance")
    assert res.status == "HIT"
    assert res.risk_level == RiskLevel.CRITICAL
    assert res.matched_brand == "Citadel"
    assert res.matched_alias == "citadel"
    assert res.vertical_match is True
    assert "CRITICAL" in res.reason


def test_brand_collision_high_different_vertical():
    """2. Same brand match, different vertical -> HIGH not CRITICAL."""
    res = check_known_brand_collision("citadelpact.com", category="travel_hospitality")
    assert res.status == "HIT"
    assert res.risk_level == RiskLevel.HIGH
    assert res.risk_level != RiskLevel.CRITICAL
    assert res.matched_brand == "Citadel"
    assert res.matched_alias == "citadel"
    assert res.vertical_match is False
    assert "HIGH" in res.reason


def test_docker_collision():
    """3. 'dockterm' -> HIGH or CRITICAL."""
    res = check_known_brand_collision("dockterm.com", category="devtools")
    assert res.status == "HIT"
    assert res.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
    assert res.matched_brand == "Docker"
    assert res.matched_alias in ["dock", "dockterm"]


def test_tether_collision_both_variants():
    """4. 'stilltether' and 'cleartether' both flagged."""
    res_still = check_known_brand_collision("stilltether.com", category="crypto_web3")
    assert res_still.status == "HIT"
    assert res_still.matched_brand == "Tether"
    assert res_still.matched_alias == "tether"
    assert res_still.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]

    res_clear = check_known_brand_collision("cleartether.com", category="crypto_web3")
    assert res_clear.status == "HIT"
    assert res_clear.matched_brand == "Tether"
    assert res_clear.matched_alias == "tether"
    assert res_clear.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]


def test_no_false_positive_common_word():
    """5. Legitimate real-export candidates with no actual brand overlap pass unaffected."""
    for candidate in ["bindrule.com", "firmclause.com"]:
        res = check_known_brand_collision(candidate, category="legal_b2b")
        assert res.status == "NO_MATCH"
        assert res.risk_level is None
        assert res.matched_brand is None
        assert res.matched_alias is None


@pytest.mark.asyncio
async def test_atom_missing_key_returns_not_checked():
    """6. No ATOM_TRADEMARK_API_KEY set -> search_trademark() returns NOT_CHECKED, no network call attempted."""
    mock_http_client = MagicMock()
    mock_http_client.get = AsyncMock()

    client = AtomTrademarkClient(api_key="", client=mock_http_client)
    res = await client.search_trademark("anycandidate.com")

    assert res.status == "NOT_CHECKED"
    assert res.risk_level is None
    # Confirm via mock that HTTP client was never invoked
    mock_http_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_atom_timeout_returns_error_gracefully():
    """7. Mocked timeout -> status='ERROR', pipeline continues without raising."""
    mock_http_client = MagicMock()
    mock_http_client.get = AsyncMock(side_effect=httpx.TimeoutException("Mocked connection timeout"))

    client = AtomTrademarkClient(api_key="mock_test_key", client=mock_http_client)
    res = await client.search_trademark("timeouttest.com")

    assert res.status == "ERROR"
    assert res.risk_level is None
    assert "timeout" in res.reason.lower()


@pytest.mark.asyncio
async def test_atom_hit_escalates_risk():
    """8. Mocked 'HIT' response -> final combined risk_level reflects it appropriately."""
    mock_http_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "hit": True,
        "matches": [
            {"mark": "VentureFlow", "similarity": 0.88, "status": "REGISTERED"}
        ]
    }
    mock_http_client.get = AsyncMock(return_value=mock_response)

    atom_client = AtomTrademarkClient(api_key="mock_test_key", client=mock_http_client)
    res = await atom_client.search_trademark("ventureflow.com")

    assert res.status == "HIT"
    assert res.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
    assert len(res.raw_matches) == 1

    # Verify when integrated in TrademarkRiskEngine, combined risk reflects the Atom HIT
    mock_uspto = AsyncMock()
    mock_uspto.name = "uspto_official_api"
    mock_uspto.search.return_value = [] # USPTO returns clear (LOW)

    engine = TrademarkRiskEngine(providers=[mock_uspto], atom_client=atom_client)
    report = await engine.screen_candidate("ventureflow.com", category_context="b2b_tools")

    assert report.ip_risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
    assert "atom" in report.contributing_sources
    assert any("Atom trademark collision" in ev for ev in report.evidence)


@pytest.mark.asyncio
async def test_combined_risk_takes_highest_across_sources():
    """9. Scenario where USPTO says LOW, known_brands says NOT_CHECKED (no match), Atom says HIGH -> final result is HIGH, evidence contains Atom reason."""
    mock_uspto = AsyncMock()
    mock_uspto.name = "uspto_official_api"
    mock_uspto.search.return_value = [] # USPTO says LOW

    mock_atom_client = MagicMock()
    mock_atom_client.search_trademark = AsyncMock(return_value=AtomTrademarkResult(
        status="HIT",
        risk_level=RiskLevel.HIGH,
        raw_matches=[{"mark": "SomeMark", "similarity": 0.85}],
        reason="Atom trademark collision: 1 conflicting mark(s) found"
    ))

    engine = TrademarkRiskEngine(
        providers=[mock_uspto],
        atom_client=mock_atom_client,
        known_brands_data=[] # empty so known_brands check returns NO_MATCH
    )

    report = await engine.screen_candidate("unknownbrandxyz.com", category_context="b2b_tools")

    assert report.ip_risk_level == RiskLevel.HIGH
    assert "atom" in report.contributing_sources
    assert any("Atom trademark collision" in ev for ev in report.evidence)
    assert report.sources["uspto"]["risk_level"] == "LOW"
    assert report.sources["atom"]["risk_level"] == "HIGH"
    assert report.sources["known_brands"]["status"] == "NO_MATCH"

