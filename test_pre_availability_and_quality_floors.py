"""
Domain Hunter - Test Suite: Pre-Availability Ranking, Dynamic Batching & Tier A Quality Floors
=============================================================================================
Tests:
1. Pre-availability scoring calculates zero-external-API scores properly for all morphologies.
2. Stratified selection respects the 7 category diversity quotas without single-strategy flooding.
3. Unanchored weak gibberish is placed at the end of the scan queue, preserving registry quota.
4. Tier A Quality Floor: Pronunciation floor (< 65.0) prevents high score from entering Tier A.
5. Tier A Quality Floor: Hear-to-spell floor (< 60.0) prevents high score from entering Tier A.
6. Tier A Quality Floor: Commercial naturalness floor (< 65.0) prevents high score from entering Tier A.
7. Tier A Quality Floor: Brandability floor (< 70.0) prevents high score from entering Tier A.
8. Tier A Quality Floor: Clean candidate meeting all floors successfully enters Tier A.
9. Dynamic Batched Availability Scanning checks the entire batch without premature cutoff at 45.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from quality_engine.pre_availability import (
    calculate_pre_availability_score,
    rank_and_stratify_candidates
)
from quality_engine.quality_tiers import QualityTierEngine
from quality_engine.invented_quality import (
    get_availability_pipeline_config,
    get_tier_a_floors_config
)
from availability import AvailabilityEngine, AvailabilityStatus, AvailabilityResult


# =========================================================================
# TEST 1: Pre-availability score calculation (Zero External Calls)
# =========================================================================
def test_pre_availability_score_calculation():
    # 1. ONE_WORD / REAL_WORD
    cand_real = {
        "domain": "cloud.com",
        "naming_type": "ONE_WORD",
        "generation_strategy": "ONE_WORD",
        "one_word_features": {"real_word_score": 95.0, "zipf_frequency": 5.2},
        "structural_features": {"label": "cloud", "pronounceability_score": 90.0, "spelling_simplicity": 95.0}
    }
    score_real = calculate_pre_availability_score(cand_real)
    assert score_real >= 85.0, f"Expected high score for real common word, got {score_real}"

    # 2. INVENTED ANCHORED (kinetoc)
    cand_anchored = {
        "domain": "kinetoc.com",
        "naming_type": "INVENTED",
        "generation_strategy": "INVENTED",
        "structural_features": {"label": "kinetoc"}
    }
    score_anchored = calculate_pre_availability_score(cand_anchored)
    assert score_anchored >= 75.0, f"Expected strong score for anchored invented, got {score_anchored}"
    assert cand_anchored.get("invented_subtype") in ["HYBRID_ANCHORED", "LEXICAL_ANCHORED"]

    # 3. INVENTED UNANCHORED GIBBERISH (tusokn)
    cand_gibberish = {
        "domain": "tusokn.com",
        "naming_type": "INVENTED",
        "generation_strategy": "INVENTED",
        "structural_features": {"label": "tusokn"}
    }
    score_gibberish = calculate_pre_availability_score(cand_gibberish)
    assert score_anchored > score_gibberish, f"Anchored ({score_anchored}) must outscore gibberish ({score_gibberish})"
    assert score_gibberish < 60.0, f"Expected low score for tusokn, got {score_gibberish}"


# =========================================================================
# TEST 2: Stratified Diversity Selection respects Category Quotas
# =========================================================================
def test_stratified_diversity_selection_quotas():
    # Generate 100 synthetic candidates spanning all 7 categories
    raw_pool = []
    
    # 20 real words
    for i in range(20):
        raw_pool.append({
            "domain": f"realword{i}.com",
            "naming_type": "ONE_WORD",
            "generation_strategy": "ONE_WORD",
            "one_word_features": {"real_word_score": 90.0, "zipf_frequency": 4.5},
            "structural_features": {"label": f"realword{i}"}
        })
    # 20 compounds
    for i in range(20):
        raw_pool.append({
            "domain": f"craftbase{i}.com",
            "naming_type": "COMPOUND",
            "generation_strategy": "COMPOUND",
            "structural_features": {"label": f"craftbase{i}", "pronounceability_score": 85.0, "spelling_simplicity": 85.0}
        })
    # 20 semantics
    for i in range(20):
        raw_pool.append({
            "domain": f"novavibe{i}.com",
            "naming_type": "SEMANTIC_BRANDABLE",
            "generation_strategy": "SEMANTIC_BRANDABLE",
            "structural_features": {"label": f"novavibe{i}", "pronounceability_score": 85.0, "spelling_simplicity": 85.0}
        })
    # 20 invented (10 anchored, 10 unanchored)
    for i in range(10):
        raw_pool.append({
            "domain": f"kinetoc{i}.com",
            "naming_type": "INVENTED",
            "generation_strategy": "INVENTED",
            "structural_features": {"label": "kinetoc"}
        })
    for i in range(10):
        raw_pool.append({
            "domain": f"tusokn{i}.com",
            "naming_type": "INVENTED",
            "generation_strategy": "INVENTED",
            "structural_features": {"label": "tusokn"}
        })
    # 10 prefix-suffix
    for i in range(10):
        raw_pool.append({
            "domain": f"getflow{i}.com",
            "naming_type": "PREFIX_SUFFIX",
            "generation_strategy": "PREFIX_SUFFIX",
            "structural_features": {"label": f"getflow{i}", "pronounceability_score": 80.0, "spelling_simplicity": 80.0}
        })
    # 10 keywords
    for i in range(10):
        raw_pool.append({
            "domain": f"cloudai{i}.com",
            "naming_type": "KEYWORD",
            "generation_strategy": "KEYWORD",
            "structural_features": {"label": f"cloudai{i}", "pronounceability_score": 80.0, "spelling_simplicity": 80.0}
        })

    ranked = rank_and_stratify_candidates(raw_pool, target_total=60)
    assert len(ranked) == len(raw_pool), "All candidates must be preserved in the ranked queue"

    # Check top 30 slice: Must contain a diverse mix, NOT just 100% of any single category
    top_30 = ranked[:30]
    top_strats = set(c.get("generation_strategy") for c in top_30)
    assert "ONE_WORD" in top_strats
    assert "COMPOUND" in top_strats
    assert "SEMANTIC_BRANDABLE" in top_strats
    assert "INVENTED" in top_strats


# =========================================================================
# TEST 3: Unanchored Weak Gibberish Deprioritized to End of Queue
# =========================================================================
def test_unanchored_weak_gibberish_deprioritized():
    pool = [
        {"domain": "tusokn.com", "naming_type": "INVENTED", "generation_strategy": "INVENTED", "structural_features": {"label": "tusokn"}},
        {"domain": "kinetoc.com", "naming_type": "INVENTED", "generation_strategy": "INVENTED", "structural_features": {"label": "kinetoc"}},
        {"domain": "zuprok.com", "naming_type": "INVENTED", "generation_strategy": "INVENTED", "structural_features": {"label": "zuprok"}},
        {"domain": "flowbase.com", "naming_type": "COMPOUND", "generation_strategy": "COMPOUND", "structural_features": {"label": "flowbase", "pronounceability_score": 90.0, "spelling_simplicity": 90.0}},
        {"domain": "cloudpulse.com", "naming_type": "SEMANTIC_BRANDABLE", "generation_strategy": "SEMANTIC_BRANDABLE", "structural_features": {"label": "cloudpulse", "pronounceability_score": 90.0, "spelling_simplicity": 90.0}}
    ]

    ranked = rank_and_stratify_candidates(pool)
    ranked_domains = [c["domain"] for c in ranked]

    # kinetoc, flowbase, cloudpulse must rank ahead of tusokn
    assert ranked_domains.index("kinetoc.com") < ranked_domains.index("tusokn.com")
    assert ranked_domains.index("flowbase.com") < ranked_domains.index("tusokn.com")
    assert ranked_domains.index("cloudpulse.com") < ranked_domains.index("tusokn.com")


# =========================================================================
# TEST 4: Tier A Floor — Pronunciation (< 65.0) Demotes to Tier B
# =========================================================================
def test_tier_a_pronunciation_floor():
    cand = {
        "domain": "testpron.com",
        "morphology_type": "COMPOUND",
        "ip_risk_level": "LOW",
        "pronunciation_score": 58.0,  # Below 65.0 floor
        "hear_to_spell_score": 85.0,
        "commercial_naturalness_score": 80.0,
        "brandability_score": 85.0,
        "quality_breakdown": {
            "_float_scores": {
                "pronunciation": 58.0,
                "brandability": 85.0,
                "startup_naturalness": 80.0
            }
        }
    }
    tier = QualityTierEngine.assign_tier(cand, opportunity_score=86.0)
    assert tier == "TIER_B", f"Expected demotion to TIER_B due to pronunciation floor, got {tier}"
    assert any("Pronunciation" in w for w in cand.get("tier_a_critical_weakness", []))


# =========================================================================
# TEST 5: Tier A Floor — Hear-to-Spell (< 60.0) Demotes to Tier B
# =========================================================================
def test_tier_a_hear_to_spell_floor():
    cand = {
        "domain": "testspell.com",
        "morphology_type": "COMPOUND",
        "ip_risk_level": "LOW",
        "pronunciation_score": 85.0,
        "hear_to_spell_score": 52.0,  # Below 60.0 floor
        "commercial_naturalness_score": 80.0,
        "brandability_score": 85.0,
        "quality_breakdown": {
            "_float_scores": {
                "pronunciation": 85.0,
                "brandability": 85.0,
                "startup_naturalness": 80.0
            }
        }
    }
    tier = QualityTierEngine.assign_tier(cand, opportunity_score=86.0)
    assert tier == "TIER_B", f"Expected demotion to TIER_B due to hear-to-spell floor, got {tier}"
    assert any("Hear-to-spell" in w for w in cand.get("tier_a_critical_weakness", []))


# =========================================================================
# TEST 6: Tier A Floor — Commercial Naturalness (< 65.0) Demotes to Tier B
# =========================================================================
def test_tier_a_commercial_naturalness_floor():
    cand = {
        "domain": "testcomm.com",
        "morphology_type": "COMPOUND",
        "ip_risk_level": "LOW",
        "pronunciation_score": 85.0,
        "hear_to_spell_score": 85.0,
        "commercial_naturalness_score": 55.0,  # Below 65.0 floor
        "brandability_score": 85.0,
        "quality_breakdown": {
            "_float_scores": {
                "pronunciation": 85.0,
                "brandability": 85.0,
                "startup_naturalness": 55.0
            }
        }
    }
    tier = QualityTierEngine.assign_tier(cand, opportunity_score=86.0)
    assert tier == "TIER_B", f"Expected demotion to TIER_B due to commercial naturalness floor, got {tier}"
    assert any("Commercial naturalness" in w for w in cand.get("tier_a_critical_weakness", []))


# =========================================================================
# TEST 7: Tier A Floor — Brandability (< 70.0) Demotes to Tier B
# =========================================================================
def test_tier_a_brandability_floor():
    cand = {
        "domain": "testbrand.com",
        "morphology_type": "COMPOUND",
        "ip_risk_level": "LOW",
        "pronunciation_score": 85.0,
        "hear_to_spell_score": 85.0,
        "commercial_naturalness_score": 80.0,
        "brandability_score": 64.0,  # Below 70.0 floor
        "quality_breakdown": {
            "_float_scores": {
                "pronunciation": 85.0,
                "brandability": 64.0,
                "startup_naturalness": 80.0
            }
        }
    }
    tier = QualityTierEngine.assign_tier(cand, opportunity_score=86.0)
    assert tier == "TIER_B", f"Expected demotion to TIER_B due to brandability floor, got {tier}"
    assert any("Brandability" in w for w in cand.get("tier_a_critical_weakness", []))


# =========================================================================
# TEST 8: Tier A Floor — Clean Candidate Meeting All Floors Enters Tier A
# =========================================================================
def test_tier_a_clean_candidate_enters_tier_a():
    cand = {
        "domain": "kinetoc.com",
        "morphology_type": "INVENTED",
        "invented_quality_tier": "STRONG",
        "invented_subtype": "HYBRID_ANCHORED",
        "ip_risk_level": "LOW",
        "pronunciation_score": 88.0,
        "hear_to_spell_score": 85.0,
        "commercial_naturalness_score": 82.0,
        "brandability_score": 92.0,
        "quality_breakdown": {
            "_float_scores": {
                "pronunciation": 88.0,
                "brandability": 92.0,
                "startup_naturalness": 82.0
            }
        }
    }
    tier = QualityTierEngine.assign_tier(cand, opportunity_score=86.0)
    assert tier == "TIER_A", f"Expected TIER_A for clean strong candidate, got {tier}"
    assert len(cand.get("tier_a_critical_weakness", [])) == 0


# =========================================================================
# TEST 9: Dynamic Batching Check Batch Does Not Stop At 45 Within A Batch
# =========================================================================
@pytest.mark.asyncio
async def test_check_batch_does_not_stop_at_45_within_batch():
    engine = AvailabilityEngine()
    
    # 60 test domains
    test_domains = [f"batchtestdom{i:03d}.com" for i in range(60)]
    
    # Mock check_domain returning AVAILABLE_STANDARD for all 60 domains
    with patch.object(engine, 'check_domain', new_callable=AsyncMock) as mock_cd:
        mock_cd.side_effect = lambda d: AvailabilityResult(
            domain=d,
            status=AvailabilityStatus.AVAILABLE_STANDARD,
            provider="verisign_rdap",
            is_registered=False,
            is_premium=False,
            registration_available=True,
            availability_verified=True
        )

        # When max_available is None (the default in the dynamic batching flow),
        # all 60 domains in the batch must be checked completely!
        results = await engine.check_batch(test_domains, max_available=None)
        
        assert len(results) == 60, f"Expected all 60 domains in batch to be checked, got {len(results)}"
        available_count = sum(1 for r in results.values() if r.status == AvailabilityStatus.AVAILABLE_STANDARD)
        assert available_count == 60, f"Expected 60 available standard domains, got {available_count}"
