"""
Domain Hunter - Stage 4.5: Pre-Availability Ranking & Stratified Selection
========================================================================
Performs lightweight, deterministic pre-availability scoring and stratified
diversity selection BEFORE registry (RDAP/DoH) checks.

Guarantees:
1. ZERO external API calls (No LLM, No USPTO, No external Premium APIs).
2. Deeply leverages Phase 1 multi-signal anchoring (lexical, phonetic,
   semantic anchor, brandability heuristic, cluster penalties) for INVENTED.
3. Stratified diversity selection across 7 strategy/morphology buckets
   (REAL_WORD, COMPOUND, SEMANTIC, INVENTED_ANCHORED, PREFIX_SUFFIX, KEYWORD, MULTILINGUAL)
   so the registry scan does NOT get monopolized by any single strategy.
4. Prevents unanchored gibberish from consuming registry quotas.
"""

import math
from typing import Dict, Any, List, Optional
from quality_engine.invented_quality import (
    InventedQualityEvaluator,
    get_availability_pipeline_config,
    COMMERCIAL_ANCHOR_ROOTS
)
from quality_engine.config import RECOGNIZED_SEMANTIC_ROOTS, PHONOTACTIC_BAD_BIGRAMS, PHONOTACTIC_BAD_TRIGRAMS

try:
    from wordfreq import zipf_frequency
except ImportError:
    def zipf_frequency(word: str, lang: str = "en") -> float:
        return 0.0


def calculate_pre_availability_score(candidate: Dict[str, Any]) -> float:
    """
    Computes a low-cost, 100% deterministic pre-availability score (0-100)
    for a candidate prior to registry lookups.
    """
    domain = candidate.get("domain", "")
    label = candidate.get("structural_features", {}).get("label") or domain.replace(".com", "").strip().lower()
    char_len = len(label)
    
    naming_type = candidate.get("naming_type_info", {}).get("naming_type") or candidate.get("naming_type", "")
    strategy = candidate.get("generation_strategy", "")

    # 1. INVENTED candidates: Use Phase 1 InventedQualityEvaluator
    if naming_type == "INVENTED" or strategy == "INVENTED":
        evaluator = InventedQualityEvaluator.get_instance()
        inv_res = evaluator.evaluate_candidate(label)
        
        # Enrich candidate in-place with Phase 1 signals
        candidate["invented_subtype"] = inv_res.get("invented_subtype")
        candidate["invented_quality_tier"] = inv_res.get("invented_quality_tier")
        candidate["invented_quality_score"] = inv_res.get("invented_quality_score")
        candidate["invented_penalty"] = inv_res.get("invented_penalty", 0.0)
        candidate["brandability_heuristic_score"] = inv_res.get("brandability_heuristic_score")
        candidate["brandability_subscores"] = inv_res.get("brandability_subscores", {})
        candidate["lexical_proximity_score"] = inv_res.get("lexical_proximity_score")
        candidate["phonetic_proximity_score"] = inv_res.get("phonetic_proximity_score")
        candidate["semantic_anchor_score"] = inv_res.get("semantic_anchor_score")
        candidate["hear_to_spell_score"] = inv_res.get("brandability_subscores", {}).get("hear_to_spell", 70.0)

        # Pre-availability score: high for anchored & brandable, heavily penalized for gibberish
        raw_score = float(inv_res.get("invented_quality_score", 60.0))
        penalty = float(inv_res.get("invented_penalty", 0.0))
        score = max(10.0, min(100.0, raw_score - penalty))
        candidate["pre_availability_score"] = round(score, 2)
        return candidate["pre_availability_score"]

    # 2. REAL_WORD / ONE_WORD / REAL_FOREIGN_WORD candidates
    if naming_type in ["ONE_WORD", "REAL_WORD", "REAL_FOREIGN_WORD"] or strategy == "ONE_WORD":
        ow_info = candidate.get("one_word_features", {})
        real_word_score = float(ow_info.get("real_word_score", 85.0))
        zipf = float(ow_info.get("zipf_frequency", zipf_frequency(label, "en")))
        
        # Real English/foreign dictionary words have high organic value
        base = 86.0
        # Length preference: 4-6 chars = highest premium
        if char_len <= 6:
            base += 6.0
        elif char_len <= 8:
            base += 3.0
        elif char_len > 10:
            base -= 5.0
            
        # Frequency bonus
        if zipf >= 4.5:
            base += 6.0
        elif zipf >= 3.5:
            base += 3.0
        elif zipf < 2.0:
            base -= 4.0

        score = max(30.0, min(99.0, (base * 0.65) + (real_word_score * 0.35)))
        candidate["pre_availability_score"] = round(score, 2)
        return candidate["pre_availability_score"]

    # 3. COMPOUND, SEMANTIC_BRANDABLE, PREFIX_SUFFIX, KEYWORD candidates
    s_feat = candidate.get("structural_features", {})
    pron = float(s_feat.get("pronounceability_score", 75.0))
    simp = float(s_feat.get("spelling_simplicity", 75.0))
    
    score = 75.0
    # Length graduated preference
    if 5 <= char_len <= 8:
        score += 8.0
    elif 9 <= char_len <= 11:
        score += 4.0
    elif char_len >= 14:
        score -= 8.0

    # Pronounceability & simplicity flow
    score += (pron - 70.0) * 0.20
    score += (simp - 70.0) * 0.15

    # Semantic root recognition bonus
    has_root = any(r in label for r in RECOGNIZED_SEMANTIC_ROOTS or COMMERCIAL_ANCHOR_ROOTS)
    if has_root or naming_type == "SEMANTIC_BRANDABLE" or strategy == "SEMANTIC_BRANDABLE":
        score += 6.0

    # Bad n-gram / awkward transition check
    bad_bigrams = [bg for bg in PHONOTACTIC_BAD_BIGRAMS if bg in label]
    bad_trigrams = [tg for tg in PHONOTACTIC_BAD_TRIGRAMS if tg in label]
    if bad_bigrams or bad_trigrams:
        score -= (len(bad_bigrams) * 4.0) + (len(bad_trigrams) * 6.0)

    # Hear-to-spell heuristic
    evaluator = InventedQualityEvaluator.get_instance()
    hear_spell = evaluator.compute_hear_to_spell_score(label)
    candidate["hear_to_spell_score"] = hear_spell
    if hear_spell < 65.0:
        score -= (65.0 - hear_spell) * 0.25

    score = max(15.0, min(98.0, score))
    candidate["pre_availability_score"] = round(score, 2)
    return candidate["pre_availability_score"]


def rank_and_stratify_candidates(
    candidates: List[Dict[str, Any]],
    target_total: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Computes pre_availability_score on all candidates and stratifies them into
    an interleaved queue respecting diversity quotas across the 7 categories:
    - real_word: 20%
    - compound: 20%
    - semantic: 20%
    - invented_anchored: 15%
    - prefix_suffix: 10%
    - keyword: 10%
    - multilingual_other: 5%

    Returns the full prioritized candidate queue with pre_availability_score populated.
    """
    if not candidates:
        return []

    cfg = get_availability_pipeline_config()
    quotas = cfg.get("stratified_quotas", {
        "real_word": 0.20,
        "compound": 0.20,
        "semantic": 0.20,
        "invented_anchored": 0.15,
        "prefix_suffix": 0.10,
        "keyword": 0.10,
        "multilingual_other": 0.05
    })

    # 1. Compute pre-availability score on every candidate
    for c in candidates:
        calculate_pre_availability_score(c)

    # 2. Partition into strategy/morphology buckets
    buckets: Dict[str, List[Dict[str, Any]]] = {
        "real_word": [],
        "compound": [],
        "semantic": [],
        "invented_anchored": [],
        "prefix_suffix": [],
        "keyword": [],
        "multilingual_other": []
    }

    for c in candidates:
        nt = c.get("naming_type_info", {}).get("naming_type") or c.get("naming_type", "")
        strat = c.get("generation_strategy", "")
        inv_tier = c.get("invented_quality_tier")
        inv_sub = c.get("invented_subtype")

        if nt in ["ONE_WORD", "REAL_WORD"] or strat == "ONE_WORD":
            buckets["real_word"].append(c)
        elif nt == "COMPOUND" or strat == "COMPOUND":
            buckets["compound"].append(c)
        elif nt == "SEMANTIC_BRANDABLE" or strat == "SEMANTIC_BRANDABLE":
            buckets["semantic"].append(c)
        elif nt == "INVENTED" or strat == "INVENTED":
            # Only ANCHORED or non-weak invented candidates go to invented_anchored
            if inv_tier in ["STRONG", "MODERATE"] or (inv_sub and inv_sub != "UNANCHORED"):
                buckets["invented_anchored"].append(c)
            else:
                # Weak or unanchored gibberish goes to lowest priority bucket
                buckets["multilingual_other"].append(c)
        elif strat in ["PREFIX_SUFFIX", "AFFIX"]:
            buckets["prefix_suffix"].append(c)
        elif strat in ["KEYWORD", "CATEGORY_KEYWORD"]:
            buckets["keyword"].append(c)
        else:
            buckets["multilingual_other"].append(c)

    # 3. Sort and interleave categories in each bucket so no single category dominates the top of the queue
    for k in buckets:
        cat_map: Dict[str, List[Dict[str, Any]]] = {}
        for item in buckets[k]:
            c_name = item.get("market_category") or item.get("category") or "OTHER"
            cat_map.setdefault(c_name, []).append(item)
        for cat_list in cat_map.values():
            cat_list.sort(key=lambda x: x.get("pre_availability_score", 0.0), reverse=True)
        interleaved: List[Dict[str, Any]] = []
        while any(cat_map.values()):
            sorted_cats = sorted(
                [c for c in cat_map.keys() if cat_map[c]],
                key=lambda c: cat_map[c][0].get("pre_availability_score", 0.0),
                reverse=True
            )
            for c in sorted_cats:
                if cat_map[c]:
                    interleaved.append(cat_map[c].pop(0))
        buckets[k] = interleaved

    # 4. Proportional round-robin interleaving
    # Normalize quota proportions to a block of 20 slots
    total_q = sum(quotas.values()) or 1.0
    slot_allocation = {k: max(1, int(round((v / total_q) * 20))) for k, v in quotas.items()}

    ordered_candidates: List[Dict[str, Any]] = []
    seen_ids = set()

    # Interleave while any bucket has candidates
    while any(len(b) > 0 for b in buckets.values()):
        progress_made = False
        for bucket_key, count in slot_allocation.items():
            b = buckets[bucket_key]
            for _ in range(count):
                if b:
                    cand = b.pop(0)
                    cid = cand.get("candidate_id") or cand.get("domain")
                    if cid not in seen_ids:
                        seen_ids.add(cid)
                        ordered_candidates.append(cand)
                    progress_made = True
                else:
                    break
        if not progress_made:
            break

    return ordered_candidates
