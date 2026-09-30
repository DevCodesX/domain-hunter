"""
Phonetic Engine: Pure Python Soundex & Metaphone Phonetic Clustering
Clusters domain candidates by acoustic pronunciation to prevent homophonic
and near-homophonic candidates (e.g., agenlux / agenvos, sdkloom / sdkgrid)
from dominating generation runs.
"""

import re
from typing import Dict, List, Tuple, Any, Set
from difflib import SequenceMatcher


def soundex(word: str) -> str:
    """
    Standard Soundex algorithm (American Soundex).
    Produces 4-character code (Letter + 3 digits).
    """
    clean = re.sub(r'[^a-zA-Z]', '', word).upper()
    if not clean:
        return "Z000"

    first_letter = clean[0]
    mapping = {
        'B': '1', 'F': '1', 'P': '1', 'V': '1',
        'C': '2', 'G': '2', 'J': '2', 'K': '2', 'Q': '2', 'S': '2', 'X': '2', 'Z': '2',
        'D': '3', 'T': '3',
        'L': '4',
        'M': '5', 'N': '5',
        'R': '6'
    }

    digits = []
    prev_code = mapping.get(first_letter, '0')

    for char in clean[1:]:
        code = mapping.get(char, '0')
        if code != '0':
            if code != prev_code:
                digits.append(code)
            prev_code = code
        else:
            prev_code = '0'  # Vowel or H/W resets identical adjacent consonant blocking

    # Pad or truncate to 3 digits
    digits_str = "".join(digits[:3]).ljust(3, '0')
    return f"{first_letter}{digits_str}"


def metaphone(word: str, max_length: int = 6) -> str:
    """
    Metaphone phonetic encoder (Pure Python).
    Reduces English/Latin words to their phonetic consonant skeleton.
    """
    clean = re.sub(r'[^a-zA-Z]', '', word).upper()
    if not clean:
        return ""

    # Initial silent letters
    if clean.startswith(('KN', 'GN', 'PN', 'AE', 'WR')):
        clean = clean[1:]
    elif clean.startswith('X'):
        clean = 'S' + clean[1:]
    elif clean.startswith('WH'):
        clean = 'W' + clean[2:]

    result = []
    i = 0
    length = len(clean)

    # First vowel preserved phonetically
    if clean and clean[0] in 'AEIOU':
        result.append(clean[0])
        i = 1

    while i < length and len(result) < max_length:
        c = clean[i]
        nxt = clean[i + 1] if i + 1 < length else ''
        prv = clean[i - 1] if i > 0 else ''

        # Skip duplicate adjacent letters (except C)
        if c == prv and c != 'C':
            i += 1
            continue

        if c == 'B':
            # Silent B after M at word end
            if not (prv == 'M' and i == length - 1):
                result.append('B')
        elif c == 'C':
            if nxt == 'H':
                result.append('X')  # 'ch' sound
                i += 1
            elif nxt in 'EIY':
                result.append('S')  # soft C
            else:
                result.append('K')  # hard C
        elif c == 'D':
            if nxt == 'G' and i + 2 < length and clean[i + 2] in 'EIY':
                result.append('J')  # 'dg' as in bridge
                i += 1
            else:
                result.append('T')
        elif c in 'EIU':
            pass  # Vowels skipped after first position
        elif c == 'F':
            result.append('F')
        elif c == 'G':
            if nxt == 'H' and (i == length - 2 or (i + 2 < length and clean[i + 2] not in 'AEIOU')):
                pass  # Silent GH
            elif nxt in 'EIY':
                result.append('J')  # Soft G
            else:
                result.append('K')  # Hard G
        elif c == 'H':
            if nxt in 'AEIOU' and (not prv or prv not in 'CGPST'):
                result.append('H')
        elif c == 'J':
            result.append('J')
        elif c == 'K':
            if prv != 'C':
                result.append('K')
        elif c == 'L':
            result.append('L')
        elif c == 'M':
            result.append('M')
        elif c == 'N':
            result.append('N')
        elif c == 'P':
            if nxt == 'H':
                result.append('F')
                i += 1
            else:
                result.append('P')
        elif c == 'Q':
            result.append('K')
        elif c == 'R':
            result.append('R')
        elif c == 'S':
            if nxt == 'H' or (nxt == 'I' and i + 2 < length and clean[i + 2] in 'AO'):
                result.append('X')  # 'sh' sound
                i += 1
            else:
                result.append('S')
        elif c == 'T':
            if nxt == 'H':
                result.append('0')  # 'th' sound
                i += 1
            elif nxt == 'I' and i + 2 < length and clean[i + 2] in 'AO':
                result.append('X')  # 'tion' sound
                i += 1
            elif nxt == 'C' and i + 2 < length and clean[i + 2] == 'H':
                pass  # 'tch'
            else:
                result.append('T')
        elif c == 'V':
            result.append('F')
        elif c == 'W':
            if nxt in 'AEIOU':
                result.append('W')
        elif c == 'X':
            result.append('K')
            result.append('S')
        elif c == 'Y':
            if nxt in 'AEIOU':
                result.append('Y')
        elif c == 'Z':
            result.append('S')

        i += 1

    return "".join(result)[:max_length]


class PhoneticEngine:
    """
    Computes phonetic keys, similarity, and clustering for domain candidate labels.
    """

    @classmethod
    def get_phonetic_key(cls, domain_or_label: str) -> str:
        """
        Computes composite phonetic signature: Metaphone + Soundex.
        Example: 'agenlux' -> 'AJNLKS_A254'
        """
        label = domain_or_label.lower().replace(".com", "").strip()
        meta = metaphone(label, max_length=7)
        snd = soundex(label)
        return f"{meta}_{snd}"

    @classmethod
    def get_phonetic_cluster_id(cls, domain_or_label: str) -> str:
        """
        Returns a high-level cluster key representing acoustic family.
        Groups words sharing leading 3-consonant phonetic signature.
        """
        label = domain_or_label.lower().replace(".com", "").strip()
        meta = metaphone(label, max_length=5)
        snd = soundex(label)
        # First 3 chars of metaphone + primary soundex digit
        lead_meta = meta[:3] if len(meta) >= 3 else meta.ljust(3, '_')
        return f"PHON_{lead_meta}_{snd[:2]}"

    @classmethod
    def calculate_phonetic_similarity(cls, label_a: str, label_b: str) -> float:
        """
        Calculates phonetic similarity (0.0 to 1.0) between two labels.
        Evaluates Metaphone string similarity, Soundex match, and initial consonant harmony.
        """
        a = label_a.lower().replace(".com", "").strip()
        b = label_b.lower().replace(".com", "").strip()
        if a == b:
            return 1.0

        meta_a = metaphone(a)
        meta_b = metaphone(b)
        snd_a = soundex(a)
        snd_b = soundex(b)

        # Syllable and length alignment constraints
        syl_a = max(1, len(re.findall(r"[aeiouy]+", a)))
        syl_b = max(1, len(re.findall(r"[aeiouy]+", b)))
        syl_diff = abs(syl_a - syl_b)
        len_diff = abs(len(a) - len(b))
        seq_ratio = SequenceMatcher(None, a, b).ratio()

        # 1. Exact metaphone match: genuine homophones require syllable and length harmony
        if meta_a and meta_a == meta_b:
            if syl_diff == 0 and len_diff <= 1 and seq_ratio >= 0.70:
                return 0.95
            elif syl_diff <= 1 and len_diff <= 2 and seq_ratio >= 0.60:
                return round(max(0.65, min(0.85, 0.70 + (seq_ratio * 0.20) - (len_diff * 0.05))), 3)
            else:
                # Different syllable count / large length mismatch cannot be an authentic phonetic homophone
                return round(max(0.35, min(0.65, 0.45 + (seq_ratio * 0.25) - (len_diff * 0.06) - (syl_diff * 0.10))), 3)

        # 2. Metaphone sequence similarity
        meta_ratio = SequenceMatcher(None, meta_a, meta_b).ratio() if (meta_a and meta_b) else 0.0

        # 3. Soundex equivalence
        soundex_bonus = 0.20 if snd_a == snd_b else 0.0

        # 4. Common phonetic prefix
        common_len = 0
        for ca, cb in zip(meta_a, meta_b):
            if ca == cb:
                common_len += 1
            else:
                break
        prefix_ratio = (common_len / max(len(meta_a), len(meta_b))) if max(len(meta_a), len(meta_b)) > 0 else 0.0

        score = (meta_ratio * 0.45) + soundex_bonus + (prefix_ratio * 0.20) + (seq_ratio * 0.15) - (syl_diff * 0.08) - (len_diff * 0.04)
        return round(min(1.0, max(0.0, score)), 3)

    @classmethod
    def get_composite_phonetic_key(cls, domain_or_label: str) -> str:
        """Alias for get_phonetic_cluster_id."""
        return cls.get_phonetic_cluster_id(domain_or_label)

    @classmethod
    def compute_phonetic_similarity(cls, label_a: str, label_b: str) -> float:
        """Alias for calculate_phonetic_similarity."""
        return cls.calculate_phonetic_similarity(label_a, label_b)

    @classmethod
    def cluster_candidates(cls, candidates: List[Any], threshold: float = 0.70) -> Dict[str, List[Any]]:
        """
        Clusters a list of candidates into phonetic families.
        Returns a dictionary {cluster_id: [candidates]}.
        """
        def get_name(item):
            if isinstance(item, str):
                return item
            if isinstance(item, dict):
                return item.get("domain_name") or item.get("domain", "")
            return getattr(item, "domain_name", getattr(item, "domain", str(item)))

        clusters: Dict[str, List[Any]] = {}

        for cand in candidates:
            name = get_name(cand)
            cluster_id = cls.get_phonetic_cluster_id(name)
            
            # 1. If exact cluster_id already registered, append immediately
            if cluster_id in clusters:
                clusters[cluster_id].append(cand)
                continue

            # 2. Check if it aligns with an existing cluster via high phonetic similarity
            assigned = False
            for existing_cid, members in clusters.items():
                rep_name = get_name(members[0])
                if cls.calculate_phonetic_similarity(name, rep_name) >= threshold:
                    clusters[existing_cid].append(cand)
                    assigned = True
                    break
            
            if not assigned:
                clusters[cluster_id] = [cand]

        return clusters

    @classmethod
    def get_candidate_cluster_map(cls, candidates: List[Any], threshold: float = 0.70) -> Dict[str, str]:
        """
        Returns a mapping from candidate domain name to its assigned phonetic cluster ID.
        """
        def get_name(item):
            if isinstance(item, str):
                return item
            if isinstance(item, dict):
                return item.get("domain_name") or item.get("domain", "")
            return getattr(item, "domain_name", getattr(item, "domain", str(item)))

        clusters = cls.cluster_candidates(candidates, threshold=threshold)
        cand_to_cluster = {}
        for cid, members in clusters.items():
            for m in members:
                name = get_name(m)
                cand_to_cluster[name] = cid
                cand_to_cluster[name.lower().replace(".com", "").strip()] = cid
        return cand_to_cluster


