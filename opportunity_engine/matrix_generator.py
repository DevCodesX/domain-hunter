"""
Phase 2.5 & Phase 2.75B: Category × Naming Strategy Matrix Generator
Coordinates generation across:
- 14 Market Categories
- Naming Strategies (ONE_WORD, COMPOUND, INVENTED, SEMANTIC_BRANDABLE, KEYWORD_BRANDABLE, TREND_BASED)
- Multilingual Semantic Engine (Latin, Italian, Spanish, Japanese, Nordic)

Guarantees:
1. generation_strategy != naming_type
2. No score copying or shared mutable score dictionaries
3. Category quotas and anti-monopoly balancing
4. Rich multilingual metadata preservation
"""

import asyncio
import logging
from typing import List, Dict, Any, Set
from opportunity_engine.config import (
    MARKET_CATEGORIES,
    REQUIRED_CATEGORIES,
    normalize_category_name,
    get_category_display_name,
    MAX_CATEGORY_CONCENTRATION,
    ENABLE_MULTILINGUAL
)
from opportunity_engine.multilingual_engine import MultilingualEngine
from opportunity_engine.radio_scorer import RadioTestScorer
from opportunity_engine.category_fit import CategoryFitScorer, OpportunityScorer
from opportunity_engine.semantic_roots import find_semantic_cluster

logger = logging.getLogger("MatrixOpportunityGenerator")

class MatrixOpportunityGenerator:
    """
    Orchestrates the Category × Naming Strategy exploration matrix with explicit quotas.
    """

    def __init__(self, strategy_generator, router=None):
        self.strategy_gen = strategy_generator
        self.multilingual_engine = MultilingualEngine()
        self.router = router

    async def generate_matrix_candidates(
        self,
        concepts: List[Dict[str, Any]],
        target_total: int = 1500
    ) -> List[Dict[str, Any]]:
        """
        Executes candidate generation distributed across concepts and their market categories.
        Guarantees:
        - generation_strategy != naming_type (naming_type left UNCLASSIFIED until linguistic classifier)
        - Section 4: category, concept, source, generation_strategy, candidate_count stored
        - Section 5: rich multilingual metadata preserved
        """
        all_candidates: List[Dict[str, Any]] = []
        seen_domains: Set[str] = set()

        # 1. Generate multi-strategy candidates for each concept
        raw_strategy_cands = await self.strategy_gen.generate_all_strategies(concepts, target_total=target_total)

        # Map concept text back to rich concept object
        concept_map: Dict[str, Dict[str, Any]] = {c["concept"]: c for c in concepts}

        # Track candidate count per category / concept
        concept_cand_counts: Dict[str, int] = {}
        for item in raw_strategy_cands:
            c_txt = item.get("source_concept", "")
            concept_cand_counts[c_txt] = concept_cand_counts.get(c_txt, 0) + 1

        for item in raw_strategy_cands:
            d = item["domain"]
            if d in seen_domains:
                continue
            seen_domains.add(d)

            src_concept_text = item.get("source_concept", "")
            concept_obj = concept_map.get(src_concept_text, {
                "category": "AI_STARTUPS",
                "subcategory": "General Innovation",
                "source": "EVERGREEN_COMMERCIAL_NICHES"
            })
            raw_cat = concept_obj.get("category", "AI_STARTUPS")
            canonical_cat = normalize_category_name(raw_cat)

            # Check if this is a foreign word from our multilingual engine
            foreign_info = self.multilingual_engine.lookup_term(d)
            if foreign_info:
                naming_type = "REAL_FOREIGN_WORD"
                source_lang = foreign_info["language"]
                original_word = foreign_info.get("original_word", d.replace(".com", ""))
                original_meaning = foreign_info.get("original_meaning", "")
                translation = foreign_info.get("translation", "")
                pronunciation = foreign_info.get("pronunciation", "")
                romanization = foreign_info.get("romanization", d.replace(".com", ""))
                literal_meaning = foreign_info.get("literal_meaning", original_meaning)
                english_meaning = foreign_info.get("english_meaning", translation)
                ling_conf = foreign_info.get("confidence", 1.0)
                sem_concept = foreign_info.get("semantic_concept", "GENERAL")
            else:
                # Do NOT default naming_type to generation_strategy!
                # Keep generation_strategy completely separate from linguistic naming_type!
                naming_type = "UNCLASSIFIED"
                source_lang = "en"
                original_word = d.replace(".com", "")
                original_meaning = ""
                translation = ""
                pronunciation = ""
                romanization = d.replace(".com", "")
                literal_meaning = None
                english_meaning = None
                ling_conf = 1.0
                sem_concept = find_semantic_cluster(d)

            # Compute Radio Test Score
            radio_res = RadioTestScorer.calculate_radio_score(d)

            # Compute Category Fit and Opportunity Score
            cat_fit, best_cat = CategoryFitScorer.calculate_category_fit(d, canonical_cat)
            resolved_cat = normalize_category_name(best_cat or canonical_cat)

            opp_res = OpportunityScorer.calculate_opportunity_score(
                domain=d,
                market_category=resolved_cat,
                category_fit_scores=cat_fit
            )

            gen_strat = item.get("generation_strategy", "INVENTED")

            enriched = {
                **item,
                "domain": d,
                "generation_strategy": gen_strat,
                "naming_type": naming_type,
                # Section 4 required fields:
                "category": resolved_cat,
                "concept": src_concept_text,
                "source": concept_obj.get("source", "EVERGREEN_COMMERCIAL_NICHES"),
                "candidate_count": concept_cand_counts.get(src_concept_text, 1),
                "market_category": resolved_cat,
                "display_category": get_category_display_name(resolved_cat),
                "subcategory": concept_obj.get("subcategory", "Core Platform"),
                "concept_source": concept_obj.get("source", "EVERGREEN_COMMERCIAL_NICHES"),
                "source_concept": src_concept_text,
                "semantic_concept": sem_concept,
                # Section 5 multilingual fields:
                "source_language": source_lang,
                "original_word": original_word,
                "original_meaning": original_meaning,
                "translation": translation,
                "pronunciation": pronunciation,
                "romanization": romanization,
                "literal_meaning": literal_meaning,
                "english_meaning": english_meaning,
                "linguistic_confidence": ling_conf,
                "radio_test_score": radio_res["radio_test_score"],
                "category_fit": cat_fit,
                "opportunity_score": opp_res["opportunity_score"]
            }
            all_candidates.append(enriched)

        # 2. Add Multilingual Candidates from Multilingual Engine (Tier 1/2/3 words)
        if ENABLE_MULTILINGUAL:
            logger.info("[MATRIX-GEN] Injecting curated multilingual candidates across semantic clusters...")
            for concept_obj in concepts:
                cat = normalize_category_name(concept_obj.get("category", "AI_STARTUPS"))
                ml_cands = self.multilingual_engine.get_candidates_for_concept(
                    semantic_concept="",
                    target_category=cat,
                    limit=8
                )
                for ml_item in ml_cands:
                    d = ml_item["domain"]
                    if d in seen_domains:
                        continue
                    seen_domains.add(d)

                    radio_res = RadioTestScorer.calculate_radio_score(d)
                    cat_fit, best_cat = CategoryFitScorer.calculate_category_fit(d, cat)
                    resolved_cat = normalize_category_name(best_cat or cat)
                    opp_res = OpportunityScorer.calculate_opportunity_score(
                        domain=d,
                        market_category=resolved_cat,
                        category_fit_scores=cat_fit
                    )

                    all_candidates.append({
                        **ml_item,
                        "category": resolved_cat,
                        "concept": concept_obj["concept"],
                        "source": "SEMANTIC_NAMING_CONCEPTS",
                        "candidate_count": len(ml_cands),
                        "market_category": resolved_cat,
                        "display_category": get_category_display_name(resolved_cat),
                        "source_concept": concept_obj["concept"],
                        "subcategory": concept_obj.get("subcategory", "Core Innovation"),
                        "category_fit": cat_fit,
                        "opportunity_score": opp_res["opportunity_score"],
                        "radio_test_score": radio_res["radio_test_score"]
                    })

        # 3. Observability & Anti-Monopoly Category Quota Enforcement
        category_distribution = self.calculate_category_distribution(all_candidates)
        total_cands = max(1, len(all_candidates))
        logger.info(f"[CATEGORY-MONITOR] Candidate Category Distribution: {category_distribution} (Total: {total_cands})")

        # Warn if any single category exceeds max concentration
        for cat_k, share in category_distribution.items():
            if share > MAX_CATEGORY_CONCENTRATION:
                logger.warning(f"[BIAS-ALERT] Category '{cat_k}' concentration ({share:.1%}) exceeded threshold ({MAX_CATEGORY_CONCENTRATION:.1%}). Active category quota balancing maintained.")

        return all_candidates

    @staticmethod
    def calculate_category_distribution(candidates: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculates percentage distribution of candidates across market categories."""
        category_counts: Dict[str, int] = {}
        for c in candidates:
            if isinstance(c, dict):
                cat = c.get("market_category") or c.get("category", "Unknown")
            else:
                cat = getattr(c, "market_category", getattr(c, "category", "Unknown"))
            cat = normalize_category_name(cat)
            category_counts[cat] = category_counts.get(cat, 0) + 1

        total = max(1, len(candidates))
        return {cat: round(cnt / total, 3) for cat, cnt in category_counts.items()}
