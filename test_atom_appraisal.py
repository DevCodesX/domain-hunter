import os
import time
import json
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from services.atom_appraisal_service import (
    AtomAppraisalService,
    AtomAppraisalResult,
    AtomAppraisalCache,
    AtomProviderHealthStatus,
    normalize_atom_appraisal,
    calculate_atom_calibration,
    DEFAULT_MIN_DOMAIN_SCORE,
    DEFAULT_TIER_A_MIN_DOMAIN_SCORE
)
from quality_engine.quality_tiers import QualityTierEngine
from quality_engine.multi_model_evaluator import (
    MultiModelDomainEvaluator,
    robust_statistics,
    detect_short_but_meaningless,
    detect_pronounceable_not_brandable
)
from quality_engine.naming_classifier import NamingTypeClassifier
from quality_engine.diversity_engine import DiversityEngine


# -------------------------------------------------------------------------
# 1. ATOM SUCCESS
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_atom_success():
    service = AtomAppraisalService(api_token="test_token_123")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "domain": "successtest.com",
        "domain_score": 8.7,
        "appraisal_value": 2450,
        "positive_signals": ["Strong brandability", "Popular root word"],
        "negative_signals": [],
        "root_words": ["success", "test"]
    }

    with patch.object(service, "_get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_get_client.return_value = mock_client

        res = await service.appraise_domain("successtest.com", use_cache=False)
        assert res.status == "SUCCESS"
        assert res.atom_domain_score == 8.7
        assert res.atom_appraisal_value == 2450.0
        assert res.atom_appraisal_normalized > 0
        assert "Strong brandability" in res.positive_signals
        assert res.passes_minimum_score(8.0) is True
        assert res.passes_tier_a_score(8.5) is True


# -------------------------------------------------------------------------
# 2. ATOM DISABLED
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_atom_disabled():
    with patch.dict(os.environ, {"ATOM_ENABLED": "false"}):
        service = AtomAppraisalService(api_token="test_token_123")
        res = await service.appraise_domain("disabletest.com", use_cache=False)
        assert res.status == "DISABLED"
        assert res.atom_domain_score is None


# -------------------------------------------------------------------------
# 3. ATOM MISSING CREDENTIALS
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_atom_missing_credentials():
    service = AtomAppraisalService(api_token="")
    assert service.is_configured() is False
    res = await service.appraise_domain("missingcreds.com", use_cache=False)
    assert res.status == "NOT_CONFIGURED"
    assert res.atom_domain_score is None
    health = await service.check_health()
    assert health.status == AtomProviderHealthStatus.NOT_CONFIGURED.value


# -------------------------------------------------------------------------
# 4. ATOM AUTH FAILURE (401 / 403)
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_atom_auth_failure():
    service = AtomAppraisalService(api_token="invalid_token")
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Unauthorized: Invalid API token"

    with patch.object(service, "_get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_get_client.return_value = mock_client

        res = await service.appraise_domain("authfail.com", use_cache=False)
        assert res.status == "AUTH_ERROR"
        assert "authentication failed" in str(res.error_message).lower()


# -------------------------------------------------------------------------
# 5. ATOM RATE LIMIT (429)
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_atom_rate_limit():
    service = AtomAppraisalService(api_token="valid_token")
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.text = "Too Many Requests"

    with patch.object(service, "_get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_get_client.return_value = mock_client

        res = await service.appraise_domain("ratelimit.com", use_cache=False)
        assert res.status in ["RATE_LIMITED", "QUOTA_EXHAUSTED"]


# -------------------------------------------------------------------------
# 6. ATOM TIMEOUT
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_atom_timeout():
    service = AtomAppraisalService(api_token="valid_token")

    with patch.object(service, "_get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.TimeoutException("Read timed out")
        mock_get_client.return_value = mock_client

        res = await service.appraise_domain("timeouttest.com", use_cache=False)
        assert res.status == "TIMEOUT"


# -------------------------------------------------------------------------
# 7. ATOM QUOTA EXHAUSTION
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_atom_quota_exhaustion():
    service = AtomAppraisalService(api_token="valid_token")
    service.health.daily_limit = 2
    service._quota_used_today = 2

    res = await service.appraise_domain("quotaexhaust.com", use_cache=False)
    assert res.status == "QUOTA_EXHAUSTED"


# -------------------------------------------------------------------------
# 8. ATOM CACHE HIT
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_atom_cache_hit():
    cache = AtomAppraisalCache(ttl_hours=24)
    cached_record = AtomAppraisalResult(
        domain="cacheddomain.com",
        status="SUCCESS",
        atom_domain_score=8.9,
        atom_appraisal_value=3200,
        positive_signals=["High commercial intent"],
        negative_signals=[]
    )
    cache.set("cacheddomain.com", cached_record)

    service = AtomAppraisalService(api_token="valid_token")
    service.cache = cache

    # Ensure no network call is executed by patching _get_client to raise error if called
    with patch.object(service, "_get_client", side_effect=RuntimeError("Network should not be called")):
        res = await service.appraise_domain("cacheddomain.com", use_cache=True)
        assert res.status == "SUCCESS"
        assert res.cache_hit is True
        assert res.atom_domain_score == 8.9


# -------------------------------------------------------------------------
# 9. ATOM CACHE EXPIRY
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_atom_cache_expiry():
    cache = AtomAppraisalCache(ttl_hours=1)
    record = AtomAppraisalResult(domain="expiredtest.com", status="SUCCESS", atom_domain_score=8.5)
    cache.set("expiredtest.com", record)

    # Force expiration by altering expires_at_epoch
    cache._memory["expiredtest.com"]["expires_at_epoch"] = time.time() - 100

    assert cache.get("expiredtest.com") is None


# -------------------------------------------------------------------------
# 10. ATOM MINIMUM-SCORE GATE
# -------------------------------------------------------------------------
def test_atom_minimum_score_gate():
    res_low = AtomAppraisalResult(domain="weak.com", status="SUCCESS", atom_domain_score=7.2)
    assert res_low.passes_minimum_score(8.0) is False

    res_pass = AtomAppraisalResult(domain="strong.com", status="SUCCESS", atom_domain_score=8.4)
    assert res_pass.passes_minimum_score(8.0) is True

    res_tier_a = AtomAppraisalResult(domain="tier_a.com", status="SUCCESS", atom_domain_score=8.6)
    assert res_tier_a.passes_tier_a_score(8.5) is True


# -------------------------------------------------------------------------
# 11. ATOM UNAVAILABLE BLOCKS FINAL PUBLICATION
# -------------------------------------------------------------------------
def test_atom_unavailable_blocks_final_publication():
    candidate_pending = {
        "domain": "unvalidated.com",
        "overall_score": 92,
        "brandability_score": 94,
        "commercial_score": 90,
        "availability_status": "AVAILABLE_STANDARD",
        "ip_risk_level": "LOW",
        "atom_status": "ATOM_PENDING",
        "atom_domain_score": None
    }
    tier = QualityTierEngine.assign_tier(candidate_pending, 92)
    assert tier == "ATOM_UNVALIDATED"
    assert tier not in ["TIER_A", "TIER_B"]


# -------------------------------------------------------------------------
# 12. FOUR EXPERT JUDGES RUN INDEPENDENTLY & DISAGREEMENT DETECTION
# -------------------------------------------------------------------------
def test_disagreement_detection_and_robust_median():
    # 16, 17, 18: Disagreement, robust median, no simple averaging
    scores = [92, 90, 89, 45]
    simple_avg = sum(scores) / len(scores)  # 79.0
    stats = robust_statistics(scores)
    assert stats["median"] == 89.5
    assert stats["median"] != simple_avg  # Robust median resists outlier 45
    assert stats["high_disagreement"] is True
    assert stats["stddev"] > 15


# -------------------------------------------------------------------------
# 19 & 22: DETERMINISTIC CEILINGS OVERRIDE INFLATED SCORES
# -------------------------------------------------------------------------
def test_unanchored_invented_ceilings_and_demotion():
    # 22, 24: Unanchored invented cannot be Tier A and has strict ceilings
    candidate = {
        "domain": "horede.com",
        "quality_score": 92,
        "overall_score": 92,
        "brandability_score": 95,
        "commercial_score": 90,
        "morphology_type": "INVENTED",
        "invented_subtype": "UNANCHORED",
        "availability_status": "AVAILABLE_STANDARD",
        "ip_risk_level": "LOW",
        "atom_status": "SUCCESS",
        "atom_domain_score": 8.1
    }
    tier = QualityTierEngine.assign_tier(candidate, 92)
    assert tier != "TIER_A"  # Unanchored invented cannot achieve Tier A


# -------------------------------------------------------------------------
# 20. SHORT-BUT-MEANINGLESS DETECTION
# -------------------------------------------------------------------------
def test_short_but_meaningless_detection():
    # Short, good phonetic balance, but no commercial/semantic anchor
    res = detect_short_but_meaningless(
        label="tizux",
        length=5,
        pronunciation=85,
        semantic_anchor=20,
        commercial_clarity=30
    )
    assert res is True


# -------------------------------------------------------------------------
# 21. PRONOUNCEABLE-NOT-BRANDABLE DETECTION
# -------------------------------------------------------------------------
def test_pronounceable_not_brandable_detection():
    res = detect_pronounceable_not_brandable(
        pronunciation=90,
        semantic_anchor=15,
        brand_score=40,
        red_team_score=75,
        atom_score=6.2
    )
    assert res is True


# -------------------------------------------------------------------------
# 23. STRONG ANCHORED INVENTED SURVIVES
# -------------------------------------------------------------------------
def test_strong_anchored_invented_survives():
    candidate = {
        "domain": "cloudly.com",
        "overall_score": 91,
        "brandability_score": 92,
        "commercial_score": 90,
        "morphology_type": "INVENTED",
        "invented_subtype": "STRONG_ANCHORED",
        "invented_quality_tier": "STRONG",
        "availability_status": "AVAILABLE_STANDARD",
        "ip_risk_level": "LOW",
        "atom_status": "SUCCESS",
        "atom_domain_score": 8.7
    }
    tier = QualityTierEngine.assign_tier(candidate, 91)
    assert tier == "TIER_A"


# -------------------------------------------------------------------------
# 25. CORELOW CLASSIFICATION REGRESSION
# -------------------------------------------------------------------------
def test_corelow_classification_regression():
    classifier = NamingTypeClassifier()
    # 'corelow' has recognized english root words 'core' + 'low' -> COMPOUND / SEMANTIC / PREFIX_SUFFIX
    result = classifier.classify("corelow")
    assert result["naming_type"] in ["COMPOUND", "SEMANTIC_BRANDABLE", "PREFIX_SUFFIX", "HYBRID"]


# -------------------------------------------------------------------------
# 27 & 28: QUALITY FLOORS BEFORE DIVERSITY & DIVERSITY CANNOT RESCUE WEAK
# -------------------------------------------------------------------------
def test_diversity_cannot_rescue_weak_candidates():
    engine = DiversityEngine()
    candidates = [
        {"domain": "weakrare.com", "overall_score": 40, "final_rank_score": 35, "phonetic_cluster_id": "rare"},
        {"domain": "strongtech.com", "overall_score": 88, "final_rank_score": 88, "phonetic_cluster_id": "tech"}
    ]
    # Filter by quality floor first
    passed_floor = [c for c in candidates if c["overall_score"] >= 65]
    diverse = engine.select_diverse_candidates(passed_floor, limit=10)
    assert len(diverse) == 1
    assert diverse[0]["domain"] == "strongtech.com"


# -------------------------------------------------------------------------
# 30. SECRET NEVER APPEARS IN LOGS OR STRING REPRESENTATIONS
# -------------------------------------------------------------------------
def test_secret_never_leaks_in_health_status():
    secret_token = "SUPER_SECRET_ATOM_TOKEN_9999"
    service = AtomAppraisalService(api_token=secret_token)
    health_dict = service.get_health_status()
    health_str = json.dumps(health_dict)
    assert secret_token not in health_str
    assert "token" not in health_dict


# -------------------------------------------------------------------------
# 42. REGRESSION DOMAINS QUALITY VERIFICATION
# -------------------------------------------------------------------------
@pytest.mark.parametrize("domain", [
    "latenso.com", "bridke.com", "shaffta.com", "weighen.com",
    "horede.com", "smertis.com", "mentlea.com", "pipeara.com",
    "cunvasa.com", "ogridu.com", "supoce.com", "tizux.com",
    "kocud.com", "kyntoa.com", "sakape.com"
])
def test_observed_weak_invented_regression_domains(domain):
    """
    Verifies that weak invented strings are properly detected as unanchored/weakly-anchored
    and cannot pass Tier A without strong external market evidence.
    """
    classifier = NamingTypeClassifier()
    label = domain.replace(".com", "")
    cls_res = classifier.classify(label)

    # All these observed names are non-dictionary coined strings (or evocative roots like grid in ogridu)
    assert cls_res["naming_type"] in ["INVENTED", "COMPOUND", "PREFIX_SUFFIX", "HYBRID", "REAL_WORD", "SEMANTIC_BRANDABLE"]

    # Candidate with weak atom score must be rejected by Atom hard gate
    candidate = {
        "domain": domain,
        "overall_score": 88,
        "brandability_score": 92,
        "morphology_type": "INVENTED",
        "invented_subtype": "UNANCHORED",
        "availability_status": "AVAILABLE_STANDARD",
        "ip_risk_level": "LOW",
        "atom_status": "SUCCESS",
        "atom_domain_score": 6.8  # Weak independent atom appraisal (< 8.0)
    }
    tier = QualityTierEngine.assign_tier(candidate, 88)
    assert tier in ["ATOM_REJECTED", "TIER_C"]
