"""
Phase 2.5 & Phase 2.75B: Market Opportunity Universe Configuration
Defines market categories, subcategories, target allocations, and CPC/market intent signals.
Enforces the mandatory 14-category diversity universe with explicit per-run quotas:
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

import os
import json
from typing import Dict, Any, List, Optional

# =========================================================================
# 1. MANDATORY 14-CATEGORY DIVERSITY UNIVERSE
# =========================================================================
REQUIRED_CATEGORIES: List[str] = [
    "AI_STARTUPS",
    "AI_AGENTS",
    "MICRO_SAAS",
    "AI_TOOLING",
    "FINANCE",
    "PERSONAL_FINANCE",
    "CRYPTO_WEB3",
    "LEGAL_B2B",
    "B2B_HIGH_CPC",
    "HOME_SERVICES",
    "LOCAL_SERVICES",
    "GEO_SERVICES",
    "B2B_TOOLS",
    "EMERGING_TECH"
]

MARKET_CATEGORIES: Dict[str, Dict[str, Any]] = {
    "AI_STARTUPS": {
        "slug": "ai_startups",
        "display_name": "AI Startups",
        "description": "Foundation model companies, generative AI startups, and frontier AI software",
        "default_allocation": 0.08,
        "subcategories": ["Foundation Models", "Generative AI", "Applied AI", "Enterprise GenAI"],
        "keywords": ["model", "neural", "intel", "cortex", "cogni", "synapse", "vector", "latent", "gen"],
        "commercial_intent_weight": 0.95,
        "market_size_weight": 0.96,
        "buyer_density_weight": 0.92
    },
    "AI_AGENTS": {
        "slug": "ai_agents",
        "display_name": "AI Agents",
        "description": "Autonomous agents, multi-agent swarms, workflow executors, and agentic orchestration",
        "default_allocation": 0.08,
        "subcategories": ["Autonomous Agents", "Multi-Agent Swarms", "Agentic Workflows", "AI Delegation"],
        "keywords": ["agent", "auto", "swarm", "exec", "action", "bot", "delegate", "pilot", "operator"],
        "commercial_intent_weight": 0.96,
        "market_size_weight": 0.94,
        "buyer_density_weight": 0.93
    },
    "MICRO_SAAS": {
        "slug": "micro_saas",
        "display_name": "Micro-SaaS & Tooling",
        "description": "Specialized productivity, workflow utilities, analytics, and vertical software",
        "default_allocation": 0.08,
        "subcategories": ["Developer Tools", "Productivity", "SEO Tools", "Analytics", "Workflow Automation"],
        "keywords": ["kit", "dock", "desk", "craft", "tool", "stack", "flow", "loop", "pulse", "grid"],
        "commercial_intent_weight": 0.88,
        "market_size_weight": 0.85,
        "buyer_density_weight": 0.92
    },
    "AI_TOOLING": {
        "slug": "ai_tooling",
        "display_name": "AI Tooling",
        "description": "MLOps, evaluation suites, prompt management, vector indexers, and fine-tuning rails",
        "default_allocation": 0.07,
        "subcategories": ["MLOps", "Prompt Management", "Vector Indexing", "LLM Evaluation", "Inference Routers"],
        "keywords": ["prompt", "eval", "tune", "tensor", "pipeline", "router", "weights", "embed", "infer"],
        "commercial_intent_weight": 0.93,
        "market_size_weight": 0.90,
        "buyer_density_weight": 0.91
    },
    "FINANCE": {
        "slug": "finance",
        "display_name": "Finance",
        "description": "FinTech, enterprise treasury, B2B payments, multi-currency settlement, and capital",
        "default_allocation": 0.08,
        "subcategories": ["FinTech", "Payments", "Treasury", "Liquidity", "B2B Settlement", "Accounting Rails"],
        "keywords": ["capital", "vault", "ledger", "treasury", "settle", "fisc", "mint", "asset", "pay"],
        "commercial_intent_weight": 0.98,
        "market_size_weight": 0.96,
        "buyer_density_weight": 0.95
    },
    "PERSONAL_FINANCE": {
        "slug": "personal_finance",
        "display_name": "Personal Finance",
        "description": "Consumer budgeting, automated wealth building, tax filing, and retirement",
        "default_allocation": 0.07,
        "subcategories": ["Personal Wealth", "Budgeting", "Consumer Tax", "Savings Automation", "Retirement"],
        "keywords": ["wealth", "nest", "save", "penny", "budget", "vest", "coin", "harvest", "pocket"],
        "commercial_intent_weight": 0.90,
        "market_size_weight": 0.93,
        "buyer_density_weight": 0.88
    },
    "CRYPTO_WEB3": {
        "slug": "crypto_web3",
        "display_name": "Crypto / Web3",
        "description": "Stablecoin settlement rails, tokenized real-world assets, decentralized protocols",
        "default_allocation": 0.07,
        "subcategories": ["Stablecoins", "Tokenization", "DeFi", "Web3 Infrastructure", "Crypto Security"],
        "keywords": ["chain", "block", "node", "hash", "token", "crypto", "ether", "vault", "proof", "mint", "dao"],
        "commercial_intent_weight": 0.86,
        "market_size_weight": 0.84,
        "buyer_density_weight": 0.85
    },
    "LEGAL_B2B": {
        "slug": "legal_b2b",
        "display_name": "Legal Services",
        "description": "Corporate contract intelligence, legal compliance, patent search, and corporate governance",
        "default_allocation": 0.08,
        "subcategories": ["Contract Review", "Corporate Compliance", "Patent Search", "Legal Tech", "Governance"],
        "keywords": ["legal", "counsel", "claim", "veritas", "charter", "brief", "firm", "advisory", "statute", "lex"],
        "commercial_intent_weight": 0.99,
        "market_size_weight": 0.92,
        "buyer_density_weight": 0.95
    },
    "B2B_HIGH_CPC": {
        "slug": "b2b_high_cpc",
        "display_name": "B2B High-CPC / Commercial Services",
        "description": "Enterprise cybersecurity, insurance underwriting, business consulting, and HR compliance",
        "default_allocation": 0.08,
        "subcategories": ["Commercial Insurance", "Cybersecurity", "HR Compliance", "Enterprise Consulting"],
        "keywords": ["shield", "guard", "audit", "insure", "surety", "risk", "trust", "prime", "posture"],
        "commercial_intent_weight": 0.99,
        "market_size_weight": 0.92,
        "buyer_density_weight": 0.95
    },
    "HOME_SERVICES": {
        "slug": "home_services",
        "display_name": "Home Services",
        "description": "Residential HVAC, plumbing, roofing, electrical, cleaning, and remodel contractor software",
        "default_allocation": 0.07,
        "subcategories": ["HVAC Software", "Plumbing Dispatch", "Roofing Estimates", "Trade Contracting", "Home Repair"],
        "keywords": ["home", "pipe", "heat", "cool", "roof", "spark", "clean", "fix", "repair", "craft"],
        "commercial_intent_weight": 0.94,
        "market_size_weight": 0.89,
        "buyer_density_weight": 0.88
    },
    "LOCAL_SERVICES": {
        "slug": "local_services",
        "display_name": "Local Services",
        "description": "Local business marketing, reputation management, customer booking, and local dispatch",
        "default_allocation": 0.07,
        "subcategories": ["Local Booking", "Reputation Management", "Local Business Dispatch", "Review Automation"],
        "keywords": ["local", "serve", "pro", "dispatch", "care", "yard", "route", "book", "reach"],
        "commercial_intent_weight": 0.92,
        "market_size_weight": 0.87,
        "buyer_density_weight": 0.86
    },
    "GEO_SERVICES": {
        "slug": "geo_services",
        "display_name": "Geo Services",
        "description": "Fleet tracking, geo-fencing, physical route optimization, field service dispatch",
        "default_allocation": 0.06,
        "subcategories": ["Fleet Tracking", "Route Optimization", "Geo-Fencing", "Field Services", "Logistics Dispatch"],
        "keywords": ["fleet", "geo", "zone", "track", "route", "map", "point", "haul", "cargo", "roof", "repair", "field", "dispatch"],
        "commercial_intent_weight": 0.90,
        "market_size_weight": 0.86,
        "buyer_density_weight": 0.85
    },
    "B2B_TOOLS": {
        "slug": "b2b_tools",
        "display_name": "B2B Tools",
        "description": "B2B sales enablement, CRM synchronization, RevOps intelligence, and internal tools",
        "default_allocation": 0.07,
        "subcategories": ["Sales Enablement", "RevOps Intelligence", "CRM Sync", "Internal Enterprise Tools"],
        "keywords": ["sync", "metric", "pipe", "suite", "board", "reach", "lead", "rev", "deal"],
        "commercial_intent_weight": 0.91,
        "market_size_weight": 0.88,
        "buyer_density_weight": 0.90
    },
    "EMERGING_TECH": {
        "slug": "emerging_tech",
        "display_name": "Emerging Technology",
        "description": "Robotics telemetry, spatial computing, clean energy tech, quantum software, and IoT",
        "default_allocation": 0.07,
        "subcategories": ["Robotics Telemetry", "Spatial Computing", "Clean Energy Tech", "IoT Systems", "Quantum"],
        "keywords": ["bot", "robo", "spatial", "quantum", "kinetic", "solar", "sensor", "aero", "fusion", "orbit"],
        "commercial_intent_weight": 0.85,
        "market_size_weight": 0.89,
        "buyer_density_weight": 0.82
    }
}

# Backward compatibility alias map
CATEGORY_ALIASES: Dict[str, str] = {
    "AI & Technology": "AI_STARTUPS",
    "Micro-SaaS & Tooling": "MICRO_SAAS",
    "Finance": "FINANCE",
    "B2B High-CPC / Commercial Services": "B2B_HIGH_CPC",
    "Geo Services": "GEO_SERVICES",
    "Crypto / Web3": "CRYPTO_WEB3",
    "Emerging Technology": "EMERGING_TECH",
    "Commerce": "B2B_TOOLS",
    "Sports & Entertainment": "EMERGING_TECH",
    "ai_tech": "AI_STARTUPS",
    "micro_saas": "MICRO_SAAS",
    "finance": "FINANCE",
    "b2b_cpc": "B2B_HIGH_CPC",
    "geo_services": "GEO_SERVICES",
    "crypto_web3": "CRYPTO_WEB3",
    "emerging_tech": "EMERGING_TECH"
}

def normalize_category_name(cat: Optional[str]) -> str:
    """Normalizes any category identifier or display name into canonical universe key."""
    if not cat:
        return "AI_STARTUPS"
    cat_str = str(cat).strip()
    if cat_str in MARKET_CATEGORIES:
        return cat_str
    if cat_str in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[cat_str]
    for key, data in MARKET_CATEGORIES.items():
        if cat_str.lower() == data["display_name"].lower() or cat_str.lower() == data["slug"].lower():
            return key
    # Default fallback
    return "AI_STARTUPS"

def get_category_display_name(cat: Optional[str]) -> str:
    """Returns friendly display name for a category key."""
    canon = normalize_category_name(cat)
    return MARKET_CATEGORIES.get(canon, {}).get("display_name", canon)

class CategoryBudgetManager:
    """Manager for category normalization, quotas, and diversity allocation."""
    @staticmethod
    def normalize_category(cat: Optional[str]) -> str:
        return normalize_category_name(cat)


# =========================================================================
# 2. CONCENTRATION & DIVERSITY THRESHOLDS
# =========================================================================
# Maximum fraction of candidates that any single category is allowed to produce (anti-monopoly guard)
MAX_CATEGORY_CONCENTRATION: float = float(os.getenv("MAX_CATEGORY_CONCENTRATION", "0.20"))

# Enable / Disable multilingual semantic discovery
ENABLE_MULTILINGUAL: bool = os.getenv("ENABLE_MULTILINGUAL", "true").lower() == "true"

# Default category target allocations
DEFAULT_CATEGORY_ALLOCATION: Dict[str, float] = {
    cat: data["default_allocation"] for cat, data in MARKET_CATEGORIES.items()
}

def get_category_allocations() -> Dict[str, float]:
    """Returns the configured or default category target allocations."""
    env_alloc = os.getenv("CATEGORY_ALLOCATIONS")
    if env_alloc:
        try:
            parsed = json.loads(env_alloc)
            tot = sum(parsed.values())
            if 0.95 <= tot <= 1.05:
                return {normalize_category_name(k): v for k, v in parsed.items()}
        except Exception:
            pass
    return DEFAULT_CATEGORY_ALLOCATION.copy()
