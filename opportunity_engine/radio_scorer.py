"""
Phase 2.5: Radio / Spelling-From-Sound Scorer
Measures the 'Radio Test':
"If an American hears this name once, how likely are they to type and spell it correctly on the first attempt?"
Calculates deterministic phonetic clarity, orthographic transparency, and ambiguous sound penalties.
"""

import re
from typing import Dict, Any, List

# Phonetic ambiguity patterns that fail the radio test
AMBIGUOUS_PATTERNS = [
    # (Regex pattern, penalty, reason)
    (r'ph', 8, "Ambiguity between 'ph' and 'f'"),
    (r'[aeiou]c[eiy]', 5, "Ambiguity between soft 'c' and 's'"),
    (r'q(?!u)', 14, "Odd 'q' without following 'u'"),
    (r'[bcdfghjklmnpqrstvwxyz]{3,}', 10, "Complex 3+ consonant cluster"),
    (r'(kn|gn|wr|ps|mb\b)', 12, "Silent letter sequence"),
    (r'(ei|ie)', 6, "Ambiguous 'ie' vs 'ei' vowel spelling"),
    (r'([bcdfghjklmnpqrstvwz])\1', 4, "Double consonant spelling ambiguity"),
    (r'[a-z]y[a-z]', 4, "Internal 'y' vowel ambiguity with 'i'"),
    (r'(ight|ough)', 8, "Archaic English irregular spelling"),
    (r'[xz]{2,}', 12, "Unusual repetitive sibilants")
]

class RadioTestScorer:
    """
    Evaluates how intuitively a domain name can be spelled directly from its spoken sound.
    """

    @staticmethod
    def calculate_radio_score(domain_or_label: str) -> Dict[str, Any]:
        label = domain_or_label.lower().strip()
        if label.endswith(".com"):
            label = label[:-4]

        length = len(label)
        base_score = 92
        penalties = 0
        detected_ambiguities: List[str] = []

        # 1. Check orthographic ambiguity rules
        for pattern, penalty, reason in AMBIGUOUS_PATTERNS:
            if re.search(pattern, label):
                penalties += penalty
                detected_ambiguities.append(reason)

        # 2. Length penalties (very long words cause spelling drift)
        if length > 12:
            length_penalty = (length - 12) * 4
            penalties += length_penalty
            detected_ambiguities.append(f"Excessive character length ({length} chars)")
        elif length <= 2:
            penalties += 10
            detected_ambiguities.append("Too short for distinctive spoken clarity")

        # 3. Vowel-Consonant alternation bonus (smooth CVCV / CVC structure)
        is_smooth_alternating = bool(re.match(r'^([bcdfghjklmnpqrstvwxyz][aeiou]){2,}[bcdfghjklmnpqrstvwxyz]?$', label))
        if is_smooth_alternating and length >= 4:
            base_score += 5  # Bonus for natural phonetic cadence like 'nova', 'tempo', 'matrix'

        final_score = max(20, min(98, base_score - penalties))

        return {
            "radio_test_score": final_score,
            "label": label,
            "spelling_ambiguities": detected_ambiguities,
            "phonetic_transparency": "HIGH" if final_score >= 82 else ("MEDIUM" if final_score >= 65 else "LOW")
        }
