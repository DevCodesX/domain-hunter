"""
Phase 2.5: Category Fit & Opportunity Discovery Scoring
Evaluates:
1. Category Fit: Which commercial markets could actually adopt this domain?
2. Opportunity Score: Separate from Quality Score, measures market size, CPC intent, buyer density, and trend signal.
"""

from typing import Dict, Any, Tuple
from opportunity_engine.config import MARKET_CATEGORIES

class CategoryFitScorer:
    """
    Evaluates semantic and lexical alignment across all 9 market categories.
    """

    @staticmethod
    def calculate_category_fit(domain_or_label: str, source_category: str = "") -> Tuple[Dict[str, int], str]:
        """
        Returns a map {category_slug: score_0_to_100} and the primary detected category name.
        """
        label = domain_or_label.lower().strip()
        if label.endswith(".com"):
            label = label[:-4]

        fit_scores: Dict[str, int] = {}
        best_category = "AI_STARTUPS"
        highest_score = 0

        for cat_name, data in MARKET_CATEGORIES.items():
            slug = data["slug"]
            score = 30  # Baseline neutral fit

            # Check keyword matches
            keywords = data.get("keywords", [])
            matches = sum(1 for kw in keywords if kw in label)
            
            if matches >= 2:
                score += 45
            elif matches == 1:
                score += 30

            # Match with explicit source category if known (support aliases)
            if source_category:
                from opportunity_engine.config import CategoryBudgetManager
                norm_src = CategoryBudgetManager.normalize_category(source_category)
                if cat_name == norm_src or (cat_name.lower() in source_category.lower() or source_category.lower() in cat_name.lower()):
                    score += 25

            # Subcategory token matching
            for sub in data.get("subcategories", []):
                for sub_w in sub.lower().split():
                    if len(sub_w) >= 4 and sub_w in label:
                        score += 15
                        break

            clamped = max(10, min(99, score))
            fit_scores[slug] = clamped

            if clamped > highest_score:
                highest_score = clamped
                best_category = cat_name

        return fit_scores, best_category


class OpportunityScorer:
    """
    Calculates the Opportunity Discovery Score (separate from Quality Score).
    Measures the market viability, commercial CPC value, and buyer density.
    """

    @staticmethod
    def calculate_opportunity_score(
        domain: str,
        market_category: str,
        category_fit_scores: Dict[str, int],
        trend_score: int = 80
    ) -> Dict[str, Any]:
        cat_data = MARKET_CATEGORIES.get(market_category)
        if not cat_data:
            from opportunity_engine.config import CategoryBudgetManager
            resolved = CategoryBudgetManager.normalize_category(market_category)
            cat_data = MARKET_CATEGORIES.get(resolved, MARKET_CATEGORIES.get("AI_STARTUPS", list(MARKET_CATEGORIES.values())[0]))
        slug = cat_data["slug"]

        # Component metrics (scaled 0-100)
        commercial_intent = int(cat_data.get("commercial_intent_weight", 0.85) * 100)
        market_size = int(cat_data.get("market_size_weight", 0.85) * 100)
        buyer_density = int(cat_data.get("buyer_density_weight", 0.85) * 100)
        domain_fit = category_fit_scores.get(slug, 70)
        startup_activity = 92 if slug in ["ai_tech", "micro_saas", "crypto_web3", "finance"] else 75

        # Weighted calculation
        # Commercial Intent: 25%, Market Size: 20%, Buyer Density: 20%, Domain Fit: 15%, Trend: 10%, Startup: 10%
        composite = (
            (commercial_intent * 0.25) +
            (market_size * 0.20) +
            (buyer_density * 0.20) +
            (domain_fit * 0.15) +
            (trend_score * 0.10) +
            (startup_activity * 0.10)
        )

        opportunity_score = max(25, min(98, int(round(composite))))

        return {
            "opportunity_score": opportunity_score,
            "commercial_intent": commercial_intent,
            "market_size": market_size,
            "buyer_density": buyer_density,
            "domain_fit": domain_fit,
            "startup_activity": startup_activity,
            "primary_category": market_category,
            "primary_slug": slug
        }
