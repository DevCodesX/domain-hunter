"""
TrademarkRiskEngine: Analyzes exact matches, spelling similarity, phonetic collisions,
famous brand conflicts, commercial context, and combines 3 trademark data sources:
1. Curated Known Brands substring containment (Task A)
2. Official USPTO open trademark API (existing)
3. Dedicated Atom trademark search API (Task B)

Assigns IP risk levels:
- LOW (0-25)
- MEDIUM (26-55)
- HIGH (56-80)
- CRITICAL (81-100)
"""

import logging
import re
from typing import List, Dict, Any, Optional
from risk_engine.models import (
    RiskLevel,
    BrandStatus,
    MatchType,
    IPRiskReport,
    TrademarkMatch,
    ExistingBrandMatch
)
from risk_engine.brand_engine import ExistingBrandEngine
from risk_engine.negative_screening import NegativeSemanticScreening
from risk_engine.providers.base import TrademarkProvider
from risk_engine.providers.uspto import USPTOProvider
from risk_engine.known_brand_matcher import check_known_brand_collision, BrandRiskResult
from risk_engine.atom_trademark_client import AtomTrademarkClient, AtomTrademarkResult

logger = logging.getLogger("TrademarkRiskEngine")

SEVERITY_ORDER = {
    RiskLevel.CRITICAL: 4,
    RiskLevel.HIGH: 3,
    RiskLevel.MEDIUM: 2,
    RiskLevel.LOW: 1,
    RiskLevel.NOT_CHECKED: 0,
    None: 0
}

class TrademarkRiskEngine:
    def __init__(
        self,
        providers: Optional[List[TrademarkProvider]] = None,
        brand_engine: Optional[ExistingBrandEngine] = None,
        negative_screening: Optional[NegativeSemanticScreening] = None,
        atom_client: Optional[AtomTrademarkClient] = None,
        known_brands_data: Optional[List[Dict[str, Any]]] = None
    ):
        self.providers = providers or [USPTOProvider()]
        self.brand_engine = brand_engine or ExistingBrandEngine()
        self.negative_screening = negative_screening or NegativeSemanticScreening()
        self.atom_client = atom_client or AtomTrademarkClient()
        self.known_brands_data = known_brands_data

    async def screen_candidate(
        self,
        domain_name: str,
        category_context: str = ""
    ) -> IPRiskReport:
        """
        Executes complete IP, trademark, brand, and negative screening on domain.
        Combines 3 sources:
        1. Known brands substring collision check (fast, free, local pre-check)
        2. USPTO trademark API (always runs)
        3. Atom trademark search API (runs unless known_brands already flagged CRITICAL)

        Returns an IPRiskReport with highest combined risk level, transparent source tracking,
        contributing sources, evidence trail, and actionable decision.
        """
        domain = domain_name.lower().strip()
        label = domain.replace(".com", "").split(".")[0].strip()
        clean_label = re.sub(r'[^a-z]', '', label)

        trademark_matches: List[TrademarkMatch] = []
        brand_matches: List[ExistingBrandMatch] = []
        evidence_list: List[str] = []
        reasons_list: List[str] = []

        # -------------------------------------------------------------
        # 1. Negative & Sensitive Semantic Screening
        # -------------------------------------------------------------
        is_negative, neg_terms = self.negative_screening.screen(clean_label or label)
        if is_negative:
            evidence_list.append(f"Contains negative or high-risk term(s): {', '.join(neg_terms)}")
            reasons_list.append("Negative or sensitive term detected")

        # -------------------------------------------------------------
        # 2. Existing Curated Brand Intelligence Analysis
        # -------------------------------------------------------------
        brand_matches = self.brand_engine.analyze_domain(clean_label or label)
        for bm in brand_matches:
            evidence_list.append(bm.evidence)

        # -------------------------------------------------------------
        # 3. TASK A: Fast Pre-Check — Known Brands Substring Collision
        # -------------------------------------------------------------
        brand_collision_res: BrandRiskResult = check_known_brand_collision(
            clean_label or label,
            category=category_context,
            known_brands_data=self.known_brands_data
        )

        source_known_brands: Dict[str, Any] = {
            "status": brand_collision_res.status,
            "risk_level": brand_collision_res.risk_level.value if brand_collision_res.risk_level else "NOT_CHECKED",
            "matched_brand": brand_collision_res.matched_brand,
            "matched_alias": brand_collision_res.matched_alias,
            "reason": brand_collision_res.reason
        }

        if brand_collision_res.status == "HIT":
            evidence_list.append(brand_collision_res.reason)
            reasons_list.append(brand_collision_res.reason)

        # -------------------------------------------------------------
        # 4. USPTO Provider Search (Always runs — invariant preserved)
        # -------------------------------------------------------------
        uspto_matches: List[TrademarkMatch] = []
        uspto_status = "CHECKED"
        for provider in self.providers:
            try:
                tm_results = await provider.search(clean_label or label)
                trademark_matches.extend(tm_results)
                uspto_matches.extend(tm_results)
                for tm in tm_results:
                    evidence_list.append(tm.evidence)
            except Exception as e:
                logger.debug(f"Trademark search provider '{provider.name}' error: {e}")
                uspto_status = "ERROR"

        # Determine USPTO-specific risk level
        uspto_risk_level = RiskLevel.LOW
        for tm in uspto_matches:
            if tm.similarity_score >= 0.95:
                if SEVERITY_ORDER[RiskLevel.CRITICAL] > SEVERITY_ORDER[uspto_risk_level]:
                    uspto_risk_level = RiskLevel.CRITICAL
                reasons_list.append(f"Exact/direct trademark match '{tm.trademark_name}'")
            elif tm.similarity_score >= 0.80:
                if SEVERITY_ORDER[RiskLevel.HIGH] > SEVERITY_ORDER[uspto_risk_level]:
                    uspto_risk_level = RiskLevel.HIGH
                reasons_list.append(f"Substantial trademark similarity to '{tm.trademark_name}'")
            elif tm.similarity_score >= 0.70:
                if SEVERITY_ORDER[RiskLevel.MEDIUM] > SEVERITY_ORDER[uspto_risk_level]:
                    uspto_risk_level = RiskLevel.MEDIUM

        source_uspto: Dict[str, Any] = {
            "status": uspto_status,
            "risk_level": uspto_risk_level.value,
            "matches_count": len(uspto_matches),
            "reason": f"USPTO trademark matches: {len(uspto_matches)}" if uspto_matches else "USPTO: No conflicting marks found"
        }

        # -------------------------------------------------------------
        # 5. TASK B & C: Atom Trademark Search
        # (Skip Atom call if known_brands already flagged CRITICAL)
        # -------------------------------------------------------------
        if brand_collision_res.risk_level == RiskLevel.CRITICAL:
            atom_res = AtomTrademarkResult(
                status="NOT_CHECKED (skipped — already CRITICAL)",
                risk_level=None,
                raw_matches=[],
                reason="Atom: NOT_CHECKED (skipped — already CRITICAL from known brands)"
            )
            evidence_list.append(atom_res.reason)
        else:
            atom_res = await self.atom_client.search_trademark(clean_label or label)
            if atom_res.reason:
                evidence_list.append(atom_res.reason)
            if atom_res.status == "HIT":
                reasons_list.append(atom_res.reason)

        source_atom: Dict[str, Any] = {
            "status": atom_res.status,
            "risk_level": atom_res.risk_level.value if atom_res.risk_level else "NOT_CHECKED",
            "matches_count": len(atom_res.raw_matches),
            "reason": atom_res.reason
        }

        # -------------------------------------------------------------
        # 6. Evaluate Brand Engine & Negative Screening Risk Levels
        # -------------------------------------------------------------
        brand_engine_level = RiskLevel.LOW
        for bm in brand_matches:
            if bm.brand_status == BrandStatus.FAMOUS_BRAND:
                if bm.confidence >= 0.85:
                    if SEVERITY_ORDER[RiskLevel.CRITICAL] > SEVERITY_ORDER[brand_engine_level]:
                        brand_engine_level = RiskLevel.CRITICAL
                    reasons_list.append(f"High collision with famous brand '{bm.brand_name}'")
                else:
                    if SEVERITY_ORDER[RiskLevel.HIGH] > SEVERITY_ORDER[brand_engine_level]:
                        brand_engine_level = RiskLevel.HIGH
                    reasons_list.append(f"Moderate similarity to famous brand '{bm.brand_name}'")
            elif bm.brand_status == BrandStatus.ESTABLISHED_BRAND:
                if bm.confidence >= 0.85:
                    if SEVERITY_ORDER[RiskLevel.HIGH] > SEVERITY_ORDER[brand_engine_level]:
                        brand_engine_level = RiskLevel.HIGH
                    reasons_list.append(f"High similarity to established brand '{bm.brand_name}'")
                else:
                    if SEVERITY_ORDER[RiskLevel.MEDIUM] > SEVERITY_ORDER[brand_engine_level]:
                        brand_engine_level = RiskLevel.MEDIUM
            elif bm.brand_status == BrandStatus.ACTIVE_BUSINESS:
                if SEVERITY_ORDER[RiskLevel.MEDIUM] > SEVERITY_ORDER[brand_engine_level]:
                    brand_engine_level = RiskLevel.MEDIUM

        negative_level = RiskLevel.CRITICAL if is_negative else RiskLevel.LOW

        # -------------------------------------------------------------
        # 7. TASK C: Combine All Three Sources (Take Highest Risk Level)
        # CRITICAL > HIGH > MEDIUM > LOW > NOT_CHECKED
        # -------------------------------------------------------------
        sources_to_compare = [
            brand_collision_res.risk_level,
            uspto_risk_level,
            atom_res.risk_level,
            brand_engine_level,
            negative_level
        ]

        final_level = max(sources_to_compare, key=lambda l: SEVERITY_ORDER.get(l, 0))
        if SEVERITY_ORDER.get(final_level, 0) == 0:
            final_level = RiskLevel.LOW

        # -------------------------------------------------------------
        # 8. TASK D: Contributing Sources Identification
        # -------------------------------------------------------------
        contributing_sources: List[str] = []
        if brand_collision_res.risk_level == final_level:
            contributing_sources.append("known_brands")
        if uspto_risk_level == final_level and uspto_risk_level != RiskLevel.LOW:
            contributing_sources.append("uspto")
        if atom_res.risk_level == final_level:
            contributing_sources.append("atom")
        if brand_engine_level == final_level and brand_engine_level != RiskLevel.LOW:
            contributing_sources.append("curated_brands")
        if is_negative and negative_level == final_level:
            contributing_sources.append("negative_screening")

        # If clean domain cleared at LOW risk
        if not contributing_sources and final_level == RiskLevel.LOW:
            contributing_sources = ["known_brands", "uspto"]
            if atom_res.status == "NO_HIT":
                contributing_sources.append("atom")

        # -------------------------------------------------------------
        # 9. Score and Decision Mapping
        # -------------------------------------------------------------
        if final_level == RiskLevel.CRITICAL:
            risk_score = 95
            decision = "REJECT"
        elif final_level == RiskLevel.HIGH:
            risk_score = 75
            decision = "REVIEW"
        elif final_level == RiskLevel.MEDIUM:
            risk_score = 45
            decision = "PASS"
        elif final_level == RiskLevel.LOW:
            risk_score = 10
            decision = "PASS"
        else:
            risk_score = 0
            decision = "REVIEW"

        if not reasons_list:
            reasons_list.append("No significant conflict detected by configured screening sources")

        exact_match_count = (
            sum(1 for tm in trademark_matches if getattr(tm, "match_type", None) == MatchType.EXACT)
            + sum(1 for bm in brand_matches if getattr(bm, "confidence", 0) >= 0.99)
            + (1 if brand_collision_res.status == "HIT" and brand_collision_res.risk_level == RiskLevel.CRITICAL else 0)
        )
        similar_match_count = (
            sum(1 for tm in trademark_matches if getattr(tm, "match_type", None) != MatchType.EXACT)
            + sum(1 for bm in brand_matches if 0.70 <= getattr(bm, "confidence", 0) < 0.99)
            + (1 if brand_collision_res.status == "HIT" and brand_collision_res.risk_level == RiskLevel.HIGH else 0)
        )
        brand_match_count = len(brand_matches) + (1 if brand_collision_res.status == "HIT" else 0)
        provider_name = ", ".join([p.name for p in self.providers] + ["CuratedBrandEngine", "KnownBrandsMatcher", "AtomTrademarkAPI"])

        return IPRiskReport(
            domain=domain,
            ip_risk_level=final_level,
            ip_check_status="CHECKED",
            ip_risk_score=risk_score,
            exact_match_count=exact_match_count,
            similar_match_count=similar_match_count,
            brand_match_count=brand_match_count,
            provider=provider_name,
            trademark_matches=[tm.model_dump() for tm in trademark_matches],
            brand_matches=[bm.model_dump() for bm in brand_matches],
            negative_associations=neg_terms if is_negative else [],
            evidence=evidence_list,
            decision=decision,
            reasons=reasons_list,
            contributing_sources=contributing_sources,
            sources={
                "known_brands": source_known_brands,
                "uspto": source_uspto,
                "atom": source_atom
            }
        )

    @staticmethod
    def create_not_checked_report(domain: str, reason: str = "IP screening not yet performed") -> IPRiskReport:
        return IPRiskReport(
            domain=domain,
            ip_risk_level=RiskLevel.NOT_CHECKED,
            ip_check_status="NOT_CHECKED",
            ip_risk_score=0,
            exact_match_count=0,
            similar_match_count=0,
            brand_match_count=0,
            provider="NONE",
            decision="REVIEW",
            reasons=[reason],
            contributing_sources=[],
            sources={
                "known_brands": {"status": "NOT_CHECKED", "risk_level": "NOT_CHECKED", "reason": reason},
                "uspto": {"status": "NOT_CHECKED", "risk_level": "NOT_CHECKED", "reason": reason},
                "atom": {"status": "NOT_CHECKED", "risk_level": "NOT_CHECKED", "reason": reason}
            }
        )
