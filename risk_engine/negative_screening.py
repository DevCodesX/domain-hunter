"""
Negative Semantic Screening Engine
Provides deterministic, lightweight negative and sensitive semantic screening:
- Offensive, derogatory, or hate terms
- Explicit, adult, or sexual terms
- Violent or illegal associations
- Problematic slang meanings
"""

import re
from typing import List, Dict, Any, Tuple

# Curated list of offensive, profane, violent, or illicit roots
NEGATIVE_TERMS_SUBSTRINGS = {
    # Hate, offensive, derogatory
    "scam", "fraud", "phish", "malware", "virus", "trojan", "ransom", "spyware",
    "hack", "crack", "pirate", "illegal", "stolen", "counterfeit", "fake", "ponzi",
    "nazi", "terror", "jihad", "kill", "murder", "suicide", "bomb", "weapon", "poison",
    # Explicit adult terms
    "porn", "xxx", "sex", "nude", "naked", "erotic", "nsfw", "escort", "gambling", "casino",
    "betting", "poker", "drugs", "cocaine", "heroin", "meth", "weed"
}

class NegativeSemanticScreening:
    def __init__(self):
        # Build regex pattern for fast whole-word and boundary matching
        pattern_str = r"(?:^|[_-])(" + "|".join(re.escape(term) for term in NEGATIVE_TERMS_SUBSTRINGS) + r")(?:$|[_-])"
        self.exact_pattern = re.compile(pattern_str, re.IGNORECASE)

    def screen(self, domain_label: str) -> Tuple[bool, List[str]]:
        """
        Screens domain label for negative, offensive, or sensitive terms.
        Returns:
            (has_negative_association: bool, detected_terms: List[str])
        """
        label = domain_label.lower().replace(".com", "").strip()
        detected = []

        # Check whole word boundary match
        matches = self.exact_pattern.findall(label)
        if matches:
            detected.extend(matches)

        # Check substring inclusion if label is essentially the bad word or prefix
        for term in NEGATIVE_TERMS_SUBSTRINGS:
            # If label equals term or starts/ends with term in obvious compound
            if label == term or label.startswith(term) or label.endswith(term):
                if term not in detected:
                    detected.append(term)

        is_flagged = len(detected) > 0
        return is_flagged, detected
