"""
Phase 2.5 & Phase 2.75B: Multilingual Semantic Naming Engine
Curates and evaluates multilingual candidates across Latin, Italian, Spanish, Japanese,
and Nordic languages.
Ensures semantic concepts come first:
hand, mind, eye, key, bridge, compass, forge, engine, flow, speed, light, insight,
wisdom, simple, clear, connect, network, core, root, foundation, build, motion, instant.

Every candidate preserves:
source_language, original_word, original_meaning, translation, pronunciation, romanization, semantic_concept.
Strictly filters out words that fail English pronunciation, radio test, or shortness.
"""

import re
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("MultilingualEngine")

# =========================================================================
# 1. CURATED MULTILINGUAL LEXICAL DATABASE (VERIFIED MEANINGS & PHONETICS)
# =========================================================================
MULTILINGUAL_DICTIONARY: Dict[str, Dict[str, Any]] = {
    # --- LATIN POOL ---
    "veritas": {
        "language": "Latin", "tier": 1,
        "original_word": "veritas", "original_meaning": "truth / reality",
        "english_meaning": "truth", "translation": "truth",
        "pronunciation": "VEHR-ih-tas", "romanization": "veritas",
        "part_of_speech": "noun", "semantic_concept": "clear",
        "pronunciation_difficulty": 10, "spelling_difficulty": 10, "confidence": 1.0
    },
    "celer": {
        "language": "Latin", "tier": 1,
        "original_word": "celer", "original_meaning": "swift / fast",
        "english_meaning": "swift", "translation": "swift",
        "pronunciation": "SEH-ler", "romanization": "celer",
        "part_of_speech": "adjective", "semantic_concept": "speed",
        "pronunciation_difficulty": 8, "spelling_difficulty": 8, "confidence": 1.0
    },
    "nexus": {
        "language": "Latin", "tier": 1,
        "original_word": "nexus", "original_meaning": "connection / binding",
        "english_meaning": "connection / link", "translation": "connection",
        "pronunciation": "NEK-sus", "romanization": "nexus",
        "part_of_speech": "noun", "semantic_concept": "connect",
        "pronunciation_difficulty": 8, "spelling_difficulty": 8, "confidence": 1.0
    },
    "solum": {
        "language": "Latin", "tier": 1,
        "original_word": "solum", "original_meaning": "foundation / ground / solid base",
        "english_meaning": "foundation / solid ground", "translation": "foundation",
        "pronunciation": "SO-lum", "romanization": "solum",
        "part_of_speech": "noun", "semantic_concept": "foundation",
        "pronunciation_difficulty": 8, "spelling_difficulty": 8, "confidence": 1.0
    },
    "radix": {
        "language": "Latin", "tier": 1,
        "original_word": "radix", "original_meaning": "root / origin / primary source",
        "english_meaning": "root / fundamental origin", "translation": "root",
        "pronunciation": "RAY-diks", "romanization": "radix",
        "part_of_speech": "noun", "semantic_concept": "root",
        "pronunciation_difficulty": 10, "spelling_difficulty": 10, "confidence": 1.0
    },
    "clarus": {
        "language": "Latin", "tier": 1,
        "original_word": "clarus", "original_meaning": "clear / bright / renowned",
        "english_meaning": "clear / illustrious", "translation": "clear",
        "pronunciation": "KLAH-rus", "romanization": "clarus",
        "part_of_speech": "adjective", "semantic_concept": "clear",
        "pronunciation_difficulty": 8, "spelling_difficulty": 8, "confidence": 1.0
    },
    "motus": {
        "language": "Latin", "tier": 1,
        "original_word": "motus", "original_meaning": "motion / movement / drive",
        "english_meaning": "motion / impulse", "translation": "motion",
        "pronunciation": "MO-tus", "romanization": "motus",
        "part_of_speech": "noun", "semantic_concept": "motion",
        "pronunciation_difficulty": 6, "spelling_difficulty": 6, "confidence": 1.0
    },
    "statim": {
        "language": "Latin", "tier": 1,
        "original_word": "statim", "original_meaning": "immediately / at once",
        "english_meaning": "instant / immediate", "translation": "instant",
        "pronunciation": "STAH-tim", "romanization": "statim",
        "part_of_speech": "adverb", "semantic_concept": "instant",
        "pronunciation_difficulty": 8, "spelling_difficulty": 8, "confidence": 1.0
    },
    "clavis": {
        "language": "Latin", "tier": 1,
        "original_word": "clavis", "original_meaning": "key / instrument of opening",
        "english_meaning": "key / cipher", "translation": "key",
        "pronunciation": "KLAH-vis", "romanization": "clavis",
        "part_of_speech": "noun", "semantic_concept": "key",
        "pronunciation_difficulty": 8, "spelling_difficulty": 8, "confidence": 1.0
    },
    "pons": {
        "language": "Latin", "tier": 1,
        "original_word": "pons", "original_meaning": "bridge / crossing",
        "english_meaning": "bridge", "translation": "bridge",
        "pronunciation": "PONZ", "romanization": "pons",
        "part_of_speech": "noun", "semantic_concept": "bridge",
        "pronunciation_difficulty": 6, "spelling_difficulty": 6, "confidence": 1.0
    },
    "fluo": {
        "language": "Latin", "tier": 1,
        "original_word": "fluo", "original_meaning": "to flow / stream / glide",
        "english_meaning": "flow / stream", "translation": "flow",
        "pronunciation": "FLOO-oh", "romanization": "fluo",
        "part_of_speech": "verb", "semantic_concept": "flow",
        "pronunciation_difficulty": 6, "spelling_difficulty": 6, "confidence": 1.0
    },
    "simplex": {
        "language": "Latin", "tier": 1,
        "original_word": "simplex", "original_meaning": "simple / plain / uncompounded",
        "english_meaning": "simple / elegant", "translation": "simple",
        "pronunciation": "SIM-pleks", "romanization": "simplex",
        "part_of_speech": "adjective", "semantic_concept": "simple",
        "pronunciation_difficulty": 8, "spelling_difficulty": 8, "confidence": 1.0
    },

    # --- ITALIAN POOL ---
    "volo": {
        "language": "Italian", "tier": 1,
        "original_word": "volo", "original_meaning": "flight / soaring motion",
        "english_meaning": "flight / speed", "translation": "flight",
        "pronunciation": "VO-lo", "romanization": "volo",
        "part_of_speech": "noun", "semantic_concept": "speed",
        "pronunciation_difficulty": 6, "spelling_difficulty": 6, "confidence": 1.0
    },
    "mente": {
        "language": "Italian", "tier": 1,
        "original_word": "mente", "original_meaning": "mind / intellect / spirit",
        "english_meaning": "mind / intellect", "translation": "mind",
        "pronunciation": "MEN-teh", "romanization": "mente",
        "part_of_speech": "noun", "semantic_concept": "mind",
        "pronunciation_difficulty": 6, "spelling_difficulty": 6, "confidence": 1.0
    },
    "chiaro": {
        "language": "Italian", "tier": 1,
        "original_word": "chiaro", "original_meaning": "clear / bright / lucid",
        "english_meaning": "clear / evident", "translation": "clear",
        "pronunciation": "KYAH-ro", "romanization": "chiaro",
        "part_of_speech": "adjective", "semantic_concept": "clear",
        "pronunciation_difficulty": 10, "spelling_difficulty": 10, "confidence": 1.0
    },
    "ponte": {
        "language": "Italian", "tier": 1,
        "original_word": "ponte", "original_meaning": "bridge / link across gap",
        "english_meaning": "bridge / connector", "translation": "bridge",
        "pronunciation": "PON-teh", "romanization": "ponte",
        "part_of_speech": "noun", "semantic_concept": "bridge",
        "pronunciation_difficulty": 6, "spelling_difficulty": 6, "confidence": 1.0
    },
    "chiave": {
        "language": "Italian", "tier": 1,
        "original_word": "chiave", "original_meaning": "key / pivotal access",
        "english_meaning": "key / master token", "translation": "key",
        "pronunciation": "KYAH-veh", "romanization": "chiave",
        "part_of_speech": "noun", "semantic_concept": "key",
        "pronunciation_difficulty": 10, "spelling_difficulty": 10, "confidence": 1.0
    },
    "flusso": {
        "language": "Italian", "tier": 1,
        "original_word": "flusso", "original_meaning": "continuous flow / stream",
        "english_meaning": "flow / stream", "translation": "flow",
        "pronunciation": "FLUS-so", "romanization": "flusso",
        "part_of_speech": "noun", "semantic_concept": "flow",
        "pronunciation_difficulty": 8, "spelling_difficulty": 8, "confidence": 1.0
    },
    "luce": {
        "language": "Italian", "tier": 1,
        "original_word": "luce", "original_meaning": "light / clarity / ray",
        "english_meaning": "light / illumination", "translation": "light",
        "pronunciation": "LOO-cheh", "romanization": "luce",
        "part_of_speech": "noun", "semantic_concept": "light",
        "pronunciation_difficulty": 8, "spelling_difficulty": 8, "confidence": 1.0
    },
    "subito": {
        "language": "Italian", "tier": 1,
        "original_word": "subito", "original_meaning": "immediately / instantaneously",
        "english_meaning": "instant / immediate", "translation": "instant",
        "pronunciation": "SOO-bee-to", "romanization": "subito",
        "part_of_speech": "adverb", "semantic_concept": "instant",
        "pronunciation_difficulty": 6, "spelling_difficulty": 6, "confidence": 1.0
    },
    "rete": {
        "language": "Italian", "tier": 1,
        "original_word": "rete", "original_meaning": "network / web / grid",
        "english_meaning": "network / mesh", "translation": "network",
        "pronunciation": "REH-teh", "romanization": "rete",
        "part_of_speech": "noun", "semantic_concept": "network",
        "pronunciation_difficulty": 6, "spelling_difficulty": 6, "confidence": 1.0
    },

    # --- SPANISH POOL ---
    "onda": {
        "language": "Spanish", "tier": 1,
        "original_word": "onda", "original_meaning": "wave / ripple / vibration",
        "english_meaning": "wave / motion", "translation": "wave",
        "pronunciation": "ON-dah", "romanization": "onda",
        "part_of_speech": "noun", "semantic_concept": "motion",
        "pronunciation_difficulty": 6, "spelling_difficulty": 6, "confidence": 1.0
    },
    "claro": {
        "language": "Spanish", "tier": 1,
        "original_word": "claro", "original_meaning": "clear / bright / evident",
        "english_meaning": "clear / distinct", "translation": "clear",
        "pronunciation": "KLAH-ro", "romanization": "claro",
        "part_of_speech": "adjective", "semantic_concept": "clear",
        "pronunciation_difficulty": 6, "spelling_difficulty": 6, "confidence": 1.0
    },
    "puente": {
        "language": "Spanish", "tier": 1,
        "original_word": "puente", "original_meaning": "bridge / crossing connector",
        "english_meaning": "bridge / link", "translation": "bridge",
        "pronunciation": "PWEN-teh", "romanization": "puente",
        "part_of_speech": "noun", "semantic_concept": "bridge",
        "pronunciation_difficulty": 8, "spelling_difficulty": 8, "confidence": 1.0
    },
    "llave": {
        "language": "Spanish", "tier": 1,
        "original_word": "llave", "original_meaning": "key / opener",
        "english_meaning": "key / access", "translation": "key",
        "pronunciation": "YAH-veh", "romanization": "llave",
        "part_of_speech": "noun", "semantic_concept": "key",
        "pronunciation_difficulty": 8, "spelling_difficulty": 10, "confidence": 1.0
    },
    "forja": {
        "language": "Spanish", "tier": 1,
        "original_word": "forja", "original_meaning": "forge / workshop of creation",
        "english_meaning": "forge / smithy", "translation": "forge",
        "pronunciation": "FOR-hah", "romanization": "forja",
        "part_of_speech": "noun", "semantic_concept": "forge",
        "pronunciation_difficulty": 8, "spelling_difficulty": 8, "confidence": 1.0
    },
    "flujo": {
        "language": "Spanish", "tier": 1,
        "original_word": "flujo", "original_meaning": "flow / stream / flux",
        "english_meaning": "flow / stream", "translation": "flow",
        "pronunciation": "FLOO-ho", "romanization": "flujo",
        "part_of_speech": "noun", "semantic_concept": "flow",
        "pronunciation_difficulty": 8, "spelling_difficulty": 8, "confidence": 1.0
    },
    "raiz": {
        "language": "Spanish", "tier": 1,
        "original_word": "raíz", "original_meaning": "root / foundation / origin",
        "english_meaning": "root / source", "translation": "root",
        "pronunciation": "rah-EES", "romanization": "raiz",
        "part_of_speech": "noun", "semantic_concept": "root",
        "pronunciation_difficulty": 6, "spelling_difficulty": 6, "confidence": 1.0
    },
    "red": {
        "language": "Spanish", "tier": 1,
        "original_word": "red", "original_meaning": "network / web / grid",
        "english_meaning": "network / mesh", "translation": "network",
        "pronunciation": "REHD", "romanization": "red",
        "part_of_speech": "noun", "semantic_concept": "network",
        "pronunciation_difficulty": 4, "spelling_difficulty": 4, "confidence": 1.0
    },

    # --- JAPANESE POOL ---
    "zen": {
        "language": "Japanese", "tier": 2,
        "original_word": "禅", "original_meaning": "meditative focus / clarity of mind",
        "english_meaning": "clarity / calm focus", "translation": "mind",
        "pronunciation": "ZEN", "romanization": "zen",
        "part_of_speech": "noun", "semantic_concept": "mind",
        "pronunciation_difficulty": 4, "spelling_difficulty": 4, "confidence": 1.0
    },
    "sora": {
        "language": "Japanese", "tier": 2,
        "original_word": "空", "original_meaning": "open sky / limitless space",
        "english_meaning": "sky / openness", "translation": "clear",
        "pronunciation": "SO-rah", "romanization": "sora",
        "part_of_speech": "noun", "semantic_concept": "clear",
        "pronunciation_difficulty": 6, "spelling_difficulty": 6, "confidence": 1.0
    },
    "kagi": {
        "language": "Japanese", "tier": 2,
        "original_word": "鍵", "original_meaning": "key / essential unlock",
        "english_meaning": "key / master token", "translation": "key",
        "pronunciation": "KAH-gee", "romanization": "kagi",
        "part_of_speech": "noun", "semantic_concept": "key",
        "pronunciation_difficulty": 6, "spelling_difficulty": 6, "confidence": 1.0
    },
    "hashi": {
        "language": "Japanese", "tier": 2,
        "original_word": "橋", "original_meaning": "bridge / connecting path",
        "english_meaning": "bridge / conduit", "translation": "bridge",
        "pronunciation": "HAH-shee", "romanization": "hashi",
        "part_of_speech": "noun", "semantic_concept": "bridge",
        "pronunciation_difficulty": 6, "spelling_difficulty": 6, "confidence": 1.0
    },
    "hikari": {
        "language": "Japanese", "tier": 2,
        "original_word": "光", "original_meaning": "light / beam / illumination",
        "english_meaning": "light / beacon", "translation": "light",
        "pronunciation": "hee-KAH-ree", "romanization": "hikari",
        "part_of_speech": "noun", "semantic_concept": "light",
        "pronunciation_difficulty": 8, "spelling_difficulty": 8, "confidence": 1.0
    },
    "satori": {
        "language": "Japanese", "tier": 2,
        "original_word": "悟り", "original_meaning": "insight / deep comprehension / awakening",
        "english_meaning": "insight / wisdom", "translation": "insight",
        "pronunciation": "sah-TOH-ree", "romanization": "satori",
        "part_of_speech": "noun", "semantic_concept": "insight",
        "pronunciation_difficulty": 6, "spelling_difficulty": 6, "confidence": 1.0
    },

    # --- NORDIC POOL ---
    "fjord": {
        "language": "Nordic", "tier": 2,
        "original_word": "fjord", "original_meaning": "deep sea inlet / navigable passage",
        "english_meaning": "deep channel / waterway", "translation": "flow",
        "pronunciation": "FYORD", "romanization": "fjord",
        "part_of_speech": "noun", "semantic_concept": "flow",
        "pronunciation_difficulty": 12, "spelling_difficulty": 12, "confidence": 1.0
    },
    "snabb": {
        "language": "Nordic", "tier": 2,
        "original_word": "snabb", "original_meaning": "quick / rapid / agile",
        "english_meaning": "fast / swift", "translation": "speed",
        "pronunciation": "SNAB", "romanization": "snabb",
        "part_of_speech": "adjective", "semantic_concept": "speed",
        "pronunciation_difficulty": 8, "spelling_difficulty": 10, "confidence": 1.0
    },
    "bro": {
        "language": "Nordic", "tier": 2,
        "original_word": "bro", "original_meaning": "bridge / causeway",
        "english_meaning": "bridge", "translation": "bridge",
        "pronunciation": "BROO", "romanization": "bro",
        "part_of_speech": "noun", "semantic_concept": "bridge",
        "pronunciation_difficulty": 4, "spelling_difficulty": 4, "confidence": 1.0
    },
    "ljus": {
        "language": "Nordic", "tier": 2,
        "original_word": "ljus", "original_meaning": "light / bright / clear",
        "english_meaning": "light / illumination", "translation": "light",
        "pronunciation": "YOOSE", "romanization": "ljus",
        "part_of_speech": "noun", "semantic_concept": "light",
        "pronunciation_difficulty": 14, "spelling_difficulty": 14, "confidence": 1.0
    },
    "logos": {
        "language": "Greek", "tier": 1,
        "original_word": "logos", "original_meaning": "reason / word / thought",
        "english_meaning": "reason / logic", "translation": "logic",
        "pronunciation": "LOH-gos", "romanization": "logos",
        "part_of_speech": "noun", "semantic_concept": "wisdom",
        "pronunciation_difficulty": 5, "spelling_difficulty": 5, "confidence": 1.0
    },
    "zen": {
        "language": "Japanese", "tier": 1,
        "original_word": "zen", "original_meaning": "meditation / calm focus",
        "english_meaning": "calm / meditation", "translation": "focus",
        "pronunciation": "ZEN", "romanization": "zen",
        "part_of_speech": "noun", "semantic_concept": "simple",
        "pronunciation_difficulty": 5, "spelling_difficulty": 5, "confidence": 1.0
    }
}

class MultilingualEngine:
    """
    Evaluates, retrieves, and screens multilingual semantic words for brand naming.
    """

    def __init__(self):
        self.dictionary = MULTILINGUAL_DICTIONARY

    def lookup_term(self, term: str) -> Optional[Dict[str, Any]]:
        """Look up verified lexical record for a foreign term."""
        clean = term.lower().strip()
        if clean.endswith(".com"):
            clean = clean[:-4]
        return self.dictionary.get(clean)

    def is_verified_foreign_word(self, word: str) -> bool:
        """Checks if the word exists in the verified multilingual lexical repository."""
        clean = word.lower().strip()
        if clean.endswith(".com"):
            clean = clean[:-4]
        return clean in self.dictionary

    def evaluate_foreign_word_brandability(self, term: str) -> Dict[str, Any]:
        """
        Objectively measures properties of a foreign-language candidate:
        - length (shortness)
        - pronunciation simplicity in global/US English context
        - spelling from sound simplicity (radio test)
        - memorability & commercial clarity
        """
        clean = term.lower().strip()
        if clean.endswith(".com"):
            clean = clean[:-4]

        rec = self.lookup_term(clean)
        length = len(clean)

        pronounce_diff = rec["pronunciation_difficulty"] if rec else 25
        spelling_diff = rec["spelling_difficulty"] if rec else 25

        # Check for harsh un-Anglicized consonant clusters
        has_awkward_cluster = bool(re.search(r'[bcdfghjklmnpqrstvwxyz]{4,}', clean))
        has_silent_letters = bool(re.search(r'(sch|gn|cz|sz|kn|ps)', clean))

        if has_awkward_cluster:
            pronounce_diff += 20
        if has_silent_letters:
            spelling_diff += 15

        # Length penalty
        length_penalty = 0
        if length > 8:
            length_penalty = (length - 8) * 8
        elif length < 3:
            length_penalty = 20

        brandability = max(20, min(96, int(95 - (pronounce_diff * 0.4) - (spelling_diff * 0.3) - length_penalty)))
        radio_score = max(20, min(95, int(92 - spelling_diff - (8 if has_silent_letters else 0))))

        passes = (
            length <= 8
            and not has_awkward_cluster
            and brandability >= 68
            and radio_score >= 70
        )

        return {
            "term": clean,
            "is_foreign": rec is not None,
            "language": rec["language"] if rec else "Unknown",
            "tier": rec.get("tier", 2) if rec else 3,
            "original_word": rec.get("original_word", clean) if rec else clean,
            "original_meaning": rec.get("original_meaning", "") if rec else "",
            "translation": rec.get("translation", rec.get("english_meaning", "")) if rec else "",
            "literal_meaning": rec.get("literal_meaning", rec.get("original_meaning", "")) if rec else "",
            "english_meaning": rec.get("english_meaning", "") if rec else "",
            "pronunciation": rec.get("pronunciation", clean) if rec else clean,
            "romanization": rec.get("romanization", clean) if rec else clean,
            "semantic_concept": rec.get("semantic_concept", "UNKNOWN") if rec else "UNKNOWN",
            "length": length,
            "pronunciation_difficulty": pronounce_diff,
            "spelling_difficulty": spelling_diff,
            "brandability": brandability,
            "radio_test_score": radio_score,
            "passes_foreign_brandability_gate": passes,
            "confidence": rec.get("confidence", 0.5) if rec else 0.5
        }

    def get_candidates_for_concept(
        self,
        semantic_concept: str = "",
        target_category: str = "",
        limit: int = 12
    ) -> List[Dict[str, Any]]:
        """
        Retrieves top verified multilingual domain candidates matching a semantic concept or category.
        """
        candidates: List[Dict[str, Any]] = []
        concept_match_set = set()
        if semantic_concept:
            sc_lower = semantic_concept.lower()
            concept_match_set.add(sc_lower)
            cluster_aliases = {
                "speed_movement": {"speed", "motion", "flow"},
                "intelligence_clarity": {"mind", "insight", "wisdom", "clear"},
                "trust_security": {"root", "foundation", "key"},
                "capability": {"hand", "forge", "engine"},
                "connection": {"connect", "network", "bridge"},
                "building": {"build", "foundation", "forge"},
                "growth": {"core", "root"}
            }
            if sc_lower in cluster_aliases:
                concept_match_set.update(cluster_aliases[sc_lower])

        for term, data in self.dictionary.items():
            item_concept = str(data.get("semantic_concept", "")).lower()
            matches_concept = (not semantic_concept) or (item_concept in concept_match_set)
            if matches_concept:
                eval_res = self.evaluate_foreign_word_brandability(term)
                if eval_res["passes_foreign_brandability_gate"]:
                    candidates.append({
                        "domain": f"{term}.com",
                        "term": term,
                        "generation_strategy": "ONE_WORD",
                        "naming_type": "REAL_FOREIGN_WORD",
                        "market_category": target_category or "AI_STARTUPS",
                        "concept_source": "SEMANTIC_NAMING_CONCEPTS",
                        "semantic_concept": data.get("semantic_concept", "GENERAL"),
                        "source_language": data["language"],
                        "original_word": data.get("original_word", term),
                        "original_meaning": data.get("original_meaning", data.get("literal_meaning", "")),
                        "translation": data.get("translation", data.get("english_meaning", "")),
                        "literal_meaning": data.get("literal_meaning", data.get("original_meaning", "")),
                        "english_meaning": data.get("english_meaning", ""),
                        "pronunciation": data.get("pronunciation", term),
                        "romanization": data.get("romanization", term),
                        "linguistic_confidence": data.get("confidence", 1.0),
                        "radio_test_score": eval_res["radio_test_score"],
                        "generator_model": f"multilingual_engine_{data['language'].lower()}"
                    })
            if len(candidates) >= limit:
                break
        return candidates
