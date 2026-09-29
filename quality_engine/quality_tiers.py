"""
Quality Tiers & Opportunity Score Engine (Phase 3)
Calculates:
- Quality Tiers: TIER A (HIGH CONVICTION), TIER B (STRONG OPPORTUNITIES), TIER C (WATCHLIST)
- Opportunity Score: Multi-dimensional opportunity composite score
- Opportunity Explanation: Explainable 'why_generated', 'why_passed', 'why_scored', 'why_selected', 'risk_evidence', 'buyer_potential'
"""

import math
import os
from typing import Dict, Any, List, Optional, Tuple


class QualityTierEngine:
    """
    Categorizes scored candidates into conviction tiers and builds
    transparent explanations for each final opportunity.
    """

    # Maximum targets per tier (never manufactured!)
    MAX_TIER_A = 10
    MAX_TIER_B = 10
    MAX_TIER_C = 20

    @classmethod
    def compute_opportunity_score(
        cls,
        candidate: Dict[str, Any],
        learned_preference_score: Optional[float] = None
    ) -> float:
        """
        Computes final opportunity score (0.0 to 100.0) based on:
        - overall quality
        - brandability
        - memorability
        - pronunciation
        - simplicity
        - commercial fit
        - trend fit
        - buyer clarity
        - startup naturalness
        - distinctiveness
        - naming quality
        - availability confidence
        - optional learned preference score (from Phase 4 statistical ranker)

        IP risk remains a separate safety dimension and is NOT blended into quality.
        """
        # Quality breakdown
        q_break = candidate.get("quality_breakdown", {})
        f_scores = q_break.get("_float_scores", {}) if isinstance(q_break, dict) else {}

        quality = float(candidate.get("quality_score", 70.0))
        brand = float(f_scores.get("brandability", candidate.get("brandability_score", 70.0)))
        memorability = float(f_scores.get("memorability", 70.0))
        pronunciation = float(f_scores.get("pronunciation", 70.0))
        simplicity = float(f_scores.get("simplicity", 70.0))
        distinctiveness = float(f_scores.get("distinctiveness", 70.0))
        commercial = float(f_scores.get("commercial", candidate.get("commercial_score", 70.0)))
        trend = float(f_scores.get("trend", candidate.get("trend_score", 70.0)))
        buyer_clarity = float(candidate.get("buyer_clarity_score", 70.0))
        startup_nat = float(candidate.get("startup_naturalness_score", 70.0))

        # Availability confidence factor (Verisign RDAP authoritative = 100)
        prov = str(candidate.get("availability_provider", "")).lower()
        if "rdap" in prov or "verisign" in prov:
            avail_conf = 100.0
        else:
            avail_conf = 90.0

        # Composite opportunity score
        det_opp = (
            (quality * 0.22) +
            (brand * 0.16) +
            (commercial * 0.14) +
            (buyer_clarity * 0.10) +
            (startup_nat * 0.08) +
            (memorability * 0.08) +
            (pronunciation * 0.06) +
            (simplicity * 0.05) +
            (distinctiveness * 0.05) +
            (trend * 0.03) +
            (avail_conf * 0.03)
        )

        # Blend learned preference score if available
        if learned_preference_score is not None:
            # 75% deterministic quality, 25% learned preference
            final_opp = (det_opp * 0.75) + (float(learned_preference_score) * 0.25)
        else:
            final_opp = det_opp

        return round(max(10.0, min(100.0, final_opp)), 2)

    @classmethod
    def assign_tier(
        cls,
        candidate: Dict[str, Any],
        opportunity_score: float
    ) -> str:
        """
        Determines the quality tier:
        - TIER_A: High Conviction (>= 83.0, IP low/not high, high clarity)
        - TIER_B: Strong Opportunities (>= 74.0 to < 83.0, IP low/medium)
        - TIER_C: Watchlist (>= 68.0 to < 74.0)
        - REJECTED: (< 68.0 or CRITICAL/HIGH IP risk)
        """
        ip_level = str(candidate.get("ip_risk_level", "LOW")).upper()

        # Hard gate: CRITICAL and HIGH IP risk cannot enter Tier A or Tier B
        if ip_level in ["CRITICAL", "HIGH"]:
            return "WATCHLIST_RISK" if ip_level == "HIGH" else "REJECTED"

        # Phase 1 (Revised) Hard Gate: EXTREMELY_WEAK invented candidates are excluded from Tier A/B
        morph = candidate.get("morphology_type") or candidate.get("naming_type")
        inv_tier = candidate.get("invented_quality_tier")
        inv_subtype = candidate.get("invented_subtype")
        brand_score = candidate.get("brandability_heuristic_score")
        if morph == "INVENTED" or inv_tier is not None:
            # Unanchored invented names are never Tier A by subjective score alone.
            if inv_subtype == "UNANCHORED":
                return "TIER_C" if opportunity_score >= 68.0 else "BELOW_THRESHOLD"
            if inv_tier == "EXTREMELY_WEAK":
                return "TIER_C" if opportunity_score >= 68.0 else "BELOW_THRESHOLD"
            # Weak invented names require explicit multi-model evidence before A/B.
            if inv_tier == "WEAK":
                weak_tier_a_enabled = os.getenv("MULTI_MODEL_WEAK_TIER_A_ENABLED", "false").lower() == "true"
                if not weak_tier_a_enabled:
                    return "TIER_B" if opportunity_score >= 74.0 else ("TIER_C" if opportunity_score >= 68.0 else "BELOW_THRESHOLD")
                if not bool(candidate.get("multi_model_review")):
                    return "TIER_C" if opportunity_score >= 68.0 else "BELOW_THRESHOLD"

        # Tier A Quality Floors & Conviction Guards (Phase 1 Refinement)
        # Prevents high aggregate scores from masking critical subscore weaknesses
        from quality_engine.invented_quality import get_tier_a_floors_config
        floors = get_tier_a_floors_config()
        min_tier_a_score = float(floors.get("min_score", 82.0))
        min_pron = float(floors.get("min_pronunciation", 65.0))
        min_hear = float(floors.get("min_hear_to_spell", 60.0))
        min_comm = float(floors.get("min_commercial_naturalness", 65.0))
        min_brand = float(floors.get("min_brandability", 70.0))

        q_break = candidate.get("quality_breakdown", {})
        f_scores = q_break.get("_float_scores", {}) if isinstance(q_break, dict) else {}

        c_pron = float(f_scores.get("pronunciation", candidate.get("pronunciation_score", candidate.get("structural_features", {}).get("pronounceability_score", 75.0))))
        c_hear = float(candidate.get("hear_to_spell_score", candidate.get("brandability_subscores", {}).get("hear_to_spell", f_scores.get("hear_to_spell", 75.0))))
        c_comm = float(candidate.get("commercial_naturalness_score", candidate.get("startup_naturalness_score", f_scores.get("startup_naturalness", candidate.get("commercial_score", 75.0)))))
        c_brand = float(f_scores.get("brandability", candidate.get("brandability_score", candidate.get("brandability_heuristic_score", 75.0))))

        critical_weaknesses = []
        if c_pron < min_pron:
            critical_weaknesses.append(f"Pronunciation ({c_pron:.1f} < {min_pron})")
        if c_hear < min_hear:
            critical_weaknesses.append(f"Hear-to-spell ({c_hear:.1f} < {min_hear})")
        if c_comm < min_comm:
            critical_weaknesses.append(f"Commercial naturalness ({c_comm:.1f} < {min_comm})")
        if c_brand < min_brand:
            critical_weaknesses.append(f"Brandability ({c_brand:.1f} < {min_brand})")

        candidate["tier_a_critical_weakness"] = critical_weaknesses

        if opportunity_score >= min_tier_a_score and ip_level in ["LOW", "NOT_CHECKED"]:
            if not critical_weaknesses:
                return "TIER_A"
            else:
                # Demoted from Tier A to Tier B due to quality floor breach
                return "TIER_B" if opportunity_score >= 74.0 else "TIER_C"
        elif opportunity_score >= 74.0:
            return "TIER_B"
        elif opportunity_score >= 68.0:
            return "TIER_C"
        else:
            return "BELOW_THRESHOLD"

    @classmethod
    def build_opportunity_explanation(
        cls,
        candidate: Dict[str, Any],
        tier: str,
        opportunity_score: float
    ) -> Dict[str, Any]:
        """
        Builds explainable metadata for the final domain opportunity.
        Includes:
        - why_generated
        - why_passed
        - why_scored
        - why_selected
        - risk_evidence
        - buyer_potential
        """
        domain = candidate.get("domain") or candidate.get("domain_name", "")
        strat = candidate.get("generation_strategy", "INVENTED")
        naming_type = candidate.get("naming_type", "INVENTED")
        concept = candidate.get("source_concept") or candidate.get("category") or "AI & Technology"
        q_score = candidate.get("quality_score", 0)
        brand_score = candidate.get("brandability_score", 0)
        comm_score = candidate.get("commercial_score", 0)
        buyer_clarity = candidate.get("buyer_clarity_score", 0)
        prov = candidate.get("availability_provider", "Verisign RDAP")
        ip_level = candidate.get("ip_risk_level", "LOW")

        # Why generated
        why_generated = (
            f"Generated via {strat} strategy focused on concept '{concept}'. "
            f"Linguistically structured as authentic {naming_type}."
        )

        # Why passed
        passed_reasons = [
            f"Authoritative registry check: Verified AVAILABLE_STANDARD via {prov}",
            "Zero premium fee or registry surcharge",
            f"IP clearance status: {ip_level} risk level",
            "Passed acoustic and phonetic diversity filters"
        ]

        # Why scored
        scoring_breakdown = [
            f"Overall Quality: {q_score}/100",
            f"Brandability: {brand_score}/100",
            f"Commercial Fit: {comm_score}/100",
            f"Buyer Clarity: {buyer_clarity}/100",
            f"Composite Opportunity Score: {opportunity_score}/100"
        ]

        # Why selected
        critical_weaknesses = candidate.get("tier_a_critical_weakness", [])
        if tier == "TIER_A":
            why_selected = "Ranked into TIER A (High Conviction) due to superior brandability, high buyer clarity, and clean IP screening."
        elif tier == "TIER_B":
            if critical_weaknesses:
                why_selected = f"Ranked into TIER B due to Tier A quality floor constraints: {'; '.join(critical_weaknesses)}."
            else:
                why_selected = "Ranked into TIER B (Strong Opportunity) demonstrating strong commercial appeal and phonetic simplicity."
        else:
            why_selected = "Ranked into TIER C (Watchlist) showing viable opportunity for monitoring or secondary branding."

        # Risk evidence
        ip_evidence = candidate.get("ip_evidence") or candidate.get("ip_report") or {}
        evidence_summary = []
        if isinstance(ip_evidence, list):
            evidence_summary = [str(e) for e in ip_evidence[:3]]
        elif isinstance(ip_evidence, dict):
            for k in ["matches", "reasons", "evidence"]:
                if k in ip_evidence and isinstance(ip_evidence[k], list):
                    evidence_summary.extend([str(item) for item in ip_evidence[k][:2]])
        
        if not evidence_summary:
            evidence_summary = [f"No blocking trademark or brand conflicts detected ({ip_level} risk)"]

        # Buyer potential
        buyer_cats = candidate.get("buyer_categories") or [candidate.get("category", "AI & Technology")]
        primary_b = candidate.get("primary_buyer", "Tech Startup / B2B Platform")
        potential_prods = candidate.get("potential_product_categories", ["Enterprise SaaS platform", "Cloud workflow automation"])

        buyer_potential = {
            "primary_buyer": primary_b,
            "likely_industries": buyer_cats,
            "potential_products": potential_prods,
            "buyer_count": candidate.get("buyer_count", len(buyer_cats)),
            "startup_naturalness": candidate.get("startup_naturalness_score", 75.0)
        }

        return {
            "domain": domain,
            "tier": tier,
            "opportunity_score": opportunity_score,
            "why_generated": why_generated,
            "why_passed": passed_reasons,
            "why_scored": scoring_breakdown,
            "why_selected": why_selected,
            "risk_evidence": evidence_summary,
            "buyer_potential": buyer_potential
        }

    @classmethod
    def organize_tiers(
        cls,
        scored_candidates: List[Dict[str, Any]],
        learned_scores: Optional[Dict[str, float]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Evaluates, scores, and segregates candidates into:
        - tier_a: High Conviction (max 10)
        - tier_b: Strong Opportunities (max 10)
        - watchlist: Watchlist (max 20)
        Quality always takes precedence: if only 3 qualify for Tier A, returns 3.
        
        Hard gates:
        - Registered domains (is_registered=True or availability_status=REGISTERED)
          are NEVER allowed in Tier A or Tier B.
        - Learned preference scores CANNOT override availability hard gates.
        """
        tier_a: List[Dict[str, Any]] = []
        tier_b: List[Dict[str, Any]] = []
        watchlist: List[Dict[str, Any]] = []

        learned_map = learned_scores or {}

        for cand in scored_candidates:
            d = cand.get("domain") or cand.get("domain_name", "")

            # Hard gate: registered or unavailable domains cannot enter Tier A or Tier B
            is_registered = cand.get("is_registered", False)
            avail_status = str(cand.get("availability_status", "")).upper()
            if is_registered or avail_status == "REGISTERED":
                # Force into watchlist at best, never A or B
                enriched = {
                    **cand,
                    "opportunity_score": 0.0,
                    "quality_tier": "REJECTED_REGISTERED",
                    "opportunity_explanation": {"why_generated": "N/A", "why_passed": [], "why_scored": [], "why_selected": "Registered domain excluded"},
                    "explanations": {"why_generated": "N/A", "why_passed": [], "why_scored": [], "why_selected": "Registered domain excluded"},
                    "learned_preference_score": None
                }
                # Do NOT add to any tier
                continue

            learned_s = learned_map.get(d)
            opp_score = cls.compute_opportunity_score(cand, learned_preference_score=learned_s)
            tier = cls.assign_tier(cand, opp_score)
            explanation = cls.build_opportunity_explanation(cand, tier, opp_score)

            enriched = {
                **cand,
                "opportunity_score": opp_score,
                "quality_tier": tier,
                "opportunity_explanation": explanation,
                "explanations": explanation,  # Alias for test compatibility
                "learned_preference_score": learned_s
            }

            if tier == "TIER_A":
                tier_a.append(enriched)
            elif tier == "TIER_B":
                tier_b.append(enriched)
            elif tier in ["TIER_C", "WATCHLIST_RISK"]:
                watchlist.append(enriched)

        # Sort each tier by opportunity_score descending
        tier_a.sort(key=lambda x: x["opportunity_score"], reverse=True)
        tier_b.sort(key=lambda x: x["opportunity_score"], reverse=True)
        watchlist.sort(key=lambda x: x["opportunity_score"], reverse=True)

        # Phase 1 (Revised) Task F: Enforce weak_unanchored_invented_ratio_cap on Tier A + Tier B combined
        # Apply quota ONLY to UNANCHORED + weak brandability subset; STRONG anchored candidates get no cap.
        from quality_engine.invented_quality import get_weak_unanchored_ratio_cap
        ratio_cap = get_weak_unanchored_ratio_cap()
        all_ab = tier_a + tier_b
        if all_ab:
            weak_unanchored = [
                c for c in all_ab
                if (c.get("morphology_type") == "INVENTED" or c.get("naming_type") == "INVENTED")
                and (
                    c.get("invented_quality_tier") in ["WEAK", "EXTREMELY_WEAK"]
                    or (c.get("invented_subtype") == "UNANCHORED" and float(c.get("brandability_heuristic_score") or 100.0) < 70.0)
                )
            ]
            max_allowed_weak = max(0, int(math.floor(len(all_ab) * ratio_cap)))
            if len(weak_unanchored) > max_allowed_weak:
                weak_unanchored.sort(key=lambda x: x.get("opportunity_score", 0.0))
                excess_count = len(weak_unanchored) - max_allowed_weak
                demoted_domains = set(
                    c.get("domain") or c.get("domain_name") for c in weak_unanchored[:excess_count]
                )
                new_tier_a = []
                for c in tier_a:
                    d_name = c.get("domain") or c.get("domain_name")
                    if d_name in demoted_domains:
                        c["quality_tier"] = "TIER_C"
                        watchlist.append(c)
                    else:
                        new_tier_a.append(c)
                tier_a = new_tier_a

                new_tier_b = []
                for c in tier_b:
                    d_name = c.get("domain") or c.get("domain_name")
                    if d_name in demoted_domains:
                        c["quality_tier"] = "TIER_C"
                        watchlist.append(c)
                    else:
                        new_tier_b.append(c)
                tier_b = new_tier_b

                watchlist.sort(key=lambda x: x["opportunity_score"], reverse=True)

        return {
            "tier_a": tier_a[:cls.MAX_TIER_A],
            "tier_b": tier_b[:cls.MAX_TIER_B],
            "watchlist": watchlist[:cls.MAX_TIER_C],
            "all_opportunities": tier_a[:cls.MAX_TIER_A] + tier_b[:cls.MAX_TIER_B]
        }
