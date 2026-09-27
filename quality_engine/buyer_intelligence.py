"""
Buyer Intelligence Engine (Phase 3)
Evaluates candidate-specific commercial buyer intent, industry applicability,
product categories, startup naturalness, and buyer clarity.
"""

import re
import hashlib
from typing import Dict, Any, List, Optional, Tuple


class BuyerIntelligenceEngine:
    """
    Candidate-specific Buyer Intelligence Engine.
    Determines plausible buyer archetypes, product categories, sector applicability,
    and commercial intent for domain candidates.
    """

    # Industry archetypes and detailed product applications
    SECTOR_PROFILES: Dict[str, Dict[str, Any]] = {
        "AI_SAAS": {
            "name": "AI & Autonomous Systems",
            "keywords": {"ai", "agent", "intel", "model", "mind", "neural", "bot", "auto", "cogni", "syn", "deep", "tensor", "smart", "logic", "nexus"},
            "buyer_archetype": "AI Startup / Autonomous Workflow Platform",
            "potential_products": ["Autonomous agent infrastructure", "Enterprise LLM orchestrator", "Predictive intelligence API", "AI workflow studio"],
            "applicability_key": "ai_applicability"
        },
        "DEV_TOOLS": {
            "name": "Developer Tools & Infrastructure",
            "keywords": {"dev", "code", "stack", "node", "mesh", "grid", "hub", "api", "git", "box", "dock", "build", "wire", "link", "pipe", "crate", "forge", "vector"},
            "buyer_archetype": "Developer Tools / Cloud Infrastructure Provider",
            "potential_products": ["DevOps automation suite", "Developer telemetry platform", "Cloud runtime engine", "API gateway"],
            "applicability_key": "developer_tool_applicability"
        },
        "B2B_SAAS": {
            "name": "B2B SaaS & Enterprise Productivity",
            "keywords": {"desk", "flow", "base", "shift", "sync", "track", "work", "craft", "task", "pulse", "core", "point", "suite", "board", "space", "ops"},
            "buyer_archetype": "B2B SaaS / Enterprise Productivity Platform",
            "potential_products": ["Operations management software", "Workforce orchestration tool", "Business analytics portal", "Collaboration platform"],
            "applicability_key": "saas_applicability"
        },
        "FINTECH": {
            "name": "FinTech & Digital Commerce",
            "keywords": {"pay", "fund", "cash", "coin", "ledger", "vault", "capital", "yield", "trade", "tax", "settle", "wallet", "credit", "asset", "trust"},
            "buyer_archetype": "FinTech / Corporate Treasury Rails",
            "potential_products": ["Payment settlement protocol", "Corporate liquidity platform", "Cross-border treasury rails", "Automated billing software"],
            "applicability_key": "fintech_applicability"
        },
        "ECOMMERCE": {
            "name": "E-Commerce & Supply Chain Logistics",
            "keywords": {"shop", "cart", "market", "ship", "pack", "store", "drop", "lane", "cargo", "fleet", "hub", "shelf", "route"},
            "buyer_archetype": "Omnichannel Commerce / Logistics Network",
            "potential_products": ["Global fulfillment engine", "Digital storefront infrastructure", "Inventory intelligence system", "Multi-carrier logistics hub"],
            "applicability_key": "ecommerce_applicability"
        },
        "SECURITY": {
            "name": "Cybersecurity & Risk Intelligence",
            "keywords": {"safe", "shield", "guard", "auth", "lock", "armor", "gate", "wall", "trust", "seal", "watch", "sentry", "ward", "veritas"},
            "buyer_archetype": "Enterprise Cybersecurity / Compliance Firm",
            "potential_products": ["Zero-trust identity platform", "Automated threat intelligence suite", "Cloud posture compliance scanner"],
            "applicability_key": "enterprise_applicability"
        }
    }

    # Authoritative Latin/Romance/Classic brand endings that boost enterprise credibility
    AUTHORITATIVE_ENDINGS = ("ic", "is", "ex", "ix", "or", "us", "en", "on", "er", "ium", "os", "al", "a", "o", "io", "ia")

    @classmethod
    def analyze_candidate(
        cls,
        domain_or_label: str,
        market_category: str = "AI & Technology",
        naming_type: str = "INVENTED",
        concept: str = ""
    ) -> Dict[str, Any]:
        """
        Extracts comprehensive buyer intelligence for a domain candidate.
        Returns candidate-specific profile with:
        - likely buyer industries
        - potential product categories
        - sector applicability scores (saas, startup, enterprise, ecommerce, fintech, ai, devtool)
        - geographic potential
        - primary_buyer
        - secondary_buyers
        - buyer_count
        - buyer_clarity_score
        - startup_naturalness
        """
        label = domain_or_label.lower().replace(".com", "").strip()
        n = len(label)

        # 1. Base length credibility
        if 4 <= n <= 6:
            base_credibility = 86.0 + (6 - n) * 2.5
        elif n == 7:
            base_credibility = 83.0
        elif n == 8:
            base_credibility = 79.5
        elif n <= 10:
            base_credibility = 74.0 - (n - 8) * 3.5
        else:
            base_credibility = max(42.0, 66.0 - (n - 10) * 4.2)

        # 2. Endings bonus / penalty
        if label.endswith(cls.AUTHORITATIVE_ENDINGS):
            base_credibility += 3.5
        elif label.endswith(("lux", "vos", "ync", "vio", "tra", "tix")):
            base_credibility -= 2.5

        # 3. Harsh letter penalty
        harsh_pairs = {"zt", "fq", "gq", "zk", "xz", "zx", "jx", "xj", "vj", "jv", "qp"}
        harsh_pen = sum(10.0 for i in range(n - 1) if label[i:i+2] in harsh_pairs)
        if "q" in label and "qu" not in label:
            harsh_pen += 12.0
        base_credibility -= harsh_pen

        # Sector scores calculation
        sector_scores: Dict[str, float] = {}
        sector_matches: List[Tuple[str, float, str, List[str]]] = []

        # Hash-based variance (0.01 - 1.99 pts) for unique scoring without ties
        h_val = (int(hashlib.sha256(label.encode("utf-8")).hexdigest()[:8], 16) % 200) / 100.0

        for sector_id, prof in cls.SECTOR_PROFILES.items():
            kw_hits = sum(1 for kw in prof["keywords"] if kw in label)
            concept_hits = 1 if any(kw in concept.lower() for kw in prof["keywords"]) else 0
            
            # Baseline score tailored by candidate length and keyword alignment
            sector_score = base_credibility * 0.75 + (kw_hits * 10.0) + (concept_hits * 4.0) + h_val
            
            # Boost sector score if market_category matches profile intent
            if sector_id == "AI_SAAS" and "ai" in market_category.lower():
                sector_score += 8.0
            elif sector_id == "FINTECH" and "finance" in market_category.lower():
                sector_score += 8.0
            elif sector_id == "DEV_TOOLS" and ("tool" in market_category.lower() or "tech" in market_category.lower()):
                sector_score += 7.0
            elif sector_id == "B2B_SAAS" and ("saas" in market_category.lower() or "commercial" in market_category.lower()):
                sector_score += 7.0
            elif sector_id == "ECOMMERCE" and "commerce" in market_category.lower():
                sector_score += 8.0
            elif sector_id == "SECURITY" and "security" in market_category.lower():
                sector_score += 8.0

            final_sector_score = round(max(25.0, min(98.5, sector_score)), 2)
            sector_scores[prof["applicability_key"]] = final_sector_score
            sector_matches.append((sector_id, final_sector_score, prof["buyer_archetype"], prof["potential_products"]))

        # Sort sectors by strength of fit
        sector_matches.sort(key=lambda x: x[1], reverse=True)

        primary_sector_id, primary_score, primary_buyer, primary_products = sector_matches[0]
        secondary_buyers = [m[2] for m in sector_matches[1:3] if m[1] >= 65.0]
        
        likely_industries = [cls.SECTOR_PROFILES[m[0]]["name"] for m in sector_matches if m[1] >= 68.0]
        if not likely_industries:
            likely_industries = [cls.SECTOR_PROFILES[primary_sector_id]["name"]]

        potential_products = list(primary_products[:2])
        if len(sector_matches) > 1 and sector_matches[1][1] >= 65.0:
            potential_products.extend(sector_matches[1][3][:2])

        # Buyer count: number of distinct sectors with >= 68.0 score
        buyer_count = max(1, sum(1 for m in sector_matches if m[1] >= 68.0))

        # Startup applicability & naturalness
        startup_applicability = round(max(30.0, min(98.0, (base_credibility * 0.85) + (10.0 if naming_type in ["ONE_WORD", "REAL_WORD", "INVENTED"] else 4.0) + h_val)), 2)
        enterprise_applicability = round(max(25.0, min(97.0, (base_credibility * 0.80) + (12.0 if label.endswith(cls.AUTHORITATIVE_ENDINGS) else 2.0) + h_val)), 2)

        # Buyer clarity score
        buyer_clarity_score = round(max(35.0, min(98.0, (primary_score * 0.65) + (base_credibility * 0.35))), 2)

        # Startup naturalness
        startup_naturalness = round(max(30.0, min(98.0, (startup_applicability * 0.60) + (buyer_clarity_score * 0.40))), 2)

        # Geographic potential
        if n <= 6 and label.isalpha():
            geographic_potential = "Global Tier-1 (US, EU, APAC)"
        elif n <= 9:
            geographic_potential = "Global English & Tech Hubs"
        else:
            geographic_potential = "Regional / Niche Commercial Markets"

        return {
            "domain": f"{label}.com",
            "buyer_categories": likely_industries,
            "buyer_count": buyer_count,
            "primary_buyer": primary_buyer,
            "secondary_buyers": secondary_buyers,
            "potential_product_categories": potential_products,
            "buyer_clarity_score": buyer_clarity_score,
            "startup_naturalness": startup_naturalness,
            "saas_applicability": sector_scores.get("saas_applicability", 60.0),
            "startup_applicability": startup_applicability,
            "enterprise_applicability": enterprise_applicability,
            "ecommerce_applicability": sector_scores.get("ecommerce_applicability", 50.0),
            "fintech_applicability": sector_scores.get("fintech_applicability", 50.0),
            "ai_applicability": sector_scores.get("ai_applicability", 60.0),
            "developer_tool_applicability": sector_scores.get("developer_tool_applicability", 60.0),
            "geographic_potential": geographic_potential,
            "commercial_archetype": f"{primary_buyer} — {likely_industries[0] if likely_industries else market_category}"
        }

    @classmethod
    def evaluate(
        cls,
        domain: str = "",
        category: str = "AI & Technology",
        concept: str = "",
        naming_type: str = "INVENTED"
    ) -> Dict[str, Any]:
        """
        Adapter method: maps test-expected keyword arguments to analyze_candidate.
        Enriches output with keys the Phase 3/4 tests expect:
        - primary_archetype
        - target_sectors
        - product_categories
        - startup_naturalness (float 0.0-1.0)
        - potential_buyer_count
        - geographic_potential
        """
        result = cls.analyze_candidate(
            domain_or_label=domain,
            market_category=category,
            naming_type=naming_type,
            concept=concept
        )

        # Enrich with test-expected keys
        result["primary_archetype"] = result.get("primary_buyer", "Tech Startup")
        result["target_sectors"] = result.get("buyer_categories", [category])
        result["product_categories"] = result.get("potential_product_categories", [])
        # Normalize startup_naturalness to 0.0-1.0 range
        raw_nat = float(result.get("startup_naturalness", 70.0))
        result["startup_naturalness"] = round(max(0.0, min(1.0, raw_nat / 100.0)), 4)
        result["potential_buyer_count"] = result.get("buyer_count", 1)

        return result
