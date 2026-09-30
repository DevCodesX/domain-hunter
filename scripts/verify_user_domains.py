"""
Verification script for user-reported domains before and after quality engineering
"""
from quality_engine.quality_scorer import QualityScorer
from quality_engine.feature_extractor import QualityFeatureExtractor
from quality_engine.one_word_engine import OneWordQualityEngine
from quality_engine.naming_classifier import NamingTypeClassifier
from quality_engine.quality_tiers import QualityTierEngine

fe = QualityFeatureExtractor()
nc = NamingTypeClassifier()
ow = OneWordQualityEngine()
qs = QualityScorer()

domains = [
    "horede.com", "smertis.com", "mentlea.com", "pipeara.com", "cunvasa.com",
    "synclow.com", "apexlow.com", "primelow.com", "nodeshade.com",
    "kinetoc.com", "vectra.com"
]

print(f"{'DOMAIN':<14} | {'TYPE':<9} | {'SUBTYPE/TIER':<20} | {'OVERALL':<7} | {'BRAND':<7} | {'COMM':<7} | {'TREND':<7} | {'TIER':<8} | {'SEL_SCORE':<9}")
print("-" * 105)

for d in domains:
    sf = fe.extract_features(d)
    of = ow.compute_one_word_score(d)
    nt = nc.classify(d)
    s = qs.score_candidate(d, structural_features=sf, one_word_features=of, naming_type_info=nt, concept="Cloud Infrastructure & AI Systems")
    
    cand = {
        "domain": d,
        "morphology_type": s.get("morphology_type"),
        "naming_type": s.get("naming_type"),
        "invented_quality_tier": s.get("invented_quality_tier"),
        "invented_subtype": s.get("invented_subtype"),
        "brandability_heuristic_score": s.get("brandability_score"),
        "quality_score": s.get("overall_score"),
        "brandability_score": s.get("brandability_score"),
        "commercial_score": s.get("commercial_score"),
        "trend_score": s.get("trend_score"),
        "buyer_clarity_score": s.get("buyer_clarity_score"),
        "startup_naturalness_score": s.get("startup_naturalness_score"),
        "is_word_glue": s.get("quality_breakdown", {}).get("is_word_glue"),
        "glue_type": s.get("quality_breakdown", {}).get("glue_type"),
        "word_glue_penalty": s.get("quality_breakdown", {}).get("word_glue_penalty", 0),
        "ip_risk_level": "LOW",
        "quality_breakdown": s.get("quality_breakdown")
    }
    
    opp_score = QualityTierEngine.compute_opportunity_score(cand)
    tier = QualityTierEngine.assign_tier(cand, opp_score)
    sel_score = QualityTierEngine.compute_selection_score(cand)
    
    m_type = s.get("morphology_type", "")
    if m_type == "INVENTED":
        tier_info = f"{s.get('invented_subtype', '')}/{s.get('invented_quality_tier', '')}"
    else:
        tier_info = s.get("quality_breakdown", {}).get("glue_type", "COMPOUND") or "COMPOUND"
    
    ov = s.get('overall_score', 0.0)
    br = s.get('brandability_score', 0.0)
    cm = s.get('commercial_score', 0.0)
    tr = s.get('trend_score', 0.0)
    
    print(f"{d:<14} | {m_type:<9} | {tier_info:<20} | {ov:<7.1f} | {br:<7.1f} | {cm:<7.1f} | {tr:<7.1f} | {tier:<8} | {sel_score:<9.1f}")
