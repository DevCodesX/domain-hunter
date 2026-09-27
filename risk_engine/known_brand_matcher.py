"""
Known Brand Substring Collision Detector
Performs fast, exact substring containment checks against curated known brands.
Enforces category/vertical sensitivity:
- Match in same vertical -> CRITICAL risk
- Match in different vertical -> HIGH risk
- No match -> NO_MATCH (status="NO_MATCH", risk_level=None)
"""

import json
import os
import re
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from risk_engine.models import RiskLevel

logger = logging.getLogger("KnownBrandMatcher")

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "known_brands.json")

class BrandRiskResult(BaseModel):
    status: str = "NO_MATCH"  # "HIT" | "NO_MATCH"
    risk_level: Optional[RiskLevel] = None  # RiskLevel.CRITICAL | RiskLevel.HIGH | None
    matched_brand: Optional[str] = None
    matched_alias: Optional[str] = None
    vertical_match: bool = False
    brand_verticals: List[str] = Field(default_factory=list)
    candidate_vertical: Optional[str] = None
    reason: str = ""

_CACHED_KNOWN_BRANDS: Optional[List[Dict[str, Any]]] = None

def load_known_brands(filepath: Optional[str] = None) -> List[Dict[str, Any]]:
    """Loads and caches the known brands dataset from JSON."""
    global _CACHED_KNOWN_BRANDS
    path = filepath or DATA_PATH
    if _CACHED_KNOWN_BRANDS is not None and filepath is None:
        return _CACHED_KNOWN_BRANDS

    if not os.path.exists(path):
        logger.warning(f"known_brands.json not found at {path}")
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "brands" in data:
                data = data["brands"]
            if filepath is None:
                _CACHED_KNOWN_BRANDS = data
            return data
    except Exception as e:
        logger.error(f"Error loading known brands from {path}: {e}")
        return []

def _normalize_candidate(candidate: str) -> str:
    """Normalizes candidate: strip .com, lowercase, strip non-alphabetic characters."""
    cand = candidate.lower().strip()
    if cand.endswith(".com"):
        cand = cand[:-4]
    return re.sub(r'[^a-z]', '', cand)

def _is_vertical_match(candidate_category: str, brand_verticals: List[str]) -> bool:
    """Checks whether the candidate's category/vertical matches any of the brand's listed verticals."""
    if not candidate_category or not brand_verticals:
        return False

    cand_norm = candidate_category.lower().replace("-", "_").strip()
    cand_tokens = set(re.findall(r'[a-z0-9]+', cand_norm))

    for bv in brand_verticals:
        bv_norm = bv.lower().replace("-", "_").strip()
        bv_tokens = set(re.findall(r'[a-z0-9]+', bv_norm))

        # Direct equality or substring containment
        if cand_norm == bv_norm or cand_norm in bv_norm or bv_norm in cand_norm:
            return True

        # Token set overlap (e.g. "finance" in {"personal", "finance"})
        if cand_tokens & bv_tokens:
            return True

    return False

def check_known_brand_collision(
    candidate: str,
    category: str = "",
    known_brands_data: Optional[List[Dict[str, Any]]] = None
) -> BrandRiskResult:
    """
    Checks for exact substring containment of any brand alias within the normalized candidate string.
    - If match found:
        - If candidate's category/vertical matches brand verticals -> CRITICAL
        - If category differs -> HIGH
    - If no match found -> NO_MATCH (risk_level=None)
    Minimum alias length of 4 characters prevents false positives.
    """
    if not candidate:
        return BrandRiskResult(
            status="NO_MATCH",
            risk_level=None,
            reason="Empty candidate string"
        )

    norm_cand = _normalize_candidate(candidate)
    if len(norm_cand) < 4:
        return BrandRiskResult(
            status="NO_MATCH",
            risk_level=None,
            reason="Candidate too short for substring screening"
        )

    brands = known_brands_data if known_brands_data is not None else load_known_brands()

    matches = []
    for entry in brands:
        brand_name = entry.get("brand", "")
        aliases = entry.get("aliases", [])
        verticals = entry.get("vertical", [])

        for alias in aliases:
            clean_alias = alias.lower().strip()
            # Enforce minimum alias length of 4 characters to guard against false positives
            if len(clean_alias) >= 4 and clean_alias in norm_cand:
                vert_match = _is_vertical_match(category, verticals)
                matches.append({
                    "brand": brand_name,
                    "alias": clean_alias,
                    "verticals": verticals,
                    "vertical_match": vert_match,
                    "risk_level": RiskLevel.CRITICAL if vert_match else RiskLevel.HIGH,
                    "alias_len": len(clean_alias)
                })

    if not matches:
        return BrandRiskResult(
            status="NO_MATCH",
            risk_level=None,
            matched_brand=None,
            matched_alias=None,
            vertical_match=False,
            brand_verticals=[],
            candidate_vertical=category,
            reason="No known brand collision detected"
        )

    # Sort matches: CRITICAL over HIGH, then longest matched alias
    def sort_key(m):
        severity = 2 if m["risk_level"] == RiskLevel.CRITICAL else 1
        return (severity, m["alias_len"])

    matches.sort(key=sort_key, reverse=True)
    best = matches[0]

    if best["vertical_match"]:
        reason = (
            f"Known brand collision: candidate encapsulates '{best['brand']}' "
            f"(alias '{best['alias']}') matching vertical '{category}' -> CRITICAL risk"
        )
    else:
        brand_verts_str = ", ".join(best["verticals"]) if best["verticals"] else "unspecified"
        reason = (
            f"Known brand collision: candidate encapsulates '{best['brand']}' "
            f"(alias '{best['alias']}'). Vertical differs (brand: [{brand_verts_str}], "
            f"candidate: '{category}') -> HIGH risk"
        )

    return BrandRiskResult(
        status="HIT",
        risk_level=best["risk_level"],
        matched_brand=best["brand"],
        matched_alias=best["alias"],
        vertical_match=best["vertical_match"],
        brand_verticals=best["verticals"],
        candidate_vertical=category,
        reason=reason
    )
