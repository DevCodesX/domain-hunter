"""
Phonetic and String Similarity Algorithms
Includes:
- Levenshtein edit distance & normalized similarity
- Jaro-Winkler similarity
- Soundex phonetic encoding
- Metaphone phonetic encoding
- Token & affix similarity
"""

import re
from typing import Tuple, Set, Dict, Any

def levenshtein_distance(s1: str, s2: str) -> int:
    """Computes exact Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]

def levenshtein_similarity(s1: str, s2: str) -> float:
    """Normalized Levenshtein similarity (0.0 to 1.0)."""
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    dist = levenshtein_distance(s1.lower(), s2.lower())
    return 1.0 - (dist / max_len)

def jaro_winkler_similarity(s1: str, s2: str, p: float = 0.1) -> float:
    """
    Computes Jaro-Winkler similarity between two strings (0.0 to 1.0).
    Rewards common prefixes, ideal for brand and typo matching.
    """
    s1, s2 = s1.lower(), s2.lower()
    if s1 == s2:
        return 1.0

    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0

    match_distance = (max(len1, len2) // 2) - 1
    s1_matches = [False] * len1
    s2_matches = [False] * len2
    matches = 0
    transpositions = 0

    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)
        for j in range(start, end):
            if s2_matches[j]:
                continue
            if s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    transpositions = transpositions // 2
    jaro = (matches / len1 + matches / len2 + (matches - transpositions) / matches) / 3.0

    # Prefix scale (up to 4 characters)
    prefix = 0
    for i in range(min(4, min(len1, len2))):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break

    return jaro + (prefix * p * (1.0 - jaro))

def soundex(name: str) -> str:
    """
    Computes standard American Soundex phonetic code (Letter + 3 digits).
    Example: 'Smith' -> 'S530', 'Smythe' -> 'S530'
    """
    s = re.sub(r"[^A-Za-z]", "", name.upper())
    if not s:
        return "0000"

    mapping = {
        "B": "1", "F": "1", "P": "1", "V": "1",
        "C": "2", "G": "2", "J": "2", "K": "2", "Q": "2", "S": "2", "X": "2", "Z": "2",
        "D": "3", "T": "3",
        "L": "4",
        "M": "5", "N": "5",
        "R": "6"
    }

    first_char = s[0]
    encoded = [first_char]
    prev_code = mapping.get(first_char, "0")

    for char in s[1:]:
        code = mapping.get(char, "0")
        if code != "0" and code != prev_code:
            encoded.append(code)
            if len(encoded) == 4:
                break
        prev_code = code

    # Pad with zeros
    while len(encoded) < 4:
        encoded.append("0")

    return "".join(encoded)

def metaphone(word: str) -> str:
    """
    Simplified Metaphone algorithm encoding English pronunciation phonetically.
    Captures phonetic equivalents like C/K, PH/F, AU/O.
    """
    w = word.upper().strip()
    if not w:
        return ""

    # Drop non-alphas
    w = re.sub(r"[^A-Z]", "", w)
    if not w:
        return ""

    # Initial transforms
    if w.startswith(("KN", "GN", "PN", "AE", "WR")):
        w = w[1:]
    elif w.startswith("X"):
        w = "S" + w[1:]
    elif w.startswith("WH"):
        w = "W" + w[2:]

    result = []
    i = 0
    length = len(w)

    while i < length and len(result) < 6:
        c = w[i]
        nxt = w[i + 1] if i + 1 < length else ""
        prev = w[i - 1] if i > 0 else ""

        if c in "AEIOU":
            if i == 0:
                result.append(c)
        elif c == "B":
            if not (i == length - 1 and prev == "M"):
                result.append("B")
        elif c == "C":
            if nxt in "EIY":
                result.append("S")
            elif nxt == "H":
                result.append("X")
                i += 1
            else:
                result.append("K")
        elif c == "D":
            if nxt == "G" and (i + 2 < length and w[i + 2] in "EIY"):
                result.append("J")
                i += 1
            else:
                result.append("T")
        elif c == "F":
            result.append("F")
        elif c == "G":
            if nxt in "EIY":
                result.append("J")
            elif nxt != "H":
                result.append("K")
        elif c == "H":
            if nxt in "AEIOU" and prev not in "CGPST":
                result.append("H")
        elif c in "J":
            result.append("J")
        elif c in "K":
            if prev != "C":
                result.append("K")
        elif c == "L":
            result.append("L")
        elif c == "M":
            result.append("M")
        elif c == "N":
            result.append("N")
        elif c == "P":
            if nxt == "H":
                result.append("F")
                i += 1
            else:
                result.append("P")
        elif c == "Q":
            result.append("K")
        elif c == "R":
            result.append("R")
        elif c == "S":
            if nxt == "H":
                result.append("X")
                i += 1
            else:
                result.append("S")
        elif c == "T":
            if nxt == "H":
                result.append("0") # th sound
                i += 1
            elif nxt == "I" and (i + 2 < length and w[i + 2] in "AO"):
                result.append("X")
            else:
                result.append("T")
        elif c == "V":
            result.append("F")
        elif c == "W" or c == "Y":
            if nxt in "AEIOU":
                result.append(c)
        elif c == "X":
            result.append("KS")
        elif c == "Z":
            result.append("S")

        i += 1

    return "".join(result)

def calculate_comprehensive_similarity(term1: str, term2: str) -> Dict[str, Any]:
    """
    Computes multi-dimensional similarity between candidate and trademark/brand.
    Returns:
    {
        "levenshtein": 0.85,
        "jaro_winkler": 0.91,
        "soundex_match": True,
        "metaphone_match": True,
        "composite_similarity": 0.89,
        "is_phonetic_match": True
    }
    """
    t1 = term1.lower().replace(".com", "").strip()
    t2 = term2.lower().replace(".com", "").strip()

    if t1 == t2:
        return {
            "levenshtein": 1.0,
            "jaro_winkler": 1.0,
            "soundex_match": True,
            "metaphone_match": True,
            "composite_similarity": 1.0,
            "is_phonetic_match": True
        }

    lev = levenshtein_similarity(t1, t2)
    jw = jaro_winkler_similarity(t1, t2)
    sndx_match = (soundex(t1) == soundex(t2))
    meta_match = (metaphone(t1) == metaphone(t2)) and len(t1) > 2

    is_phonetic = sndx_match or meta_match

    # Composite similarity weighing string similarity + phonetic match
    composite = (jw * 0.55) + (lev * 0.35) + (0.10 if is_phonetic else 0.0)

    # Typo / transposition detection (e.g. "Claudora" vs "Cloudora")
    if lev >= 0.80 and is_phonetic:
        composite = max(composite, 0.88)

    return {
        "levenshtein": round(lev, 3),
        "jaro_winkler": round(jw, 3),
        "soundex_match": sndx_match,
        "metaphone_match": meta_match,
        "composite_similarity": round(min(1.0, composite), 3),
        "is_phonetic_match": is_phonetic
    }
