"""
Invented Quality Refinement Engine (Phase 1 Revised)
=====================================================
Multi-Signal Anchoring, Independent Proximity Signals, and Brandability Heuristics
for INVENTED-morphology domain candidates.

Distinguishes meaningless gibberish (e.g. tusokn, zuprok, plimvo, pebrowa)
from coined but commercially anchored names (e.g. kinetoc -> kinetic).

Enforces:
1. Three independent proximity signals:
   - lexical_proximity_score (spelling similarity to authentic dictionary words)
   - phonetic_proximity_score (acoustic similarity using Soundex & Metaphone)
   - semantic_anchor_score (anchoring to high-frequency or commercial roots)
2. Brandability heuristic composite (length-gated, naturalness, phonotactic transitions)
3. Subclassification within INVENTED morphology:
   - LEXICAL_ANCHORED, PHONETIC_ANCHORED, SEMANTIC_ANCHORED, HYBRID_ANCHORED, UNANCHORED
4. Soft penalty tiers (STRONG, MODERATE, WEAK, EXTREMELY_WEAK)
5. Runtime loading of weights from quality_engine/config/invented_quality_weights.yaml
"""

import os
import re
import math
try:
    import yaml
except ImportError:
    yaml = None
from typing import Dict, Any, List, Optional, Tuple, Set
from difflib import SequenceMatcher

# Reuse existing string and phonetic similarity tools per Task D
from risk_engine.similarity import (
    levenshtein_distance,
    levenshtein_similarity,
    jaro_winkler_similarity
)
from quality_engine.phonetic_engine import soundex, metaphone, PhoneticEngine
from quality_engine.feature_extractor import QualityFeatureExtractor
from quality_engine.brand_refinement import AIGeneratedFeelDetector
from quality_engine.config import (
    PHONOTACTIC_BAD_BIGRAMS,
    PHONOTACTIC_BAD_TRIGRAMS,
    RECOGNIZED_SEMANTIC_ROOTS
)

try:
    from wordfreq import zipf_frequency, word_frequency, top_n_list
    WORDFREQ_AVAILABLE = True
except ImportError:
    WORDFREQ_AVAILABLE = False
    def zipf_frequency(word: str, lang: str = "en") -> float:
        return 0.0
    def word_frequency(word: str, lang: str = "en") -> float:
        return 0.0
    def top_n_list(lang: str = "en", n: int = 1000) -> List[str]:
        return []

# Config path
MODULE_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(MODULE_DIR, "config", "invented_quality_weights.yaml")

# Fallback defaults if config file is absent or corrupted
DEFAULT_CONFIG: Dict[str, Any] = {
    "invented_quality": {
        "lexical_proximity": 0.25,
        "phonetic_proximity": 0.15,
        "semantic_anchor": 0.20,
        "brandability_heuristic": 0.25,
        "pronunciation": 0.10,
        "distinctiveness": 0.05
    },
    "anchor_thresholds": {
        "lexical_anchored_min": 72.0,
        "phonetic_anchored_min": 78.0,
        "semantic_anchored_min": 68.0,
        "hybrid_anchored_requires_n_strong": 2
    },
    "brandability_subweights": {
        "length": 0.20,
        "vowel_ending_bonus_max": 3,
        "pronunciation_simplicity": 0.18,
        "orthographic_simplicity": 0.10,
        "hear_to_spell": 0.12,
        "syllable_naturalness": 0.10,
        "unnatural_cluster_penalty": 0.12,
        "memorability_pattern": 0.08,
        "distinctiveness": 0.05,
        "morphological_elegance": 0.05
    },
    "penalty_tiers": {
        "strong_multiplier": 1.0,
        "strong_penalty": 0.0,
        "moderate_penalty": 6.0,
        "weak_penalty": 16.0,
        "extremely_weak_penalty": 26.0,
        "extremely_weak_brandability_threshold": 40.0,
        "weak_unanchored_invented_ratio_cap": 0.15
    },
    "availability_pipeline": {
        "preferred_available": 45,
        "max_registry_checks": 600,
        "batch_initial": 300,
        "batch_step": 150,
        "stratified_quotas": {
            "real_word": 0.20,
            "compound": 0.20,
            "semantic": 0.20,
            "invented_anchored": 0.15,
            "prefix_suffix": 0.10,
            "keyword": 0.10,
            "multilingual_other": 0.05
        }
    },
    "tier_a_floors": {
        "min_score": 82.0,
        "min_pronunciation": 65.0,
        "min_hear_to_spell": 60.0,
        "min_commercial_naturalness": 65.0,
        "min_brandability": 70.0
    }
}


def _parse_simple_yaml(content: str) -> Dict[str, Any]:
    """Basic indent-based YAML parser for key-value structures when PyYAML is unavailable."""
    result: Dict[str, Any] = {}
    current_section: Optional[str] = None
    for line in content.splitlines():
        line = line.split("#")[0].rstrip()
        if not line:
            continue
        if not line.startswith(" ") and ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            if not val:
                current_section = key
                result[current_section] = {}
            else:
                try:
                    result[key] = float(val) if "." in val else int(val)
                except ValueError:
                    result[key] = val
        elif line.startswith("  ") and current_section and ":" in line:
            subline = line.strip()
            k, v = subline.split(":", 1)
            k = k.strip()
            v = v.strip()
            try:
                result[current_section][k] = float(v) if "." in v else int(v)
            except ValueError:
                result[current_section][k] = v
    return result


def load_invented_quality_config() -> Dict[str, Any]:
    """Loads configuration from YAML file at runtime, falling back to defaults."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                content = f.read()
            if yaml is not None:
                data = yaml.safe_load(content)
            else:
                data = _parse_simple_yaml(content)
            if isinstance(data, dict):
                cfg = dict(DEFAULT_CONFIG)
                for k, v in data.items():
                    if isinstance(v, dict) and k in cfg:
                        cfg[k] = {**cfg[k], **v}
                    else:
                        cfg[k] = v
                return cfg
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


# Curated commercial anchor roots for semantic anchoring (supplementing wordfreq)
COMMERCIAL_ANCHOR_ROOTS: Set[str] = {
    *RECOGNIZED_SEMANTIC_ROOTS,
    "kinetic", "kinetics", "dynamo", "dynamic", "vector", "tempo", "flux",
    "stride", "scale", "forge", "spark", "pulse", "stream", "stack", "nest",
    "wave", "logic", "craft", "vault", "prism", "nexus", "shift", "orbit",
    "surge", "grid", "node", "core", "crest", "beacon", "haven", "summit",
    "sphere", "matrix", "apex", "vibe", "blend", "scope", "pivot", "drive",
    "trace", "bloom", "fleet", "flair", "sparkle", "radiant", "zenith", "vertex",
    "tensor", "anchor", "canvas", "ledger", "quantum", "cipher", "timber",
    "harbor", "atlas", "mantle", "sentry", "chronicle", "path", "link", "gate",
    "loop", "seed", "byte", "sync", "fuse", "flare", "glyph", "aura", "echo",
    "halo", "rune", "quest", "reach", "swift", "brave", "prime", "solid",
    "vivid", "noble", "bold", "clear", "fresh", "bright", "smart", "trust",
    "merit", "valor", "honor", "grace", "vigor", "verve", "zest", "keen",
    "pace", "flow", "cloud", "data", "bridge", "signal", "point", "atlas"
}

_UNNATURAL_ENDINGS = ("kn", "qn", "vn", "fq", "wz", "okn", "skn", "vrn")
_AWKWARD_CLUSTERS = [
    "skn", "sdr", "mv", "okn", "wz", "fq", "qf", "zx", "xz", "vj", "jv",
    "zpr", "vpr", "nv", "tp", "tk", "bvg", "ptk", "zb", "zg", "qj", "jq",
    "qk", "kq", "qn", "nq", "gln", "lro", "bvo"
]


class AnchorVocabularyIndex:
    """
    Indexed vocabulary cache built from wordfreq top 35,000 English words.
    Provides fast O(1)/O(K) candidates for Levenshtein and Phonetic matching.
    """
    _instance: Optional["AnchorVocabularyIndex"] = None

    def __init__(self, top_n: int = 35000):
        self.words: List[str] = []
        self.bigram_index: Dict[str, List[int]] = {}
        self.metaphone_index: Dict[str, List[str]] = {}
        self.soundex_index: Dict[str, List[str]] = {}
        self._build_index(top_n)

    def _build_index(self, top_n: int):
        raw_words: List[str] = []
        if WORDFREQ_AVAILABLE:
            raw_words = top_n_list("en", top_n)
        if not raw_words:
            raw_words = list(COMMERCIAL_ANCHOR_ROOTS)

        # Include commercial roots explicitly to ensure they are searchable
        all_words_set = set(raw_words).union(COMMERCIAL_ANCHOR_ROOTS)
        self.words = [w.lower().strip() for w in all_words_set if w.isalpha() and 3 <= len(w) <= 12]

        for idx, w in enumerate(self.words):
            # Bigram index for fast lexical candidate filtering
            bgs = set(w[i:i + 2] for i in range(len(w) - 1))
            for bg in bgs:
                self.bigram_index.setdefault(bg, []).append(idx)

            # Phonetic indices
            m = metaphone(w)
            s = soundex(w)
            if m:
                self.metaphone_index.setdefault(m, []).append(w)
            if s:
                self.soundex_index.setdefault(s, []).append(w)

    @classmethod
    def get_instance(cls) -> "AnchorVocabularyIndex":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


class InventedQualityEvaluator:
    """
    Evaluates INVENTED morphology domain candidates using multi-signal anchoring,
    brandability heuristics, subclassification, and soft penalty tiers.
    """
    _instance: Optional["InventedQualityEvaluator"] = None

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or load_invented_quality_config()
        self.vocab_index = AnchorVocabularyIndex.get_instance()
        self.feature_extractor = QualityFeatureExtractor()

    @classmethod
    def get_instance(cls) -> "InventedQualityEvaluator":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def reload_config(self):
        """Reload configuration from disk."""
        self.config = load_invented_quality_config()

    # =========================================================================
    # TASK A: Three Independent Proximity Signals
    # =========================================================================

    def compute_lexical_proximity(self, label: str) -> Tuple[float, List[Dict[str, Any]]]:
        """
        TASK A.1: Lexical proximity (orthographic spelling similarity to real words).
        Finds top 3-5 nearest real words from wordfreq dictionary.
        Weighted toward closest 1-2 matches, informed by anchor count support.
        A genuine anchor must have high normalized Levenshtein similarity (>= 0.70)
        and combined similarity >= 0.75, not an accidental loose substring match.
        """
        clean = label.lower().strip()
        clean_len = len(clean)
        if clean_len < 2:
            return 15.0, []

        clean_bgs = set(clean[i:i + 2] for i in range(clean_len - 1))

        # Query candidates sharing bigrams with length diff <= 2
        cand_indices: Dict[int, int] = {}
        for bg in clean_bgs:
            for idx in self.vocab_index.bigram_index.get(bg, []):
                cand_indices[idx] = cand_indices.get(idx, 0) + 1

        scored_matches: List[Tuple[str, int, float, float]] = []
        for idx, count in cand_indices.items():
            if count >= 2:
                word = self.vocab_index.words[idx]
                if abs(len(word) - clean_len) <= 2:
                    dist = levenshtein_distance(clean, word)
                    # For a genuine anchor: distance must be <= 2
                    # and for short words (<=6 chars), distance must be <= 1 or high length ratio
                    if dist <= 2:
                        lev_sim = levenshtein_similarity(clean, word)
                        if lev_sim >= 0.70:
                            jw_sim = jaro_winkler_similarity(clean, word)
                            combined_sim = (lev_sim * 0.65) + (jw_sim * 0.35)
                            if combined_sim >= 0.75:
                                scored_matches.append((word, dist, combined_sim, lev_sim))

        # Sort by edit distance ascending, then combined similarity descending
        scored_matches.sort(key=lambda x: (x[1], -x[2]))

        top_matches = scored_matches[:5]
        lexical_anchors: List[Dict[str, Any]] = []
        for w, dist, sim, lev_s in top_matches:
            z = zipf_frequency(w, "en") if WORDFREQ_AVAILABLE else 0.0
            lexical_anchors.append({
                "word": w,
                "distance": dist,
                "similarity": round(sim * 100.0, 1),
                "levenshtein_similarity": round(lev_s * 100.0, 1),
                "anchor_frequency": round(z, 2)
            })

        if not top_matches:
            return 15.0, []

        # Weighted aggregate toward closest 1-2 matches
        sims = [m[2] * 100.0 for m in top_matches]
        weights = [0.60, 0.25, 0.15][:len(sims)]
        w_sum = sum(weights)
        raw_score = sum(s * w for s, w in zip(sims, weights)) / w_sum

        # Anchor count support factor: down-weights isolated single coincidental match (Task A.1 & Test 3)
        plausible_count = sum(1 for m in top_matches if m[1] <= 2 and m[2] >= 0.75)
        if plausible_count == 1:
            support_factor = 0.75  # isolated match discount
        elif plausible_count == 2:
            support_factor = 0.88
        else:
            support_factor = 1.0

        lexical_proximity_score = round(max(10.0, min(98.0, raw_score * support_factor)), 2)
        return lexical_proximity_score, lexical_anchors

    def compute_phonetic_proximity(self, label: str) -> Tuple[float, List[Dict[str, Any]]]:
        """
        TASK A.2: Phonetic proximity (sound similarity to real words).
        Reuses Soundex/Metaphone infrastructure per Task D.
        Independent of lexical proximity.
        Compares phonetic codes (initial sound harmony, Soundex, Metaphone).
        """
        clean = label.lower().strip()
        clean_len = len(clean)
        if clean_len < 2:
            return 15.0, []

        cand_snd = soundex(clean)
        cand_meta = metaphone(clean)
        cand_syl = self.feature_extractor.count_syllables(clean)

        # Retrieve words sharing Soundex or Metaphone
        phon_cand_words: Set[str] = set()
        if cand_snd in self.vocab_index.soundex_index:
            phon_cand_words.update(self.vocab_index.soundex_index[cand_snd])
        if cand_meta in self.vocab_index.metaphone_index:
            phon_cand_words.update(self.vocab_index.metaphone_index[cand_meta])

        scored_phonetics: List[Tuple[str, float]] = []
        for w in phon_cand_words:
            # Phonetic code compatibility:
            # 1. Initial consonant harmony (sound starts the same)
            init_match = (clean[0] == w[0]) or (clean[0] in "ck" and w[0] in "ck") or (clean[0] in "fp" and w[0] in "fp")
            if not init_match:
                continue

            # 2. Syllable count harmony (syllables within 1, length within 2)
            w_syl = self.feature_extractor.count_syllables(w)
            if abs(w_syl - cand_syl) > 1 or abs(len(w) - clean_len) > 2:
                continue
            # If syllable counts differ, length difference must be <= 1 to be a genuine phonetic cousin
            if abs(w_syl - cand_syl) >= 1 and abs(len(w) - clean_len) >= 2:
                continue

            # 3. Homophone distance constraint: phonetic cousins must have edit distance <= 2
            if levenshtein_distance(clean, w) > 2:
                continue

            # 4. Phonetic similarity calculation reusing PhoneticEngine
            p_sim = PhoneticEngine.calculate_phonetic_similarity(clean, w)
            if p_sim >= 0.80:
                scored_phonetics.append((w, p_sim))

        scored_phonetics.sort(key=lambda x: -x[1])
        top_phonetics = scored_phonetics[:5]

        phonetic_anchors: List[Dict[str, Any]] = []
        for w, p_sim in top_phonetics:
            z = zipf_frequency(w, "en") if WORDFREQ_AVAILABLE else 0.0
            phonetic_anchors.append({
                "word": w,
                "phonetic_similarity": round(p_sim * 100.0, 1),
                "metaphone": metaphone(w),
                "soundex": soundex(w),
                "anchor_frequency": round(z, 2)
            })

        if not top_phonetics:
            return 15.0, []

        p_scores = [p[1] * 100.0 for p in top_phonetics]
        weights = [0.60, 0.25, 0.15][:len(p_scores)]
        w_sum = sum(weights)
        raw_score = sum(s * w for s, w in zip(p_scores, weights)) / w_sum

        plausible_count = sum(1 for p in top_phonetics if p[1] >= 0.80)
        if plausible_count == 1:
            support_factor = 0.75
        elif plausible_count == 2:
            support_factor = 0.88
        else:
            support_factor = 1.0

        phonetic_proximity_score = round(max(10.0, min(98.0, raw_score * support_factor)), 2)
        return phonetic_proximity_score, phonetic_anchors

    def compute_semantic_anchors(
        self,
        label: str,
        lexical_anchors: List[Dict[str, Any]],
        phonetic_anchors: List[Dict[str, Any]]
    ) -> Tuple[float, List[Dict[str, Any]], float]:
        """
        TASK A.3: Semantic anchor score.
        Checks if closest anchor carries commercial/semantic meaning or is accidental match.
        Uses wordfreq frequency and commercial root status.
        CRITICAL RULE: A phonetic match can ONLY serve as a semantic anchor if there is
        genuine morphological root sharing (shared prefix >= 3 chars or high lexical similarity >= 0.75).
        Accidental consonant skeleton collisions (e.g. 'horede' -> 'hard') are disqualified.
        """
        seen_words: Set[str] = set()
        eligible_candidates: List[Dict[str, Any]] = []

        for la in lexical_anchors:
            w = la["word"]
            if w not in seen_words and (la["distance"] <= 2 and la["similarity"] >= 75.0):
                seen_words.add(w)
                eligible_candidates.append({
                    "word": w,
                    "closeness": la["similarity"] / 100.0,
                    "distance": la["distance"],
                    "source": "LEXICAL"
                })

        for pa in phonetic_anchors:
            w = pa["word"]
            if w not in seen_words and pa["phonetic_similarity"] >= 80.0:
                # Genuine morphological root check: require shared prefix >= 3 chars or strong lexical similarity
                common_pfx = 0
                for ca, cb in zip(label, w):
                    if ca == cb:
                        common_pfx += 1
                    else:
                        break
                if common_pfx >= 3 or levenshtein_similarity(label, w) >= 0.75:
                    seen_words.add(w)
                    eligible_candidates.append({
                        "word": w,
                        "closeness": pa["phonetic_similarity"] / 100.0,
                        "distance": 1 if pa["phonetic_similarity"] >= 90.0 else 2,
                        "source": "PHONETIC"
                    })

        if not eligible_candidates:
            return 15.0, [], 0.0

        meaningful_anchors: List[Dict[str, Any]] = []
        best_meaningfulness = 0.0
        best_anchor_freq = 0.0

        for cand in eligible_candidates:
            w = cand["word"]
            z = zipf_frequency(w, "en") if WORDFREQ_AVAILABLE else 0.0
            is_comm = w in COMMERCIAL_ANCHOR_ROOTS

            # Meaningfulness evaluation based on frequency and commercial recognition
            if z >= 4.5:
                base_meaning = 90.0
            elif z >= 3.8:
                base_meaning = 80.0
            elif z >= 3.0:
                base_meaning = 68.0
            elif z >= 2.0:
                base_meaning = 35.0
            else:
                base_meaning = 15.0

            if is_comm:
                base_meaning = min(98.0, base_meaning + 18.0)

            # If obscure and not a commercial root, strictly cap meaningfulness (Task A.3 & Test 3)
            if z < 2.5 and not is_comm:
                base_meaning = min(20.0, base_meaning)

            meaning_score = base_meaning * cand["closeness"]
            if meaning_score >= 50.0:
                meaningful_anchors.append({
                    "word": w,
                    "anchor_frequency": round(z, 2),
                    "is_commercial_root": is_comm,
                    "closeness": round(cand["closeness"] * 100.0, 1),
                    "semantic_score": round(meaning_score, 1)
                })

            if meaning_score > best_meaningfulness:
                best_meaningfulness = meaning_score
                best_anchor_freq = z

        meaningful_anchors.sort(key=lambda x: -x["semantic_score"])
        semantic_anchor_score = round(max(10.0, min(98.0, best_meaningfulness)), 2)

        return semantic_anchor_score, meaningful_anchors, round(best_anchor_freq, 2)

    # =========================================================================
    # TASK B: Brandability Heuristic Composite (10 Subscores)
    # =========================================================================

    def compute_hear_to_spell_score(self, label: str) -> float:
        """
        Directional heuristic approximation modeling guessability of spelling when heard aloud.
        Penalizes ambiguous letter combinations and silent letters.
        """
        clean = label.lower().strip()
        hear_to_spell = 100.0
        if re.search(r"c[eiy]", clean):  # soft C sounds like S
            hear_to_spell -= 12.0
        if "k" in clean and "ck" not in clean:  # K sound could be C
            hear_to_spell -= 8.0
        if "ck" in clean:
            hear_to_spell -= 6.0
        if "ph" in clean:  # sounds like F
            hear_to_spell -= 14.0
        if "gh" in clean:  # silent or F
            hear_to_spell -= 15.0
        if "x" in clean:  # sounds like KS or Z
            hear_to_spell -= 10.0
        if "z" in clean:  # sounds like S
            hear_to_spell -= 8.0
        for diphthong in ("ea", "ie", "ei", "ey", "oo", "ou", "ai", "ay"):
            if diphthong in clean:
                hear_to_spell -= 7.0
        if clean.startswith(("kn", "gn", "pn", "wr", "ps")):  # silent initial
            hear_to_spell -= 20.0
        if re.search(r"([bdfglmnprstz])\1", clean):  # double consonants ambiguity
            hear_to_spell -= 8.0
        return round(max(20.0, min(100.0, hear_to_spell)), 2)

    def compute_brandability_subscores(
        self,
        label: str,
        existing_cluster_keys: Optional[Set[str]] = None
    ) -> Tuple[float, Dict[str, float]]:
        """
        TASK B: Computes all 10 independent brandability subscores and composite.
        Enforces:
        - length_score is graduated and gated (cannot rescue fundamentally weak names)
        - vowel_ending_bonus is capped small (0-3 pts)
        - unnatural_cluster_penalty specifically flags awkward transitions (tusokn, sdrata, plimvo)
        - all subweights loaded from config
        """
        clean = label.lower().strip()
        length = len(clean)
        subweights = self.config.get("brandability_subweights", DEFAULT_CONFIG["brandability_subweights"])

        # 1. length_score (Graduated per Task B.1)
        # 4 chars: good but flagged as "needs proof"
        # 5-7 chars: highest preference tier
        # 8-9 chars: good
        # 10-11 chars: needs strong justification
        # 12+ chars: penalty
        if length == 4:
            raw_length_score = 78.0
        elif 5 <= length <= 7:
            raw_length_score = 98.0 if length == 6 else 95.0
        elif 8 <= length <= 9:
            raw_length_score = 82.0 if length == 8 else 76.0
        elif 10 <= length <= 11:
            raw_length_score = 55.0 if length == 10 else 48.0
        else:
            raw_length_score = max(15.0, 40.0 - (length - 12) * 6.0)

        # 2. vowel_ending_bonus (Capped small per Task B.2)
        # Vowel ending bonus is intentionally small (0-3 pts): ending consonants (-k, -t, -x, -d)
        # can still be punchy and elegant; phonetic elegance matters more than last-character-is-a-vowel.
        vowel_max = float(subweights.get("vowel_ending_bonus_max", 3.0))
        ends_with_vowel = clean[-1] in "aeiouy" if clean else False
        vowel_ending_bonus = min(vowel_max, 3.0) if ends_with_vowel else 0.0

        # 3. pronunciation_simplicity_score (Reuses QualityFeatureExtractor per Task B.3 & D)
        pronounceability = float(self.feature_extractor.compute_pronounceability_score(clean))

        # 4. orthographic_simplicity_score (Reuses QualityFeatureExtractor per Task B.4)
        orthographic_simplicity = float(self.feature_extractor.compute_spelling_simplicity(clean))

        # 5. hear_to_spell_score (Directional heuristic approximation per Task B.5)
        # Models guessability of spelling when heard aloud (penalizes ambiguous spellings)
        hear_to_spell_score = self.compute_hear_to_spell_score(clean)

        # 6. syllable_naturalness_score (Reuses count_syllables per Task B.6)
        syllables = self.feature_extractor.count_syllables(clean)
        if syllables == 2:
            syllable_naturalness = 100.0  # optimal brandable sweet spot
        elif syllables == 3:
            syllable_naturalness = 90.0
        elif syllables == 1:
            syllable_naturalness = 76.0
        elif syllables == 4:
            syllable_naturalness = 60.0
        else:
            syllable_naturalness = max(20.0, 45.0 - (syllables - 4) * 15.0)

        # 7. unnatural_cluster_penalty (Independent feature per Task B.7)
        # Specifically detects and penalizes awkward consonant clusters (tusokn, sdrata, plimvo)
        cluster_penalty = 0.0
        flagged_clusters: List[str] = []

        # Check bad bigrams
        for i in range(len(clean) - 1):
            bg = clean[i:i + 2]
            bg_score = PHONOTACTIC_BAD_BIGRAMS.get(bg, 1.0)
            if bg_score < 0.4:
                cluster_penalty += (0.4 - bg_score) * 45.0
                flagged_clusters.append(bg)

        # Check bad trigrams
        for i in range(len(clean) - 2):
            tg = clean[i:i + 3]
            tg_score = PHONOTACTIC_BAD_TRIGRAMS.get(tg, 1.0)
            if tg_score < 0.4:
                cluster_penalty += (0.4 - tg_score) * 55.0
                flagged_clusters.append(tg)

        # Check explicit unnatural endings (e.g. kn in tusokn, vrn in bivorn)
        for ending in _UNNATURAL_ENDINGS:
            if clean.endswith(ending):
                cluster_penalty += 32.0
                flagged_clusters.append(f"ending:{ending}")
                break

        # Check explicit awkward clusters (e.g. sdr in sdrata, mv in plimvo)
        for awkward in _AWKWARD_CLUSTERS:
            if awkward in clean:
                cluster_penalty += 24.0
                flagged_clusters.append(awkward)

        # Excessive consecutive consonants
        if re.search(r"[bcdfghjklmnpqrstvwxz]{4,}", clean):
            cluster_penalty += 30.0
            flagged_clusters.append("consonant_quad")

        # Zero vowels
        v_count = sum(1 for c in clean if c in "aeiouy")
        if v_count == 0 and length >= 4:
            cluster_penalty += 60.0
            flagged_clusters.append("zero_vowels")

        unnatural_cluster_penalty = round(min(80.0, cluster_penalty), 2)
        cluster_naturalness_score = round(max(10.0, 100.0 - unnatural_cluster_penalty), 2)

        # 8. memorability_pattern_score (Heuristic proxy per Task B.8)
        memorability_pattern = 68.0
        is_alternating = True
        for i in range(len(clean) - 1):
            v1 = clean[i] in "aeiouy"
            v2 = clean[i + 1] in "aeiouy"
            if v1 == v2:
                is_alternating = False
                break
        if is_alternating and length >= 5:
            memorability_pattern += 18.0

        if length >= 4 and clean[:2] == clean[2:4]:
            memorability_pattern += 12.0

        memorability_pattern_score = round(max(25.0, min(98.0, memorability_pattern)), 2)

        # 9. distinctiveness_score (Reuses Phonetic Clustering per Task B.9 & D)
        phon_key = PhoneticEngine.get_composite_phonetic_key(clean)
        distinctiveness = 82.0
        if existing_cluster_keys and phon_key in existing_cluster_keys:
            distinctiveness -= 25.0
        distinctiveness_score = round(max(30.0, min(95.0, distinctiveness)), 2)

        # 10. morphological_elegance_score (Synthesizes structural signals per Task B.10)
        ai_feel = AIGeneratedFeelDetector.evaluate_ai_feel(clean)
        ai_feel_score = float(ai_feel["ai_generated_feel_score"])
        vowel_ratio = v_count / max(1, length)
        ratio_penalty = abs(vowel_ratio - 0.45) * 60.0
        elegance = 100.0 - (ai_feel_score * 0.35) - (unnatural_cluster_penalty * 0.35) - ratio_penalty
        morphological_elegance_score = round(max(15.0, min(95.0, elegance)), 2)

        # =========================================================================
        # CRITICAL CONSTRAINT: length_score gating (Task B.1)
        # length_score must never single-handedly rescue a candidate with poor pronunciation / no anchors.
        # =========================================================================
        core_quality = (
            (pronounceability * 0.35) +
            (orthographic_simplicity * 0.25) +
            (cluster_naturalness_score * 0.40)
        )
        if core_quality < 55.0:
            # Multiplicative gating: length contribution scales down with poor core quality
            effective_length_score = round(raw_length_score * (core_quality / 55.0), 2)
        else:
            effective_length_score = raw_length_score

        # Composite brandability weighted calculation
        norm_weights = {
            "length": float(subweights.get("length", 0.20)),
            "pronunciation_simplicity": float(subweights.get("pronunciation_simplicity", 0.18)),
            "orthographic_simplicity": float(subweights.get("orthographic_simplicity", 0.10)),
            "hear_to_spell": float(subweights.get("hear_to_spell", 0.12)),
            "syllable_naturalness": float(subweights.get("syllable_naturalness", 0.10)),
            "unnatural_cluster_penalty": float(subweights.get("unnatural_cluster_penalty", 0.12)),
            "memorability_pattern": float(subweights.get("memorability_pattern", 0.08)),
            "distinctiveness": float(subweights.get("distinctiveness", 0.05)),
            "morphological_elegance": float(subweights.get("morphological_elegance", 0.05)),
        }
        total_w = sum(norm_weights.values())

        composite_base = (
            (effective_length_score * norm_weights["length"]) +
            (pronounceability * norm_weights["pronunciation_simplicity"]) +
            (orthographic_simplicity * norm_weights["orthographic_simplicity"]) +
            (hear_to_spell_score * norm_weights["hear_to_spell"]) +
            (syllable_naturalness * norm_weights["syllable_naturalness"]) +
            (cluster_naturalness_score * norm_weights["unnatural_cluster_penalty"]) +
            (memorability_pattern_score * norm_weights["memorability_pattern"]) +
            (distinctiveness_score * norm_weights["distinctiveness"]) +
            (morphological_elegance_score * norm_weights["morphological_elegance"])
        ) / total_w

        # If severe unnatural clusters were detected, apply direct cluster deduction
        # so unnatural candidates (e.g. tusokn, sdrata) cannot coast on other dimensions
        if unnatural_cluster_penalty >= 25.0:
            composite_base = max(15.0, composite_base - (unnatural_cluster_penalty * 0.6))

        # Add vowel_ending_bonus (capped small, max 3)
        brandability_heuristic_score = round(max(10.0, min(100.0, composite_base + vowel_ending_bonus)), 2)

        subscores = {
            "length_score": effective_length_score,
            "raw_length_score": raw_length_score,
            "vowel_ending_bonus": vowel_ending_bonus,
            "pronunciation_simplicity_score": pronounceability,
            "orthographic_simplicity_score": orthographic_simplicity,
            "hear_to_spell_score": hear_to_spell_score,
            "syllable_naturalness_score": syllable_naturalness,
            "unnatural_cluster_penalty": unnatural_cluster_penalty,
            "cluster_naturalness_score": cluster_naturalness_score,
            "memorability_pattern_score": memorability_pattern_score,
            "distinctiveness_score": distinctiveness_score,
            "morphological_elegance_score": morphological_elegance_score,
            "flagged_unnatural_clusters": flagged_clusters
        }

        return brandability_heuristic_score, subscores

    # =========================================================================
    # TASK C & F: Subclassification, Composite Scorer & Soft Penalty Tiers
    # =========================================================================

    def evaluate_candidate(
        self,
        domain_or_label: str,
        existing_cluster_keys: Optional[Set[str]] = None
    ) -> Dict[str, Any]:
        """
        Complete Phase 1 evaluation for an INVENTED candidate.
        Returns all independent proximity signals, brandability subscores,
        subtype, tier, composite invented_quality_score, and soft penalty.
        """
        label = domain_or_label.lower().replace(".com", "").strip()

        # Task A: Three independent proximity signals
        lex_score, lex_anchors = self.compute_lexical_proximity(label)
        phon_score, phon_anchors = self.compute_phonetic_proximity(label)
        sem_score, sem_anchors, anchor_freq = self.compute_semantic_anchors(label, lex_anchors, phon_anchors)

        # Task B: Brandability composite
        brand_score, brand_subscores = self.compute_brandability_subscores(label, existing_cluster_keys)

        # Task C: Subclassification
        thresholds = self.config.get("anchor_thresholds", DEFAULT_CONFIG["anchor_thresholds"])
        lex_min = float(thresholds.get("lexical_anchored_min", 72.0))
        phon_min = float(thresholds.get("phonetic_anchored_min", 78.0))
        sem_min = float(thresholds.get("semantic_anchored_min", 68.0))
        hybrid_req = int(thresholds.get("hybrid_anchored_requires_n_strong", 2))

        is_lex_strong = (lex_score >= lex_min and len(lex_anchors) >= 1)
        is_phon_strong = (phon_score >= phon_min and len(phon_anchors) >= 1)
        is_sem_strong = (sem_score >= sem_min and len(sem_anchors) >= 1)

        strong_count = sum([is_lex_strong, is_phon_strong, is_sem_strong])

        if strong_count >= hybrid_req:
            subtype = "HYBRID_ANCHORED"
        elif is_sem_strong:
            subtype = "SEMANTIC_ANCHORED"
        elif is_lex_strong:
            subtype = "LEXICAL_ANCHORED"
        elif is_phon_strong:
            subtype = "PHONETIC_ANCHORED"
        else:
            subtype = "UNANCHORED"

        # Task F: Soft penalty tiers
        pen_cfg = self.config.get("penalty_tiers", DEFAULT_CONFIG["penalty_tiers"])
        ext_weak_thresh = float(pen_cfg.get("extremely_weak_brandability_threshold", 40.0))
        strong_pen = float(pen_cfg.get("strong_penalty", 0.0))
        mod_pen = float(pen_cfg.get("moderate_penalty", 6.0))
        weak_pen = float(pen_cfg.get("weak_penalty", 16.0))
        ext_weak_pen = float(pen_cfg.get("extremely_weak_penalty", 26.0))

        # Check for multiple plausible anchors and robust anchor frequency (Task A.1 & Test 3)
        total_anchors = len(lex_anchors) + len(phon_anchors)
        has_multiple_anchors = total_anchors >= 2
        is_anchor_frequent = anchor_freq >= 3.0

        # Authenticity evidence check for STRONG tier:
        # Requires either an explicit commercial root (e.g. kinetic in kinetoc, vector in vectra)
        # with prefix match >= 3 chars, OR deep stem sharing (>= 4-character prefix match with high similarity),
        # AND clean phonotactics without unnatural consonant clusters.
        has_commercial_anchor = any(
            (a.get("is_commercial_root") and (label.startswith(a["word"][:3]) or a.get("closeness", 0) >= 85.0))
            for a in sem_anchors
        )
        has_deep_stem = any(
            (la.get("similarity", 0) >= 78.0 and len(la.get("word", "")) >= 4 and label.startswith(la["word"][:4]))
            for la in lex_anchors
        )
        has_clean_phonotactics = brand_subscores.get("unnatural_cluster_penalty", 0.0) < 15.0
        has_strong_evidence = (has_commercial_anchor or has_deep_stem) and has_clean_phonotactics

        # STRONG requires robust anchoring (HYBRID or high-semantic/lexical) + multiple anchors + high frequency + high brandability + authentic evidence
        if (
            subtype == "HYBRID_ANCHORED"
            and brand_score >= 68.0
            and has_multiple_anchors
            and is_anchor_frequent
            and sem_score >= 65.0
            and has_strong_evidence
        ):
            tier = "STRONG"
            penalty = strong_pen
        elif (
            subtype in ["LEXICAL_ANCHORED", "SEMANTIC_ANCHORED"]
            and brand_score >= 70.0
            and has_multiple_anchors
            and is_anchor_frequent
            and sem_score >= 70.0
            and has_strong_evidence
        ):
            tier = "STRONG"
            penalty = strong_pen
        elif subtype != "UNANCHORED":
            tier = "MODERATE"
            penalty = mod_pen
        elif subtype == "UNANCHORED" and brand_score >= ext_weak_thresh and brand_subscores.get("unnatural_cluster_penalty", 0.0) < 30.0:
            tier = "WEAK"
            penalty = weak_pen
        else:
            tier = "EXTREMELY_WEAK"
            penalty = ext_weak_pen

        # Task J: Anchor-Adjusted Brandability Calibration (Part J)
        # Prevents short random strings from receiving inflated 85-98 brand scores
        brand_cfg = self.config.get("invented_brandability", DEFAULT_CONFIG.get("invented_brandability", {}))
        if tier == "STRONG":
            anchor_factor = float(brand_cfg.get("anchor_factor_strong", 1.00))
        elif tier == "MODERATE" or subtype in ["LEXICAL_ANCHORED", "SEMANTIC_ANCHORED", "PHONETIC_ANCHORED"]:
            anchor_factor = float(brand_cfg.get("anchor_factor_moderate", 0.88))
        elif tier == "WEAK":
            anchor_factor = float(brand_cfg.get("anchor_factor_weak", 0.72))
        else:
            anchor_factor = float(brand_cfg.get("anchor_factor_unanchored", 0.58))

        raw_brand_score = round(float(brand_score), 2)
        # Unanchored candidates without any recognized root cannot have raw brand score above 74.0
        if subtype == "UNANCHORED":
            raw_brand_score = min(74.0, raw_brand_score)

        anchor_adjusted_brand_score = round(max(5.0, min(99.0, raw_brand_score * anchor_factor)), 2)

        # Enforce Quality Ceilings on brandability
        from quality_engine.config import get_quality_ceilings_config
        ceilings = get_quality_ceilings_config()
        ceil_key = tier if tier in ceilings else (subtype if subtype in ceilings else "UNANCHORED")
        max_brand_ceiling = float(ceilings.get(ceil_key, {}).get("max_brandability", 98.0))
        anchor_adjusted_brand_score = min(anchor_adjusted_brand_score, max_brand_ceiling)

        # Task E: Composite invented_quality_score (using calibrated brandability)
        w_inv = self.config.get("invented_quality", DEFAULT_CONFIG["invented_quality"])
        pron_score = brand_subscores["pronunciation_simplicity_score"]
        dist_score = brand_subscores["distinctiveness_score"]

        inv_composite = (
            (lex_score * float(w_inv.get("lexical_proximity", 0.25))) +
            (phon_score * float(w_inv.get("phonetic_proximity", 0.15))) +
            (sem_score * float(w_inv.get("semantic_anchor", 0.20))) +
            (anchor_adjusted_brand_score * float(w_inv.get("brandability_heuristic", 0.25))) +
            (pron_score * float(w_inv.get("pronunciation", 0.10))) +
            (dist_score * float(w_inv.get("distinctiveness", 0.05)))
        )
        invented_quality_score = round(max(5.0, min(99.0, inv_composite)), 2)
        max_overall_ceiling = float(ceilings.get(ceil_key, {}).get("max_overall_quality", 98.0))
        invented_quality_score = min(invented_quality_score, max_overall_ceiling)

        return {
            "domain": f"{label}.com",
            "label": label,
            "lexical_proximity_score": lex_score,
            "lexical_anchors": lex_anchors,
            "phonetic_proximity_score": phon_score,
            "phonetic_anchors": phon_anchors,
            "semantic_anchor_score": sem_score,
            "semantic_anchors": sem_anchors,
            "anchor_frequency": anchor_freq,
            "raw_brandability_heuristic_score": raw_brand_score,
            "anchor_adjusted_brandability_score": anchor_adjusted_brand_score,
            "brandability_anchor_factor": anchor_factor,
            "brandability_heuristic_score": anchor_adjusted_brand_score,  # Calibrated score for backward compat
            "brandability_subscores": brand_subscores,
            "invented_subtype": subtype,
            "invented_quality_tier": tier,
            "invented_quality_score": invented_quality_score,
            "invented_penalty": penalty
        }



# =========================================================================
# Convenience standalone helper functions
# =========================================================================

def invented_quality_score(domain_or_label: str) -> float:
    """Returns composite invented_quality_score (0-100) for a candidate."""
    evaluator = InventedQualityEvaluator.get_instance()
    res = evaluator.evaluate_candidate(domain_or_label)
    return res["invented_quality_score"]


def invented_subtype(domain_or_label: str) -> str:
    """Returns invented_subtype ('LEXICAL_ANCHORED', 'HYBRID_ANCHORED', 'UNANCHORED', etc.)."""
    evaluator = InventedQualityEvaluator.get_instance()
    res = evaluator.evaluate_candidate(domain_or_label)
    return res["invented_subtype"]


def evaluate_invented_candidate(domain_or_label: str) -> Dict[str, Any]:
    """Returns full evaluation dictionary for an invented candidate."""
    evaluator = InventedQualityEvaluator.get_instance()
    return evaluator.evaluate_candidate(domain_or_label)


def get_weak_unanchored_ratio_cap() -> float:
    """Loads weak_unanchored_invented_ratio_cap from config."""
    cfg = load_invented_quality_config()
    pen_cfg = cfg.get("penalty_tiers", {})
    return float(pen_cfg.get("weak_unanchored_invented_ratio_cap", 0.15))


def get_availability_pipeline_config() -> Dict[str, Any]:
    """Loads availability_pipeline settings from config."""
    cfg = load_invented_quality_config()
    return cfg.get("availability_pipeline", DEFAULT_CONFIG["availability_pipeline"])


def get_tier_a_floors_config() -> Dict[str, Any]:
    """Loads tier_a_floors settings from config."""
    cfg = load_invented_quality_config()
    return cfg.get("tier_a_floors", DEFAULT_CONFIG["tier_a_floors"])


def calculate_invented_semantic_relevance(
    invented_eval: Dict[str, Any],
    concept: str = "",
    market_category: str = "AI & Technology"
) -> float:
    """
    Computes transparent, evidence-based semantic relevance for INVENTED candidates (Part K):
    - UNANCHORED: low semantic relevance (25.0 - 45.0) unless strong concept evidence exists
    - ANCHORED: semantic relevance grows with anchor quality and concept fit (50.0 - 75.0)
    - STRONG / HYBRID: can reach high semantic relevance (72.0 - 92.0)
    Eliminates arbitrary default 78.0 for unanchored strings.
    """
    subtype = invented_eval.get("invented_subtype", "UNANCHORED")
    tier = invented_eval.get("invented_quality_tier", "WEAK")
    sem_score = float(invented_eval.get("semantic_anchor_score", 0.0) or 0.0)
    lex_score = float(invented_eval.get("lexical_proximity_score", 0.0) or 0.0)
    label = (invented_eval.get("label") or invented_eval.get("domain", "")).lower().replace(".com", "").strip()

    # Check for direct concept word overlap
    concept_tokens = [w.lower() for w in re.findall(r'[a-zA-Z]{3,}', concept)]
    has_concept_overlap = any(tok in label or (len(tok) >= 4 and label in tok) for tok in concept_tokens) if concept_tokens else False

    if subtype == "UNANCHORED" or tier == "EXTREMELY_WEAK":
        # Base low range for unanchored: 25.0 - 45.0
        base = 28.0 + (sem_score * 0.10)
        if has_concept_overlap:
            base += 14.0
        return round(min(45.0, max(15.0, base)), 3)
    elif tier == "STRONG" or subtype == "HYBRID_ANCHORED":
        # Strong/Hybrid: 72.0 - 92.0 based on anchor quality
        base = 72.0 + (sem_score * 0.15) + (lex_score * 0.08)
        if has_concept_overlap:
            base += 6.0
        return round(min(94.0, max(65.0, base)), 3)
    elif subtype in ["SEMANTIC_ANCHORED", "LEXICAL_ANCHORED"]:
        # Anchored: 52.0 - 75.0
        base = 52.0 + (sem_score * 0.18) + (lex_score * 0.10)
        if has_concept_overlap:
            base += 5.0
        return round(min(78.0, max(45.0, base)), 3)
    else:  # PHONETIC_ANCHORED or MODERATE
        base = 45.0 + (sem_score * 0.15)
        if has_concept_overlap:
            base += 5.0
        return round(min(68.0, max(35.0, base)), 3)

