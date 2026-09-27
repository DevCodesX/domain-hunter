"""
NamingTypeClassifier: Deterministically classifies domain candidates into standard linguistic naming types:
- REAL_WORD / ONE_WORD
- FOREIGN_WORD
- COMPOUND
- INVENTED / COINED
- PREFIX_SUFFIX
- HYBRID
- SEMANTIC_BRANDABLE
- RANDOM

Classification is strictly based on actual linguistic and morphological structure,
completely independent of generation_strategy (generation_strategy != naming_type).
"""

import re
from typing import Dict, Any, Tuple, Optional, List
from quality_engine.feature_extractor import QualityFeatureExtractor
from quality_engine.one_word_engine import OneWordQualityEngine

COMMON_PREFIXES = {
    "get", "try", "use", "my", "go", "the", "hyper", "meta", "omni", "nova", "apex", 
    "zen", "pure", "open", "neo", "pro", "syn", "pan", "re", "uni", "cyber", "auto",
    "algo", "synt", "poly", "tele", "ultra", "multi", "inter", "micro", "macro"
}

COMMON_SUFFIXES = {
    "labs", "lab", "hq", "base", "flow", "stack", "pulse", "craft", "nest", "loop", 
    "grid", "wave", "sync", "node", "hub", "box", "zone", "ly", "fy", "io", "ia",
    "ai", "bot", "cast", "lens", "mind", "path", "run", "set", "shift", "view", "wire",
    "tech", "corp", "sys", "line", "link", "ware", "port"
}

# Common tech/business keywords often found in compound and keyword-brandable domains
TECH_KEYWORDS = {
    "data", "cloud", "code", "dev", "tech", "byte", "bit", "net", "web", "app", 
    "flow", "stack", "node", "grid", "mesh", "link", "sync", "scale", "auth", "crypt",
    "agent", "model", "intel", "neural", "logic", "cyber", "tensor", "metric", "signal",
    "track", "pay", "cash", "coin", "fund", "health", "care", "pulse", "bio", "gene",
    "vault", "forge", "spark", "orbit", "prism", "surge", "haven", "crest", "stride"
}

KNOWN_FOREIGN_ROOTS = {
    # Latin / Classical
    "veritas", "celer", "fidelis", "solum", "valere", "audax", "motus", "ordo", "radix",
    "clarus", "firmus", "rectus", "vindex", "opus", "vectis", "lex", "axis", "statera",
    "tutela", "custos", "fiducia", "pacta", "norma", "jura", "aequitas", "verus", "sanctio",
    "forma", "certo", "proba", "recta", "clario", "valida", "kleros", "celeris", "fluxus",
    "rivus", "nodus", "lumen", "novus", "agilis", "fortis", "faber", "tenax", "prisma",
    "thalweg", "caldera", "strata", "fulcrum", "rhizome", "aurum", "terra", "modus",
    # Italian / Spanish / Romance
    "volo", "vivo", "faro", "bravo", "senso", "primo", "curia", "onda", "brio", "cima",
    "puro", "clair", "elan", "vigie", "pivot", "terra", "sora", "vita", "vero",
    # Greek
    "chronos", "kairos", "kratos", "logos", "telos", "axon", "synapse", "dendrite", "kortex",
    "azimuth", "astrolabe", "kinesis", "noema", "techne", "phronesis",
    # German / Nordic
    "kraft", "stark", "fjord", "malm", "nord",
    # Japanese / Sanskrit
    "zen", "kaizen", "sora", "kumo", "dharma", "karma", "prana"
}

EVOCATIVE_SEMANTIC_ROOTS = {
    "aura", "wave", "loom", "grid", "pulse", "spark", "crest", "beacon", "orbit",
    "nexus", "stride", "flair", "haven", "zenith", "vertex", "tensor", "anchor"
}


class NamingTypeClassifier:
    def __init__(self, one_word_engine: Optional[OneWordQualityEngine] = None):
        self.one_word_engine = one_word_engine or OneWordQualityEngine()
        self.fe = self.one_word_engine.fe

    def split_compound(self, word: str) -> Optional[Tuple[str, str]]:
        """
        Attempts to split a compound word into two recognized, authentic English dictionary words.
        Constraints:
        - Total word length must be at least 6 characters (e.g. 3+3 min).
        - Both left and right parts must be at least 3 characters.
        - Both parts must be verified dictionary words (via OneWordQualityEngine with strict Zipf).
        Example: "cloudnest" -> ("cloud", "nest"), "datadog" -> ("data", "dog").
        Will NEVER split short invented words like "guvni", "woztu", "jipna", "nefqi", "feskop".
        """
        w = word.lower().strip()
        if len(w) < 6:
            return None

        best_split = None
        best_score = 0.0

        for i in range(3, len(w) - 2):
            left = w[:i]
            right = w[i:]

            is_left_dict, left_zipf = self.one_word_engine.is_dictionary_word(left)
            is_right_dict, right_zipf = self.one_word_engine.is_dictionary_word(right)

            if is_left_dict and is_right_dict:
                score = left_zipf + right_zipf
                if score > best_score:
                    best_score = score
                    best_split = (left, right)

        return best_split

    def classify(self, domain_or_label: str) -> Dict[str, Any]:
        """
        Classifies domain into one of the standard naming types:
        REAL_WORD (ONE_WORD), FOREIGN_WORD, COMPOUND, INVENTED (COINED), PREFIX_SUFFIX, HYBRID, SEMANTIC_BRANDABLE, RANDOM

        Strictly decoupled from generation strategy:
        generation_strategy != naming_type
        """
        domain = domain_or_label.lower().replace(".com", "").strip()
        features = self.fe.extract_features(domain)

        # 1. Hard filter failure -> RANDOM / LOW_QUALITY
        if not features["passes_hard_filter"]:
            return {
                "naming_type": "RANDOM",
                "confidence": 0.95,
                "reason": f"Failed hard quality filters: {features.get('hard_rejection_reason')}",
                "components": []
            }

        # 2. Check for authentic English dictionary word: ONE_WORD / REAL_WORD
        one_word_eval = self.one_word_engine.compute_one_word_score(domain)
        if one_word_eval["is_one_word"] and len(domain) <= 12:
            return {
                "naming_type": "ONE_WORD",
                "subtype": "REAL_ONE_WORD",
                "linguistic_type": "REAL_WORD",
                "confidence": 0.95,
                "reason": f"Authentic single dictionary word with Zipf frequency {one_word_eval['word_frequency']}",
                "components": [domain]
            }

        # 3. Check for recognized FOREIGN_WORD (classical or foreign root)
        if domain in KNOWN_FOREIGN_ROOTS:
            return {
                "naming_type": "FOREIGN_WORD",
                "confidence": 0.92,
                "reason": f"Classical / foreign linguistic root ('{domain}')",
                "components": [domain]
            }

        # 4. Check for COMPOUND (Two authentic dictionary words glued together)
        split = self.split_compound(domain)
        if split:
            left, right = split
            is_left_dict, _ = self.one_word_engine.is_dictionary_word(left)
            is_right_dict, _ = self.one_word_engine.is_dictionary_word(right)

            if is_left_dict and is_right_dict:
                functional_prefixes = {"get", "try", "use", "my", "go", "the"}
                functional_suffixes = {"ly", "fy", "io", "ia", "hq", "labs", "lab", "corp", "ware", "port", "sys"}
                if left in functional_prefixes:
                    return {
                        "naming_type": "PREFIX_SUFFIX",
                        "confidence": 0.90,
                        "reason": f"Functional prefix '{left}' attached to root '{right}'",
                        "components": [left, right]
                    }
                if right in functional_suffixes:
                    return {
                        "naming_type": "PREFIX_SUFFIX",
                        "confidence": 0.90,
                        "reason": f"Root '{left}' with functional suffix '{right}'",
                        "components": [left, right]
                    }
                return {
                    "naming_type": "COMPOUND",
                    "confidence": 0.92,
                    "reason": f"Authentic compound word formed by '{left}' and '{right}'",
                    "components": [left, right]
                }

        # 5. Check for PREFIX_SUFFIX pattern with known affixes
        # Prefix check (e.g. "GetPulse", "OmniFlow", "HyperSync")
        for p in sorted(COMMON_PREFIXES, key=len, reverse=True):
            if domain.startswith(p) and len(domain) >= len(p) + 3:
                rem = domain[len(p):]
                is_rem_dict, _ = self.one_word_engine.is_dictionary_word(rem)
                if is_rem_dict or rem in TECH_KEYWORDS or rem in KNOWN_FOREIGN_ROOTS:
                    return {
                        "naming_type": "PREFIX_SUFFIX",
                        "confidence": 0.88,
                        "reason": f"Prefix '{p}' attached to root '{rem}'",
                        "components": [p, rem]
                    }

        # Suffix check (e.g. "PulseLabs", "FlowHQ", "AgentBase")
        for s in sorted(COMMON_SUFFIXES, key=len, reverse=True):
            if domain.endswith(s) and len(domain) >= len(s) + 3:
                base = domain[:-len(s)]
                is_base_dict, _ = self.one_word_engine.is_dictionary_word(base)
                if is_base_dict or base in TECH_KEYWORDS or base in KNOWN_FOREIGN_ROOTS:
                    return {
                        "naming_type": "PREFIX_SUFFIX",
                        "confidence": 0.88,
                        "reason": f"Base '{base}' with brandable suffix '{s}'",
                        "components": [base, s]
                    }

        # 6. Check for HYBRID (One genuine dictionary word + recognized coined suffix/prefix)
        COINED_SUFFIXES = {"ify", "ly", "fy", "io", "ia", "ex", "ix", "ox", "tra", "ora", "iva", "vix", "zen", "gen", "tron", "oid", "able", "ise", "ize"}
        for s in sorted(COINED_SUFFIXES, key=len, reverse=True):
            if domain.endswith(s) and len(domain) >= len(s) + 3:
                base = domain[:-len(s)]
                is_base_dict, _ = self.one_word_engine.is_dictionary_word(base)
                if is_base_dict:
                    return {
                        "naming_type": "HYBRID",
                        "confidence": 0.88,
                        "reason": f"Lexical base '{base}' with coined suffix '{s}'",
                        "components": [base, s]
                    }

        # 7. Check for SEMANTIC_BRANDABLE (Evocative brandable roots)
        if any(root in domain for root in EVOCATIVE_SEMANTIC_ROOTS) and len(domain) <= 11:
            return {
                "naming_type": "SEMANTIC_BRANDABLE",
                "confidence": 0.85,
                "reason": f"Evocative semantic brandable domain",
                "components": [domain]
            }

        # 8. Single-token novel neologisms: INVENTED / COINED
        # (e.g. woztu, guvni, jipna, nefqi, lomdex, kispem, fybris, feskop, plidoc, nyspel, toovira, capevio, masvera, agenvos)
        if features["pronounceability_score"] >= 50.0:
            return {
                "naming_type": "INVENTED",
                "subtype": "INVENTED_ONE_WORD",
                "linguistic_type": "COINED",
                "confidence": 0.88,
                "reason": f"Phonetically sound invented neologism / coined single-token (Pronunciation score {features['pronounceability_score']})",
                "components": [domain]
            }

        # 9. Default fallback: low-pronounceability invented or random
        return {
            "naming_type": "INVENTED" if features["pronounceability_score"] >= 40.0 else "RANDOM",
            "subtype": "INVENTED_ONE_WORD" if features["pronounceability_score"] >= 40.0 else "RANDOM_STRING",
            "linguistic_type": "INVENTED" if features["pronounceability_score"] >= 40.0 else "RANDOM",
            "confidence": 0.65,
            "reason": "Classified based on structural phonetic analysis",
            "components": [domain]
        }
