"""
Morphology Classifier: Classifies domain candidates into standard naming morphologies:
- REAL_WORD
- FOREIGN_WORD
- COMPOUND
- INVENTED
- PREFIX_SUFFIX
- HYBRID
- SEMANTIC_BRANDABLE

Tracks morphological distribution to prevent generator monopolization.
"""

import re
from typing import Dict, Any, Optional, Tuple, List
from quality_engine.one_word_engine import OneWordQualityEngine
from quality_engine.brand_refinement import WordGlueDetector


class MorphologyClassifier:
    """
    Determines structural morphology of candidate domains.
    """

    KNOWN_FOREIGN_ROOTS = {
        # Latin / Romance
        "lex", "vox", "veritas", "celer", "nexus", "aurum", "terra", "opus", "modus",
        "statera", "tutela", "custos", "fiducia", "pacta", "norma", "jura",
        "aequitas", "verus", "sanctio", "forma", "ordo", "certo", "proba",
        "recta", "clario", "valida", "kleros", "celeris", "fluxus", "rivus",
        "nodus", "lumen", "novus", "agilis", "fortis", "faber", "tenax",
        "prisma", "thalweg", "caldera", "strata", "fulcrum", "rhizome",
        # Greek
        "axon", "synapse", "dendrite", "kortex", "azimuth", "astrolabe",
        # Japanese / Sanskrit
        "sora", "kumo", "kaizen", "dharma", "karma", "prana"
    }

    AFFIX_LIST = {
        "sdk", "api", "dev", "ops", "rev", "fin", "tax", "pay", "bio",
        "bot", "app", "web", "net", "sys", "geo", "doc", "law", "med",
        "flow", "sync", "mesh", "node", "core", "grid", "wave", "loom"
    }

    def __init__(self):
        self.one_word_engine = OneWordQualityEngine()

    def classify_morphology(
        self,
        domain_or_label: str,
        source_concept: str = "",
        generation_strategy: str = ""
    ) -> Dict[str, Any]:
        """
        Classifies domain into one of the 7 morphology classes:
        REAL_WORD, FOREIGN_WORD, COMPOUND, INVENTED, PREFIX_SUFFIX, HYBRID, SEMANTIC_BRANDABLE
        """
        label = domain_or_label.lower().replace(".com", "").strip()

        # 1. Check for single real dictionary English word
        is_dict, zipf = self.one_word_engine.is_dictionary_word(label)
        if is_dict and zipf >= 3.0 and len(label) <= 12:
            return {
                "morphology": "REAL_WORD",
                "confidence": 0.95,
                "components": [label],
                "details": f"English dictionary word (Zipf: {zipf:.2f})"
            }

        # 2. Check for real foreign / classical root
        if label in self.KNOWN_FOREIGN_ROOTS or any(root == label for root in self.KNOWN_FOREIGN_ROOTS):
            return {
                "morphology": "FOREIGN_WORD",
                "confidence": 0.90,
                "components": [label],
                "details": "Classical/Foreign linguistic root"
            }

        # 3. Check for recognized compound (two dictionary words glued)
        glue_res = WordGlueDetector.detect_word_glue(label)
        if glue_res.get("components") and len(glue_res["components"]) == 2:
            c1, c2 = glue_res["components"]
            if len(c1) >= 3 and len(c2) >= 3:
                is_c1_dict, _ = self.one_word_engine.is_dictionary_word(c1)
                is_c2_dict, _ = self.one_word_engine.is_dictionary_word(c2)

                if is_c1_dict and is_c2_dict:
                    return {
                        "morphology": "COMPOUND",
                        "confidence": 0.92,
                        "components": [c1, c2],
                        "details": f"Dictionary compound ({c1} + {c2})"
                    }
                elif (is_c1_dict and c2 in self.AFFIX_LIST) or (c1 in self.AFFIX_LIST and is_c2_dict):
                    return {
                        "morphology": "PREFIX_SUFFIX",
                        "confidence": 0.88,
                        "components": [c1, c2],
                        "details": f"Affix combination ({c1} + {c2})"
                    }

        # 3b. Direct dictionary compound split (e.g. core+low, data+dog, iron+clad)
        if len(label) >= 6:
            functional_prefixes = {"get", "try", "use", "my", "go", "the", "sdk", "api"}
            functional_suffixes = {"ly", "fy", "io", "ia", "hq", "labs", "lab", "corp", "ware", "port", "sys"}
            for split_idx in range(3, len(label) - 2):
                w1 = label[:split_idx]
                w2 = label[split_idx:]
                is_w1, _ = self.one_word_engine.is_dictionary_word(w1)
                is_w2, _ = self.one_word_engine.is_dictionary_word(w2)
                if is_w1 and is_w2:
                    if w1 in functional_prefixes or w2 in functional_suffixes:
                        return {
                            "morphology": "PREFIX_SUFFIX",
                            "confidence": 0.88,
                            "components": [w1, w2],
                            "details": f"Functional affix combination ({w1} + {w2})"
                        }
                    return {
                        "morphology": "COMPOUND",
                        "confidence": 0.93,
                        "components": [w1, w2],
                        "details": f"Direct dictionary compound ({w1} + {w2})"
                    }


        # 4. Check for known affix prefix/suffix
        for affix in sorted(self.AFFIX_LIST, key=len, reverse=True):
            if label.startswith(affix) and len(label) >= len(affix) + 3:
                stem = label[len(affix):]
                is_stem_dict, _ = self.one_word_engine.is_dictionary_word(stem)
                if is_stem_dict:
                    return {
                        "morphology": "PREFIX_SUFFIX",
                        "confidence": 0.88,
                        "components": [affix, stem],
                        "details": f"Prefix affix '{affix}' + stem '{stem}'"
                    }
            elif label.endswith(affix) and len(label) >= len(affix) + 3:
                stem = label[:-len(affix)]
                is_stem_dict, _ = self.one_word_engine.is_dictionary_word(stem)
                if is_stem_dict:
                    return {
                        "morphology": "PREFIX_SUFFIX",
                        "confidence": 0.88,
                        "components": [stem, affix],
                        "details": f"Stem '{stem}' + suffix affix '{affix}'"
                    }

        # 4b. Check for recognized HYBRID (Dictionary word + coined suffix)
        COINED_SUFFIXES = ("ify", "ly", "fy", "io", "ia", "ex", "ix", "ox", "tra", "ora", "iva", "vix", "zen", "gen", "tron", "oid", "able")
        for cs in COINED_SUFFIXES:
            if label.endswith(cs) and len(label) >= len(cs) + 3:
                stem = label[:-len(cs)]
                is_stem_dict, _ = self.one_word_engine.is_dictionary_word(stem)
                if is_stem_dict:
                    return {
                        "morphology": "HYBRID",
                        "confidence": 0.86,
                        "components": [stem, cs],
                        "details": f"Hybrid dictionary stem '{stem}' + coined suffix '{cs}'"
                    }

        # 5. Check if it's semantic brandable or pure invented
        if generation_strategy == "SEMANTIC_BRANDABLE" or any(s in label for s in ["aura", "wave", "loom", "grid"]):
            return {
                "morphology": "SEMANTIC_BRANDABLE",
                "confidence": 0.80,
                "components": [label],
                "details": "Evocative semantic brandable"
            }

        # 6. Default to INVENTED
        return {
            "morphology": "INVENTED",
            "confidence": 0.88,
            "components": [label],
            "details": "Coined phonetically unified brand"
        }

    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def classify(cls, domain_or_label: str) -> str:
        """Convenience classmethod returning standard morphology string."""
        inst = cls.get_instance()
        res = inst.classify_morphology(domain_or_label)
        return res.get("morphology", "INVENTED")

    @classmethod
    def calculate_ai_naming_artifact_score(cls, domain_or_label: str) -> float:
        """
        Calculates ai_naming_artifact_score (0-100) as a penalty signal for:
        - excessive X/V/Z/Y usage
        - forced Latin-looking endings (-lux, -vos, -vera, -vio, -ync, -tra, -tix)
        - repeated prefixes (sdk, agen)
        - repetitive CVC/CVCC templates with low vowel ratio
        - generic synthetic startup flavor
        """
        label = domain_or_label.lower().replace(".com", "").strip()
        score = 15.0  # baseline organic feel

        # 1. Excessive X, V, Z, Y stuffing
        synthetic_chars = sum(1 for c in label if c in "xvzy")
        if synthetic_chars >= 3:
            score += 32.0
        elif synthetic_chars == 2:
            score += 18.0

        # 2. Forced Latin-looking / synthetic suffixes
        synthetic_endings = ("lux", "vos", "vera", "vio", "ync", "tra", "tix", "ora", "ix", "ox")
        if label.endswith(synthetic_endings):
            score += 24.0

        # 3. Common synthetic prefixes
        if label.startswith(("sdk", "agen", "algo", "synt")):
            score += 22.0

        # 4. Syllable structure & vowel harmony
        vowels = set("aeiouy")
        vowel_ratio = sum(1 for c in label if c in vowels) / max(1, len(label))
        if vowel_ratio < 0.28:
            score += 20.0
        elif vowel_ratio > 0.65:
            score += 10.0

        # 5. Awkward consonant clusters
        awkward = ["sdk", "tk", "zk", "xz", "zx", "jx", "xj", "vj", "jv"]
        if any(a in label for a in awkward):
            score += 25.0

        return round(max(5.0, min(95.0, score)), 2)

    @classmethod
    def infer_template(cls, domain_or_label: str) -> str:
        """
        Infers the structural naming template (e.g. REAL_WORD, PREFIX_STEM, STEM_SUFFIX, COMPOUND, CVC_BLEND).
        """
        label = domain_or_label.lower().replace(".com", "").strip()
        morph = cls.classify(label)
        if morph in ["REAL_WORD", "FOREIGN_WORD"]:
            return "ONE_WORD_ROOT"
        if morph == "COMPOUND":
            return "WORD_WORD_COMPOUND"
        if label.startswith(("meta", "nova", "sync", "flow", "apex", "sdk", "agen")):
            return "PREFIX_STEM"
        if label.endswith(("labs", "base", "flow", "stack", "pulse", "grid", "lux", "vos", "ync")):
            return "STEM_SUFFIX"
        
        # Build consonant-vowel pattern
        cv = "".join("V" if c in "aeiouy" else "C" for c in label)
        return cv if len(cv) <= 8 else "COINED_NEOLOGISM"

