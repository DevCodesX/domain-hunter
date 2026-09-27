"""
Phase 2.5: Semantic Root Library
Extensible commercial root concepts, morphemes, affixes, and conceptual clusters.
"""

from typing import Dict, List, Any, Set

SEMANTIC_ROOT_LIBRARY: Dict[str, Dict[str, Any]] = {
    "CAPABILITY": {
        "concept": "Capability, agency, tooling, and mastery",
        "roots": ["hand", "mind", "eye", "key", "tool", "engine", "craft", "forge", "skill", "helm", "task", "gear", "prime", "pro"],
        "affixes": ["craft", "work", "smith", "ops", "tech", "forge"],
        "category_affinity": ["AI & Technology", "Micro-SaaS & Tooling", "Geo Services"]
    },
    "SPEED_MOVEMENT": {
        "concept": "Velocity, rapid execution, agility, and dynamic momentum",
        "roots": ["fast", "swift", "flow", "move", "pulse", "wave", "flight", "momentum", "surge", "rush", "dash", "glide", "sprint", "spark"],
        "affixes": ["flow", "pulse", "wave", "glide", "swift", "run"],
        "category_affinity": ["Commerce", "AI & Technology", "Micro-SaaS & Tooling"]
    },
    "INTELLIGENCE_CLARITY": {
        "concept": "Insight, vision, transparency, sense-making, and intellectual precision",
        "roots": ["light", "vision", "sense", "wisdom", "insight", "clear", "bright", "view", "apex", "beam", "lens", "scope", "scan", "aura"],
        "affixes": ["iq", "ai", "mind", "sense", "scope", "view"],
        "category_affinity": ["AI & Technology", "B2B High-CPC / Commercial Services", "Finance"]
    },
    "CONNECTION": {
        "concept": "Interoperability, networks, bridges, integration, and collaboration",
        "roots": ["link", "node", "bridge", "mesh", "network", "connect", "hub", "sync", "rail", "wire", "web", "port", "bond", "dock"],
        "affixes": ["link", "node", "sync", "hub", "mesh", "rail"],
        "category_affinity": ["Crypto / Web3", "Micro-SaaS & Tooling", "Commerce"]
    },
    "BUILDING": {
        "concept": "Foundations, architectural solidity, infrastructure, and synthesis",
        "roots": ["build", "forge", "make", "craft", "base", "root", "foundation", "stack", "frame", "block", "core", "tier", "ground"],
        "affixes": ["base", "stack", "block", "frame", "craft"],
        "category_affinity": ["AI & Technology", "Geo Services", "Crypto / Web3"]
    },
    "GROWTH": {
        "concept": "Expansion, scaling, compounding value, and yield",
        "roots": ["rise", "grow", "scale", "bloom", "expand", "boost", "leap", "surge", "prime", "yield", "sprout", "soar", "gain", "peak"],
        "affixes": ["scale", "boost", "rise", "yield", "grow"],
        "category_affinity": ["Finance", "Micro-SaaS & Tooling", "Commerce"]
    },
    "TRUST_SECURITY": {
        "concept": "Fidelity, auditability, safety, resilience, and verified truth",
        "roots": ["sure", "true", "secure", "solid", "proof", "safe", "vault", "guard", "shield", "ward", "anchor", "lock", "firm", "veritas"],
        "affixes": ["guard", "shield", "safe", "vault", "sure"],
        "category_affinity": ["B2B High-CPC / Commercial Services", "Finance", "Crypto / Web3"]
    }
}

def get_roots_for_category(category: str) -> List[str]:
    """Returns relevant semantic roots that align with a given market category."""
    matched_roots: List[str] = []
    for group_name, data in SEMANTIC_ROOT_LIBRARY.items():
        if category in data.get("category_affinity", []):
            matched_roots.extend(data["roots"])
    if not matched_roots:
        # Fallback to general high-value roots
        matched_roots = SEMANTIC_ROOT_LIBRARY["CAPABILITY"]["roots"] + SEMANTIC_ROOT_LIBRARY["CONNECTION"]["roots"]
    return list(dict.fromkeys(matched_roots))

def find_semantic_cluster(word: str) -> str:
    """Finds which semantic root concept a given word or domain label belongs to."""
    w = word.lower()
    for cluster_name, data in SEMANTIC_ROOT_LIBRARY.items():
        for r in data["roots"]:
            if r in w:
                return cluster_name
        for aff in data["affixes"]:
            if w.endswith(aff) or w.startswith(aff):
                return cluster_name
    return "GENERAL_COMMERCIAL"
