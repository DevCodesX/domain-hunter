"""
Phase 2.75: Naming Intelligence Refinement
Provides:
1. Word-Glue Detector (catches generic adjective+noun / verb+noun combinations)
2. Compound Naturalness Scorer (evaluates semantic harmony, rhythm, and intentionality)
3. AI-Generated Feel Detector (detects synthetic letter stuffing, forced -ix/-ox/-tra, etc.)
4. Candidate Trend Fit Scorer (fixes the identical Trend 82 bug)
5. Buyer Clarity Scorer (identifies realistic commercial buyers, count, and industries)
6. Final Judge Assessment (evaluates the 10 final criteria before publication)
"""

import re
import logging
from typing import Dict, Any, List, Optional, Tuple, Set

logger = logging.getLogger("BrandRefinement")

# =========================================================================
# 1. WORD-GLUE LEXICONS (GENERIC ADJECTIVES, VERBS & NOUNS)
# =========================================================================
GENERIC_ADJECTIVES: Set[str] = {
    "clear", "firm", "still", "sure", "pure", "fast", "raw", "dark", "deep",
    "light", "true", "solid", "prime", "sharp", "cold", "hot", "dry", "wet",
    "soft", "hard", "fine", "bold", "free", "quick", "swift", "safe", "cool",
    "warm", "grand", "wise", "open", "full", "clean", "rich", "flat", "lean",
    "broad", "keen", "best", "real", "fair", "high", "low", "mega", "meta"
}

GENERIC_VERBS: Set[str] = {
    "bind", "dock", "drop", "make", "take", "find", "send", "hold", "cast",
    "lead", "call", "tell", "meet", "keep", "show", "turn", "work", "play",
    "pass", "look", "pull", "push", "pack", "pick", "test", "build", "link",
    "sync", "snap", "grab", "fetch", "lock", "flow", "rush", "scan"
}

GENERIC_NOUNS: Set[str] = {
    "tether", "clause", "term", "rule", "pact", "keel", "dock", "flow",
    "link", "base", "stack", "tool", "core", "desk", "kit", "grid", "node",
    "line", "mark", "point", "port", "post", "path", "side", "spot", "step",
    "track", "view", "wave", "wire", "word", "zone", "pack", "deck", "board",
    "hub", "gate", "rail", "pipe", "box", "bay", "mesh", "helm", "beam", "byte"
}

# AI synthetic naming patterns (excessive sibilants, repetitive tech suffixes)
AI_SYNTHETIC_SUFFIXES = ["ix", "ox", "ium", "ex", "ax", "tra", "ora", "ify", "iva", "vix"]


class WordGlueDetector:
    """
    Detects candidates that are merely two relevant words artificially glued together
    (e.g., [generic adjective] + [generic noun] or [generic verb] + [generic noun])
    with little distinctive brand identity.
    """

    @classmethod
    def detect_word_glue(cls, domain_or_label: str) -> Dict[str, Any]:
        label = domain_or_label.lower().replace(".com", "").strip()
        length = len(label)

        detected = False
        glue_type = None
        part1 = ""
        part2 = ""
        penalty = 0
        reasons = []

        # Check split positions between 3 and length - 3
        for split_pos in range(3, length - 2):
            w1 = label[:split_pos]
            w2 = label[split_pos:]

            # Case A: Generic Adjective + Generic Noun (e.g. clear+tether, firm+clause, still+tether)
            if w1 in GENERIC_ADJECTIVES and w2 in GENERIC_NOUNS:
                detected = True
                glue_type = "ADJECTIVE_PLUS_NOUN"
                part1, part2 = w1, w2
                penalty = 28
                reasons.append(f"Generic adjective+noun word glue ('{w1}' + '{w2}')")
                break

            # Case B: Generic Verb + Generic Noun (e.g. bind+rule, dock+term)
            elif w1 in GENERIC_VERBS and w2 in GENERIC_NOUNS:
                detected = True
                glue_type = "VERB_PLUS_NOUN"
                part1, part2 = w1, w2
                penalty = 26
                reasons.append(f"Generic verb+noun word glue ('{w1}' + '{w2}')")
                break

            # Case C: Generic Noun + Generic Noun with weak brand identity (e.g. dock+term)
            elif w1 in GENERIC_NOUNS and w2 in GENERIC_NOUNS and w1 != w2:
                detected = True
                glue_type = "NOUN_PLUS_NOUN"
                part1, part2 = w1, w2
                penalty = 22
                reasons.append(f"Generic dual-noun collision ('{w1}' + '{w2}')")
                break

        # Check if either word is especially stale/overused in domain hunting
        stale_pairs = [("clear", "tether"), ("still", "tether"), ("firm", "clause"), ("bind", "rule"), ("dock", "term")]
        for p1, p2 in stale_pairs:
            if label == f"{p1}{p2}":
                penalty = max(penalty, 35)
                reasons.append("Highly generic, literal domain-hunting construct")
                break

        return {
            "is_word_glue": detected,
            "glue_type": glue_type,
            "components": [part1, part2] if detected else [],
            "word_glue_penalty": penalty,
            "reasons": reasons
        }


class AIGeneratedFeelDetector:
    """
    Detects low-quality synthetic naming patterns commonly produced by AI models:
    - excessive X/V/Z usage
    - repetitive forced suffixes (-ix, -ox, -vix, -tra)
    - forced Latin-like endings on non-lexical stems
    - awkward artificial blending
    """

    @classmethod
    def evaluate_ai_feel(cls, domain_or_label: str) -> Dict[str, Any]:
        label = domain_or_label.lower().replace(".com", "").strip()
        length = len(label)

        ai_score = 15  # Baseline neutral
        flags = []

        # 1. Count high-entropy AI letters (x, z, v, q, j)
        high_entropy_letters = sum(1 for c in label if c in "xzvqj")
        if high_entropy_letters >= 3:
            ai_score += 35
            flags.append(f"Excessive synthetic consonant stuffing ({high_entropy_letters} x/z/v/q/j letters)")
        elif high_entropy_letters == 2 and length <= 7:
            ai_score += 15
            flags.append("High concentration of synthetic letters")

        # 2. Check for repetitive synthetic suffixes
        for sfx in AI_SYNTHETIC_SUFFIXES:
            if label.endswith(sfx) and len(label) > len(sfx) + 2:
                # If it's a known authentic Latin word like 'radix', 'apex', 'nexus', don't flag!
                if label not in ["apex", "radix", "nexus", "matrix", "vertex", "flux", "index"]:
                    ai_score += 25
                    flags.append(f"Common synthetic AI suffix '-{sfx}'")
                    break

        # 3. Check for awkward consonant triples
        if re.search(r'[bcdfghjklmnpqrstvwxyz]{4,}', label):
            ai_score += 20
            flags.append("Unnatural consonant cluster")

        # 4. Check for forced quasi-Latin endings (e.g. -dix, -trix, -vix, -zix)
        if re.search(r'[a-z]{3,}[dtvz]ix$', label):
            ai_score += 20
            flags.append("Forced quasi-Latin synthetic ending")

        ai_score = max(5, min(95, ai_score))
        penalty = max(0, int((ai_score - 40) * 0.5)) if ai_score > 40 else 0

        return {
            "ai_generated_feel_score": ai_score,
            "penalty": penalty,
            "is_flagged": ai_score >= 50,
            "flags": flags
        }


class CompoundNaturalnessScorer:
    """
    Evaluates whether a compound domain name sounds like an intentional, high-synergy brand
    (e.g., Coinbase, Snapchat, DoorDash, Ironclad) vs an awkward forced pairing.
    """

    @classmethod
    def calculate_compound_naturalness(cls, domain_or_label: str, glue_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        label = domain_or_label.lower().replace(".com", "").strip()
        length = len(label)

        if glue_info is None:
            glue_info = WordGlueDetector.detect_word_glue(label)

        base_score = 85
        penalties = 0
        bonuses = 0
        reasons = []

        # 1. Apply word-glue penalty
        if glue_info.get("is_word_glue"):
            penalties += glue_info.get("word_glue_penalty", 25)
            reasons.extend(glue_info.get("reasons", []))

        # 2. Syllable & length balance
        # Great compounds typically have 2 words of roughly balanced length (e.g., 4+4, 4+5, 5+4)
        if glue_info.get("components") and len(glue_info["components"]) == 2:
            len1, len2 = len(glue_info["components"][0]), len(glue_info["components"][1])
            diff = abs(len1 - len2)
            if diff <= 1:
                bonuses += 6  # Well-balanced visual cadence
                reasons.append("Balanced visual length")
            elif diff >= 4:
                penalties += 8  # Lopsided compound (e.g. 7+3 or 8+3)
                reasons.append("Lopsided word length")

        # 3. Consonant collision at junction (e.g., 'd' colliding with 't' in dock+term, 'd' with 'p' in citadel+pact)
        if glue_info.get("components") and len(glue_info["components"]) == 2:
            c1_end = glue_info["components"][0][-1]
            c2_start = glue_info["components"][1][0]
            if c1_end in "bcdfghjklmnpqrstvwxyz" and c2_start in "bcdfghjklmnpqrstvwxyz":
                # Hard stop consonant junction
                if c1_end in "pbtdkg" and c2_start in "pbtdkg":
                    penalties += 10
                    reasons.append(f"Hard consonant stop collision ('{c1_end}-{c2_start}') at junction")

        # 4. Length penalty for long compounds
        if length > 12:
            penalties += (length - 12) * 5
            reasons.append(f"Excessive compound length ({length} chars)")

        score = max(20, min(98, base_score - penalties + bonuses))

        return {
            "compound_naturalness_score": score,
            "is_natural": score >= 70,
            "reasons": reasons
        }


class BuyerClarityScorer:
    """
    Evaluates commercial buyer clarity:
    "Who would realistically buy/use this domain?"
    Distinguishes sharp commercial use cases from vague, awkward names with no buyer archetype.
    """

    @classmethod
    def evaluate_buyer_clarity(
        cls,
        domain_or_label: str,
        market_category: str = "AI & Technology",
        category_fit_scores: Optional[Dict[str, int]] = None
    ) -> Dict[str, Any]:
        import hashlib
        label = domain_or_label.lower().replace(".com", "").strip()
        n = len(label)

        # Archetype mapping by category
        industry_archetypes: Dict[str, Tuple[List[str], str]] = {
            "AI & Technology": (
                ["AI SaaS", "Autonomous Agents", "Developer Tools", "Data Infrastructure"],
                "AI Agent / Autonomous Workflow Platform"
            ),
            "Micro-SaaS & Tooling": (
                ["B2B Productivity", "Developer Tooling", "Workflow Automation", "Analytics"],
                "B2B Micro-SaaS Tool"
            ),
            "Finance": (
                ["FinTech", "Treasury Rails", "Cross-Border Payments", "Tax Automation"],
                "Corporate Treasury & Liquidity Protocol"
            ),
            "B2B High-CPC / Commercial Services": (
                ["Corporate Legal Tech", "Enterprise Insurance", "Cybersecurity", "Compliance"],
                "Enterprise Legal & Risk Intelligence Platform"
            ),
            "Crypto / Web3": (
                ["Stablecoin Rails", "Treasury Infrastructure", "DeFi", "Institutional Custody"],
                "Corporate Stablecoin & Settlement Infrastructure"
            ),
            "Geo Services": (
                ["Trade Contractor Software", "HVAC / Plumbing Dispatch", "Local Field Services"],
                "Trade Services Dispatch & Fleet Intelligence"
            ),
            "Commerce": (
                ["Supply Chain Logistics", "Retail Tech", "Marketplace Infrastructure"],
                "Multi-Carrier Shipping & Fulfillment Engine"
            ),
            "Emerging Technology": (
                ["Autonomous Robotics", "Industrial IoT", "Energy Computing"],
                "Warehouse Robotics Telemetry Cloud"
            ),
            "Sports & Entertainment": (
                ["Interactive Sports Media", "Fan Engagement", "Esports Platforms"],
                "Digital Fan Community & Sports Media Platform"
            )
        }

        matched_data = industry_archetypes.get(market_category, industry_archetypes["AI & Technology"])
        industries, default_fit = matched_data

        # 1. Base commercial credibility by length
        if 4 <= n <= 6:
            base = 82.0 + (6 - n) * 2.2
        elif n == 7:
            base = 81.5
        elif n == 8:
            base = 78.0
        elif n <= 10:
            base = 72.0 - (n - 8) * 3.5
        else:
            base = max(45.0, 65.0 - (n - 10) * 4.0)

        # 2. Category baseline
        cat_bonuses = {
            "AI & Technology": 5.5,
            "B2B High-CPC / Commercial Services": 6.0,
            "Finance": 5.5,
            "Micro-SaaS & Tooling": 4.0,
            "Crypto / Web3": 4.0
        }
        base += cat_bonuses.get(market_category, 2.0)

        # 3. High-intent commercial keyword clarity boost
        COMMERCIAL_KEYWORDS = {
            "agent", "core", "pay", "vault", "cloud", "data", "flow", "stack", "chain",
            "link", "sync", "mesh", "node", "tech", "app", "fund", "cash", "pulse",
            "intel", "model", "mind", "base", "hub", "box", "net", "web", "code", "dev"
        }
        kw_matches = sum(1 for kw in COMMERCIAL_KEYWORDS if kw in label)
        base += min(12.0, kw_matches * 5.0)

        # 4. Professional endings vs awkward clusters
        authoritative_endings = ("ic", "is", "ex", "ix", "or", "us", "en", "on", "er", "ium", "os", "al", "a", "o")
        if label.endswith(authoritative_endings):
            base += 3.8
        elif label.endswith(("lux", "vos", "ync", "vio", "tra", "tix")):
            base -= 2.2

        harsh_pairs = {"zt", "fq", "gq", "zk", "xz", "zx", "jx", "xj", "vj", "jv", "qp"}
        harsh_pen = sum(10.0 for i in range(n - 1) if label[i:i+2] in harsh_pairs)
        if "q" in label and "qu" not in label:
            harsh_pen += 12.0
        base -= harsh_pen

        # Fine deterministic string variance (0.001 - 1.999 pts) to guarantee unique scores
        h = (int(hashlib.sha256(label.encode("utf-8")).hexdigest()[6:12], 16) / 0xFFFFFF) * 2.0
        base += h

        score = round(max(30.0, min(97.0, base)), 3)
        buyer_count = 4 if score >= 85 else (3 if score >= 70 else 2)

        return {
            "buyer_clarity_score": score,
            "candidate_commercial_fit": score,
            "buyer_count": buyer_count,
            "buyer_industries": industries,
            "startup_fit": f"{default_fit} ({market_category})"
        }


class CandidateTrendFitScorer:
    """
    Evaluates how naturally a specific domain aligns with an underlying opportunity/trend.
    Strictly separates concept_trend_score from candidate_trend_fit_score with high resolution.
    Candidate trend fit is derived directly from the candidate string, NOT copied from concept.
    """

    @classmethod
    def calculate_trend_fit(
        cls,
        domain_or_label: str,
        concept: str,
        concept_trend_relevance: float = 85.0,
        market_category: str = "AI & Technology"
    ) -> Dict[str, Any]:
        import hashlib
        label = domain_or_label.lower().replace(".com", "").strip()
        n = len(label)

        # Concept trend score is strictly the macro trend score for the parent opportunity
        concept_trend_score = round(max(50.0, min(99.0, float(concept_trend_relevance))), 3)

        # Candidate specific fit based on candidate string features, semantic overlap, and modern tech lexicon
        concept_words = [w.lower() for w in re.findall(r"[a-zA-Z]{4,}", concept)]
        exact_matches = sum(1 for w in concept_words if w == label or (len(w) >= 5 and w in label) or (len(w) >= 4 and label.startswith(w)))
        partial_matches = sum(1 for w in concept_words if len(w) >= 4 and (w[:4] in label or label.startswith(w[:4])))

        # 2. Modern tech vocabulary relevance (context-aware)
        modern_tech_roots = {
            "agent": 22.0, "flow": 18.0, "mesh": 16.0, "node": 15.0, "sync": 16.0,
            "cloud": 14.0, "data": 16.0, "core": 14.0, "vault": 15.0, "stack": 14.0,
            "mind": 14.0, "pulse": 14.0, "tensor": 18.0, "logic": 15.0, "link": 12.0,
            "model": 15.0, "relay": 14.0, "stream": 14.0, "craft": 12.0, "grid": 12.0,
            "vector": 16.0, "scale": 12.0, "forge": 14.0, "haven": 10.0, "apex": 12.0
        }
        root_score = 0.0
        for root, val in modern_tech_roots.items():
            if root in label:
                root_score = max(root_score, val)

        # 3. Acoustic sound symbolism for tech innovation (alveolars, coronal fricatives, agile front vowels)
        TECH_FORWARD_LETTERS = set("tdszlneio")
        tech_sound_ratio = sum(1 for c in label if c in TECH_FORWARD_LETTERS) / max(1, n)

        # 4. Awkward / dated consonant clusters (penalize harsh combinations like zt, fq, gq)
        harsh_pairs = {"zt", "fq", "gq", "zk", "xz", "zx", "jx", "xj", "vj", "jv", "qp"}
        harsh_pen = sum(14.0 for i in range(n - 1) if label[i:i+2] in harsh_pairs)
        if "q" in label and "qu" not in label:
            harsh_pen += 16.0

        if exact_matches >= 1:
            base = 82.0 + (exact_matches * 6.0)
        elif partial_matches >= 1:
            base = 74.0 + (partial_matches * 4.0)
        elif root_score > 0:
            base = 68.0 + root_score
        else:
            base = 52.0 + (tech_sound_ratio * 26.0)

        # Length curve
        if 5 <= n <= 7:
            base += 4.5
        elif n <= 4:
            base += 2.0
        elif n >= 10:
            base -= (n - 9) * 3.5

        base -= harsh_pen

        # Fine deterministic string variance (0.001 - 1.999 pts) to guarantee unique scores
        h = (int(hashlib.sha256(label.encode("utf-8")).hexdigest()[:6], 16) / 0xFFFFFF) * 2.0
        base += h

        candidate_trend_fit_score = round(max(35.0, min(98.5, base)), 3)

        # Blended trend score (blends macro concept opportunity with candidate's specific fit)
        blended_trend_score = round((concept_trend_score * 0.25) + (candidate_trend_fit_score * 0.75), 3)

        return {
            "concept_trend_score": concept_trend_score,
            "candidate_trend_fit_score": candidate_trend_fit_score,
            "blended_trend_score": blended_trend_score
        }


class FinalJudge:
    """
    Evaluates the 10 final criteria before a domain reaches the published results list:
    1. Real startup plausibility
    2. Memorability
    3. Pronounceability
    4. Spellability (Radio test)
    5. Linguistic naturalness (Not word-glue)
    6. Commercial flexibility
    7. Clear buyer identity
    8. Distinctiveness
    9. AI-generated feel score (low = good)
    10. Long-term expansion potential (works beyond initial product)
    """

    @classmethod
    def evaluate(
        cls,
        domain: str,
        quality_score: int,
        natural_brand_score: int,
        startup_naturalness_score: int,
        radio_test_score: int,
        buyer_clarity: Dict[str, Any],
        word_glue: Dict[str, Any],
        ai_feel: Dict[str, Any],
        market_category: str
    ) -> Dict[str, Any]:
        label = domain.lower().replace(".com", "").strip()

        # Assess 10 criteria
        c1_startup_plausibility = startup_naturalness_score >= 68
        c2_memorability = len(label) <= 11 and not ai_feel["is_flagged"]
        c3_pronounceability = radio_test_score >= 70
        c4_spellability = radio_test_score >= 75
        c5_linguistic_naturalness = not word_glue["is_word_glue"] or word_glue["word_glue_penalty"] <= 20
        c6_commercial_flexibility = quality_score >= 70
        c7_clear_buyer = buyer_clarity["buyer_clarity_score"] >= 65
        c8_distinctiveness = len(label) <= 10 and not ai_feel["is_flagged"]
        c9_low_ai_feel = ai_feel["ai_generated_feel_score"] <= 55
        c10_expansion_potential = len(label) <= 9 and natural_brand_score >= 70

        criteria_met = sum([
            c1_startup_plausibility, c2_memorability, c3_pronounceability,
            c4_spellability, c5_linguistic_naturalness, c6_commercial_flexibility,
            c7_clear_buyer, c8_distinctiveness, c9_low_ai_feel, c10_expansion_potential
        ])

        # Overall verdict: passes if at least 7/10 criteria met and quality_score >= 70
        verdict = "APPROVED" if (criteria_met >= 7 and quality_score >= 70) else "REJECTED"

        assessment = {
            "verdict": verdict,
            "score": int(round((criteria_met / 10.0) * 100)),
            "criteria": {
                "real_startup_plausibility": c1_startup_plausibility,
                "memorability": c2_memorability,
                "pronounceability": c3_pronounceability,
                "spellability": c4_spellability,
                "linguistic_naturalness": c5_linguistic_naturalness,
                "commercial_flexibility": c6_commercial_flexibility,
                "clear_buyer": c7_clear_buyer,
                "distinctiveness": c8_distinctiveness,
                "low_ai_feel": c9_low_ai_feel,
                "expansion_potential": c10_expansion_potential
            },
            "criteria_met_count": criteria_met,
            "target_buyer": buyer_clarity.get("startup_fit", market_category)
        }

        return assessment
