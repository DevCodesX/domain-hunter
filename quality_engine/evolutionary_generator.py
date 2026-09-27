"""
Evolutionary Domain Generator (Phase 3)
Implements an evolutionary loop:
Concept -> Seed generation -> Pre-evaluation -> Keep top candidates ->
Phonetic & Morphological Mutations (vowel/consonant substitution, prefix/suffix mutation,
phonetic simplification, semantic substitution) -> Re-evaluation -> Strongest candidates.

Safety Invariant:
Never mutate a domain that has high IP risk, trademark conflict, or registered status
into a candidate without re-running through all gates.
"""

import re
import random
import logging
import datetime
from typing import List, Dict, Any, Set, Optional

logger = logging.getLogger("EvolutionaryGenerator")


class EvolutionaryGenerator:
    """
    Evolves candidate domain names through guided linguistic mutations.
    """

    VOWELS = ["a", "e", "i", "o", "u"]
    MUTABLE_CONSONANTS = {
        "b": ["p", "v", "d"],
        "c": ["k", "s"],
        "d": ["t", "b"],
        "f": ["v", "ph"],
        "g": ["k", "j"],
        "k": ["c", "q"],
        "l": ["r", "w"],
        "m": ["n"],
        "n": ["m", "l"],
        "p": ["b"],
        "r": ["l"],
        "s": ["z", "c"],
        "t": ["d"],
        "v": ["f", "b"],
        "z": ["s"]
    }

    CURATED_PREFIX_MUTATIONS = {
        "data": ["base", "cloud", "mesh"],
        "cloud": ["data", "apex", "core"],
        "apex": ["prime", "peak", "zenith"],
        "core": ["prime", "base", "hub"],
        "flow": ["sync", "wave", "pulse"],
        "mind": ["cogni", "intel", "logic"],
        "meta": ["nova", "omni", "neo"]
    }

    CURATED_SUFFIX_MUTATIONS = {
        "labs": ["works", "hq", "base"],
        "flow": ["sync", "pulse", "stream"],
        "nest": ["haven", "vault", "base"],
        "hub": ["node", "grid", "mesh"],
        "stack": ["forge", "craft", "deck"],
        "wave": ["pulse", "surge", "shift"]
    }

    def __init__(self, feature_extractor=None):
        self.fe = feature_extractor

    def mutate_vowel(self, label: str, rng: random.Random) -> str:
        """Substitutes a vowel with another natural vowel."""
        chars = list(label)
        vowel_indices = [i for i, ch in enumerate(chars) if ch in self.VOWELS]
        if not vowel_indices:
            return label
        idx = rng.choice(vowel_indices)
        current = chars[idx]
        choices = [v for v in self.VOWELS if v != current]
        chars[idx] = rng.choice(choices)
        return "".join(chars)

    def mutate_consonant(self, label: str, rng: random.Random) -> str:
        """Substitutes a consonant with a phonetically compatible consonant."""
        chars = list(label)
        consonant_indices = [i for i, ch in enumerate(chars) if ch in self.MUTABLE_CONSONANTS]
        if not consonant_indices:
            return label
        idx = rng.choice(consonant_indices)
        current = chars[idx]
        replacements = self.MUTABLE_CONSONANTS.get(current, [])
        if replacements:
            chars[idx] = rng.choice(replacements)
        return "".join(chars)

    def mutate_prefix(self, label: str, rng: random.Random) -> str:
        """Mutates a recognized prefix."""
        for p, alts in self.CURATED_PREFIX_MUTATIONS.items():
            if label.startswith(p) and len(label) > len(p) + 2:
                alt = rng.choice(alts)
                return f"{alt}{label[len(p):]}"
        return label

    def mutate_suffix(self, label: str, rng: random.Random) -> str:
        """Mutates a recognized suffix."""
        for s, alts in self.CURATED_SUFFIX_MUTATIONS.items():
            if label.endswith(s) and len(label) > len(s) + 2:
                alt = rng.choice(alts)
                return f"{label[:-len(s)]}{alt}"
        return label

    def simplify_phonetics(self, label: str) -> str:
        """Smooths awkward consonant clusters."""
        smoothed = label
        # Replace harsh clusters
        smoothed = re.sub(r"(.)\1{2,}", r"\1", smoothed) # triplicates to single
        smoothed = smoothed.replace("qq", "qu").replace("zz", "z").replace("xx", "x")
        return smoothed

    def generate_mutations(
        self,
        seed_candidates: List[Dict[str, Any]],
        mutation_count_per_seed: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Takes top seed candidates and generates diverse morphological mutations.
        Preserves metadata traceability.
        """
        mutated_candidates: List[Dict[str, Any]] = []
        seen: Set[str] = {c.get("domain", "").lower() for c in seed_candidates}
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        rng = random.Random(42)

        mutation_ops = [
            self.mutate_vowel,
            self.mutate_consonant,
            self.mutate_prefix,
            self.mutate_suffix
        ]

        for seed in seed_candidates:
            orig_domain = seed.get("domain", "")
            orig_label = orig_domain.replace(".com", "").strip().lower()
            if len(orig_label) < 4:
                continue

            for _ in range(mutation_count_per_seed):
                op = rng.choice(mutation_ops)
                mutated_label = op(orig_label, rng)
                mutated_label = self.simplify_phonetics(mutated_label)

                new_domain = f"{mutated_label}.com"
                if new_domain not in seen and 4 <= len(mutated_label) <= 14:
                    seen.add(new_domain)
                    mutated_candidates.append({
                        "domain": new_domain,
                        "generation_strategy": seed.get("generation_strategy", "INVENTED"),
                        "naming_type": seed.get("naming_type", "INVENTED"),
                        "source_concept": seed.get("source_concept", ""),
                        "market_category": seed.get("market_category", "AI & Technology"),
                        "generator_model": "evolutionary_mutation_engine",
                        "generation_timestamp": now_iso,
                        "parent_domain": orig_domain,
                        "is_evolutionary_mutation": True
                    })

        logger.info(f"[EVOLUTIONARY] Generated {len(mutated_candidates)} mutations from {len(seed_candidates)} seeds.")
        return mutated_candidates
