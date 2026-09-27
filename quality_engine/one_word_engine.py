"""
OneWordQualityEngine: Dedicated linguistic engine to evaluate one-word domain candidates.
Distinguishes real dictionary words from invented words, compounds, phrases, and random strings.
Uses wordfreq for Zipf frequencies and lexical familiarity, with graceful local fallback.
"""

import math
from typing import Dict, Any, Optional, Tuple
from quality_engine.feature_extractor import QualityFeatureExtractor

# Try importing wordfreq
try:
    from wordfreq import zipf_frequency, word_frequency
    WORDFREQ_AVAILABLE = True
except ImportError:
    WORDFREQ_AVAILABLE = False
    def zipf_frequency(word: str, lang: str = "en") -> float:
        return 0.0
    def word_frequency(word: str, lang: str = "en") -> float:
        return 0.0

# Curated core vocabulary set for instant O(1) dictionary verification
# Supplemented with common tech/business nouns, verbs, and adjectives
CORE_VOCAB_SAMPLE = {
    "data", "cloud", "flow", "forge", "spark", "pulse", "stream", "stack", "nest", "wave", "logic",
    "craft", "vault", "prism", "nexus", "shift", "orbit", "surge", "grid", "node", "core",
    "crest", "beacon", "haven", "summit", "stride", "scale", "sphere", "matrix", "vector", "apex",
    "vibe", "blend", "scope", "pivot", "drive", "trace", "bloom", "fleet", "flock", "flair",
    "sparkle", "glimmer", "radiant", "zenith", "vertex", "tensor", "anchor", "canvas", "ledger", "quantum",
    "stride", "cipher", "beacon", "foster", "timber", "harbor", "atlas", "mantle", "sentry", "chronicle",
    "path", "link", "gate", "loop", "seed", "byte", "sync", "fuse", "flare", "tempo",
    "glyph", "aura", "echo", "halo", "rune", "crest", "quest", "reach", "spark", "swift",
    "brave", "prime", "solid", "vivid", "noble", "bold", "clear", "fresh", "bright", "smart",
    "trust", "merit", "valor", "honor", "grace", "vigor", "vigor", "verve", "zest", "keen"
}

# Curated real 3-letter English words with high lexical familiarity
REAL_3_LETTER_WORDS = {
    "app", "dev", "net", "web", "doc", "pay", "hub", "lab", "bot", "fit", "key", "art",
    "box", "sun", "air", "sky", "red", "law", "med", "bio", "tax", "run", "top", "car",
    "log", "cat", "dog", "fox", "zen", "bar", "pro", "sea", "one", "day", "way", "bit",
    "byte", "row", "map", "set", "gem", "tip", "ace", "joy", "aim", "ray", "arc", "dot",
    "cap", "tag", "pad", "tab", "bag", "cup", "fan", "van", "bed", "oil", "gas", "ice",
    "pin", "pot", "rod", "jar", "rug", "tin", "lid", "pan", "pen", "ink", "hat", "tie",
    "nut", "fly", "bee", "bug", "ant", "cow", "pig", "owl", "bat", "elk", "ape", "zoo",
    "arm", "eye", "ear", "lip", "jaw", "rib", "hip", "leg", "toe", "gut", "fat", "age",
    "era", "god", "man", "boy", "son", "guy", "lad", "sir", "dad", "mom", "kid", "kin",
    "foe", "spy", "cop", "vet", "act", "aid", "ask", "beg", "bet", "bid", "bow", "buy",
    "cry", "cue", "cut", "dig", "dip", "dry", "eat", "end", "err", "fed", "fee", "fix",
    "get", "has", "had", "hit", "hop", "hug", "jam", "jog", "jot", "lay", "led", "let",
    "lie", "lit", "met", "mix", "nod", "opt", "owe", "own", "peg", "pop", "put", "ran",
    "rid", "rip", "rob", "rot", "rub", "saw", "say", "see", "sew", "sit", "tap", "try",
    "tug", "use", "vow", "war", "wed", "wet", "win", "won", "zap", "zip", "raw"
}


class OneWordQualityEngine:
    def __init__(self, feature_extractor: Optional[QualityFeatureExtractor] = None):
        self.fe = feature_extractor or QualityFeatureExtractor()

    def is_dictionary_word(self, word: str) -> Tuple[bool, float]:
        """
        Check if word is an authentic English dictionary word and return (is_dict, zipf_score).
        Requires genuine lexical presence:
        - Words < 3 chars are NEVER considered standalone dictionary words for domain naming.
        - 3-letter words must be established English words with Zipf >= 3.6.
        - Words >= 4 chars must have Zipf >= 3.2 or be in CORE_VOCAB_SAMPLE.
        """
        w = word.lower().strip()
        if not w.isalpha() or len(w) < 3:
            return False, 0.0

        if w in CORE_VOCAB_SAMPLE:
            z = zipf_frequency(w, "en") if WORDFREQ_AVAILABLE else 4.5
            return True, max(z, 4.0)

        if WORDFREQ_AVAILABLE:
            z = zipf_frequency(w, "en")
            if len(w) == 3:
                # 3-letter words must be in curated English lexicon and have high usage
                if w in REAL_3_LETTER_WORDS and z >= 3.6:
                    return True, z
                return False, z
            else:
                # 4+ letter words require Zipf >= 3.2 for authentic dictionary standing
                if z >= 3.2:
                    return True, z
                return False, z

        # Fallback if wordfreq is unavailable
        if len(w) == 3 and w in REAL_3_LETTER_WORDS:
            return True, 4.0

        return False, 0.0

    def compute_lexical_familiarity(self, zipf_score: float) -> float:
        """
        Maps Zipf frequency (typically 0.0 to 7.0) to a 0-100 familiarity index.
        Zipf 5.0+ -> 95-100 (Household words: 'water', 'cloud')
        Zipf 4.0-5.0 -> 80-94 (High recognition: 'forge', 'nexus')
        Zipf 3.0-4.0 -> 60-79 (Solid recognition: 'zenith', 'vector')
        Zipf 1.5-2.9 -> 35-59 (Uncommon dictionary words)
        Zipf 0.0 -> 10-30 (Invented or unknown)
        """
        if zipf_score <= 0:
            return 15.0
        # Linear/sigmoid mapping
        score = (zipf_score / 6.0) * 100.0
        return max(10.0, min(100.0, score))

    def compute_linguistic_complexity(self, word: str, syllables: int) -> float:
        """
        Linguistic complexity score (0 to 100, where lower is simpler / better for branding).
        Evaluates length, consonant clusters, and syllable weight.
        """
        w = word.lower()
        length = len(w)

        # Base complexity from length and syllables
        complexity = (length * 3.5) + (syllables * 8.0)

        # Consonant cluster penalties
        _, v_count, c_count = self.fe.calculate_vowel_consonant_ratio(w)
        if c_count > v_count * 1.5:
            complexity += 15.0

        return max(5.0, min(100.0, complexity))

    def compute_one_word_score(self, word: str) -> Dict[str, Any]:
        """
        Evaluates a candidate specifically under the One-Word Domain criteria.
        Returns comprehensive feature metadata.
        """
        w = word.lower().replace(".com", "").strip()
        features = self.fe.extract_features(w)

        is_dict, zipf = self.is_dictionary_word(w)
        familiarity = self.compute_lexical_familiarity(zipf)
        complexity = self.compute_linguistic_complexity(w, features["syllable_count"])

        # Determine if it qualifies as an authentic one-word domain
        is_one_word = is_dict and features["passes_hard_filter"] and len(w) <= 14
        is_real_one_word = is_one_word
        # Invented one-word: single token, pronounceable, but NOT in English dictionary
        is_invented_one_word = (not is_dict) and features["passes_hard_filter"] and len(w) <= 12 and w.isalpha()

        # Overall one-word strength (0 to 100)
        # Shorter, highly familiar, pronounceable single words command highest value
        if is_one_word:
            length_bonus = max(0.0, (10.0 - len(w)) * 3.0) # short word premium
            syllable_factor = 20.0 if features["syllable_count"] <= 2 else 10.0
            one_word_score = (familiarity * 0.45) + (float(features["pronounceability_score"]) * 0.35) + length_bonus + syllable_factor
        else:
            # If not a recognized single dictionary word
            one_word_score = 0.0

        one_word_score = round(max(0.0, min(100.0, one_word_score)), 3)

        return {
            "is_one_word": is_one_word,
            "is_real_one_word": is_real_one_word,
            "is_invented_one_word": is_invented_one_word,
            "is_dictionary_word": is_dict,
            "word_frequency": round(zipf, 3),
            "raw_word_frequency": word_frequency(w, "en") if WORDFREQ_AVAILABLE else 0.0,
            "syllable_count": features["syllable_count"],
            "pronunciation_score": float(features["pronounceability_score"]),
            "lexical_familiarity": round(familiarity, 3),
            "word_length": len(w),
            "linguistic_complexity": round(complexity, 3),
            "one_word_score": one_word_score
        }
