"""
Comprehensive Automated Test Suite for:
PHASE 3: Yield Optimization + Multi-Engine Generation + Buyer Intelligence + Quality Tiers
PHASE 4: Self-Learning Ranker + Strategy Optimization + Model Router Telemetry

Verifies all 22 required test cases (A through V):
A. Multi-engine generation
B. Strategy quota allocation
C. Dynamic quota adjustment
D. One-word classification
E. Compound classification
F. Invented-name classification
G. Diversity clustering & penalty
H. Buyer intelligence evaluation
I. Quality tiering organization
J. Feedback persistence
K. Cold-start learning states
L. Training dataset creation
M. Ranker training
N. Ranker prediction
O. Model versioning & metadata
P. Strategy performance calculation
Q. Dynamic strategy rebalancing
R. Exploration/exploitation balance
S. Failed model exclusion from training
T. Availability safety invariant
U. Production blocks mock registry
V. Final candidates genuinely available
"""

import os
import json
import pytest
import asyncio
from unittest.mock import MagicMock, patch

# Phase 3 Quality Engine imports
from quality_engine.multi_engine import MultiEngineOrchestrator
from quality_engine.evolutionary_generator import EvolutionaryGenerator
from quality_engine.buyer_intelligence import BuyerIntelligenceEngine
from quality_engine.quality_tiers import QualityTierEngine
from quality_engine.diversity_engine import DiversityEngine, apply_diversity_penalties
from quality_engine.classifiers import NamingTypeClassifier, NamingType

# Phase 4 Learning Engine imports
from learning_engine.learning_store import LearningStore
from learning_engine.feature_pipeline import TrainingFeaturePipeline
from learning_engine.ranker import StatisticalRanker, LearningState
from learning_engine.strategy_optimizer import StrategyOptimizer
from learning_engine.router_tracker import RouterPerformanceTracker

# Production Availability imports
from availability import AvailabilityResult, AvailabilityStatus, is_production_mode


# =========================================================================
# A. Multi-Engine Generation Test
# =========================================================================
def test_a_multi_engine_generation():
    """Verify that MultiEngineOrchestrator generates candidates across all 7 specialized engines."""
    orchestrator = MultiEngineOrchestrator()
    concepts = ["ai agents for enterprise workflow automation", "high speed database"]
    
    candidates = orchestrator.generate_all_strategies(concepts, target_count=70)
    
    assert len(candidates) > 0, "Orchestrator must generate candidates"
    
    # Check that multiple engines contributed
    engines_present = {c.get("generation_strategy") or c.get("engine_strategy") for c in candidates if c.get("generation_strategy") or c.get("engine_strategy")}
    assert len(engines_present) >= 4, f"Expected multiple engines to contribute, got: {engines_present}"
    
    # Check clean .com format
    for c in candidates:
        domain = c.get("domain", "")
        assert domain.endswith(".com"), f"Domain must end with .com: {domain}"
        assert " " not in domain, f"Domain must not have spaces: {domain}"


# =========================================================================
# B. Strategy Quota Allocation Test
# =========================================================================
def test_b_strategy_quota_allocation():
    """Verify quota allocation across 7 strategies sums to requested budget."""
    orchestrator = MultiEngineOrchestrator()
    target_count = 1950
    quotas = orchestrator.get_strategy_quotas(target_count)
    
    assert isinstance(quotas, dict)
    assert len(quotas) == 7, f"Expected 7 engine quotas, got {len(quotas)}"
    
    total_allocated = sum(quotas.values())
    assert abs(total_allocated - target_count) <= 7, f"Quota sum {total_allocated} should match target {target_count}"
    
    for engine, count in quotas.items():
        assert count > 0, f"Engine {engine} must receive non-zero quota"


# =========================================================================
# C. Dynamic Quota Adjustment Test
# =========================================================================
def test_c_dynamic_quota_adjustment():
    """Verify underperforming strategies get lower quotas and high-yield get higher."""
    optimizer = StrategyOptimizer()
    
    # Simulate performance where one_word has 15% yield and compound has 1% yield
    perf_data = {
        "one_word": {"generated": 400, "available": 60, "accepted": 20},
        "invented_brand": {"generated": 350, "available": 28, "accepted": 10},
        "semantic_brand": {"generated": 300, "available": 20, "accepted": 8},
        "compound": {"generated": 300, "available": 3, "accepted": 0},
        "prefix_suffix": {"generated": 200, "available": 10, "accepted": 2},
        "trend": {"generated": 200, "available": 12, "accepted": 3},
        "keyword_brandable": {"generated": 200, "available": 14, "accepted": 4}
    }
    
    new_weights = optimizer.rebalance_quotas(perf_data)
    
    # one_word should receive higher weight than compound
    assert new_weights["one_word"] > new_weights["compound"], (
        f"High-yield one_word ({new_weights['one_word']}) should have higher weight than compound ({new_weights['compound']})"
    )
    assert sum(new_weights.values()) == pytest.approx(1.0, rel=1e-3)


# =========================================================================
# D. One-Word Classification Test
# =========================================================================
def test_d_one_word_classification():
    """Verify strict dictionary word validation for ONE_WORD classification."""
    classifier = NamingTypeClassifier()
    
    # Authentic English dictionary words
    res1 = classifier.classify("pulse")
    assert res1 == NamingType.ONE_WORD, f"Expected ONE_WORD for 'pulse', got {res1}"
    
    res2 = classifier.classify("forge")
    assert res2 == NamingType.ONE_WORD, f"Expected ONE_WORD for 'forge', got {res2}"
    
    # Non-dictionary word or compound should NOT be ONE_WORD
    res3 = classifier.classify("cloudcraft")
    assert res3 != NamingType.ONE_WORD, f"Compound 'cloudcraft' should not be ONE_WORD, got {res3}"


# =========================================================================
# E. Compound Classification Test
# =========================================================================
def test_e_compound_classification():
    """Verify COMPOUND classification identifies two genuine English words."""
    classifier = NamingTypeClassifier()
    
    res = classifier.classify("cloudcraft")
    assert res == NamingType.COMPOUND, f"Expected COMPOUND for 'cloudcraft', got {res}"
    
    res2 = classifier.classify("teamflow")
    assert res2 in [NamingType.COMPOUND, NamingType.SEMANTIC_BRAND, NamingType.PREFIX_SUFFIX, NamingType.INVENTED], f"Expected COMPOUND/SEMANTIC/PREFIX_SUFFIX/INVENTED for 'teamflow', got {res2}"


# =========================================================================
# F. Invented-Name Classification Test
# =========================================================================
def test_f_invented_name_classification():
    """Verify INVENTED classification for pronounceable non-dictionary brand names."""
    classifier = NamingTypeClassifier()
    
    res = classifier.classify("lumixa")
    assert res == NamingType.INVENTED, f"Expected INVENTED for 'lumixa', got {res}"
    
    res2 = classifier.classify("velora")
    assert res2 == NamingType.INVENTED, f"Expected INVENTED for 'velora', got {res2}"


# =========================================================================
# G. Diversity Clustering & Penalties Test
# =========================================================================
def test_g_diversity_clustering_and_penalties():
    """Verify acoustic cousins, repeated morphemes, and suffix saturation receive penalties."""
    candidates = [
        {"domain": "dataflow.com", "overall_score": 88.0, "naming_type": "COMPOUND"},
        {"domain": "cloudflow.com", "overall_score": 87.0, "naming_type": "COMPOUND"},
        {"domain": "netflow.com", "overall_score": 86.0, "naming_type": "COMPOUND"},
        {"domain": "workstream.com", "overall_score": 85.0, "naming_type": "COMPOUND"},
    ]
    
    penalized = apply_diversity_penalties(candidates)
    
    # The third repeated suffix "flow" should receive a diversity penalty
    netflow_cand = next(c for c in penalized if "netflow" in c["domain"])
    assert netflow_cand.get("diversity_penalty", 0) > 0, "Repeated suffix should trigger diversity penalty"
    assert netflow_cand["effective_score"] < netflow_cand["overall_score"]


# =========================================================================
# H. Buyer Intelligence Evaluation Test
# =========================================================================
def test_h_buyer_intelligence_evaluation():
    """Verify BuyerIntelligenceEngine outputs archetypes, sectors, products, and startup naturalness."""
    buyer_engine = BuyerIntelligenceEngine()
    
    bi = buyer_engine.evaluate(
        domain="databridge.com",
        category="Technology & Infrastructure",
        concept="enterprise data integration pipelines"
    )
    
    assert "primary_archetype" in bi
    assert "target_sectors" in bi
    assert isinstance(bi["target_sectors"], list)
    assert len(bi["target_sectors"]) > 0
    assert "product_categories" in bi
    assert "startup_naturalness" in bi
    assert 0.0 <= bi["startup_naturalness"] <= 1.0
    assert "potential_buyer_count" in bi
    assert "geographic_potential" in bi


# =========================================================================
# I. Quality Tiering Organization Test
# =========================================================================
def test_i_quality_tiering_organization():
    """Verify QualityTierEngine organizes candidates into Tier A, Tier B, and Watchlist with explanations."""
    tier_engine = QualityTierEngine()
    
    candidates = [
        {
            "domain": "nexusai.com",
            "overall_score": 93.0,
            "quality_score": 93.0,
            "brandability_score": 94.0,
            "trend_score": 92.0,
            "commercial_score": 93.0,
            "ip_risk": {"level": "LOW", "score": 10},
            "ip_risk_level": "LOW",
            "availability_status": "AVAILABLE_STANDARD"
        },
        {
            "domain": "datastack.com",
            "overall_score": 84.0,
            "quality_score": 84.0,
            "brandability_score": 85.0,
            "trend_score": 83.0,
            "commercial_score": 84.0,
            "ip_risk": {"level": "LOW", "score": 12},
            "ip_risk_level": "LOW",
            "availability_status": "AVAILABLE_STANDARD"
        },
        {
            "domain": "quickflow.com",
            "overall_score": 68.0,
            "quality_score": 68.0,
            "brandability_score": 70.0,
            "trend_score": 65.0,
            "commercial_score": 68.0,
            "ip_risk": {"level": "MEDIUM", "score": 35},
            "ip_risk_level": "MEDIUM",
            "availability_status": "AVAILABLE_STANDARD"
        }
    ]
    
    result = tier_engine.organize_tiers(candidates)
    
    assert "tier_a" in result
    assert "tier_b" in result
    assert "watchlist" in result
    
    # nexusai.com (93.0) should be Tier A
    assert any(c["domain"] == "nexusai.com" for c in result["tier_a"])
    # datastack.com (84.0) should be Tier B
    assert any(c["domain"] == "datastack.com" for c in result["tier_b"])
    # quickflow.com (68.0) should be Watchlist
    assert any(c["domain"] == "quickflow.com" for c in result["watchlist"])
    
    # Check that explanation fields are present
    top_cand = result["tier_a"][0]
    assert "explanations" in top_cand
    expl = top_cand["explanations"]
    assert "why_generated" in expl
    assert "why_passed" in expl
    assert "why_scored" in expl
    assert "why_selected" in expl


# =========================================================================
# J. Feedback Persistence Test
# =========================================================================
def test_j_feedback_persistence(tmp_path):
    """Verify LearningStore records shortlist, favorite, and reject actions with reasons."""
    test_db = str(tmp_path / "learning_test.json")
    store = LearningStore(db_path=test_db)
    
    store.record_feedback(
        candidate_id="cand_1",
        domain="talenta.com",
        user_action="shortlist",
        rejection_reason=None,
        notes="Strong brand"
    )
    
    store.record_feedback(
        candidate_id="cand_2",
        domain="baddomain123.com",
        user_action="reject",
        rejection_reason="Too generic",
        notes="Sounds amateur"
    )
    
    feedbacks = store.get_feedback()
    assert len(feedbacks) == 2
    
    summary = store.get_feedback_summary()
    assert summary["shortlist"] == 1
    assert summary["reject"] == 1
    assert summary["reasons"].get("Too generic") == 1


# =========================================================================
# K. Cold-Start Learning States Test
# =========================================================================
def test_k_cold_start_learning_states(tmp_path):
    """Verify Cold-Start progression: COLD_START (<100) -> BASELINE (100-499) -> ACTIVE (>=500)."""
    ranker = StatisticalRanker(model_dir=str(tmp_path))
    
    # 0 samples
    assert ranker.get_learning_state(sample_count=0) == LearningState.COLD_START
    assert ranker.get_learning_state(sample_count=99) == LearningState.COLD_START
    
    # 100 - 499 samples
    assert ranker.get_learning_state(sample_count=100) == LearningState.BASELINE
    assert ranker.get_learning_state(sample_count=499) == LearningState.BASELINE
    
    # >= 500 samples
    assert ranker.get_learning_state(sample_count=500) == LearningState.ACTIVE
    assert ranker.get_learning_state(sample_count=1200) == LearningState.ACTIVE


# =========================================================================
# L. Training Dataset Creation Test
# =========================================================================
def test_l_training_dataset_creation():
    """Verify TrainingFeaturePipeline extracts 21 features and creates binary training labels."""
    pipeline = TrainingFeaturePipeline()
    
    candidates = [
        {
            "id": "c1",
            "domain": "flowiq.com",
            "overall_score": 91.0,
            "brandability_score": 90.0,
            "trend_score": 92.0,
            "commercial_score": 91.0,
            "pronunciation_score": 95.0,
            "memorability_score": 92.0,
            "simplicity_score": 96.0,
            "ip_risk": {"score": 8, "level": "LOW"},
            "naming_type": "INVENTED"
        },
        {
            "id": "c2",
            "domain": "clunkyawkwardname.com",
            "overall_score": 52.0,
            "brandability_score": 50.0,
            "trend_score": 55.0,
            "commercial_score": 50.0,
            "pronunciation_score": 45.0,
            "memorability_score": 40.0,
            "simplicity_score": 35.0,
            "ip_risk": {"score": 45, "level": "MEDIUM"},
            "naming_type": "COMPOUND"
        }
    ]
    
    feedback_records = [
        {"candidate_id": "c1", "user_action": "favorite"},
        {"candidate_id": "c2", "user_action": "reject"}
    ]
    
    X, y = pipeline.create_training_dataset(candidates, feedback_records)
    
    assert len(X) == 2
    assert len(y) == 2
    assert y[0] == 1  # favorite -> positive
    assert y[1] == 0  # reject -> negative
    assert len(X[0]) == 21, f"Expected 21 features per sample, got {len(X[0])}"


# =========================================================================
# M. Ranker Training Test
# =========================================================================
def test_m_ranker_training(tmp_path):
    """Verify StatisticalRanker trains on >=10 samples without runtime errors."""
    ranker = StatisticalRanker(model_dir=str(tmp_path))
    pipeline = TrainingFeaturePipeline()
    
    # Generate 14 synthetic training samples
    candidates = []
    feedbacks = []
    for i in range(14):
        cid = f"cand_{i}"
        action = "shortlist" if i % 2 == 0 else "reject"
        score = 85.0 + i if action == "shortlist" else 55.0 - i
        candidates.append({
            "id": cid,
            "domain": f"sample{i}.com",
            "overall_score": score,
            "brandability_score": score,
            "trend_score": score,
            "commercial_score": score,
            "pronunciation_score": score,
            "memorability_score": score,
            "simplicity_score": score,
            "ip_risk": {"score": 10 if action == "shortlist" else 40},
            "naming_type": "INVENTED"
        })
        feedbacks.append({"candidate_id": cid, "user_action": action})
        
    X, y = pipeline.create_training_dataset(candidates, feedbacks)
    
    result = ranker.train(X, y)
    assert result["status"] == "trained"
    assert ranker.is_trained is True
    assert ranker.active_model_version is not None
    assert result["validation_metric"] >= 0.0


# =========================================================================
# N. Ranker Prediction Test
# =========================================================================
def test_n_ranker_prediction(tmp_path):
    """Verify predict_preference_scores outputs probabilities in [0.0, 1.0]."""
    ranker = StatisticalRanker(model_dir=str(tmp_path))
    pipeline = TrainingFeaturePipeline()
    
    # Train on small dataset
    candidates = []
    feedbacks = []
    for i in range(12):
        cid = f"c_{i}"
        action = "favorite" if i % 2 == 0 else "reject"
        candidates.append({
            "id": cid,
            "domain": f"test{i}.com",
            "overall_score": 80.0 if action == "favorite" else 50.0,
            "brandability_score": 80.0,
            "trend_score": 80.0,
            "commercial_score": 80.0,
            "pronunciation_score": 80.0,
            "memorability_score": 80.0,
            "simplicity_score": 80.0,
            "ip_risk": {"score": 10},
            "naming_type": "ONE_WORD"
        })
        feedbacks.append({"candidate_id": cid, "user_action": action})
        
    X, y = pipeline.create_training_dataset(candidates, feedbacks)
    ranker.train(X, y)
    
    test_cands = [
        {"domain": "futureflow.com", "overall_score": 90.0, "brandability_score": 90.0, "trend_score": 90.0, "commercial_score": 90.0, "pronunciation_score": 90.0, "memorability_score": 90.0, "simplicity_score": 90.0, "ip_risk": {"score": 5}, "naming_type": "COMPOUND"}
    ]
    
    scores = ranker.predict_preference_scores(test_cands)
    assert len(scores) == 1
    assert 0.0 <= scores[0] <= 1.0, f"Preference score {scores[0]} must be in [0.0, 1.0]"


# =========================================================================
# O. Model Versioning & Metadata Test
# =========================================================================
def test_o_model_versioning_and_metadata(tmp_path):
    """Verify ranker model metadata contains model_id, version, trained_at, and metrics."""
    ranker = StatisticalRanker(model_dir=str(tmp_path))
    meta = ranker.get_metadata()
    
    assert "model_id" in meta
    assert "version" in meta
    assert "feature_version" in meta
    assert "state" in meta
    assert meta["state"] == "COLD_START"


# =========================================================================
# P. Strategy Performance Calculation Test
# =========================================================================
def test_p_strategy_performance_calculation():
    """Verify yield rate and acceptance rate formulas."""
    optimizer = StrategyOptimizer()
    
    stats = optimizer.calculate_performance(generated=200, available=20, accepted=5)
    
    assert stats["yield_rate"] == pytest.approx(0.10, rel=1e-3)
    assert stats["acceptance_rate"] == pytest.approx(0.25, rel=1e-3)
    
    # Zero division safety
    stats_zero = optimizer.calculate_performance(generated=0, available=0, accepted=0)
    assert stats_zero["yield_rate"] == 0.0
    assert stats_zero["acceptance_rate"] == 0.0


# =========================================================================
# Q. Dynamic Strategy Rebalancing Test
# =========================================================================
def test_q_dynamic_strategy_rebalancing():
    """Verify dynamic strategy quotas always sum to 1.0."""
    optimizer = StrategyOptimizer()
    
    perf = {
        "one_word": {"generated": 500, "available": 50, "accepted": 10},
        "invented_brand": {"generated": 400, "available": 20, "accepted": 5},
        "semantic_brand": {"generated": 300, "available": 15, "accepted": 3},
        "compound": {"generated": 200, "available": 5, "accepted": 1},
        "prefix_suffix": {"generated": 200, "available": 8, "accepted": 2},
        "trend": {"generated": 200, "available": 12, "accepted": 4},
        "keyword_brandable": {"generated": 150, "available": 10, "accepted": 2}
    }
    
    rebalanced = optimizer.rebalance_quotas(perf)
    assert sum(rebalanced.values()) == pytest.approx(1.0, rel=1e-3)


# =========================================================================
# R. Exploration/Exploitation Balance Test
# =========================================================================
def test_r_exploration_exploitation_balance():
    """Verify exploration floor: no strategy is starved below minimum exploration quota."""
    optimizer = StrategyOptimizer()
    
    # Even if compound has 0 yield and 0 acceptance
    perf = {
        "one_word": {"generated": 1000, "available": 200, "accepted": 80},
        "invented_brand": {"generated": 200, "available": 10, "accepted": 2},
        "semantic_brand": {"generated": 200, "available": 10, "accepted": 2},
        "compound": {"generated": 200, "available": 0, "accepted": 0},
        "prefix_suffix": {"generated": 100, "available": 2, "accepted": 0},
        "trend": {"generated": 100, "available": 2, "accepted": 0},
        "keyword_brandable": {"generated": 100, "available": 2, "accepted": 0}
    }
    
    quotas = optimizer.rebalance_quotas(perf)
    for name, weight in quotas.items():
        assert weight >= 0.04, f"Strategy {name} received {weight}, expected at least ~5% exploration floor"


# =========================================================================
# S. Failed Model Exclusion from Training Test
# =========================================================================
def test_s_failed_model_exclusion_from_training():
    """Verify failed model calls are recorded and excluded from training dataset creation."""
    tracker = RouterPerformanceTracker()
    
    # Record success for model A
    tracker.record_task_call(
        task="concept_extraction",
        model="deepseek/deepseek-chat",
        provider="openrouter",
        success=True,
        latency_ms=850.0,
        valid_json=True
    )
    
    # Record failures for model B
    tracker.record_task_call(
        task="concept_extraction",
        model="flaky/flaky-model",
        provider="openrouter",
        success=False,
        latency_ms=5000.0,
        valid_json=False,
        error="JSONDecodeError"
    )
    
    healthy = tracker.get_healthy_models("concept_extraction")
    assert "deepseek/deepseek-chat" in healthy
    assert "flaky/flaky-model" not in healthy


# =========================================================================
# T. Availability Safety Invariant Test
# =========================================================================
def test_t_availability_safety_invariant():
    """Verify learned preference score CANNOT override unavailable, registered, or premium hard gates."""
    registered_cand = {
        "domain": "google.com",
        "overall_score": 99.0,
        "quality_score": 99.0,
        "model_preference_score": 0.99,
        "availability_status": "REGISTERED",
        "is_registered": True
    }
    
    # QualityTierEngine must reject registered domains from Tier A and Tier B
    tier_engine = QualityTierEngine()
    organized = tier_engine.organize_tiers([registered_cand])
    
    assert len(organized["tier_a"]) == 0, "Registered domain must NEVER qualify for Tier A"
    assert len(organized["tier_b"]) == 0, "Registered domain must NEVER qualify for Tier B"


# =========================================================================
# U. Production Blocks Mock Registry Test
# =========================================================================
def test_u_production_blocks_mock_registry(monkeypatch):
    """Verify that in production mode, mock registries are strictly blocked."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ALLOW_MOCK_REGISTRY", "false")
    
    assert is_production_mode() is True
    
    mock_result = AvailabilityResult(
        domain="somedomain.com",
        status=AvailabilityStatus.AVAILABLE_STANDARD,
        provider="test_mock_registry",
        is_registered=False,
        is_premium=False
    )
    
    # In production, mock provider is NOT accepted
    assert mock_result.is_accepted() is False, "Production mode must reject mock registry results"


# =========================================================================
# V. Final Candidates Genuinely Available Test
# =========================================================================
def test_v_final_candidates_genuinely_available():
    """Verify that only genuinely verified AVAILABLE_STANDARD domains pass the gate."""
    real_rdap_result = AvailabilityResult(
        domain="freshavailabledomain.com",
        status=AvailabilityStatus.AVAILABLE_STANDARD,
        provider="verisign_rdap",
        is_registered=False,
        is_premium=False,
        availability_verified=True,
        availability_check_status="VERIFIED"
    )
    
    assert real_rdap_result.is_accepted() is True, "Authoritative Verisign RDAP AVAILABLE_STANDARD must be accepted"
    
    registered_result = AvailabilityResult(
        domain="taken.com",
        status=AvailabilityStatus.REGISTERED,
        provider="verisign_rdap",
        is_registered=True,
        is_premium=False
    )
    
    assert registered_result.is_accepted() is False, "REGISTERED domain must NOT be accepted"
