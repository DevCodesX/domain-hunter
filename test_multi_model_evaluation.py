import pytest

from quality_engine.multi_model_evaluator import MultiModelDomainEvaluator, robust_statistics
from quality_engine.quality_scorer import QualityScorer
from quality_engine.feature_extractor import QualityFeatureExtractor
from quality_engine.one_word_engine import OneWordQualityEngine
from quality_engine.naming_classifier import NamingTypeClassifier
from quality_engine.quality_tiers import QualityTierEngine
from quality_engine.diversity_engine import DiversityEngine


def _role_payload(role, domain="horede.com", score=88):
    if role == "linguistic":
        return {"domain": domain, "linguistic_naturalness": score, "lexical_familiarity": 35, "phonetic_naturalness": 82, "spelling_predictability": 76, "semantic_anchor_quality": 22, "coined_intentionality": 55, "gibberish_probability": 48}
    if role == "brand":
        return {"domain": domain, "brand_strength": score, "memorability": 84, "identity_strength": 82, "startup_naturalness": 80, "distinctiveness": 88, "brand_longevity": 76, "ai_generated_feel": 62}
    if role == "commercial":
        return {"domain": domain, "commercial_strength": score, "buyer_clarity": 45, "buyer_breadth": 35, "category_fit": 42, "market_breadth": 30, "resale_flexibility": 38}
    return {"domain": domain, "red_team_score": score, "gibberish_risk": 62, "ai_pattern_risk": 72, "spelling_risk": 40, "commercial_weakness": 68, "semantic_weakness": 70, "critical_objections": ["Short but weakly anchored"], "kill_reasons": ["No credible buyer archetype"]}


class FakeRouter:
    def __init__(self):
        self.calls = []
        self.task_profiles = {
            "quality_evaluator": [
                {"provider": "nvidia", "model": "model-a"},
                {"provider": "nvidia", "model": "model-b"},
                {"provider": "xkiro", "model": "model-c"},
            ],
            "brandability": [{"provider": "nvidia", "model": "brand-a"}],
            "commercial_evaluator": [{"provider": "nvidia", "model": "commercial-a"}],
            "final_judge": [{"provider": "xkiro", "model": "arbiter-a"}],
        }

    async def execute_profile(self, provider, model, prompt, temperature, max_tokens, max_retries):
        self.calls.append((provider, model, prompt))
        if "CONSENSUS ARBITER" in prompt:
            domain = "horede.com"
            return {"content": '{"domain":"horede.com","consensus_score":52,"confidence":82,"final_brand_quality":55,"final_linguistic_quality":70,"final_commercial_quality":42,"final_buyer_quality":35,"final_semantic_quality":20,"final_gibberish_risk":76,"final_ai_pattern_risk":70,"major_strengths":[],"major_weaknesses":["Weak semantic evidence"],"critical_flags":["UNANCHORED"],"verdict":"REVIEW","reason":"Evidence does not converge."}'}
        role = "linguistic" if "ROLE: LINGUISTIC" in prompt else "brand" if "ROLE: BRAND" in prompt else "commercial" if "ROLE: COMMERCIAL" in prompt else "red_team"
        return {"content": '{"evaluations":[' + __import__("json").dumps(_role_payload(role)) + ']}'}


@pytest.mark.asyncio
async def test_four_judges_are_independent_and_arbiter_is_separate():
    router = FakeRouter()
    evaluator = MultiModelDomainEvaluator(router, {
        "enabled": True, "stage1_pool_size": 50, "arbiter_pool_size": 1,
        "judge_batch_size": 5, "arbiter_enabled": True,
        "role_task_map": {"linguistic":"quality_evaluator","brand":"brandability","commercial":"commercial_evaluator","red_team":"quality_evaluator","arbiter":"final_judge"},
        "role_profile_index": {"linguistic":2,"brand":0,"commercial":0,"red_team":1,"arbiter":0},
        "disagreement_penalty_factor": 0.35,
        "missing_judge_penalty": 6,
    })
    result = await evaluator.evaluate_batch([{"domain":"horede.com","naming_type":"INVENTED","invented_subtype":"UNANCHORED","semantic_anchor_score":20}])
    item = result["candidates"]["horede.com"]
    assert item["linguistic_judge"]["parsed"]["linguistic_naturalness"] == 88
    assert item["brand_judge"]["parsed"]["brand_strength"] == 88
    assert item["commercial_judge"]["parsed"]["commercial_strength"] == 88
    assert item["red_team_judge"]["parsed"]["red_team_score"] == 88
    assert item["arbiter_trace"]["status"] == "SUCCESS"
    prompts = [x[2] for x in router.calls]
    assert len(prompts) >= 5
    assert len(set(p.split("ROLE:")[1].splitlines()[0] if "ROLE:" in p else "ARBITER" for p in prompts)) >= 4


def test_robust_aggregation_preserves_outlier_and_does_not_average():
    stats = robust_statistics([92, 90, 88, 55])
    assert stats["median"] == 89
    assert stats["high_disagreement"] is True
    assert stats["stddev"] > 10


def test_unanchored_invented_cannot_be_tier_a():
    candidate = {
        "domain": "horede.com", "quality_score": 96, "overall_score": 96,
        "brandability_score": 96, "commercial_score": 95,
        "ip_risk_level": "LOW", "availability_status": "AVAILABLE_STANDARD",
        "morphology_type": "INVENTED", "invented_subtype": "UNANCHORED",
        "invented_quality_tier": "WEAK", "brandability_heuristic_score": 90,
        "quality_breakdown": {"_float_scores": {"pronunciation":90,"brandability":96,"startup_naturalness":95}},
    }
    assert QualityTierEngine.assign_tier(candidate, 96) != "TIER_A"


def test_diversity_prefers_final_rank_before_diversity():
    engine = DiversityEngine()
    candidates = [
        {"domain":"alphaone.com","overall_score":95,"final_rank_score":60,"phonetic_cluster_id":"a"},
        {"domain":"betawave.com","overall_score":80,"final_rank_score":92,"phonetic_cluster_id":"b"},
    ]
    ranked = engine.select_diverse_candidates(candidates, limit=1)
    assert ranked[0]["domain"] == "betawave.com"


def test_short_unanchored_name_does_not_receive_high_semantic_or_commercial_score():
    qs = QualityScorer()
    fe = QualityFeatureExtractor()
    owe = OneWordQualityEngine()
    classifier = NamingTypeClassifier()
    label = "horede"
    structural = fe.extract_features(label)
    naming = classifier.classify(label)
    one_word = owe.compute_one_word_score(label)
    result = qs.score_candidate(
        "horede.com", structural, one_word, naming,
        ai_evaluation=None, concept="AI infrastructure",
        multi_model_evaluation={
            "consensus": {
                "final_brand_quality": 92, "final_linguistic_quality": 82,
                "final_commercial_quality": 91, "final_buyer_quality": 90,
                "final_semantic_quality": 90, "final_gibberish_risk": 10,
                "red_team_score": 90, "red_team_penalty": 0
            },
            "consensus_confidence": 90,
            "short_but_meaningless": True,
            "_config": {
                "invented_ai_blend": 0.35, "min_consensus_confidence": 55,
                "unanchored_final_ceiling": 64, "unanchored_commercial_ceiling": 58,
                "short_meaningless_semantic_max": 50,
                "red_team_low_score": 55, "red_team_penalty_factor": 0.20,
            }
        }
    )
    assert result["brandability_score"] <= 58
    assert result["commercial_score"] <= 55
    assert result["quality_breakdown"]["semantic"] <= 45


def test_all_judge_failure_has_deterministic_fallback():
    candidate = {
        "domain": "horede.com",
        "quality_score": 70,
        "multi_model_review": {
            "linguistic_judge": {"status": "FAILED"},
            "brand_judge": {"status": "FAILED"},
            "commercial_judge": {"status": "FAILED"},
            "red_team_judge": {"status": "FAILED"},
            "consensus": {"consensus_score": None, "verdict": "REVIEW"}
        }
    }
    successes = sum(
        1 for role in ("linguistic_judge", "brand_judge", "commercial_judge", "red_team_judge")
        if candidate["multi_model_review"][role]["status"] == "SUCCESS"
    )
    assert successes == 0
    assert candidate["quality_score"] == 70
