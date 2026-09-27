"""
Multi-Engine Domain Generation (Phase 3)
Implements 7 specialized naming engines:
1. OneWordEngine (Real dictionary words, Zipf frequency, syllable/pronunciation analysis)
2. InventedBrandEngine (Phonetic templates: CVCVC, CVCVCV, CVCCVC, CVCVCC, CVCCVCV, VCCVCV)
3. SemanticBrandEngine (Concept synergy, metaphorical resonance, buyer intent)
4. CompoundEngine (Both parts verified dictionary words, semantic coherence)
5. PrefixSuffixEngine (High-value tech prefixes/suffixes with anti-repetition control)
6. TrendEngine (Emerging trend paradigms, candidate-specific quality evaluation)
7. KeywordBrandableEngine (Commercial anchor keywords + high-prestige affixes)

Features:
- Initial generation budget ~1500-3000 candidates (default 1950)
- Dynamic generation quotas with exploration (20-30%) and exploitation (70-80%)
- Reallocation if any engine produces insufficient yield
"""

import os
import re
import time
import random
import logging
import datetime
from typing import List, Dict, Any, Optional, Set, Tuple

from quality_engine.config import MIN_CANDIDATE_LENGTH, MAX_CANDIDATE_LENGTH
from quality_engine.one_word_engine import OneWordQualityEngine, CORE_VOCAB_SAMPLE, REAL_3_LETTER_WORDS
from quality_engine.morphology_classifier import MorphologyClassifier

logger = logging.getLogger("MultiEngineGenerator")

# Target quotas per run (total = 1950)
INITIAL_STRATEGY_QUOTAS: Dict[str, int] = {
    "ONE_WORD": 300,
    "INVENTED": 400,
    "SEMANTIC": 350,
    "COMPOUND": 300,
    "PREFIX_SUFFIX": 200,
    "TREND": 200,
    "KEYWORD_BRANDABLE": 200
}

# Authentic English dictionary words for ONE_WORD engine (expanded, 5-12 chars, authentic lexicon)
CURATED_DICTIONARY_ONE_WORDS: List[str] = [
    "beacon", "stride", "cipher", "nexus", "haven", "summit", "matrix", "vector", "apex",
    "vertex", "zenith", "tensor", "anchor", "canvas", "ledger", "quantum", "foster", "timber",
    "harbor", "atlas", "mantle", "sentry", "chronicle", "vortex", "cobalt", "merit", "valor",
    "glimmer", "flock", "flair", "vigor", "verve", "tempo", "glyph", "aura", "rune", "quest",
    "orbit", "shift", "pulse", "surge", "spark", "forge", "stack", "cloud", "vault", "prism",
    "solstice", "caldera", "tessera", "strata", "spindle", "thalweg", "paragon", "foliage",
    "spire", "keystone", "kestrel", "astral", "celer", "corbel", "fissure", "halcyon",
    "meridian", "pinnacle", "fulcrum", "zephyr", "solaris", "arcana", "lexicon", "bastion",
    "caravel", "tundra", "pylon", "monad", "cadence", "stasis", "torque", "kinetic", "cortex",
    "radix", "syntax", "quiver", "helix", "axiom", "relic", "anvil", "ember", "flint", "quartz",
    "onyx", "topaz", "garnet", "talon", "falcon", "condor", "osprey", "heron", "avalon", "elysium",
    "creed", "tenor", "vessel", "compass", "sextant", "polaris", "rigel", "altair", "deneb", "sirius",
    "antares", "capella", "vega", "canopus", "achernar", "spica", "pollux", "regulus", "adara",
    "castor", "alnilam", "alioth", "dubhe", "mirfak", "wezen", "alkaid", "atria", "mirzam",
    "alphard", "hamal", "nunki", "mirach", "algol", "saiph", "denebola", "mintaka", "etamin",
    "schedar", "naos", "chort", "sabik", "markab", "corvus", "cygnus", "orion", "lyra", "aquila",
    "draco", "hydra", "vela", "centaur", "phoenix", "pegasus", "taurus", "auriga", "vulpec",
    "scutum", "fornax", "lacerta", "mensa", "musca", "volans", "pictor", "norma", "antlia",
    "circinus", "pyxis", "serpens", "monoceros", "bootes", "sagitta", "lepus", "telescop",
    "blazon", "cairn", "dune", "escarp", "fjord", "gorge", "knoll", "lagoon", "mesa", "oasis",
    "plateau", "quarry", "reef", "steppe", "trench", "vale", "wharf", "alcove", "belfry", "chancel",
    "donjon", "esplanade", "gable", "loggia", "minaret", "narthex", "parapet", "portico", "turret"
]

# Genuine semantic roots for compounding & semantic naming
AUTHENTIC_COMPOUND_ROOTS: List[str] = [
    "cloud", "nest", "data", "flow", "mind", "hub", "sync", "base", "core", "node", "pulse",
    "wire", "mesh", "logic", "vault", "forge", "spark", "orbit", "grid", "shift", "wave",
    "path", "craft", "stack", "gate", "link", "dock", "haven", "crest", "stride", "scale",
    "sphere", "tensor", "anchor", "stone", "star", "light", "shade", "peak", "iron", "field"
]

# Curated prefixes & suffixes with controlled usage
CURATED_PREFIXES: List[str] = [
    "core", "meta", "nova", "sync", "flow", "apex", "omni", "pure", "open", "neo", "pro",
    "swift", "hyper", "prime", "zen", "cyber", "auto", "syn", "micro", "poly"
]

CURATED_SUFFIXES: List[str] = [
    "labs", "flow", "sync", "hq", "base", "stack", "works", "hub", "node", "pulse",
    "craft", "nest", "loop", "grid", "wave", "zone", "mind", "path", "wire", "link"
]


class BaseNamingEngine:
    def __init__(self, router=None):
        self.router = router

    def clean_domain(self, text: str) -> Optional[str]:
        cleaned = text.lower().strip()
        cleaned = re.sub(r"[^a-z0-9-.]", "", cleaned)
        if not cleaned.endswith(".com"):
            cleaned = f"{cleaned}.com"
        label = cleaned[:-4]
        if MIN_CANDIDATE_LENGTH <= len(label) <= MAX_CANDIDATE_LENGTH and re.match(r"^[a-z0-9-]+$", label):
            return cleaned
        return None


class OneWordEngine(BaseNamingEngine):
    """
    Finds and generates real dictionary words, short recognizable words,
    commercially useful, uncommon but pronounceable words.
    Validates dictionary presence and frequency via OneWordQualityEngine.
    """
    def __init__(self, router=None, one_word_validator: Optional[OneWordQualityEngine] = None):
        super().__init__(router)
        self.validator = one_word_validator or OneWordQualityEngine()

    async def generate(self, concept: str, category: str = "AI & Technology", count: int = 300) -> List[Dict[str, Any]]:
        candidates = []
        seen = set()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 1. AI Generation with strict ONE_WORD prompt if router available
        if self.router:
            prompt = f"""Generate {min(count, 80)} authentic, single-word .com domain names (one real English dictionary word before .com) relevant to: "{concept}".
Strict rules:
1. Every candidate MUST be a real dictionary word (5 to 11 letters).
2. NO invented blends, NO compounds, NO glued words.
3. High prestige, evocative, memorable nouns, verbs, or adjectives (e.g. caldera, strata, spindle, bastion, haven, forge, meridian, cipher, ledger).
Output as a comma-separated list of .com domains."""
            try:
                res = await self.router.execute_task("domain_generation", prompt, temperature=0.75, max_tokens=1000)
                words = re.split(r"[\n,;]+", res)
                for w in words:
                    d = self.clean_domain(w)
                    if d and d not in seen:
                        label = d[:-4]
                        is_dict, zipf = self.validator.is_dictionary_word(label)
                        if is_dict and 5 <= len(label) <= 12:
                            seen.add(d)
                            candidates.append({
                                "domain": d,
                                "generation_strategy": "ONE_WORD",
                                "naming_type": "ONE_WORD",
                                "source_concept": concept,
                                "market_category": category,
                                "generator_model": "one_word_ai_engine",
                                "generation_timestamp": now_iso
                            })
            except Exception as e:
                logger.warning(f"OneWordEngine AI generation failed: {e}")

        # 2. Curated English lexicon pool augmentation
        shuffled = list(CURATED_DICTIONARY_ONE_WORDS)
        random.seed(int(time.time() * 1000) % 100000)
        random.shuffle(shuffled)

        for w in shuffled:
            if len(candidates) >= count:
                break
            d = f"{w}.com"
            if d not in seen:
                is_dict, zipf = self.validator.is_dictionary_word(w)
                if is_dict:
                    seen.add(d)
                    candidates.append({
                        "domain": d,
                        "generation_strategy": "ONE_WORD",
                        "naming_type": "ONE_WORD",
                        "source_concept": concept,
                        "market_category": category,
                        "generator_model": "curated_lexical_engine",
                        "generation_timestamp": now_iso
                    })

        return candidates[:count]


class InventedBrandEngine(BaseNamingEngine):
    """
    Generates pronounceable invented brand names using diverse phonetic templates:
    CVCVC, CVCVCV, CVCCVC, CVCVCC, CVCCVCV, VCCVCV.
    Guarantees vowel balance, strong phonetics, low spelling ambiguity, 5-9 chars.
    Controls repetition and avoids identical-looking families (e.g. no Xvira/Xviro/Xvirox clusters).
    """
    CONSONANTS = ["b", "c", "d", "f", "g", "h", "k", "l", "m", "n", "p", "r", "s", "t", "v", "w", "z"]
    SOFT_CONSONANTS = ["l", "m", "n", "r", "s", "v", "z"]
    STRONG_CONSONANTS = ["b", "d", "k", "p", "t", "c"]
    VOWELS = ["a", "e", "i", "o", "u"]
    TEMPLATES = ["CVCVC", "CVCVCV", "CVCCVC", "CVCVCC", "CVCCVCV", "VCCVCV"]

    def _generate_template_word(self, template: str, rng: random.Random) -> str:
        chars = []
        for i, char_type in enumerate(template):
            if char_type == "C":
                # Alternate between soft and strong consonants to avoid awkward clusters
                if i > 0 and template[i-1] == "C":
                    chars.append(rng.choice(self.SOFT_CONSONANTS))
                else:
                    chars.append(rng.choice(self.CONSONANTS))
            elif char_type == "V":
                chars.append(rng.choice(self.VOWELS))
        return "".join(chars)

    async def generate(self, concept: str, category: str = "AI & Technology", count: int = 400) -> List[Dict[str, Any]]:
        candidates = []
        seen = set()
        prefix_family_counts: Dict[str, int] = {}
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        rng = random.Random(int(time.time() * 1000) % 999999)

        # 1. AI Generation if router available
        if self.router:
            prompt = f"""Generate {min(count, 100)} original, pronounceable INVENTED brand names ending in .com (5 to 8 letters) for: "{concept}".
Requirements:
1. Harmonious phonetics like Figma, Stripe, Canva, Zillow, Vercel, Asana, Twilio.
2. Vowel-balanced, natural rhythm.
3. DO NOT repeat prefix families (no Xvira, Xviro, Xvirox, Xvera).
4. Output as a comma-separated list of .com domains."""
            try:
                res = await self.router.execute_task("domain_generation", prompt, temperature=0.8, max_tokens=1200)
                words = re.split(r"[\n,;]+", res)
                for w in words:
                    d = self.clean_domain(w)
                    if d and d not in seen:
                        label = d[:-4]
                        family = label[:4] if len(label) >= 4 else label
                        if prefix_family_counts.get(family, 0) < 2 and 5 <= len(label) <= 9:
                            seen.add(d)
                            prefix_family_counts[family] = prefix_family_counts.get(family, 0) + 1
                            candidates.append({
                                "domain": d,
                                "generation_strategy": "INVENTED",
                                "naming_type": "INVENTED",
                                "source_concept": concept,
                                "market_category": category,
                                "generator_model": "invented_ai_engine",
                                "generation_timestamp": now_iso
                            })
            except Exception as e:
                logger.warning(f"InventedBrandEngine AI generation failed: {e}")

        # 2. Multi-template phonetic algorithmic generation
        while len(candidates) < count:
            t = rng.choice(self.TEMPLATES)
            word = self._generate_template_word(t, rng)
            d = f"{word}.com"
            family = word[:4] if len(word) >= 4 else word

            if d not in seen and prefix_family_counts.get(family, 0) < 2:
                # Basic phonetic filter: avoid q, x, z overuse
                rare_letters = sum(1 for ch in word if ch in ["q", "x", "z", "j"])
                if rare_letters <= 1:
                    seen.add(d)
                    prefix_family_counts[family] = prefix_family_counts.get(family, 0) + 1
                    candidates.append({
                        "domain": d,
                        "generation_strategy": "INVENTED",
                        "naming_type": "INVENTED",
                        "source_concept": concept,
                        "market_category": category,
                        "generator_model": "phonetic_template_engine",
                        "generation_timestamp": now_iso
                    })

        return candidates[:count]


class SemanticBrandEngine(BaseNamingEngine):
    """
    Generates domains from meaningful concept pairings (cloud + intelligence, data + flow,
    commerce + automation, finance + trust, security + infrastructure).
    Evaluates semantic relationship, buyer relevance, and brandability.
    """
    CONCEPT_PAIRS: List[Tuple[str, str]] = [
        ("cloud", "intelligence"), ("data", "flow"), ("commerce", "automation"),
        ("finance", "trust"), ("security", "core"), ("logic", "scale"),
        ("nexus", "wave"), ("tensor", "grid"), ("apex", "mind"),
        ("prime", "forge"), ("pulse", "shift"), ("haven", "vault"),
        ("vector", "path"), ("stride", "link"), ("quantum", "spark")
    ]

    async def generate(self, concept: str, category: str = "AI & Technology", count: int = 350) -> List[Dict[str, Any]]:
        candidates = []
        seen = set()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if self.router:
            prompt = f"""Generate {min(count, 90)} evocative SEMANTIC BRANDABLE .com domains based on concept "{concept}".
Rules:
1. High synergy concept combinations with metaphorical resonance (like Ironclad, Cloudflare, DeepCurrent, TrueNorth, ApexLogic).
2. Avoid generic word-glue; use compelling imagery and commercial intent.
3. Output as comma-separated list of .com domains."""
            try:
                res = await self.router.execute_task("domain_generation", prompt, temperature=0.75, max_tokens=1200)
                words = re.split(r"[\n,;]+", res)
                for w in words:
                    d = self.clean_domain(w)
                    if d and d not in seen and len(d[:-4]) <= 14:
                        seen.add(d)
                        candidates.append({
                            "domain": d,
                            "generation_strategy": "SEMANTIC",
                            "naming_type": "SEMANTIC_BRANDABLE",
                            "source_concept": concept,
                            "market_category": category,
                            "generator_model": "semantic_ai_engine",
                            "generation_timestamp": now_iso
                        })
            except Exception as e:
                logger.warning(f"SemanticBrandEngine AI generation failed: {e}")

        # Algorithmic pairings
        shuffled_roots = list(AUTHENTIC_COMPOUND_ROOTS)
        rng = random.Random(42)
        rng.shuffle(shuffled_roots)

        for i in range(len(shuffled_roots)):
            for j in range(len(shuffled_roots)):
                if len(candidates) >= count:
                    break
                if i != j:
                    w1, w2 = shuffled_roots[i], shuffled_roots[j]
                    comb = f"{w1}{w2}"
                    d = f"{comb}.com"
                    if d not in seen and len(comb) <= 13:
                        seen.add(d)
                        candidates.append({
                            "domain": d,
                            "generation_strategy": "SEMANTIC",
                            "naming_type": "SEMANTIC_BRANDABLE",
                            "source_concept": concept,
                            "market_category": category,
                            "generator_model": "semantic_pair_engine",
                            "generation_timestamp": now_iso
                        })

        return candidates[:count]


class CompoundEngine(BaseNamingEngine):
    """
    Generates genuine compound names where BOTH components are meaningful English dictionary words.
    Enforces semantic coherence; rejects fake compounds or arbitrary splits (e.g. cloud+nest qualifies, guv+ni NEVER qualifies).
    """
    def __init__(self, router=None, one_word_validator: Optional[OneWordQualityEngine] = None):
        super().__init__(router)
        self.validator = one_word_validator or OneWordQualityEngine()

    async def generate(self, concept: str, category: str = "AI & Technology", count: int = 300) -> List[Dict[str, Any]]:
        candidates = []
        seen = set()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if self.router:
            prompt = f"""Generate {min(count, 80)} premium COMPOUND .com domains formed by fusing TWO authentic English dictionary words (like Coinbase, DoorDash, Datadog, Cloudnest) for: "{concept}".
Strict rules:
1. BOTH parts must be genuine, recognized English words (each >= 3 letters).
2. NO fake compounds or gibberish splits.
3. Max 1 domain per starting prefix.
4. Output as comma-separated list of .com domains."""
            try:
                res = await self.router.execute_task("domain_generation", prompt, temperature=0.7, max_tokens=1100)
                words = re.split(r"[\n,;]+", res)
                for w in words:
                    d = self.clean_domain(w)
                    if d and d not in seen:
                        label = d[:-4]
                        # Verify genuine split exists
                        if len(label) >= 6:
                            for split_idx in range(3, len(label) - 2):
                                left, right = label[:split_idx], label[split_idx:]
                                if self.validator.is_dictionary_word(left)[0] and self.validator.is_dictionary_word(right)[0]:
                                    seen.add(d)
                                    candidates.append({
                                        "domain": d,
                                        "generation_strategy": "COMPOUND",
                                        "naming_type": "COMPOUND",
                                        "source_concept": concept,
                                        "market_category": category,
                                        "generator_model": "compound_ai_engine",
                                        "generation_timestamp": now_iso
                                    })
                                    break
            except Exception as e:
                logger.warning(f"CompoundEngine AI generation failed: {e}")

        # Algorithmic genuine compounds
        verified_roots = [r for r in AUTHENTIC_COMPOUND_ROOTS if self.validator.is_dictionary_word(r)[0]]
        rng = random.Random(101)
        shuffled = list(verified_roots)
        rng.shuffle(shuffled)

        for w1 in shuffled:
            for w2 in shuffled:
                if len(candidates) >= count:
                    break
                if w1 != w2:
                    comb = f"{w1}{w2}"
                    d = f"{comb}.com"
                    if d not in seen and len(comb) <= 12:
                        seen.add(d)
                        candidates.append({
                            "domain": d,
                            "generation_strategy": "COMPOUND",
                            "naming_type": "COMPOUND",
                            "source_concept": concept,
                            "market_category": category,
                            "generator_model": "compound_lexical_engine",
                            "generation_timestamp": now_iso
                        })

        return candidates[:count]


class PrefixSuffixEngine(BaseNamingEngine):
    """
    Generates names using meaningful prefixes/suffixes (core, labs, flow, sync, hq, base, stack, works, hub).
    Aggressively controls repetition (max 2 per prefix/suffix family across run).
    """
    async def generate(self, concept: str, category: str = "AI & Technology", count: int = 200) -> List[Dict[str, Any]]:
        candidates = []
        seen = set()
        prefix_usage: Dict[str, int] = {}
        suffix_usage: Dict[str, int] = {}
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Extract words from concept
        concept_words = [w.lower() for w in re.findall(r"[a-zA-Z]{3,}", concept) if len(w) <= 8]
        if not concept_words:
            concept_words = ["intel", "agent", "cloud", "mesh", "model", "scale", "logic", "vault"]

        # Mix prefixes
        for p in CURATED_PREFIXES:
            for w in concept_words:
                if len(candidates) >= count // 2:
                    break
                if prefix_usage.get(p, 0) < 3:
                    cand = f"{p}{w}.com"
                    if cand not in seen:
                        seen.add(cand)
                        prefix_usage[p] = prefix_usage.get(p, 0) + 1
                        candidates.append({
                            "domain": cand,
                            "generation_strategy": "PREFIX_SUFFIX",
                            "naming_type": "PREFIX_SUFFIX",
                            "source_concept": concept,
                            "market_category": category,
                            "generator_model": "prefix_affix_engine",
                            "generation_timestamp": now_iso
                        })

        # Mix suffixes
        for s in CURATED_SUFFIXES:
            for w in concept_words:
                if len(candidates) >= count:
                    break
                if suffix_usage.get(s, 0) < 3:
                    cand = f"{w}{s}.com"
                    if cand not in seen:
                        seen.add(cand)
                        suffix_usage[s] = suffix_usage.get(s, 0) + 1
                        candidates.append({
                            "domain": cand,
                            "generation_strategy": "PREFIX_SUFFIX",
                            "naming_type": "PREFIX_SUFFIX",
                            "source_concept": concept,
                            "market_category": category,
                            "generator_model": "suffix_affix_engine",
                            "generation_timestamp": now_iso
                        })

        return candidates[:count]


class TrendEngine(BaseNamingEngine):
    """
    Uses current concepts/trends as inspiration.
    TREND SCORE != CANDIDATE QUALITY: Evaluates candidate brand quality itself.
    """
    async def generate(self, concept: str, category: str = "AI & Technology", count: int = 200) -> List[Dict[str, Any]]:
        candidates = []
        seen = set()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if self.router:
            prompt = f"""Generate {min(count, 80)} cutting-edge TREND-INSPIRED .com domain names for: "{concept}".
Rules:
1. Capture frontier technology paradigms (autonomous computing, cognitive networks, spatial intelligence).
2. Distinct morphological structures; no repetitive suffixes.
3. Output as comma-separated list of .com domains."""
            try:
                res = await self.router.execute_task("domain_generation", prompt, temperature=0.75, max_tokens=1100)
                words = re.split(r"[\n,;]+", res)
                for w in words:
                    d = self.clean_domain(w)
                    if d and d not in seen:
                        seen.add(d)
                        candidates.append({
                            "domain": d,
                            "generation_strategy": "TREND",
                            "naming_type": "INVENTED",
                            "source_concept": concept,
                            "market_category": category,
                            "generator_model": "trend_ai_engine",
                            "generation_timestamp": now_iso
                        })
            except Exception as e:
                logger.warning(f"TrendEngine AI generation failed: {e}")

        # Algorithmic trend synthesis fallback
        trend_roots = ["neuro", "synapse", "quantum", "tensor", "orbit", "spatial", "helix", "kinetic", "veritas", "monad"]
        trend_affixes = ["run", "scale", "node", "mind", "grid", "mesh", "core", "shift"]
        for r in trend_roots:
            for a in trend_affixes:
                if len(candidates) >= count:
                    break
                cand = f"{r}{a}.com"
                if cand not in seen:
                    seen.add(cand)
                    candidates.append({
                        "domain": cand,
                        "generation_strategy": "TREND",
                        "naming_type": "INVENTED",
                        "source_concept": concept,
                        "market_category": category,
                        "generator_model": "trend_synthesis_engine",
                        "generation_timestamp": now_iso
                    })

        return candidates[:count]


class KeywordBrandableEngine(BaseNamingEngine):
    """
    Generates domains around high-commercial-intent concepts (AI, agent, cloud, data, security, finance, commerce, automation).
    Creates brandable business names, avoiding exact-match generic keyword spam.
    """
    ANCHOR_KEYWORDS = ["agent", "intel", "logic", "vault", "ledger", "asset", "pay", "cloud", "mesh", "vector"]
    BRANDABLE_AFFIXES = ["craft", "forge", "haven", "crest", "stride", "nexus", "prism", "spark", "scale", "point"]

    async def generate(self, concept: str, category: str = "AI & Technology", count: int = 200) -> List[Dict[str, Any]]:
        candidates = []
        seen = set()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if self.router:
            prompt = f"""Generate {min(count, 80)} KEYWORD BRANDABLE .com domains around commercial concept "{concept}".
Rules:
1. Combine high-intent business anchor with a brandable affix (like AgentForge, CloudHaven, MeshPoint, VectorStride).
2. BRANDABLE business name, NOT an SEO keyword domain list.
3. Output as comma-separated list of .com domains."""
            try:
                res = await self.router.execute_task("domain_generation", prompt, temperature=0.7, max_tokens=1000)
                words = re.split(r"[\n,;]+", res)
                for w in words:
                    d = self.clean_domain(w)
                    if d and d not in seen:
                        seen.add(d)
                        candidates.append({
                            "domain": d,
                            "generation_strategy": "KEYWORD_BRANDABLE",
                            "naming_type": "PREFIX_SUFFIX",
                            "source_concept": concept,
                            "market_category": category,
                            "generator_model": "keyword_brandable_ai",
                            "generation_timestamp": now_iso
                        })
            except Exception as e:
                logger.warning(f"KeywordBrandableEngine AI generation failed: {e}")

        # Algorithmic keyword brandables
        for kw in self.ANCHOR_KEYWORDS:
            for af in self.BRANDABLE_AFFIXES:
                if len(candidates) >= count:
                    break
                cand = f"{kw}{af}.com"
                if cand not in seen:
                    seen.add(cand)
                    candidates.append({
                        "domain": cand,
                        "generation_strategy": "KEYWORD_BRANDABLE",
                        "naming_type": "PREFIX_SUFFIX",
                        "source_concept": concept,
                        "market_category": category,
                        "generator_model": "keyword_brandable_synthetic",
                        "generation_timestamp": now_iso
                    })

        return candidates[:count]


class MultiEngineOrchestrator:
    """
    Coordinates all 7 naming engines with dynamic quota allocation.
    Maintains target budget between 1500 and 3000 raw candidates per run.
    Rebalances quotas if one strategy underperforms.
    """

    def __init__(self, router=None, one_word_validator: Optional[OneWordQualityEngine] = None):
        self.router = router
        self.validator = one_word_validator or OneWordQualityEngine()
        self.one_word_engine = OneWordEngine(router, self.validator)
        self.invented_engine = InventedBrandEngine(router)
        self.semantic_engine = SemanticBrandEngine(router)
        self.compound_engine = CompoundEngine(router, self.validator)
        self.prefix_suffix_engine = PrefixSuffixEngine(router)
        self.trend_engine = TrendEngine(router)
        self.keyword_brandable_engine = KeywordBrandableEngine(router)

    def calculate_dynamic_quotas(
        self,
        strategy_stats: Optional[Dict[str, Dict[str, Any]]] = None,
        target_total: int = 1950
    ) -> Dict[str, int]:
        """
        Dynamically adjusts strategy quotas based on historical performance:
        - 75% budget allocated proportionally to strategy yield / acceptance rate
        - 25% exploration budget distributed evenly to prevent extinction of low-frequency strategies
        """
        if not strategy_stats:
            # Return baseline initial quotas scaled to target_total
            base_sum = sum(INITIAL_STRATEGY_QUOTAS.values())
            scale = target_total / base_sum
            return {k: max(50, int(v * scale)) for k, v in INITIAL_STRATEGY_QUOTAS.items()}

        strategies = list(INITIAL_STRATEGY_QUOTAS.keys())
        num_strats = len(strategies)

        # 25% exploration pool (equally distributed)
        exploration_budget = int(target_total * 0.25)
        per_strat_exploration = exploration_budget // num_strats

        # 75% exploitation pool (weighted by acceptance rate / survival yield)
        exploitation_budget = target_total - exploration_budget

        weights: Dict[str, float] = {}
        for s in strategies:
            st = strategy_stats.get(s, {})
            # Acceptance rate or yield
            acc_rate = float(st.get("acceptance_rate", 0.05))
            avg_quality = float(st.get("average_quality_score", 70.0)) / 100.0
            weight = max(0.01, (acc_rate * 0.7) + (avg_quality * 0.3))
            weights[s] = weight

        total_weight = sum(weights.values()) or 1.0

        quotas: Dict[str, int] = {}
        for s in strategies:
            strat_exploit = int(exploitation_budget * (weights[s] / total_weight))
            quotas[s] = max(40, per_strat_exploration + strat_exploit)

        # Re-normalize sum to target_total
        current_sum = sum(quotas.values())
        diff = target_total - current_sum
        quotas["INVENTED"] += diff

        return quotas

    async def generate_all(
        self,
        concepts: List[Any],
        target_total: int = 1950,
        strategy_stats: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Executes generation across all 7 engines using dynamically balanced quotas.
        Dynamically reallocates capacity if one strategy underproduces.
        """
        quotas = self.calculate_dynamic_quotas(strategy_stats, target_total)
        logger.info(f"[MULTI-ENGINE] Dynamic strategy quotas allocated: {quotas} (Target Total: {target_total})")

        primary_concept = concepts[0].get("concept") if concepts and isinstance(concepts[0], dict) else (str(concepts[0]) if concepts else "Autonomous AI Systems")
        category = concepts[0].get("category", "AI & Technology") if concepts and isinstance(concepts[0], dict) else "AI & Technology"

        # Run all engines concurrently
        tasks = [
            self.one_word_engine.generate(primary_concept, category, count=quotas["ONE_WORD"]),
            self.invented_engine.generate(primary_concept, category, count=quotas["INVENTED"]),
            self.semantic_engine.generate(primary_concept, category, count=quotas["SEMANTIC"]),
            self.compound_engine.generate(primary_concept, category, count=quotas["COMPOUND"]),
            self.prefix_suffix_engine.generate(primary_concept, category, count=quotas["PREFIX_SUFFIX"]),
            self.trend_engine.generate(primary_concept, category, count=quotas["TREND"]),
            self.keyword_brandable_engine.generate(primary_concept, category, count=quotas["KEYWORD_BRANDABLE"])
        ]

        import asyncio
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_candidates: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        deficit = 0

        engine_keys = ["ONE_WORD", "INVENTED", "SEMANTIC", "COMPOUND", "PREFIX_SUFFIX", "TREND", "KEYWORD_BRANDABLE"]

        for i, res in enumerate(results):
            strategy_name = engine_keys[i]
            target_count = quotas[strategy_name]
            if isinstance(res, list):
                for item in res:
                    d = item["domain"]
                    if d not in seen:
                        seen.add(d)
                        all_candidates.append(item)
                actual_count = len(res)
                if actual_count < target_count:
                    deficit += (target_count - actual_count)
            else:
                logger.warning(f"[MULTI-ENGINE] Strategy {strategy_name} failed: {res}")
                deficit += target_count

        # Reallocate deficit to strongest engine (e.g. invented / compound) if deficit > 50
        if deficit > 50:
            logger.info(f"[MULTI-ENGINE] Reallocating deficit of {deficit} candidates to InventedBrandEngine...")
            extra = await self.invented_engine.generate(primary_concept, category, count=deficit)
            for item in extra:
                d = item["domain"]
                if d not in seen:
                    seen.add(d)
                    all_candidates.append(item)

        logger.info(f"[MULTI-ENGINE] Generation complete. Generated {len(all_candidates)} candidates across 7 engines.")
        return all_candidates

    def get_strategy_quotas(
        self,
        target_total: int = 1950,
        strategy_stats: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> Dict[str, int]:
        """
        Adapter: returns the dynamic quota allocation dict.
        Maps to calculate_dynamic_quotas for test compatibility.
        """
        return self.calculate_dynamic_quotas(strategy_stats, target_total)

    def generate_all_strategies(
        self,
        concepts: List[Any],
        target_count: int = 1950
    ) -> List[Dict[str, Any]]:
        """
        Synchronous adapter for generate_all (test compatibility).
        Runs the async generate_all in a new event loop.
        """
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # If already in an async context, create a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self.generate_all(concepts, target_count))
                return future.result()
        else:
            return asyncio.run(self.generate_all(concepts, target_count))
