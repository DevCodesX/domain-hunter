"""
Comprehensive Automated Test Suite for:
PHASE 2.5: Opportunity & Semantic Expansion Engine

Tests all required Phase 2.5 capabilities:
1. Semantic Root Library retrieval, category affinity, and cluster matching
2. Multilingual Engine dictionary lookup (verified translations, no hallucination)
3. Foreign word brandability filtering & phonetic difficulty analysis
4. Radio / spelling-from-sound scoring (radio_test_score)
5. Category fit scoring across all 9 market categories
6. Opportunity scoring (market size, commercial intent, buyer density, domain fit)
7. Multi-source concept discovery (4 sources, category quota enforcement, sports cap)
8. Matrix generation (Category × Naming Strategy × Multilingual matrix)
9. Category concentration monitoring and bias detection
10. Diversity engine with category quotas (preventing monopolization without lowering quality)
11. Provider failure resilience & dictionary fallback safety
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from opportunity_engine.config import (
    MARKET_CATEGORIES,
    MAX_CATEGORY_CONCENTRATION,
    ENABLE_MULTILINGUAL,
    get_category_allocations
)
from opportunity_engine.semantic_roots import (
    SEMANTIC_ROOT_LIBRARY,
    get_roots_for_category,
    find_semantic_cluster
)
from opportunity_engine.multilingual_engine import (
    MultilingualEngine,
    MULTILINGUAL_DICTIONARY
)
from opportunity_engine.radio_scorer import RadioTestScorer
from opportunity_engine.category_fit import (
    CategoryFitScorer,
    OpportunityScorer
)
from opportunity_engine.concept_discovery import (
    ConceptDiscoveryEngine,
    EVERGREEN_NICHES,
    STARTUP_SIGNALS
)
from opportunity_engine.matrix_generator import MatrixOpportunityGenerator
from quality_engine.diversity_engine import DiversityEngine


# =========================================================================
# 1. Semantic Root Library Tests
# =========================================================================

def test_semantic_root_library_retrieval():
    """Verify all 7 core commercial concepts exist and contain roots."""
    required_concepts = [
        "CAPABILITY", "SPEED_MOVEMENT", "INTELLIGENCE_CLARITY",
        "CONNECTION", "BUILDING", "GROWTH", "TRUST_SECURITY"
    ]
    for concept in required_concepts:
        assert concept in SEMANTIC_ROOT_LIBRARY, f"Concept {concept} must exist"
        data = SEMANTIC_ROOT_LIBRARY[concept]
        roots = data.get("roots", [])
        assert len(roots) > 0, f"Concept {concept} must have roots"
        assert all(isinstance(r, str) for r in roots)


def test_semantic_root_category_affinity():
    """Verify category affinity correctly identifies relevant semantic roots."""
    ai_roots = get_roots_for_category("AI & Technology")
    assert len(ai_roots) > 0
    # AI has affinity with intelligence, capability, speed, and building
    assert "mind" in ai_roots or "vision" in ai_roots or "engine" in ai_roots or "craft" in ai_roots

    fin_roots = get_roots_for_category("Finance")
    assert len(fin_roots) > 0
    assert "true" in fin_roots or "secure" in fin_roots or "scale" in fin_roots or "bloom" in fin_roots


def test_semantic_root_cluster_matching():
    """Verify finding the nearest semantic cluster from concept text."""
    cluster_ai = find_semantic_cluster("deep intelligence clarity and wisdom")
    assert cluster_ai == "INTELLIGENCE_CLARITY"

    cluster_spd = find_semantic_cluster("rapid velocity sprint and fast execution")
    assert cluster_spd == "SPEED_MOVEMENT"

    cluster_sec = find_semantic_cluster("secure truth audit and safe vault")
    assert cluster_sec == "TRUST_SECURITY"


# =========================================================================
# 2. Multilingual Engine & Factual Lexical Dictionary Tests
# =========================================================================

def test_multilingual_lexical_dictionary():
    """Verify dictionary entries are factually verified without LLM hallucination."""
    engine = MultilingualEngine()
    assert len(engine.dictionary) >= 20, "Should have rich multilingual dictionary"

    # Test Latin entry
    veritas = engine.lookup_term("veritas")
    assert veritas is not None
    assert veritas["language"] == "Latin"
    assert "truth" in veritas["english_meaning"].lower()
    assert veritas["confidence"] >= 0.95

    # Test Italian entry
    volo = engine.lookup_term("volo")
    assert volo is not None
    assert volo["language"] == "Italian"
    assert "flight" in volo["english_meaning"].lower() or "soaring" in volo["english_meaning"].lower()

    # Test Greek entry
    logos = engine.lookup_term("logos")
    assert logos is not None
    assert logos["language"] == "Greek"

    # Test Japanese entry
    zen = engine.lookup_term("zen")
    assert zen is not None
    assert zen["language"] == "Japanese"


def test_multilingual_brandability_filter():
    """Verify brandability filter accurately screens foreign words."""
    engine = MultilingualEngine()

    # Good brandable word: short, clean phonetics
    eval_veritas = engine.evaluate_foreign_word_brandability("veritas")
    assert eval_veritas["passes_foreign_brandability_gate"] is True
    assert eval_veritas["brandability"] >= 65
    assert eval_veritas["length"] == 7

    # Clumsy foreign words with awkward clusters fail
    eval_clumsy = engine.evaluate_foreign_word_brandability("schmetterling")
    assert eval_clumsy["passes_foreign_brandability_gate"] is False


def test_multilingual_candidate_generation():
    """Verify retrieval of multilingual domain candidates."""
    engine = MultilingualEngine()
    candidates = engine.get_candidates_for_concept(
        semantic_concept="SPEED_MOVEMENT",
        target_category="AI & Technology",
        limit=5
    )
    assert len(candidates) > 0
    for cand in candidates:
        assert cand["domain"].endswith(".com")
        assert cand["naming_type"] == "REAL_FOREIGN_WORD"
        assert cand["source_language"] in ["Latin", "Italian", "Spanish", "French", "Greek", "German", "Nordic", "Japanese"]
        assert cand["english_meaning"] != ""
        assert cand["linguistic_confidence"] >= 0.85
        assert cand["radio_test_score"] >= 50


# =========================================================================
# 3. Radio / Spelling-From-Sound Scorer Tests
# =========================================================================

def test_radio_test_scorer():
    """Verify radio test scoring based on deterministic phonetics."""
    # Clear, intuitive phonetic domains should score very high
    res_lumina = RadioTestScorer.calculate_radio_score("lumina.com")
    assert res_lumina["radio_test_score"] >= 80, f"Expected lumina to have high radio score, got {res_lumina['radio_test_score']}"

    res_veritas = RadioTestScorer.calculate_radio_score("veritas.com")
    assert res_veritas["radio_test_score"] >= 80

    # Words with confusing silent letters or awkward digraphs score lower
    res_phthisis = RadioTestScorer.calculate_radio_score("phthisis.com")
    assert res_phthisis["radio_test_score"] <= 75, f"Expected phthisis to have lower radio score, got {res_phthisis['radio_test_score']}"
    assert res_phthisis["radio_test_score"] < res_lumina["radio_test_score"]

    # Bounds check
    assert 0 <= res_lumina["radio_test_score"] <= 100
    assert 0 <= res_phthisis["radio_test_score"] <= 100


# =========================================================================
# 4. Category Fit Scorer Tests
# =========================================================================

def test_category_fit_scoring():
    """Verify category fit evaluates across all 9 market categories."""
    # AI domain
    ai_fit, ai_best = CategoryFitScorer.calculate_category_fit("agentflow.com", source_category="AI & Technology")
    assert "ai_tech" in ai_fit or "ai_startups" in ai_fit
    assert "micro_saas" in ai_fit
    assert len(ai_fit) >= 9
    assert ai_fit.get("ai_tech", ai_fit.get("ai_startups", 0)) >= 70
    assert ai_best in ["AI & Technology", "AI_STARTUPS"]

    # Finance domain
    fin_fit, fin_best = CategoryFitScorer.calculate_category_fit("payvault.com", source_category="Finance")
    assert fin_fit["finance"] >= 70
    assert fin_fit["finance"] > fin_fit.get("sports_betting", 0)

    # Geo services domain
    geo_fit, geo_best = CategoryFitScorer.calculate_category_fit("roofrepair.com", source_category="Geo Services")
    assert geo_fit["geo_services"] >= 70


# =========================================================================
# 5. Opportunity Scorer Tests
# =========================================================================

def test_opportunity_scorer():
    """Verify opportunity score calculation separates commercial potential from naming quality."""
    # High-opportunity category (AI, B2B High-CPC, Finance)
    fit_scores, _ = CategoryFitScorer.calculate_category_fit("agentcore.com", "AI & Technology")
    ai_opp = OpportunityScorer.calculate_opportunity_score(
        domain="agentcore.com",
        market_category="AI & Technology",
        category_fit_scores=fit_scores,
        trend_score=85
    )
    assert 70 <= ai_opp["opportunity_score"] <= 100
    assert ai_opp["market_size"] >= 80
    assert ai_opp["commercial_intent"] >= 80

    # High-CPC B2B
    fit_legal, _ = CategoryFitScorer.calculate_category_fit("legalguard.com", "B2B High-CPC / Commercial Services")
    legal_opp = OpportunityScorer.calculate_opportunity_score(
        domain="legalguard.com",
        market_category="B2B High-CPC / Commercial Services",
        category_fit_scores=fit_legal,
        trend_score=80
    )
    assert legal_opp["opportunity_score"] >= 70
    assert legal_opp["commercial_intent"] >= 85

    # Casual / sports category has lower commercial intent than B2B High-CPC
    fit_sports, _ = CategoryFitScorer.calculate_category_fit("betdaily.com", "Sports & Entertainment")
    sports_opp = OpportunityScorer.calculate_opportunity_score(
        domain="betdaily.com",
        market_category="Sports & Entertainment",
        category_fit_scores=fit_sports,
        trend_score=80
    )
    assert sports_opp["commercial_intent"] < legal_opp["commercial_intent"]


# =========================================================================
# 6. Multi-Source Concept Discovery & Bias Prevention Tests
# =========================================================================

@pytest.mark.asyncio
async def test_multi_source_concept_discovery_diversity():
    """
    CRITICAL TEST: Verify concept discovery draws from all 4 sources
    and prevents sports/betting from dominating the concept universe.
    """
    discovery = ConceptDiscoveryEngine()

    # Raw trending items (simulate real world where news is full of sports headlines)
    raw_trending = [
        "Cardinals vs Brewers live score",
        "Spain vs England Euro final betting odds",
        "Kylie Minogue world tour",
        "Algeria football standings",
        "UFC championship fight highlights",
        "NFL draft picks predictions"
    ]

    concepts = await discovery.discover_concepts(trending_context=raw_trending, target_count=12)

    assert len(concepts) >= 8, f"Should discover multiple concepts, got {len(concepts)}"

    # Check sources representation
    sources = {c["source"] for c in concepts}
    assert "EVERGREEN_COMMERCIAL_NICHES" in sources
    assert "STARTUP_MARKET_SIGNALS" in sources
    assert "SEMANTIC_NAMING_CONCEPTS" in sources

    # Check category distribution
    categories = [c["category"] for c in concepts]
    assert any(cat in ["AI & Technology", "AI_STARTUPS", "Micro-SaaS & Tooling", "MICRO_SAAS"] for cat in categories)
    assert any(cat in ["Finance", "FINANCE", "B2B High-CPC / Commercial Services", "B2B_HIGH_CPC"] for cat in categories)

    # Sports/betting MUST NOT dominate
    sports_count = sum(1 for c in concepts if "sport" in c["category"].lower() or "bet" in c["category"].lower())
    sports_ratio = sports_count / len(concepts)
    assert sports_ratio <= 0.15, f"Sports betting ratio must be <= 15%, got {sports_ratio:.1%}"


# =========================================================================
# 7. Matrix Opportunity Generator Tests
# =========================================================================

@pytest.mark.asyncio
async def test_matrix_opportunity_generator():
    """Verify matrix generator produces diversified candidates with Phase 2.5 metadata."""
    # Mock strategy generator
    mock_strategy_gen = MagicMock()
    mock_strategy_gen.generate_all_strategies = AsyncMock(return_value=[
        {"domain": "agentflow.com", "generation_strategy": "COMPOUND", "source_concept": "AI agents workflow automation"},
        {"domain": "paypulse.com", "generation_strategy": "COMPOUND", "source_concept": "FinTech cross-border payments"},
        {"domain": "lawcore.com", "generation_strategy": "COMPOUND", "source_concept": "Commercial contract compliance"},
        {"domain": "toolbase.com", "generation_strategy": "COMPOUND", "source_concept": "Developer productivity tools"},
        {"domain": "nexuscrypto.com", "generation_strategy": "COMPOUND", "source_concept": "Crypto treasury rails"},
        {"domain": "veritas.com", "generation_strategy": "ONE_WORD", "source_concept": "Truth and fidelity audit"}
    ])

    generator = MatrixOpportunityGenerator(strategy_generator=mock_strategy_gen)

    test_concepts = [
        {"concept": "AI agents workflow automation", "category": "AI & Technology", "subcategory": "AI Agents", "source": "STARTUP_MARKET_SIGNALS"},
        {"concept": "FinTech cross-border payments", "category": "Finance", "subcategory": "FinTech", "source": "EVERGREEN_COMMERCIAL_NICHES"},
        {"concept": "Commercial contract compliance", "category": "B2B High-CPC / Commercial Services", "subcategory": "Legal Services", "source": "EVERGREEN_COMMERCIAL_NICHES"}
    ]

    candidates = await generator.generate_matrix_candidates(concepts=test_concepts, target_total=25)

    assert len(candidates) >= 5, f"Expected candidates, got {len(candidates)}"

    for cand in candidates:
        assert cand["domain"].endswith(".com")
        assert cand["market_category"] in MARKET_CATEGORIES
        assert "radio_test_score" in cand
        assert 0 <= cand["radio_test_score"] <= 100
        assert "category_fit" in cand
        assert isinstance(cand["category_fit"], dict)
        assert "opportunity_score" in cand
        assert 0 <= cand["opportunity_score"] <= 100

    # Verify category distribution calculation
    distribution = generator.calculate_category_distribution(candidates)
    assert isinstance(distribution, dict)
    assert len(distribution) > 0


# =========================================================================
# 8. Diversity Selection with Category Quota Tests
# =========================================================================

def test_diversity_selection_category_quota():
    """Verify DiversityEngine limits any single category to prevent monopolization."""
    diversity = DiversityEngine()

    candidates = []
    # 10 sports domains with high scores
    sports_names = ["betscore.com", "oddsline.com", "gamepulse.com", "parlayking.com", "wagertrack.com", "sportsgrid.com", "matchpoint.com", "stadiumrun.com", "fieldgoal.com", "puckdrop.com"]
    for i, name in enumerate(sports_names):
        c = MagicMock()
        c.domain = name
        c.domain_name = name
        c.quality_score = 90 - i
        c.overall_score = 90 - i
        c.naming_type = "COMPOUND"
        c.generation_strategy = "COMPOUND"
        c.features = MagicMock()
        c.features.naming_type = "COMPOUND"
        c.features.syllables = 2
        c.market_category = "Sports & Entertainment"
        candidates.append(c)

    # 4 AI domains with good scores
    ai_names = ["agentflow.com", "cognicore.com", "synapsetech.com", "neuralbase.com"]
    for i, name in enumerate(ai_names):
        c = MagicMock()
        c.domain = name
        c.domain_name = name
        c.quality_score = 85 - i
        c.overall_score = 85 - i
        c.naming_type = "COMPOUND"
        c.generation_strategy = "COMPOUND"
        c.features = MagicMock()
        c.features.naming_type = "COMPOUND"
        c.features.syllables = 2
        c.market_category = "AI & Technology"
        candidates.append(c)

    # 3 Finance domains
    fin_names = ["payvault.com", "wealthstream.com", "settlequick.com"]
    for i, name in enumerate(fin_names):
        c = MagicMock()
        c.domain = name
        c.domain_name = name
        c.quality_score = 82 - i
        c.overall_score = 82 - i
        c.naming_type = "COMPOUND"
        c.generation_strategy = "COMPOUND"
        c.features = MagicMock()
        c.features.naming_type = "COMPOUND"
        c.features.syllables = 2
        c.market_category = "Finance"
        candidates.append(c)

    # Select top 10 diverse candidates with max 3 per category
    selected = diversity.select_diverse_candidates(
        candidates,
        target_count=10,
        min_quality_threshold=60,
        max_per_category=3
    )

    sports_selected = sum(1 for c in selected if getattr(c, "market_category", None) == "Sports & Entertainment")
    ai_selected = sum(1 for c in selected if getattr(c, "market_category", None) == "AI & Technology")
    fin_selected = sum(1 for c in selected if getattr(c, "market_category", None) == "Finance")

    assert sports_selected <= 3, f"Sports betting exceeded quota: {sports_selected}"
    assert ai_selected >= 3, f"AI should have filled its quota: {ai_selected}"
    assert fin_selected >= 2, f"Finance should have been selected: {fin_selected}"


# =========================================================================
# 9. Fallback & Provider Resilience Tests
# =========================================================================

@pytest.mark.asyncio
async def test_concept_discovery_fallback_on_empty_trending():
    """Verify discovery works smoothly even if Google Trends RSS is completely down/empty."""
    discovery = ConceptDiscoveryEngine()
    concepts = await discovery.discover_concepts(trending_context=[], target_count=10)
    assert len(concepts) >= 6
    assert any(c["category"] in ["AI & Technology", "AI_STARTUPS"] for c in concepts)
    assert any(c["category"] in ["B2B High-CPC / Commercial Services", "B2B_HIGH_CPC"] for c in concepts)


def test_multilingual_unknown_word_safety():
    """Verify looking up non-existent foreign words doesn't crash or hallucinate."""
    engine = MultilingualEngine()
    res = engine.lookup_term("totallyunknownword12345")
    assert res is None


if __name__ == "__main__":
    pytest.main(["-v", __file__])
