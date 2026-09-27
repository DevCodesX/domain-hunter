#!/usr/bin/env python3
"""
Domain Hunter - Phase 1 A/B Comparison Script
Compares Old Scorer vs New Invented-Quality Scorer on Raw Candidate Pool.

Evaluates:
- % INVENTED in final tier set (old vs new)
- % WEAK_UNANCHORED in final tier set (old vs new)
- Average brandability_heuristic_score
- Average lexical/phonetic/semantic proximity
- Candidate-by-candidate breakdown with subtype and anchors
"""

import sys
import os
from typing import List, Dict, Any

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from quality_engine.quality_scorer import QualityScorer
from quality_engine.invented_quality import InventedQualityEvaluator
from quality_engine.quality_tiers import QualityTierEngine
from quality_engine.feature_extractor import QualityFeatureExtractor
from quality_engine.one_word_engine import OneWordQualityEngine
from quality_engine.naming_classifier import NamingTypeClassifier


SAMPLE_INVENTED_CANDIDATES = [
    "pebrowa",
    "tusokn",
    "kinetoc",
    "cidazo",
    "natsot",
    "sdrata",
    "efluco",
    "pacelyt",
    "culosi",
    "horuvi",
    "skembo",
    "teviku",
    "bivorn",
    "glonvi",
    "pruvok",
    "plurok",
    "plimvo",
    "zuprok"
]

# Control non-invented names to simulate realistic mixed ranking pool
CONTROL_CANDIDATES = [
    {"domain": "flowbase.com", "morphology": "COMPOUND"},
    {"domain": "novalabs.com", "morphology": "COMPOUND"},
    {"domain": "peakpulse.com", "morphology": "COMPOUND"},
    {"domain": "craftcore.com", "morphology": "COMPOUND"},
]


def run_ab_comparison(candidates: List[str] = None):
    if candidates is None:
        candidates = SAMPLE_INVENTED_CANDIDATES

    fe = QualityFeatureExtractor()
    owe = OneWordQualityEngine()
    nc = NamingTypeClassifier()
    scorer = QualityScorer()

    print("=" * 80)
    print("PHASE 1 INVENTED QUALITY REFINEMENT — A/B SCORER COMPARISON")
    print("=" * 80)

    # 1. Candidate-by-Candidate Detailed Comparison
    results = []
    for name in candidates:
        domain = f"{name}.com"
        sf = fe.extract_features(name)
        ow = owe.compute_one_word_score(name)
        nt = nc.classify(name)
        
        # New evaluation
        new_res = scorer.score_candidate(
            domain,
            structural_features=sf,
            one_word_features=ow,
            naming_type_info=nt,
            morphology_type="INVENTED"
        )
        new_score = new_res["quality_score"]
        subtype = new_res.get("invented_subtype", "UNKNOWN")
        tier = new_res.get("invented_quality_tier", "UNKNOWN")
        lex = new_res.get("lexical_proximity_score", 0.0)
        phon = new_res.get("phonetic_proximity_score", 0.0)
        sem = new_res.get("semantic_anchor_score", 0.0)
        brand = new_res.get("brandability_heuristic_score", 0.0)
        penalty = new_res.get("invented_penalty", 0.0)
        anchors = [a.get("word") for a in new_res.get("lexical_anchors", [])[:2]]
        
        # Old evaluation (score without invented penalty or subclassification)
        old_score = round(min(100.0, new_score + penalty), 2)
        old_cand = {"domain": domain, "quality_score": old_score, "morphology_type": "INVENTED"}
        new_cand = {
            "domain": domain, 
            "quality_score": new_score, 
            "morphology_type": "INVENTED",
            "invented_quality_tier": tier,
            "invented_subtype": subtype,
            "brandability_heuristic_score": brand
        }
        old_opp = QualityTierEngine.compute_opportunity_score(old_cand)
        new_opp = QualityTierEngine.compute_opportunity_score(new_cand)
        old_tier = QualityTierEngine.assign_tier(old_cand, old_opp)
        new_tier_assigned = QualityTierEngine.assign_tier(new_cand, new_opp)
        
        diff = round(new_score - old_score, 2)
        
        results.append({
            "name": name,
            "domain": domain,
            "old_score": old_score,
            "new_score": new_score,
            "diff": diff,
            "subtype": subtype,
            "tier": tier,
            "old_tier": old_tier,
            "new_tier_assigned": new_tier_assigned,
            "lex": lex,
            "phon": phon,
            "sem": sem,
            "brand": brand,
            "anchors": ", ".join(anchors) if anchors else "none",
            "penalty": penalty,
        })

    # Sort by new score descending
    results.sort(key=lambda x: x["new_score"], reverse=True)

    # Print Table
    header = (
        f"{'Candidate':<10} | {'Old':<5} | {'New':<5} | {'Diff':<6} | "
        f"{'Subtype':<18} | {'Tier':<14} | {'Lex':<5} | {'Phon':<5} | {'Sem':<5} | {'Brand':<5} | {'Anchors'}"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r['name']:<10} | {r['old_score']:<5.1f} | {r['new_score']:<5.1f} | {r['diff']:<+6.1f} | "
            f"{r['subtype']:<18} | {r['tier']:<14} | {r['lex']:<5.1f} | {r['phon']:<5.1f} | {r['sem']:<5.1f} | {r['brand']:<5.1f} | {r['anchors']}"
        )

    print("\n" + "=" * 80)
    print("SIMULATED POOL TIERING & QUOTA ANALYSIS")
    print("=" * 80)

    # Simulate mixed pool with control candidates
    old_pool = []
    new_pool = []
    
    for r in results:
        old_pool.append({
            "domain": r["domain"],
            "quality_score": r["old_score"],
            "morphology_type": "INVENTED",
            "naming_type": "INVENTED",
        })
        new_pool.append({
            "domain": r["domain"],
            "quality_score": r["new_score"],
            "morphology_type": "INVENTED",
            "naming_type": "INVENTED",
            "invented_subtype": r["subtype"],
            "invented_quality_tier": r["tier"],
            "brandability_heuristic_score": r["brand"],
        })
        
    for c in CONTROL_CANDIDATES:
        c_label = c["domain"].replace(".com", "")
        sf = fe.extract_features(c_label)
        ow = owe.compute_one_word_score(c_label)
        nt = nc.classify(c_label)
        c_res = scorer.score_candidate(
            c["domain"],
            structural_features=sf,
            one_word_features=ow,
            naming_type_info=nt,
            morphology_type=c["morphology"]
        )
        score = c_res["quality_score"]
        old_pool.append({
            "domain": c["domain"],
            "quality_score": score,
            "morphology_type": c["morphology"],
        })
        new_pool.append({
            "domain": c["domain"],
            "quality_score": score,
            "morphology_type": c["morphology"],
        })

    old_tiers = QualityTierEngine.organize_tiers(old_pool)
    new_tiers = QualityTierEngine.organize_tiers(new_pool)

    def analyze_tier_pool(tiers_dict: Dict[str, List[Dict]], label: str):
        final_set = tiers_dict["tier_a"] + tiers_dict["tier_b"]
        total_final = len(final_set)
        if total_final == 0:
            print(f"[{label}] No candidates reached Tier A or B.")
            return

        invented_final = [
            c for c in final_set 
            if c.get("morphology_type") == "INVENTED" or c.get("naming_type") == "INVENTED"
        ]
        weak_unanchored = [
            c for c in invented_final 
            if c.get("invented_subtype") == "UNANCHORED" and float(c.get("brandability_heuristic_score") or 100.0) < 70.0
        ]
        
        pct_invented = (len(invented_final) / total_final) * 100
        pct_weak = (len(weak_unanchored) / total_final) * 100
        
        avg_brand = sum(float(c.get("brandability_heuristic_score") or 0.0) for c in invented_final) / max(1, len(invented_final))
        avg_lex = sum(float(c.get("lexical_proximity_score") or 0.0) for c in invented_final) / max(1, len(invented_final))
        avg_phon = sum(float(c.get("phonetic_proximity_score") or 0.0) for c in invented_final) / max(1, len(invented_final))
        avg_sem = sum(float(c.get("semantic_anchor_score") or 0.0) for c in invented_final) / max(1, len(invented_final))
        
        print(f"--- {label} ---")
        print(f"Total Tier A + B Candidates: {total_final}")
        print(f"Tier A count: {len(tiers_dict['tier_a'])}, Tier B count: {len(tiers_dict['tier_b'])}, Watchlist: {len(tiers_dict['watchlist'])}")
        print(f"% INVENTED in final set: {pct_invented:.1f}% ({len(invented_final)}/{total_final})")
        print(f"% WEAK UNANCHORED in final set: {pct_weak:.1f}% ({len(weak_unanchored)}/{total_final})")
        if invented_final:
            print(f"Average Brandability Heuristic (Invented): {avg_brand:.2f}")
            if avg_lex > 0 or avg_phon > 0 or avg_sem > 0:
                print(f"Average Lexical Proximity: {avg_lex:.2f} | Phonetic: {avg_phon:.2f} | Semantic: {avg_sem:.2f}")
        print()

    analyze_tier_pool(old_tiers, "OLD SCORING (Before Phase 1)")
    analyze_tier_pool(new_tiers, "NEW SCORING (Phase 1 Anchoring + Tiers)")

    # Key separation highlights
    print("=" * 80)
    print("KEY SEPARATION HIGHLIGHTS")
    print("=" * 80)
    kinetoc = next((r for r in results if r["name"] == "kinetoc"), None)
    tusokn = next((r for r in results if r["name"] == "tusokn"), None)
    zuprok = next((r for r in results if r["name"] == "zuprok"), None)
    plimvo = next((r for r in results if r["name"] == "plimvo"), None)

    if kinetoc:
        print(f"Anchored Leader: {kinetoc['name']} -> Score {kinetoc['new_score']}, Subtype: {kinetoc['subtype']}, Tier: {kinetoc['tier']}")
    if tusokn:
        print(f"Unanchored Gibberish: {tusokn['name']} -> Score {tusokn['new_score']}, Subtype: {tusokn['subtype']}, Tier: {tusokn['tier']}")
    if zuprok:
        print(f"Unanchored Gibberish: {zuprok['name']} -> Score {zuprok['new_score']}, Subtype: {zuprok['subtype']}, Tier: {zuprok['tier']}")
    if plimvo:
        print(f"Unanchored Gibberish: {plimvo['name']} -> Score {plimvo['new_score']}, Subtype: {plimvo['subtype']}, Tier: {plimvo['tier']}")

    if kinetoc and tusokn:
        print(f"\nSeparation Gap (kinetoc - tusokn): {kinetoc['new_score'] - tusokn['new_score']:+.2f} pts")
    if kinetoc and zuprok:
        print(f"Separation Gap (kinetoc - zuprok): {kinetoc['new_score'] - zuprok['new_score']:+.2f} pts")


if __name__ == "__main__":
    run_ab_comparison()
