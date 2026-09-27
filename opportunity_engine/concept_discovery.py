"""
Phase 2.5 & Phase 2.75B: Multi-Source Concept Discovery Engine
Discovers concepts across:
A. Trending Opportunities (filtered & categorized)
B. Evergreen Commercial Niches (High-CPC Legal, Finance, Geo Services, Accounting)
C. Startup & Product Signals (Emerging tech & SaaS venture paradigms)
D. Semantic Naming Concepts (Derived from Semantic Root Library)

Enforces strict Category Allocation across all 14 mandatory universe categories:
1. AI_STARTUPS
2. AI_AGENTS
3. MICRO_SAAS
4. AI_TOOLING
5. FINANCE
6. PERSONAL_FINANCE
7. CRYPTO_WEB3
8. LEGAL_B2B
9. B2B_HIGH_CPC
10. HOME_SERVICES
11. LOCAL_SERVICES
12. GEO_SERVICES
13. B2B_TOOLS
14. EMERGING_TECH
"""

import re
import logging
from typing import List, Dict, Any, Set
from opportunity_engine.config import (
    MARKET_CATEGORIES,
    REQUIRED_CATEGORIES,
    get_category_allocations,
    normalize_category_name,
    get_category_display_name,
    MAX_CATEGORY_CONCENTRATION
)
from opportunity_engine.semantic_roots import SEMANTIC_ROOT_LIBRARY

logger = logging.getLogger("ConceptDiscoveryEngine")

# =========================================================================
# 1. CURATED EVERGREEN COMMERCIAL NICHES ACROSS ALL 14 CATEGORIES
# =========================================================================
EVERGREEN_NICHES = [
    # AI_STARTUPS
    {"category": "AI_STARTUPS", "subcategory": "Foundation Models", "concept": "Low-latency distributed inference routing for open-weight foundation models"},
    {"category": "AI_STARTUPS", "subcategory": "Generative AI", "concept": "Enterprise generative multi-modal design and synthetic media generation workspace"},
    
    # AI_AGENTS
    {"category": "AI_AGENTS", "subcategory": "Autonomous Agents", "concept": "Autonomous multi-agent execution environment for complex enterprise research workflows"},
    {"category": "AI_AGENTS", "subcategory": "Agentic Workflows", "concept": "Self-healing asynchronous workflow agents executing end-to-end backoffice operations"},
    
    # MICRO_SAAS
    {"category": "MICRO_SAAS", "subcategory": "Developer Tools", "concept": "Automated API schema migration and client SDK generation engine"},
    {"category": "MICRO_SAAS", "subcategory": "Productivity", "concept": "Unified calendar intelligence and automated meeting preparation dossiers"},
    
    # AI_TOOLING
    {"category": "AI_TOOLING", "subcategory": "MLOps & Safety", "concept": "Automated adversarial prompt testing and LLM safety firewall for enterprise applications"},
    {"category": "AI_TOOLING", "subcategory": "Evaluation", "concept": "Continuous regression benchmarking and synthetic dataset curation for custom fine-tunes"},
    
    # FINANCE
    {"category": "FINANCE", "subcategory": "FinTech & Liquidity", "concept": "Real-time cross-border B2B treasury and liquidity settlement infrastructure"},
    {"category": "FINANCE", "subcategory": "Accounting Rails", "concept": "Automated multi-entity sales tax calculation and automated remittance rails"},
    
    # PERSONAL_FINANCE
    {"category": "PERSONAL_FINANCE", "subcategory": "Personal Wealth", "concept": "Automated wealth harvesting and tax-advantaged portfolio rebalancing for founders"},
    {"category": "PERSONAL_FINANCE", "subcategory": "Budgeting", "concept": "Autonomous household subscription optimization and recurring bill negotiation engine"},
    
    # CRYPTO_WEB3
    {"category": "CRYPTO_WEB3", "subcategory": "Stablecoins", "concept": "Programmable corporate payroll and micropayment streaming rails using regulated stablecoins"},
    {"category": "CRYPTO_WEB3", "subcategory": "Tokenization", "concept": "Hardware-isolated non-custodial key recovery protocol for enterprise treasuries"},
    
    # LEGAL_B2B
    {"category": "LEGAL_B2B", "subcategory": "Contract Review", "concept": "Automated corporate compliance and commercial contract risk review platform"},
    {"category": "LEGAL_B2B", "subcategory": "Patent Intelligence", "concept": "AI-driven prior art search and patent claim drafting intelligence"},
    
    # B2B_HIGH_CPC
    {"category": "B2B_HIGH_CPC", "subcategory": "Commercial Insurance", "concept": "Embedded commercial liability underwriting for distributed workforce enterprises"},
    {"category": "B2B_HIGH_CPC", "subcategory": "Cybersecurity", "concept": "Zero-trust identity posture monitoring and breach containment rails"},
    
    # HOME_SERVICES
    {"category": "HOME_SERVICES", "subcategory": "HVAC", "concept": "Intelligent dispatch and predictive diagnostics platform for regional HVAC contractors"},
    {"category": "HOME_SERVICES", "subcategory": "Plumbing", "concept": "Emergency residential trade service scheduling and automated fleet dispatch"},
    
    # LOCAL_SERVICES
    {"category": "LOCAL_SERVICES", "subcategory": "Local Business Software", "concept": "Automated customer review generation and local SEO management for trade services"},
    {"category": "LOCAL_SERVICES", "subcategory": "Customer Booking", "concept": "Real-time appointment scheduling and automated customer follow-up for local trade services"},
    
    # GEO_SERVICES
    {"category": "GEO_SERVICES", "subcategory": "Fleet Tracking", "concept": "Dynamic route optimization and real-time telematics dispatch for local delivery fleets"},
    {"category": "GEO_SERVICES", "subcategory": "Geo-Fencing", "concept": "High-precision spatial geofencing and automated contractor site check-in verification"},
    
    # B2B_TOOLS
    {"category": "B2B_TOOLS", "subcategory": "RevOps Intelligence", "concept": "Multi-agent asynchronous workflow orchestration for RevOps and customer success"},
    {"category": "B2B_TOOLS", "subcategory": "Sales Enablement", "concept": "Real-time outbound pipeline intelligence and contextual buyer enrichment"},
    
    # EMERGING_TECH
    {"category": "EMERGING_TECH", "subcategory": "Robotics", "concept": "Cloud telemetry and fleet synchronization infrastructure for autonomous warehouse robotics"},
    {"category": "EMERGING_TECH", "subcategory": "Spatial Computing", "concept": "Spatial digital twin visualization and predictive maintenance telemetry"}
]

# =========================================================================
# 2. STARTUP & PRODUCT SIGNALS
# =========================================================================
STARTUP_SIGNALS = [
    {"category": "AI_STARTUPS", "subcategory": "Applied AI", "concept": "Synthesized business intelligence agent answering natural language queries over relational data"},
    {"category": "AI_AGENTS", "subcategory": "Autonomous Execution", "concept": "Autonomous cloud cost optimizer negotiating spot capacity and terminating idle workloads"},
    {"category": "MICRO_SAAS", "subcategory": "Workflow Automation", "concept": "Micro-SaaS documentation sync and API changelog publishing engine"},
    {"category": "AI_TOOLING", "subcategory": "Vector Infrastructure", "concept": "Distributed hybrid vector and lexical retrieval cache for low-latency RAG systems"},
    {"category": "FINANCE", "subcategory": "Lending", "concept": "Algorithmic revenue-based working capital underwriting for subscription software"},
    {"category": "PERSONAL_FINANCE", "subcategory": "Savings", "concept": "High-yield automated treasury allocation for micro-businesses and solo entrepreneurs"},
    {"category": "CRYPTO_WEB3", "subcategory": "DeFi Security", "concept": "Real-time smart contract exploit monitoring and automated liquidity withdrawal circuit breaker"},
    {"category": "LEGAL_B2B", "subcategory": "Regulatory Compliance", "concept": "Continuous GDPR, SOC2, and ISO27001 posture tracking with evidence collection"},
    {"category": "B2B_HIGH_CPC", "subcategory": "HR Compliance", "concept": "Global contractor onboarding, local tax compliance, and automated payroll rails"},
    {"category": "HOME_SERVICES", "subcategory": "Electrical", "concept": "Residential EV charger installation quoting and permit filing automation platform"},
    {"category": "LOCAL_SERVICES", "subcategory": "Reputation", "concept": "Multi-location franchise reputation defense and customer review syndication"},
    {"category": "GEO_SERVICES", "subcategory": "Field Logistics", "concept": "Last-mile courier handoff verification and predictive arrival time alerts"},
    {"category": "B2B_TOOLS", "subcategory": "CRM Sync", "concept": "Bi-directional data synchronization bridge between warehouse databases and enterprise CRMs"},
    {"category": "EMERGING_TECH", "subcategory": "Clean Energy", "concept": "Grid-scale battery storage dispatch and virtual power plant aggregation software"}
]

class ConceptDiscoveryEngine:
    """
    Synthesizes and allocates concepts across all 4 concept sources and 14 market categories.
    """

    def __init__(self, router=None):
        self.router = router

    def _generate_semantic_concepts(self) -> List[Dict[str, Any]]:
        """Source D: Generates concepts derived directly from the Semantic Root Library."""
        concepts: List[Dict[str, Any]] = []
        for cluster_name, data in SEMANTIC_ROOT_LIBRARY.items():
            raw_affinity = data.get("category_affinity", ["AI_STARTUPS"])[0]
            cat_key = normalize_category_name(raw_affinity)
            concepts.append({
                "concept": f"{data['concept']} for modern digital enterprises",
                "category": cat_key,
                "display_category": get_category_display_name(cat_key),
                "subcategory": "Core Platform",
                "source": "SEMANTIC_NAMING_CONCEPTS",
                "commercial_relevance": 90,
                "trend_relevance": 82,
                "startup_relevance": 86
            })
        return concepts

    async def discover_concepts(
        self,
        trending_context: List[str] = None,
        target_count: int = 14
    ) -> List[Dict[str, Any]]:
        """
        Discovers and balances concepts across the 4 sources, guaranteeing broad diversity across
        all 14 required market categories without any single category monopoly.
        """
        all_concepts: List[Dict[str, Any]] = []
        category_allocations = get_category_allocations()

        # 1. Source B: Evergreen Commercial Niches
        for item in EVERGREEN_NICHES:
            cat = normalize_category_name(item.get("category"))
            all_concepts.append({
                **item,
                "category": cat,
                "display_category": get_category_display_name(cat),
                "source": "EVERGREEN_COMMERCIAL_NICHES",
                "commercial_relevance": 95,
                "trend_relevance": 80,
                "startup_relevance": 88
            })

        # 2. Source C: Startup / Product Signals
        for item in STARTUP_SIGNALS:
            cat = normalize_category_name(item.get("category"))
            all_concepts.append({
                **item,
                "category": cat,
                "display_category": get_category_display_name(cat),
                "source": "STARTUP_MARKET_SIGNALS",
                "commercial_relevance": 90,
                "trend_relevance": 92,
                "startup_relevance": 94
            })

        # 3. Source D: Semantic Naming Concepts
        all_concepts.extend(self._generate_semantic_concepts())

        # 4. Source A: Trending Opportunities (if AI router available and trend context provided)
        if self.router and trending_context:
            try:
                trend_prompt = f"""
You are an elite venture strategist and market analyst.
Trends:
{chr(10).join(trending_context[:6])}

Generate 4 high-potential emerging startup concepts mapped strictly across these categories:
1. "AI_AGENTS"
2. "FINANCE"
3. "LEGAL_B2B"
4. "MICRO_SAAS"

IMPORTANT:
Do NOT focus on sports betting, gambling, or collegiate sports rivalries.
Focus on commercial enterprise value, software, and high-margin services.

Respond STRICTLY in JSON:
{{
  "concepts": [
    {{"concept": "...", "category": "AI_AGENTS", "subcategory": "Autonomous Agents"}},
    {{"concept": "...", "category": "FINANCE", "subcategory": "FinTech"}},
    {{"concept": "...", "category": "LEGAL_B2B", "subcategory": "Contract Intelligence"}},
    {{"concept": "...", "category": "MICRO_SAAS", "subcategory": "Developer Tools"}}
  ]
}}
"""
                parsed = await self.router.execute_task_json("trend_research", trend_prompt)
                trend_items = parsed.get("concepts", [])
                for ti in trend_items:
                    raw_cat = ti.get("category", "AI_AGENTS")
                    cat = normalize_category_name(raw_cat)
                    all_concepts.append({
                        "concept": ti.get("concept", "Autonomous Workflow Engine"),
                        "category": cat,
                        "display_category": get_category_display_name(cat),
                        "subcategory": ti.get("subcategory", "Core Innovation"),
                        "source": "TRENDING_OPPORTUNITIES",
                        "commercial_relevance": 92,
                        "trend_relevance": 95,
                        "startup_relevance": 90
                    })
            except Exception as e:
                logger.warning(f"AI trending concept extraction skipped/fallback: {e}")

        # 5. DIVERSITY SELECTION ACROSS ALL 14 MARKET CATEGORIES & 4 SOURCES
        selected_concepts: List[Dict[str, Any]] = []
        seen_concept_texts: Set[str] = set()

        # Step 5a: Pick at least 1 top concept from each available source
        sources_order = [
            "EVERGREEN_COMMERCIAL_NICHES",
            "STARTUP_MARKET_SIGNALS",
            "SEMANTIC_NAMING_CONCEPTS",
            "TRENDING_OPPORTUNITIES"
        ]
        for src in sources_order:
            for c in all_concepts:
                if c.get("source") == src:
                    txt = c["concept"].lower().strip()
                    if txt not in seen_concept_texts:
                        seen_concept_texts.add(txt)
                        selected_concepts.append(c)
                        break

        # Step 5b: Group all concepts by canonical category
        by_category: Dict[str, List[Dict[str, Any]]] = {cat: [] for cat in REQUIRED_CATEGORIES}
        for c in all_concepts:
            cat = normalize_category_name(c.get("category"))
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(c)

        # Step 5c: Guarantee at least 1 concept for EACH required category in universe
        for cat_name in REQUIRED_CATEGORIES:
            pool = by_category.get(cat_name, [])
            already_selected = any(sc.get("category") == cat_name for sc in selected_concepts)
            if not already_selected:
                for item in pool:
                    txt = item["concept"].lower().strip()
                    if txt not in seen_concept_texts:
                        seen_concept_texts.add(txt)
                        selected_concepts.append(item)
                        break

        # Step 5d: Refill up to target_count according to configured category allocations
        for cat_name, alloc in category_allocations.items():
            if len(selected_concepts) >= max(target_count, 14):
                break
            pool = by_category.get(cat_name, [])
            quota = max(1, int(round(target_count * alloc)))
            count_in_cat = sum(1 for sc in selected_concepts if sc.get("category") == cat_name)
            for item in pool:
                if count_in_cat >= quota:
                    break
                txt = item["concept"].lower().strip()
                if txt not in seen_concept_texts:
                    seen_concept_texts.add(txt)
                    selected_concepts.append(item)
                    count_in_cat += 1

        # Final distribution audit log
        distribution: Dict[str, int] = {}
        for c in selected_concepts:
            cat = c["category"]
            distribution[cat] = distribution.get(cat, 0) + 1

        logger.info(f"[CONCEPT-DISCOVERY] Selected {len(selected_concepts)} balanced concepts across categories: {distribution}")
        return selected_concepts
