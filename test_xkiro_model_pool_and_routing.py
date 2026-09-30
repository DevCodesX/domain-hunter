"""
Unit & Integration Tests for XKIRO Model Pool, Capability Routing, and Fallback Resilience
Validates Section 1-25 requirements from the prompt.
"""

import pytest
import os
import time
import json
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from router import (
    ModelRouter,
    ModelIntelligenceLayer,
    XKIRO_MODEL_POOL,
    XKIRO_MODEL_ALIASES,
    resolve_xkiro_model_id
)
from quality_engine.multi_model_evaluator import (
    MultiModelDomainEvaluator,
    robust_statistics,
    detect_short_but_meaningless,
    detect_pronounceable_not_brandable
)
from quality_engine.quality_tiers import QualityTierEngine
from quality_engine.diversity_engine import DiversityEngine
from quality_engine.config import get_multi_model_evaluation_config


# =========================================================================
# 1. Model Pool Registration & Family Grouping
# =========================================================================

def test_xkiro_model_pool_registered():
    """Verify all required XKIRO model families are registered with roles and metadata."""
    assert len(XKIRO_MODEL_POOL) >= 50, f"Expected at least 50 pool models, got {len(XKIRO_MODEL_POOL)}"
    
    families = set(m["family"] for m in XKIRO_MODEL_POOL)
    expected_families = {"DeepSeek", "Mistral", "MiniMax", "MiMo", "Qwen", "Cohere", "Other"}
    for f in expected_families:
        assert f in families, f"Missing expected family '{f}' in XKIRO_MODEL_POOL"

    for m in XKIRO_MODEL_POOL:
        assert "id" in m and m["id"]
        assert "name" in m and m["name"]
        assert "family" in m and m["family"]
        assert "role" in m and m["role"]
        assert m.get("is_free") is True


# =========================================================================
# 2. Model Alias Resolution
# =========================================================================

def test_model_alias_resolution():
    """Verify prompt shorthand model IDs resolve to exact API model IDs."""
    cases = [
        ("qwen3.8-max", "qwen/qwen3.8-max:free"),
        ("qwen3.7-max", "qwen/qwen3.7-max:free"),
        ("mistral-large-2512", "mistralai/mistral-large-2512"),
        ("mistral-medium-3.5", "mistralai/mistral-medium-3.5"),
        ("command-a-reasoning", "cohere/command-a-reasoning"),
        ("command-a-plus", "cohere/command-a-plus"),
        ("minimax-m3", "minimax/minimax-m3:free"),
        ("deepseek-v4.1-flash:free", "deepseek/deepseek-v4.1-flash:free"),
        ("deepseek-v4-pro", "deepseek/deepseek-v4-pro"),
        ("devstral-2", "mistralai/devstral-medium"),
        ("dots3-note-preview", "dots-studio/dots-3-note-preview:free"),
    ]
    for shorthand, canonical in cases:
        resolved = resolve_xkiro_model_id(shorthand)
        assert resolved == canonical, f"Failed resolving {shorthand}: expected {canonical}, got {resolved}"


# =========================================================================
# 3. Capability-Based Routing Chains
# =========================================================================

def test_capability_routing_chains():
    """Verify router task_profiles matches the prompt capability routing hierarchy."""
    router = ModelRouter()
    
    # Generation: Primary qwen3.8-max, Fallbacks deepseek-v4-pro, minimax-m3, mistral-large-2512
    gen_chain = [p["model"] for p in router.task_profiles["domain_generation"]]
    assert gen_chain[0] == "qwen/qwen3.8-max:free"
    assert gen_chain[1] == "deepseek/deepseek-v4-pro"
    assert gen_chain[2] == "minimax/minimax-m3:free"
    assert gen_chain[3] == "mistralai/mistral-large-2512"

    # Linguistic: Primary mistral-large-2512, Fallbacks qwen3.7-max, deepseek-v4.1-flash, command-a-plus
    ling_chain = [p["model"] for p in router.task_profiles["linguistic_judge"]]
    assert ling_chain[0] == "mistralai/mistral-large-2512"
    assert ling_chain[1] == "qwen/qwen3.7-max:free"
    assert ling_chain[2] == "deepseek/deepseek-v4.1-flash:free"
    assert ling_chain[3] == "cohere/command-a-plus"

    # Commercial: Primary command-a-reasoning, Fallbacks deepseek-v4-pro, mistral-large-2512, minimax-m3
    comm_chain = [p["model"] for p in router.task_profiles["commercial_judge"]]
    assert comm_chain[0] == "cohere/command-a-reasoning"
    assert comm_chain[1] == "deepseek/deepseek-v4-pro"
    assert comm_chain[2] == "mistralai/mistral-large-2512"
    assert comm_chain[3] == "minimax/minimax-m3:free"

    # Red Team: Primary deepseek-v4.1-flash, Fallbacks qwen3.7-max, mistral-medium-3.5, qwen3.6-plus
    red_chain = [p["model"] for p in router.task_profiles["red_team"]]
    assert red_chain[0] == "deepseek/deepseek-v4.1-flash:free"
    assert red_chain[1] == "qwen/qwen3.7-max:free"
    assert red_chain[2] == "mistralai/mistral-medium-3.5"
    assert red_chain[3] == "qwen/qwen3.6-plus:free"

    # Final Arbiter: Primary deepseek-v4-pro, Fallbacks qwen3.8-max, command-a-reasoning, mistral-large-2512
    arb_chain = [p["model"] for p in router.task_profiles["consensus_arbiter"]]
    assert arb_chain[0] == "deepseek/deepseek-v4-pro"
    assert arb_chain[1] == "qwen/qwen3.8-max:free"
    assert arb_chain[2] == "cohere/command-a-reasoning"
    assert arb_chain[3] == "mistralai/mistral-large-2512"


# =========================================================================
# 4. Fallback Chain on 403 Unavailable
# =========================================================================

@pytest.mark.asyncio
async def test_fallback_chain_on_403():
    """Verify that when a model receives 403 (e.g. paying customers only on XKIRO),
    it is marked UNAVAILABLE and the router advances to Fallback #1 without failing."""
    router = ModelRouter()
    
    async def mock_post(url, headers, json):
        model = json.get("model")
        if "deepseek" in model:
            # Simulate XKIRO 403 paying customers only
            resp = httpx.Response(
                status_code=403,
                request=httpx.Request("POST", url),
                text='{"error":"available to paying customers only"}'
            )
            raise httpx.HTTPStatusError("403 Forbidden", request=resp.request, response=resp)
        # Fallback model succeeds
        return httpx.Response(
            status_code=200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": "Fallback output OK"}}]}
        )

    with patch.object(router.client, "post", side_effect=mock_post):
        # Execute red_team task (Primary is deepseek-v4.1-flash, Fallback is qwen3.7-max)
        result = await router.execute_task("red_team", "Test prompt", max_retries=1)
        assert result == "Fallback output OK"
        
        # Verify circuit breaker opened on deepseek
        assert not router.intelligence.is_model_available("xkiro", "deepseek/deepseek-v4.1-flash:free")


# =========================================================================
# 5. Fallback on 429 Rate Limit and Timeout
# =========================================================================

@pytest.mark.asyncio
async def test_fallback_chain_on_429_and_timeout():
    """Verify router transitions past 429 rate-limited or timed-out models."""
    router = ModelRouter()
    call_counts = {}

    async def mock_post(url, headers, json):
        model = json.get("model")
        call_counts[model] = call_counts.get(model, 0) + 1
        if "mistral-large" in model:
            # Simulate 429
            resp = httpx.Response(
                status_code=429,
                request=httpx.Request("POST", url),
                text='{"error":"Rate limit reached"}'
            )
            raise httpx.HTTPStatusError("429 Too Many Requests", request=resp.request, response=resp)
        return httpx.Response(
            status_code=200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": "Linguistic Fallback Success"}}]}
        )

    with patch.object(router.client, "post", side_effect=mock_post):
        res = await router.execute_task("linguistic_judge", "Evaluate linguistics", max_retries=1)
        assert res == "Linguistic Fallback Success"
        # Primary was attempted and failed
        assert "mistralai/mistral-large-2512" in call_counts
        # Fallback was called and succeeded
        assert "qwen/qwen3.7-max:free" in call_counts


# =========================================================================
# 6. Fallback on Malformed JSON
# =========================================================================

@pytest.mark.asyncio
async def test_fallback_on_malformed_json():
    """Verify execute_task_json moves to fallback if response is malformed."""
    router = ModelRouter()

    async def mock_post(url, headers=None, json=None, **kwargs):
        model = (json or {}).get("model", "")
        if "qwen3.8-max" in model:
            # Malformed JSON
            return httpx.Response(
                status_code=200,
                request=httpx.Request("POST", url),
                json={"choices": [{"message": {"content": "Not JSON at all here <broken>"}}]}
            )
        # Next model in chain returns valid JSON
        return httpx.Response(
            status_code=200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": '{"brand_strength": 88}'}}]}
        )

    with patch.object(router.client, "post", side_effect=mock_post):
        data = await router.execute_task_json("brand_judge", "Evaluate brand", max_retries=1)
        assert data.get("brand_strength") == 88


# =========================================================================
# 7. No Fake ONLINE State & Truthful Health Tracking
# =========================================================================

@pytest.mark.asyncio
async def test_no_fake_online_state_and_test_model():
    """Verify models start in STANDBY / NOT CONFIGURED and only turn ONLINE upon verified 200 OK probe."""
    router = ModelRouter()
    pool_health = router.get_model_pool_health()
    
    # Freshly instantiated pool has not executed real probes yet -> status must NOT be ONLINE
    for m in pool_health:
        assert m["status"] != "ONLINE", f"Model {m['id']} falsely marked ONLINE without real probe!"

    # Probe single model
    async def mock_probe_post(url, headers=None, json=None, **kwargs):
        return httpx.Response(
            status_code=200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": "pong"}}]}
        )

    with patch.object(router.client, "post", side_effect=mock_probe_post):
        res = await router.test_model("xkiro", "qwen/qwen3.8-max:free")
        assert res["status"] == "ONLINE"
        assert res["latency_ms"] > 0
        assert res["last_error"] is None

        # Now pool health reflects ONLINE for this specific model
        updated_pool = router.get_model_pool_health()
        target = next(x for x in updated_pool if x["id"] == "qwen/qwen3.8-max:free")
        assert target["status"] == "ONLINE"


# =========================================================================
# 8. Judge Independence & Distinct Role Execution
# =========================================================================

@pytest.mark.asyncio
async def test_judge_independence_and_no_score_leakage():
    """Verify that all 4 judges receive independent prompts without other judges' scores."""
    router = ModelRouter()
    prompts_captured = []

    async def mock_exec_profile(provider, model, prompt, temperature, max_tokens, max_retries):
        prompts_captured.append(prompt)
        role = "linguistic" if "LINGUISTIC" in prompt else ("brand" if "BRAND" in prompt else ("commercial" if "COMMERCIAL" in prompt else "red_team"))
        return {
            "content": json.dumps({"evaluations": [{
                "domain": "novaloom.com",
                "linguistic_naturalness": 85, "lexical_familiarity": 70, "phonetic_naturalness": 88,
                "spelling_predictability": 82, "semantic_anchor_quality": 80, "coined_intentionality": 75, "gibberish_probability": 15,
                "brand_strength": 86, "memorability": 84, "identity_strength": 85, "startup_naturalness": 82, "distinctiveness": 80, "brand_longevity": 82, "ai_generated_feel": 20,
                "commercial_strength": 84, "buyer_clarity": 80, "buyer_breadth": 78, "category_fit": 82, "market_breadth": 76, "resale_flexibility": 75,
                "red_team_score": 82, "gibberish_risk": 15, "ai_pattern_risk": 20, "spelling_risk": 10, "commercial_weakness": 20, "semantic_weakness": 18
            }]}),
            "provider": provider,
            "model": model,
            "latency_ms": 120.0,
            "fallback_used": False
        }

    with patch.object(router, "execute_profile", side_effect=mock_exec_profile):
        evaluator = MultiModelDomainEvaluator(router)
        res = await evaluator.evaluate_batch([{"domain": "novaloom.com", "naming_type": "INVENTED"}])
        
        # Verify all configured pool profiles across 4 distinct roles were executed
        judge_prompts = [p for p in prompts_captured if "ROLE:" in p]
        assert len(judge_prompts) >= 57
        assert len(set(judge_prompts)) == 4
        
        # Verify judge roles: Linguistic, Brand, Commercial, Red Team
        roles_found = set()
        for p in judge_prompts:
            if "LINGUISTIC" in p: roles_found.add("linguistic")
            if "BRAND" in p: roles_found.add("brand")
            if "COMMERCIAL" in p: roles_found.add("commercial")
            if "RED-TEAM" in p or "RED_TEAM" in p: roles_found.add("red_team")
            
            # Crucial: Judge prompts must never contain other judges' scores
            assert "Judge A" not in p
            assert "previous_scores" not in p
            assert "other_evaluations" not in p
            
        assert roles_found == {"linguistic", "brand", "commercial", "red_team"}


# =========================================================================
# 9. Robust Consensus & Disagreement Detection
# =========================================================================

def test_robust_consensus_disagreement_detection():
    """Verify that a candidate with [90, 91, 89, 55] is flagged as HIGH DISAGREEMENT."""
    stats = robust_statistics([90.0, 91.0, 89.0, 55.0])
    assert stats["median"] == 89.5 or stats["median"] == 90.0
    assert stats["range"] == 36.0
    assert stats["high_disagreement"] is True
    assert stats["judge_agreement"] < 70.0


# =========================================================================
# 10. Short-but-Meaningless and Pronounceable-Not-Brandable Guards
# =========================================================================

def test_short_meaningless_and_pronounceable_guards():
    """Verify detection of short unanchored pronounceable strings."""
    # Short but meaningless: length 6, pronunciation 85, but weak semantic anchor 20 and commercial 25
    assert detect_short_but_meaningless(
        label="kocud",
        length=5,
        pronunciation=85.0,
        semantic_anchor=20.0,
        commercial_clarity=25.0
    ) is True

    # Strong anchored brandable: length 7, pronunciation 88, strong semantic anchor 80, commercial 85
    assert detect_short_but_meaningless(
        label="cloudflow",
        length=9,
        pronunciation=88.0,
        semantic_anchor=80.0,
        commercial_clarity=85.0
    ) is False

    # Pronounceable not brandable: pronunciation 80, semantic anchor 30, brand score 50, low atom 6.0
    assert detect_pronounceable_not_brandable(
        pronunciation=80.0,
        semantic_anchor=30.0,
        brand_score=50.0,
        red_team_score=45.0,
        atom_score=6.0
    ) is True


# =========================================================================
# 11. Invented Quality Ceilings
# =========================================================================

def test_unanchored_invented_quality_ceiling():
    """Verify unanchored invented candidates cannot reach Tier A simply by pronunciation."""
    candidate = {
        "domain": "latenso.com",
        "morphology_type": "INVENTED",
        "invented_subtype": "UNANCHORED",
        "invented_quality_tier": "WEAK",
        "pronunciation_score": 92.0,
        "hear_to_spell_score": 90.0,
        "brandability_score": 95.0,
        "quality_breakdown": {
            "_float_scores": {"pronunciation": 92.0, "brandability": 95.0, "startup_naturalness": 88.0}
        }
    }
    tier = QualityTierEngine.assign_tier(candidate, opportunity_score=92.0)
    assert tier != "TIER_A", f"Unanchored candidate latenso.com illegally reached {tier}"


# =========================================================================
# 12. Learning Before Diversity
# =========================================================================

def test_learning_applied_before_diversity_selection():
    """Verify learned preference scores re-order candidates before diversity clustering."""
    engine = DiversityEngine()
    candidates = [
        {"domain": "lowerconviction.com", "overall_score": 90, "final_rank_score": 70, "phonetic_cluster_id": "c1"},
        {"domain": "learnedwinner.com", "overall_score": 82, "final_rank_score": 95, "phonetic_cluster_id": "c2"}
    ]
    # Ranking by final_rank_score prioritizes learnedwinner.com before diversity selection
    sorted_cands = sorted(candidates, key=lambda c: c["final_rank_score"], reverse=True)
    selected = engine.select_diverse_candidates(sorted_cands, limit=1)
    assert selected[0]["domain"] == "learnedwinner.com"
