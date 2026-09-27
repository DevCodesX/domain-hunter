"""
QualityFeatureExtractor: Reusable deterministic structural and linguistic feature extractor for domains.
Performs hard rejection for clearly invalid/gibberish candidates, and soft scoring for linguistic nuances.
"""

import re
import math
from typing import Dict, Any, Tuple, Optional, List

# Common English vowels (including y when functioning as vowel)
VOWELS = set("aeiouy")
CONSONANTS = set("bcdfghjklmnpqrstvwxz")

# Problematic character sequences that indicate low quality, keyboard mash, or severe unpronounceability
UNUSUAL_TRIGRAMS = {
    "xqz", "qzq", "zqx", "qzx", "vxz", "zxv", "jkx", "qkj", "qwq", "zzz", "yyy", 
    "qqq", "jjj", "vvv", "xxx", "kkk", "bcdf", "fghj", "ghjk", "jklm", "klmn",
    "mnpq", "pqrt", "rstv", "stvw", "tvwx", "vwxz", "bdfh", "cjkm"
}

# Common consonant clusters that are naturally pronounceable in English (onsets and codas)
LEGAL_CLUSTERS = {
    "th", "ch", "sh", "ph", "wh", "st", "sp", "sc", "sk", "sl", "sm", "sn", "sw",
    "pr", "br", "tr", "dr", "kr", "gr", "fr", "vr", "pl", "bl", "cl", "gl", "fl",
    "nd", "nt", "nk", "mp", "lt", "ld", "lk", "lp", "lf", "ft", "ct", "pt", "rk",
    "rt", "rd", "rm", "rn", "rp", "rf", "rs", "tch", "str", "spr", "spl", "scr"
}

class QualityFeatureExtractor:
    def __init__(self):
        # Compiled patterns for fast checks
        self.repeated_char_pattern = re.compile(r"([a-z0-9])\1{2,}") # 3 or more repeated identical chars
        self.digit_mix_pattern = re.compile(r"([a-z]+[0-9]+[a-z]+|[0-9]+[a-z]+[0-9]+)")
        self.consonant_cluster_pattern = re.compile(r"[bcdfghjklmnpqrstvwxz]{4,}")

    def count_syllables(self, word: str) -> int:
        """
        Estimate syllable count using enhanced linguistic heuristic for English.
        """
        w = word.lower().strip()
        if len(w) <= 3:
            return 1

        # Remove trailing silent 'e' unless preceded by 'l' (like 'table')
        if w.endswith("e") and not w.endswith("le") and len(w) > 3:
            w = w[:-1]

        # Match vowel sequences
        vowel_groups = re.findall(r"[aeiouy]+", w)
        count = len(vowel_groups)

        # Common exceptions
        if w.endswith("ed") and not w.endswith("ded") and not w.endswith("ted"):
            count = max(1, count - 1)
        if w.endswith("es") and not (w.endswith("ches") or w.endswith("shes") or w.endswith("ses")):
            count = max(1, count - 1)

        return max(1, count)

    def calculate_vowel_consonant_ratio(self, word: str) -> Tuple[float, int, int]:
        """
        Calculate vowel to consonant ratio and counts.
        Ideal English ratio is approximately 0.60 to 0.90 (around 40% vowels).
        """
        v_count = sum(1 for c in word if c in VOWELS)
        c_count = sum(1 for c in word if c in CONSONANTS)
        ratio = (v_count / c_count) if c_count > 0 else float(v_count)
        return ratio, v_count, c_count

    def detect_unusual_sequences(self, word: str) -> List[str]:
        """Detect unpronounceable consonant runs, invalid trigrams, or repeating sequences."""
        detected = []
        w = word.lower()

        # Check for 3+ repeated identical letters (e.g. "aaaaa", "xxx")
        rep = self.repeated_char_pattern.findall(w)
        if rep:
            detected.append(f"repeated_char_{rep[0]}")

        # Check for q not followed by u
        for i, char in enumerate(w):
            if char == "q" and (i == len(w) - 1 or w[i + 1] != "u"):
                detected.append("q_without_u")
                break

        # Check unusual trigrams
        for trigram in UNUSUAL_TRIGRAMS:
            if trigram in w:
                detected.append(f"unusual_cluster_{trigram}")

        # Check for 4+ consecutive consonants without known legal cluster
        long_clusters = self.consonant_cluster_pattern.findall(w)
        for cluster in long_clusters:
            # Check if it contains legal compound junctions (like "matchbox" tch+b)
            if not any(legal in cluster for legal in LEGAL_CLUSTERS):
                detected.append(f"awkward_consonants_{cluster}")

        return detected

    def compute_pronounceability_score(self, word: str) -> float:
        """
        Compute pronounceability score (0 to 100).
        Evaluates alternating consonant-vowel transitions, syllable structure, and cluster naturalness.
        """
        w = word.lower()
        if not w.isalpha():
            return 30.0

        length = len(w)
        if length == 0:
            return 0.0

        score = 100.0
        ratio, v_count, c_count = self.calculate_vowel_consonant_ratio(w)

        # No vowels at all is disastrous (e.g., "xqzlyv", "bcdfgh")
        if v_count == 0:
            return 10.0

        # Ideal vowel percentage is 35% - 55%
        vowel_pct = v_count / length
        if vowel_pct < 0.25:
            score -= (0.25 - vowel_pct) * 120
        elif vowel_pct > 0.65:
            score -= (vowel_pct - 0.65) * 80

        # Penalize awkward sequences
        unusual = self.detect_unusual_sequences(w)
        score -= len(unusual) * 25

        # Reward natural alternating patterns (CVCV, CVCCV, VCV)
        transitions = 0
        for i in range(len(w) - 1):
            is_v1 = w[i] in VOWELS
            is_v2 = w[i+1] in VOWELS
            if is_v1 != is_v2:
                transitions += 1

        transition_ratio = transitions / (length - 1) if length > 1 else 1.0
        if transition_ratio >= 0.5:
            score += 5.0
        else:
            score -= (0.5 - transition_ratio) * 30.0

        return max(5.0, min(100.0, score))

    def compute_spelling_simplicity(self, word: str) -> float:
        """
        Calculate spelling simplicity score (0 to 100).
        Penalizes silent letters, easily confused letters (c/k/s, ph/f), double consonants.
        """
        w = word.lower()
        score = 95.0

        # Penalize confusing digraphs that lead to typos
        confusing = ["ph", "ght", "ough", "eau", "sc", "xc", "ae", "oe"]
        for c in confusing:
            if c in w:
                score -= 10.0

        # Length penalty for visual clutter
        if len(w) > 12:
            score -= (len(w) - 12) * 3.0

        # Hyphens or digits reduce simplicity
        if "-" in w:
            score -= 15.0
        if any(c.isdigit() for c in w):
            score -= 20.0

        return max(10.0, min(100.0, score))

    def evaluate_hard_filters(self, domain_label: str) -> Tuple[bool, Optional[str]]:
        """
        Strict HARD FILTERS: Rejects only objectively invalid, spammy, or gibberish candidates.
        Returns (passes_hard_filter, rejection_reason).
        """
        label = domain_label.lower().strip()

        # 1. Length boundaries
        if len(label) < 2:
            return False, "too_short_less_than_2_chars"
        if len(label) > 28:
            return False, "too_long_exceeds_28_chars"

        # 2. Obvious repeated identical characters (e.g. "aaaaaaaa", "xxxxxx")
        if re.search(r"([a-z])\1{3,}", label):
            return False, "excessive_repeated_characters"

        # 3. Only alphanumeric and hyphens
        if not re.match(r"^[a-z0-9-]+$", label):
            return False, "invalid_characters"

        # 4. Leading, trailing or double hyphens
        if label.startswith("-") or label.endswith("-") or "--" in label:
            return False, "invalid_hyphen_placement"

        # 5. Keyboard mash / zero vowels in words longer than 3 chars
        ratio, v_count, c_count = self.calculate_vowel_consonant_ratio(label)
        if len(label) >= 4 and v_count == 0:
            return False, "no_vowels_keyboard_mash"

        # 6. Random mixed digit injection (e.g., "fast123brand", "x89yza")
        if any(c.isdigit() for c in label):
            # Allow clean pure numbers or year (like 24, 365, 2026), but reject random embedded numbers
            digits = re.findall(r"\d+", label)
            letters = re.findall(r"[a-z]+", label)
            if len(digits) > 1 or (len(digits) == 1 and len(letters) > 1 and len(digits[0]) not in [2, 4]):
                return False, "random_digit_injection"

        # 7. Unpronounceable trigram hard reject
        unusual = self.detect_unusual_sequences(label)
        if any("unusual_cluster" in u or "awkward_consonants" in u for u in unusual):
            # If 5+ consonants or severely unpronounceable
            if re.search(r"[bcdfghjklmnpqrstvwxz]{5,}", label):
                return False, "severe_unpronounceable_consonants"

        # 8. Severe unpronounceability
        pron = self.compute_pronounceability_score(label)
        if pron < 25.0:
            return False, f"unacceptable_pronunciation_score_{pron:.1f}"

        return True, None

    def extract_features(self, candidate_or_domain: str) -> Dict[str, Any]:
        """
        Extract complete structural and linguistic features for a domain name.
        """
        domain = candidate_or_domain.lower().strip()
        label = domain.replace(".com", "").split(".")[0].strip()

        passes_hard, hard_rejection_reason = self.evaluate_hard_filters(label)
        syllables = self.count_syllables(label)
        ratio, v_count, c_count = self.calculate_vowel_consonant_ratio(label)
        pronounceability = self.compute_pronounceability_score(label)
        spelling_simplicity = self.compute_spelling_simplicity(label)
        unusual_seqs = self.detect_unusual_sequences(label)

        # Visual simplicity & symmetry
        has_hyphen = "-" in label
        has_digits = any(c.isdigit() for c in label)
        visual_simplicity = 100.0 - (len(label) * 2.2) - (15.0 if has_hyphen else 0.0) - (20.0 if has_digits else 0.0)
        visual_simplicity = max(10.0, min(100.0, visual_simplicity))

        # Memorability estimation (deterministic baseline)
        memorability_est = (pronounceability * 0.45) + (visual_simplicity * 0.35) + (15.0 if len(label) <= 8 else 5.0)
        memorability_est = max(15.0, min(98.0, memorability_est))

        return {
            "domain": f"{label}.com",
            "label": label,
            "char_length": len(label),
            "syllable_count": syllables,
            "vowel_count": v_count,
            "consonant_count": c_count,
            "vowel_consonant_ratio": round(ratio, 2),
            "pronounceability_score": round(pronounceability, 1),
            "spelling_simplicity": round(spelling_simplicity, 1),
            "visual_simplicity": round(visual_simplicity, 1),
            "estimated_memorability": round(memorability_est, 1),
            "has_hyphen": has_hyphen,
            "has_digits": has_digits,
            "unusual_sequences": unusual_seqs,
            "passes_hard_filter": passes_hard,
            "hard_rejection_reason": hard_rejection_reason
        }
