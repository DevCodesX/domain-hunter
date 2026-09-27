"""
IP Decision & Explainability Engine
Enforces separation of quality score and IP risk score.
Generates human-readable explanatory reasons for each candidate.
"""

from typing import Dict, Any, List
from risk_engine.models import IPRiskReport, RiskLevel

class IPDecisionEngine:
    @staticmethod
    def evaluate_eligibility(quality_score: int, ip_risk: IPRiskReport) -> Dict[str, Any]:
        """
        Applies eligibility rules:
        - CRITICAL IP risk -> Strictly REJECT
        - HIGH IP risk -> REVIEW (only allowed if quality score is exceptional >= 88)
        - LOW / MEDIUM IP risk -> PASS (eligible)
        """
        if ip_risk.ip_risk_level == RiskLevel.CRITICAL:
            decision = "REJECT"
        elif ip_risk.ip_risk_level == RiskLevel.HIGH:
            decision = "REVIEW" if quality_score >= 88 else "REJECT"
        elif ip_risk.ip_risk_level == RiskLevel.NOT_CHECKED:
            decision = "REVIEW" if quality_score >= 70 else "REJECT"
        else:
            decision = "PASS" if quality_score >= 70 else "REJECT"

        return {
            "decision": decision,
            "is_eligible": decision in ["PASS", "REVIEW"],
            "ip_risk_level": ip_risk.ip_risk_level.value,
            "ip_risk_score": ip_risk.ip_risk_score,
            "ip_check_status": getattr(ip_risk, "ip_check_status", "CHECKED")
        }

    @staticmethod
    def build_candidate_explanation(
        domain: str,
        quality_score: int,
        quality_breakdown: Dict[str, int],
        naming_type: str,
        structural_features: Dict[str, Any],
        one_word_features: Dict[str, Any],
        ip_risk: IPRiskReport
    ) -> Dict[str, Any]:
        """
        Constructs the comprehensive, explainable candidate metadata contract.
        """
        reasons = []

        # Linguistic & structural reasons
        if naming_type == "ONE_WORD" and one_word_features.get("is_one_word"):
            reasons.append("Short authentic English dictionary word")
        elif naming_type == "COMPOUND":
            reasons.append("High-synergy compound word structure")
        elif naming_type == "INVENTED":
            reasons.append("Phonetically balanced modern invented brand")
        elif naming_type == "KEYWORD_BRANDABLE":
            reasons.append("Strong industry keyword anchor")

        if structural_features.get("pronounceability_score", 0) >= 80:
            reasons.append("Natural, easy pronunciation")

        if quality_breakdown.get("commercial", 0) >= 85:
            reasons.append("High commercial market flexibility")

        # IP risk reasons
        if ip_risk.ip_risk_level == RiskLevel.NOT_CHECKED:
            reasons.append("Trademark / IP screening not performed (Status: NOT_CHECKED)")
        elif ip_risk.ip_risk_level == RiskLevel.LOW:
            reasons.append("No significant conflict detected by configured screening sources")
        elif ip_risk.ip_risk_level == RiskLevel.MEDIUM:
            reasons.append("Moderate similarity detected; standard screening clearance")
        elif ip_risk.ip_risk_level == RiskLevel.HIGH:
            reasons.append("Requires trademark review due to similarity signals")
        else:
            reasons.append("High conflict detected with existing brand/trademark")

        eligibility = IPDecisionEngine.evaluate_eligibility(quality_score, ip_risk)

        return {
            "domain": domain,
            "domain_name": domain,
            "quality_score": quality_score,
            "overall_score": quality_score, # For backward compatibility with existing UI
            "quality_breakdown": quality_breakdown,
            "naming_type": naming_type,
            "ip_risk": {
                "level": ip_risk.ip_risk_level.value,
                "score": ip_risk.ip_risk_score,
                "check_status": getattr(ip_risk, "ip_check_status", "CHECKED"),
                "exact_match_count": getattr(ip_risk, "exact_match_count", 0),
                "similar_match_count": getattr(ip_risk, "similar_match_count", 0),
                "brand_match_count": getattr(ip_risk, "brand_match_count", 0),
                "provider": getattr(ip_risk, "provider", "USPTO / Curated Brand Engine"),
                "checked_at": getattr(ip_risk, "checked_at", None),
                "disclaimer": getattr(ip_risk, "disclaimer", "IP/trademark screening is a risk signal, not legal advice or legal clearance."),
                "trademark_matches": ip_risk.trademark_matches,
                "existing_brand_matches": ip_risk.brand_matches,
                "evidence": ip_risk.evidence,
                "contributing_sources": getattr(ip_risk, "contributing_sources", []),
                "sources": getattr(ip_risk, "sources", {})
            },
            "contributing_sources": getattr(ip_risk, "contributing_sources", []),
            "sources": getattr(ip_risk, "sources", {}),
            "decision": eligibility["decision"],
            "reasons": reasons

        }
