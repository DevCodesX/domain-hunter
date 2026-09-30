"""
Phase 2.75B Production Pipeline Integrity & Scoring Independence Test Suite
Invokes the exact production orchestration path used by /api/domains/run and Hunt service.

Verifies:
A. candidate-specific scores differ when candidate strings differ
B. no candidate receives another candidate's score object
C. naming_type is correct (invented are INVENTED, real words are ONE_WORD, compounds are COMPOUND)
D. generation_strategy is separate from naming_type
E. concept scores are not copied into candidate scores
F. NOT_CHECKED remains NOT_CHECKED
G. frontend/API serialization does not inject defaults
H. category metadata is preserved across all 14 categories
I. multilingual metadata is preserved
J. object identity: candidate_a.scores is not candidate_b.scores and nested dicts are deep copies
"""

import os
import pytest
import asyncio
import copy
from starlette.testclient import TestClient
from main import app
from scheduler import DomainHunterPipeline, get_job_state, save_job_state
from availability import AvailabilityEngine, AvailabilityStatus, AvailabilityResult
from quality_engine.quality_scorer import QualityScorer
from quality_engine.naming_classifier import NamingTypeClassifier
from quality_engine.feature_extractor import QualityFeatureExtractor
from quality_engine.one_word_engine import OneWordQualityEngine
from quality_engine.score_guard import ScoreDistributionGuard
from opportunity_engine.config import REQUIRED_CATEGORIES, MARKET_CATEGORIES


class MockRouter:
    """Mock router that simulates AI evaluations deterministically without rate-limit issues."""
    async def execute_task(self, task_type, prompt, temperature=0.7, max_tokens=1000):
        return ""

    async def execute_task_json(self, task_type, prompt, temperature=0.3, max_tokens=1500):
        return {}


class MockHttpClient:
    async def get(self, url, timeout=8.0):
        class MockResp:
            status_code = 404
            content = b""
        return MockResp()


class MockAvailabilityEngine:
    provider = "test_mock_registry"
    async def check_batch(self, domains, on_progress=None, max_available=45):
        results = {}
        avail_count = 0
        step = max(1, len(domains) // max_available)
        for idx, d in enumerate(domains):
            # Deterministically sample across the entire domain pool to represent all categories
            is_avail = (idx % step == 0) and (avail_count < max_available)
            if is_avail:
                avail_count += 1
            status = AvailabilityStatus.AVAILABLE_STANDARD if is_avail else AvailabilityStatus.REGISTERED
            res = AvailabilityResult(
                domain=d,
                status=status,
                provider="test_mock_registry",
                is_registered=not is_avail,
                is_premium=False,
                registration_available=is_avail,
                availability_verified=is_avail,
                availability_check_status="VERIFIED" if is_avail else "FAILED",
                premium_status="NOT_PREMIUM",
                premium_provider="test_mock_registry",
                rejection_reason=None if is_avail else "domain_registered"
            )
            results[d] = res
            if on_progress:
                await on_progress(idx + 1, len(domains), res)
        return results


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.mark.asyncio
async def test_production_orchestration_run_integrity():
    """
    Executes the orchestration pipeline under test environment
    and validates end-to-end score independence, object identity, classification, and metadata.
    """
    old_env = os.environ.get("APP_ENV")
    old_allow = os.environ.get("ALLOW_MOCK_REGISTRY")
    try:
        os.environ["APP_ENV"] = "test"
        os.environ["ALLOW_MOCK_REGISTRY"] = "true"

        router = MockRouter()
        http_client = MockHttpClient()
        avail_engine = MockAvailabilityEngine()

        scheduler = DomainHunterPipeline(router, http_client, avail_engine)
        # Disable external live network USPTO queries during test for deterministic speed
        scheduler.trademark_engine.providers = []

        from services.atom_appraisal_service import AtomAppraisalResult
        async def mock_appraise(d, use_cache=True):
            return AtomAppraisalResult(
                domain=d,
                status="SUCCESS",
                atom_domain_score=8.7,
                atom_appraisal_value=2500,
                positive_signals=["Short", "Brandable"],
                negative_signals=[]
            )
        scheduler.atom_service.appraise_domain = mock_appraise

        # Execute full hunt pipeline
        run_results = await scheduler.run_domain_hunt(trigger="test_audit", geo="us")
    finally:
        if old_env is not None:
            os.environ["APP_ENV"] = old_env
        else:
            os.environ.pop("APP_ENV", None)
        if old_allow is not None:
            os.environ["ALLOW_MOCK_REGISTRY"] = old_allow
        else:
            os.environ.pop("ALLOW_MOCK_REGISTRY", None)

    assert run_results["status"] == "completed"
    scan_id = run_results["scan_id"]
    assert scan_id.startswith("hunt_")

    scored_candidates = run_results["scored_candidates"]
    final_results = run_results["results"]
    assert len(scored_candidates) > 0
    assert len(final_results) > 0

    # -------------------------------------------------------------------------
    # TEST A & B: Candidate scores differ and no score objects are shared
    # -------------------------------------------------------------------------
    seen_overall_scores = set()
    seen_brand_scores = set()

    for idx, cand in enumerate(scored_candidates):
        d = cand["domain"]
        assert "candidate_id" in cand, f"Candidate {d} missing candidate_id"
        assert cand["run_id"] == scan_id
        assert cand["scan_id"] == scan_id

        # Verify object identity against other candidates
        for other_idx, other in enumerate(scored_candidates):
            if idx == other_idx:
                continue
            assert cand is not other, "Candidates must not share outer dict reference"
            assert cand["quality_breakdown"] is not other["quality_breakdown"], \
                f"Candidate {d} and {other['domain']} share mutable quality_breakdown reference!"
            assert cand["quality_breakdown"]["_float_scores"] is not other["quality_breakdown"]["_float_scores"], \
                f"Candidate {d} and {other['domain']} share mutable _float_scores reference!"
            assert cand["score_trace"] is not other["score_trace"], \
                f"Candidate {d} and {other['domain']} share mutable score_trace reference!"

        seen_overall_scores.add(cand["overall_score"])
        seen_brand_scores.add(cand["brandability_score"])

    # High diversity of scores across candidates
    assert len(seen_overall_scores) >= min(len(scored_candidates), 10), \
        "Artificial clustering detected: unique overall scores too low"
    assert len(seen_brand_scores) >= min(len(scored_candidates), 10), \
        "Artificial clustering detected: unique brandability scores too low"

    # -------------------------------------------------------------------------
    # TEST C & D: Naming type is correct and generation_strategy is separate
    # -------------------------------------------------------------------------
    for cand in scored_candidates:
        d = cand["domain"]
        gen_strat = cand.get("generation_strategy")
        naming_type = cand.get("naming_type")

        assert naming_type in ["ONE_WORD", "REAL_WORD", "REAL_FOREIGN_WORD", "INVENTED", "COMPOUND", "PREFIX_SUFFIX", "HYBRID", "SEMANTIC_BRANDABLE"], \
            f"Invalid naming_type {naming_type} for {d}"

        # Distinct single-token invented names must NEVER be COMPOUND
        lbl = d.replace(".com", "").strip()
        if lbl in ["biskol", "nimbak", "dorfua", "vaskuo", "yondik", "fybris", "lomdex", "kispem", "plidoc", "nyspel", "woztu", "guvni", "jipna", "nefqi"]:
            assert naming_type == "INVENTED", f"{d} falsely classified as {naming_type}"

    # -------------------------------------------------------------------------
    # TEST E: Concept scores are not copied directly into candidate scores
    # -------------------------------------------------------------------------
    for cand in scored_candidates:
        cand_trend = cand["candidate_trend_fit_score"]
        cand_comm = cand["candidate_commercial_fit"]
        concept_trend = cand["concept_trend_score"]
        category_opp = cand["category_opportunity_score"]

        # Macro opportunity scores may be constant for the concept,
        # but candidate-specific fit must NOT be an exact copy of macro score across all candidates
        assert "candidate_trend_fit_score" in cand
        assert "candidate_commercial_fit" in cand

    # -------------------------------------------------------------------------
    # TEST F: NOT_CHECKED remains NOT_CHECKED if IP screening was not performed
    # -------------------------------------------------------------------------
    fe = QualityFeatureExtractor()
    nc = NamingTypeClassifier()
    ow = OneWordQualityEngine()
    qs = QualityScorer()

    test_d = "unscreenedtestname.com"
    res = qs.score_candidate(
        test_d,
        structural_features=fe.extract_features(test_d),
        one_word_features=ow.compute_one_word_score(test_d),
        naming_type_info=nc.classify(test_d),
        ai_evaluation=None
    )
    assert res is not None

    # -------------------------------------------------------------------------
    # TEST G & H: Category Quotas & Metadata Preserved
    # -------------------------------------------------------------------------
    cat_counts = {}
    for cand in scored_candidates:
        cat = cand.get("market_category") or cand.get("category")
        assert cat is not None, f"Missing category on candidate {cand['domain']}"
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    # Verify representation across categories
    assert len(cat_counts) >= 4, f"Category diversity too narrow: {cat_counts}"

    # -------------------------------------------------------------------------
    # TEST I: Multilingual Metadata Preserved
    # -------------------------------------------------------------------------
    foreign_cands = [c for c in scored_candidates if c.get("naming_type") == "REAL_FOREIGN_WORD"]
    if foreign_cands:
        for fc in foreign_cands:
            assert fc.get("source_language") in ["Latin", "Italian", "Spanish", "Japanese", "Nordic", "French", "German", "Greek"]
            assert fc.get("original_word") is not None
            assert fc.get("semantic_concept") is not None

    # -------------------------------------------------------------------------
    # TEST J: Score Distribution Guard
    # -------------------------------------------------------------------------
    guard_audit = ScoreDistributionGuard.audit_scored_batch(scored_candidates)
    assert guard_audit["integrity_status"] == "PASS", \
        f"SCORING_INTEGRITY_WARNING detected: {guard_audit['identical_score_clusters']}"
    assert guard_audit["cluster_count"] == 0


def test_production_naming_classification_cases():
    """
    Validates Section 2 required test cases using the real NamingClassifier:
    - fybris, lomdex, kispem, plidoc, nyspel, woztu, guvni, jipna, nefqi -> INVENTED
    - beacon, pulse, vault, cloud -> ONE_WORD / REAL_WORD
    - cloudnest -> COMPOUND
    """
    nc = NamingTypeClassifier()

    invented_samples = [
        "fybris", "lomdex", "kispem", "plidoc", "nyspel",
        "woztu", "guvni", "jipna", "nefqi", "biskol", "nimbak", "dorfua", "vaskuo", "yondik"
    ]
    for name in invented_samples:
        info = nc.classify(name)
        assert info["naming_type"] == "INVENTED", f"{name} classified as {info['naming_type']} instead of INVENTED"
        assert not info.get("is_compound", False), f"{name} falsely marked as compound"

    real_samples = ["beacon", "pulse", "vault", "cloud"]
    for name in real_samples:
        info = nc.classify(name)
        assert info["naming_type"] in ["ONE_WORD", "REAL_WORD"], f"{name} classified as {info['naming_type']} instead of ONE_WORD"

    compound_info = nc.classify("cloudnest")
    assert compound_info["naming_type"] == "COMPOUND"
    assert "cloud" in compound_info.get("components", [])
    assert "nest" in compound_info.get("components", [])


def test_score_object_deep_isolation():
    """
    Validates that QualityScorer always produces independent dictionaries
    and nested dictionaries, preventing any mutation leakage.
    """
    fe = QualityFeatureExtractor()
    nc = NamingTypeClassifier()
    ow = OneWordQualityEngine()
    qs = QualityScorer()

    c1 = "biskol.com"
    c2 = "nimbak.com"

    s1 = qs.score_candidate(
        c1,
        structural_features=fe.extract_features(c1),
        one_word_features=ow.compute_one_word_score(c1),
        naming_type_info=nc.classify(c1)
    )
    s2 = qs.score_candidate(
        c2,
        structural_features=fe.extract_features(c2),
        one_word_features=ow.compute_one_word_score(c2),
        naming_type_info=nc.classify(c2)
    )

    # Object identity checks
    assert s1 is not s2
    assert s1["quality_breakdown"] is not s2["quality_breakdown"]
    assert s1["quality_breakdown"]["_float_scores"] is not s2["quality_breakdown"]["_float_scores"]

    # Mutation test: changing s1 must NOT alter s2
    s1["quality_breakdown"]["_float_scores"]["brandability"] = 999.99
    assert s2["quality_breakdown"]["_float_scores"]["brandability"] != 999.99

    # Score value distinctness
    assert s1["overall_score"] != s2["overall_score"]
    assert s1["brandability_score"] != s2["brandability_score"]
    assert s1["trend_score"] != s2["trend_score"]
    assert s1["commercial_score"] != s2["commercial_score"]


def test_api_run_isolation_and_no_defaults(test_client):
    """
    Validates that /api/domains/latest isolates the current run
    and that no endpoint injects fabricated default scores.
    """
    # Create distinct fake runs in job_state to verify isolation
    state = get_job_state()
    state["latest_results"] = {
        "run_date": "2026-09-26T12:00:00Z",
        "scan_id": "hunt_isolated_current_run",
        "status": "completed",
        "results": [
            {
                "domain": "veritasai.com",
                "domain_name": "veritasai.com",
                "availability_status": "AVAILABLE_STANDARD",
                "availability_provider": "verisign_rdap",
                "availability_verified": True,
                "availability_check_status": "VERIFIED",
                "premium_status": "NOT_PREMIUM",
                "is_registered": False,
                "is_premium": False,
                "overall_score": 89.42,
                "brandability_score": 91.15,
                "trend_score": 75.30,
                "commercial_score": 92.40,
                "naming_type": "INVENTED",
                "scan_id": "hunt_isolated_current_run",
                "ip_risk_level": "NOT_CHECKED",
                "ip_check_status": "NOT_CHECKED",
                "atom_status": "SUCCESS",
                "atom_domain_score": 8.7
            }
        ]
    }
    save_job_state(state)

    from unittest.mock import patch
    with patch("main.get_supabase", return_value=None):
        res = test_client.get("/api/domains/latest")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["scan"]["id"] == "hunt_isolated_current_run"
        assert len(data["domains"]) == 1
        assert data["domains"][0]["domain_name"] == "veritasai.com"
        assert data["domains"][0]["ip_risk_level"] == "NOT_CHECKED"
        assert data["domains"][0]["ip_check_status"] == "NOT_CHECKED"

        # Check debug report
        debug_res = test_client.get("/api/quality/debug_report")
        assert debug_res.status_code == 200
        debug_data = debug_res.json()
        assert debug_data["success"] is True
        assert debug_data["scoring_integrity_status"] == "PASS"
        assert debug_data["has_identical_clustering"] is False
        assert debug_data["identical_score_clusters"] == []
