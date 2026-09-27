"""
ExistingBrandEngine: Detects whether a domain candidate conflicts with an existing business, product, or brand.
Outputs brand statuses:
- NO_SIGNIFICANT_USE
- MINOR_USE
- ACTIVE_BUSINESS
- ESTABLISHED_BRAND
- FAMOUS_BRAND
With confidence and supporting evidence.
"""

from typing import Dict, Any, List, Optional
from risk_engine.models import BrandStatus, ExistingBrandMatch
from risk_engine.curated_brands import CURATED_BRANDS
from risk_engine.similarity import calculate_comprehensive_similarity

class ExistingBrandEngine:
    def __init__(self, brands_db: Optional[Dict[str, Dict[str, Any]]] = None):
        self.brands_db = brands_db or CURATED_BRANDS

    def analyze_domain(self, domain_label: str) -> List[ExistingBrandMatch]:
        """
        Analyzes domain for potential conflicts with known brands, products, or startups.
        Returns a list of ExistingBrandMatch instances with evidence and confidence.
        """
        label = domain_label.lower().replace(".com", "").strip()
        matches: List[ExistingBrandMatch] = []

        # 1. Exact match against curated brand database
        if label in self.brands_db:
            info = self.brands_db[label]
            status_enum = BrandStatus(info["status"])
            matches.append(ExistingBrandMatch(
                brand_name=label,
                brand_status=status_enum,
                confidence=1.0,
                source="curated_brand_database",
                evidence=f"Exact match with {info['status'].replace('_', ' ').title()}: '{label}' in {info['category']}."
            ))
            return matches

        # 2. Brand encapsulation / compound check (e.g. "cloudstripe", "getapple", "metaflow")
        for brand, info in self.brands_db.items():
            if len(brand) >= 4 and brand in label:
                # If brand is embedded as full word
                status_enum = BrandStatus(info["status"])
                confidence = 0.88 if info["status"] == "FAMOUS_BRAND" else 0.75
                matches.append(ExistingBrandMatch(
                    brand_name=brand,
                    brand_status=status_enum,
                    confidence=confidence,
                    source="brand_inclusion_analysis",
                    evidence=f"Domain encapsulates known brand '{brand}' ({info['category']})."
                ))

        # 3. Phonetic and fuzzy similarity check against famous/established brands
        for brand, info in self.brands_db.items():
            # Skip if length discrepancy is huge
            if abs(len(label) - len(brand)) > 3:
                continue

            sim = calculate_comprehensive_similarity(label, brand)
            if sim["composite_similarity"] >= 0.85:
                status_enum = BrandStatus(info["status"])
                matches.append(ExistingBrandMatch(
                    brand_name=brand,
                    brand_status=status_enum,
                    confidence=round(sim["composite_similarity"], 2),
                    source="phonetic_brand_similarity",
                    evidence=f"High phonetic/string similarity ({sim['composite_similarity']:.2f}) with '{brand}' ({info['category']}). Phonetic match: {sim['is_phonetic_match']}."
                ))

        return matches
