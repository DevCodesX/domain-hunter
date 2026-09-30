"""
Multiple Naming Strategies Generator
Implements modular generation strategies:
- ONE_WORD
- COMPOUND
- INVENTED
- SEMANTIC_BRANDABLE
- KEYWORD_BRANDABLE
- TREND_BASED

Features dynamic refill across strategies and standardized candidate metadata.
"""

import os
import re
import time
import asyncio
import datetime
import logging
from typing import List, Dict, Any, Optional, Set
from quality_engine.config import DEFAULT_STRATEGY_TARGETS

logger = logging.getLogger("StrategyGenerator")

# Curated seed lists for algorithmic augmentation / fallback and blend synthesis
# Phase 2.75B: Expanded 250+ authentic English one-words and evocative classical roots
HIGH_VALUE_ONE_WORDS = [
    "beacon", "stride", "cipher", "nexus", "haven", "summit", "matrix", "vector", "apex",
    "vertex", "zenith", "tensor", "anchor", "canvas", "ledger", "quantum", "foster", "timber",
    "harbor", "atlas", "mantle", "sentry", "chronicle", "vortex", "cobalt", "merit", "valor",
    "glimmer", "flock", "flair", "vigor", "verve", "tempo", "glyph", "aura", "rune", "quest",
    "orbit", "shift", "pulse", "surge", "spark", "forge", "stack", "cloud", "vault", "prism",
    "solstice", "caldera", "tessera", "strata", "spindle", "thalweg", "paragon", "foliage",
    "spire", "keystone", "prismata", "stridor", "novira", "velox", "lumina", "sora", "kumo",
    "kestrel", "veridian", "astral", "zenithic", "vectra", "omnis", "celer", "valida", "tensix",
    "veris", "aethel", "modula", "corbel", "fissure", "halcyon", "meridian", "pinnacle",
    "fulcrum", "zephyr", "solaris", "arcana", "lexicon", "bastion", "caravel", "zenon",
    "tundra", "pylon", "monad", "cadence", "valour", "stasis", "torque", "kinetic",
    "cortex", "radix", "syntax", "quiver", "helix", "axiom", "relic", "anvil",
    "ember", "flint", "quartz", "onyx", "topaz", "garnet", "talon", "falcon",
    "condor", "osprey", "heron", "avalon", "elysium", "creed", "tenor", "vessel",
    "compass", "sextant", "polaris", "rigel", "altair", "deneb", "sirius", "antares",
    "capella", "vega", "canopus", "achernar", "spica", "pollux", "regulus", "adara",
    "castor", "alnilam", "alioth", "dubhe", "mirfak", "wezen", "alkaid", "atria",
    "mirzam", "alphard", "hamal", "nunki", "mirach", "algol", "saiph", "denebola",
    "mintaka", "etamin", "schedar", "naos", "chort", "sabik", "markab", "alrescha",
    "corvus", "cygnus", "orion", "lyra", "aquila", "draco", "hydra", "vela",
    "centaur", "phoenix", "pegasus", "taurus", "auriga", "vulpec", "scutum", "fornax",
    "lacerta", "mensa", "musca", "volans", "pictor", "norma", "antlia", "circinus",
    "pyxis", "serpens", "monoceros", "bootes", "sagitta", "lepus", "telescop", "horolog"
]

CURATED_TECH_PREFIXES = [
    "meta", "nova", "sync", "flow", "apex", "omni", "vibe", "hyper", "zen", "pure",
    "open", "neo", "pro", "syn", "cyber", "auto", "core", "peak", "prime", "swift"
]

CURATED_TECH_SUFFIXES = [
    "labs", "base", "flow", "stack", "pulse", "craft", "nest", "loop", "grid", "wave",
    "sync", "node", "hub", "zone", "mind", "path", "shift", "view", "wire", "link"
]

INVENTIVE_MORPHEMES = [
    ("lyv", "ion"), ("zen", "core"), ("vist", "ora"), ("nex", "ify"), ("vel", "ora"),
    ("kyn", "etic"), ("aer", "ovibe"), ("qual", "tra"), ("syn", "tiva"), ("opt", "ora"),
    ("lum", "ira"), ("sol", "vion"), ("cog", "nix"), ("alt", "ura"), ("vol", "tix")
]

class NamingStrategyGenerator:
    def __init__(self, router):
        self.router = router
        self.targets = DEFAULT_STRATEGY_TARGETS.copy()
        from quality_engine.multi_engine import MultiEngineOrchestrator
        from quality_engine.evolutionary_generator import EvolutionaryGenerator
        self.multi_engine = MultiEngineOrchestrator(router=self.router)
        self.evolutionary_generator = EvolutionaryGenerator()

    def _clean_candidates(
        self,
        text: str,
        strategy: str,
        concept: str,
        model: str,
        category: str = "AI & Technology",
        keywords: Optional[List[str]] = None,
        batch_id: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Cleans and standardizes raw generated candidates into metadata records with
        full Section 5 traceability.
        """
        from quality_engine.morphology_classifier import MorphologyClassifier

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        records = []
        seen = set()
        active_batch_id = batch_id or f"batch_{int(time.time())}"

        # Split on commas, newlines, bullet points, numbering
        lines = re.split(r"[\n,;]+", text)
        for line in lines:
            # Strip markdown, quotes, numbers
            clean = re.sub(r"^[\d\.\-\*\s]+", "", line).strip()
            clean = clean.replace("`", "").replace("'", "").replace('"', "").lower().strip()
            
            # Extract domain pattern
            match = re.search(r"([a-z0-9-]+(?:\.com)?)", clean)
            if match:
                domain = match.group(1)
                if not domain.endswith(".com"):
                    domain = f"{domain}.com"
                
                # Basic sanity
                label = domain[:-4]
                if len(label) >= 2 and label not in seen and re.match(r"^[a-z0-9-]+$", label):
                    # Disallow contradictory modifiers in generated compound names (e.g. synclow, apexlow, primelow)
                    if strategy == "COMPOUND":
                        from quality_engine.brand_refinement import CONTRADICTORY_MODIFIERS
                        if any(label.endswith(mod) and len(label) > len(mod) + 2 for mod in CONTRADICTORY_MODIFIERS):
                            continue

                    seen.add(label)
                    template = MorphologyClassifier.infer_template(label)
                    records.append({
                        "domain": domain,
                        "generation_strategy": strategy,
                        "generation_model": model,
                        "generator_model": model,
                        "generation_prompt_version": "v2.75b",
                        "semantic_concept": concept,
                        "source_concept": concept,
                        "source_category": category,
                        "market_category": category,
                        "source_keywords": keywords or [],
                        "naming_template": template,
                        "language": "en",
                        "generation_batch_id": active_batch_id,
                        "generation_timestamp": now_iso
                    })
        return records

    async def generate_one_word(
        self,
        concept: str,
        target_count: int = 50,
        category: str = "AI & Technology",
        keywords: Optional[List[str]] = None,
        batch_id: str = ""
    ) -> List[Dict[str, Any]]:
        """Strategy A: ONE_WORD"""
        prompt = f"""
You are an elite master domain naming strategist specializing in authentic ONE-WORD .com domains.
Theme/Concept: "{concept}"
Category: "{category}"

Generate high-potential ONE-WORD .com domains relevant to this concept.
Requirements:
1. Output authentic single-word opportunities:
   a) Rare, evocative, authentic single English words (nouns, verbs, adjectives from science, architecture, geology, botany, navigation: e.g. caldera, strata, tessera, spindle, spire, thalweg, solstice, paragon, meridian, fulcrum, bastion, zenith, keystone, cipher, haven, forge).
   b) Crisp, authentic dictionary words with strong metaphorical and commercial resonance.
   c) Classical/evocative Latin, Greek, Spanish, Italian, or Nordic single root words that exist as valid standalone terms (like Lumina, Novus, Velox, Tenor, Kumo, Sora, Solana, Prisma).
2. CRITICAL ANTI-SATURATION RULES:
   - DO NOT repeat prefixes like 'sdk*', 'agen*', 'auth*', 'flow*'.
   - DO NOT repeat synthetic suffixes like '*-lux', '*-vos', '*-vera', '*-vio', '*-ync'.
   - DO NOT output generic word-glue compounds (e.g. no 'clear+tether', 'firm+clause', 'bind+rule').
   - DO NOT output coined or invented brand names (e.g. no Figma, Canva, Zillow, Zapier) - this strategy is strictly for REAL SINGLE WORDS.
3. Every candidate MUST be a single clean word before .com.
4. Output {target_count} candidates as a comma-separated list of lowercase .com domains.
No numbering or markdown.
"""
        model_name = "router/domain_generation"
        try:
            raw_text = await self.router.execute_task("domain_generation", prompt, temperature=0.75, max_tokens=1200)
            candidates = self._clean_candidates(raw_text, "ONE_WORD", concept, model_name, category, keywords, batch_id)
        except Exception as e:
            logger.warning(f"AI ONE_WORD generation error: {e}, falling back to curated dictionary seeds")
            candidates = []

        # Algorithmic augmentation if needed with verified authentic one-words
        if len(candidates) < target_count // 2:
            from quality_engine.morphology_classifier import MorphologyClassifier
            from quality_engine.one_word_engine import OneWordQualityEngine
            one_word_engine = OneWordQualityEngine()
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            active_batch = batch_id or f"batch_{int(time.time())}"
            import random
            shuffled_seeds = list(HIGH_VALUE_ONE_WORDS)
            random.seed(42)
            random.shuffle(shuffled_seeds)
            for seed in shuffled_seeds:
                if len(candidates) >= target_count:
                    break
                is_dict, _ = one_word_engine.is_dictionary_word(seed)
                if not is_dict:
                    continue
                candidates.append({
                    "domain": f"{seed}.com",
                    "generation_strategy": "ONE_WORD",
                    "generation_model": "curated_lexical_engine",
                    "generator_model": "curated_lexical_engine",
                    "generation_prompt_version": "v2.75b",
                    "semantic_concept": concept,
                    "source_concept": concept,
                    "source_category": category,
                    "market_category": category,
                    "source_keywords": keywords or [],
                    "naming_template": MorphologyClassifier.infer_template(seed),
                    "language": "en",
                    "generation_batch_id": active_batch,
                    "generation_timestamp": now_iso
                })
        return candidates

    async def generate_compound(
        self,
        concept: str,
        target_count: int = 60,
        category: str = "AI & Technology",
        keywords: Optional[List[str]] = None,
        batch_id: str = ""
    ) -> List[Dict[str, Any]]:
        """Strategy B: COMPOUND"""
        prompt = f"""
You are a premier tech startup branding strategist.
Concept: "{concept}"
Category: "{category}"

Generate creative, premium COMPOUND .com domains formed by fusing two high-synergy words with natural brand rhythm (like Coinbase, DoorDash, Ironclad, Cloudflare, Datadog).
CRITICAL RULES:
1. STRICT ANTI-GLUE RULE: DO NOT generate generic adjective+noun or verb+noun word-glue (e.g. DO NOT produce clear+tether, firm+clause, bind+rule, dock+term, still+tether, citadel+pact).
2. STRICT ANTI-CONTRADICTORY RULE: DO NOT append negative or downgrade modifiers (e.g. low, down, less, off, slow, sub, under, dull). Domains like synclow, apexlow, primelow are strictly forbidden.
3. STRICT ANTI-SATURATION RULE: DO NOT repeat prefixes across candidates (e.g. max 1 domain starting with any given prefix).
4. Words must have natural semantic synergy, great rhythm, and balanced syllable lengths (under 12 characters total before .com).
5. Output {target_count} candidates as a comma-separated list of lowercase .com domains.
No numbering or markdown.
"""
        model_name = "router/domain_generation"
        try:
            raw_text = await self.router.execute_task("domain_generation", prompt, temperature=0.7, max_tokens=1400)
            candidates = self._clean_candidates(raw_text, "COMPOUND", concept, model_name, category, keywords, batch_id)
        except Exception as e:
            logger.warning(f"AI COMPOUND generation error: {e}")
            candidates = []

        # Algorithmic augmentation with strict anti-saturation (1 per word)
        if len(candidates) < target_count // 2:
            from quality_engine.morphology_classifier import MorphologyClassifier
            concept_words = [w.lower() for w in re.findall(r'[a-zA-Z]{4,}', concept)]
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            active_batch = batch_id or f"batch_{int(time.time())}"
            used_suffixes = list(CURATED_TECH_SUFFIXES)
            import random
            random.seed(99)
            random.shuffle(used_suffixes)
            for idx, w in enumerate(list(set(concept_words))[:8]):
                s = used_suffixes[idx % len(used_suffixes)]
                cand_label = f"{w}{s}"
                candidates.append({
                    "domain": f"{cand_label}.com",
                    "generation_strategy": "COMPOUND",
                    "generation_model": "compound_synergy_engine",
                    "generator_model": "compound_synergy_engine",
                    "generation_prompt_version": "v2.75b",
                    "semantic_concept": concept,
                    "source_concept": concept,
                    "source_category": category,
                    "market_category": category,
                    "source_keywords": keywords or [],
                    "naming_template": MorphologyClassifier.infer_template(cand_label),
                    "language": "en",
                    "generation_batch_id": active_batch,
                    "generation_timestamp": now_iso
                })
        return candidates

    async def generate_invented(
        self,
        concept: str,
        target_count: int = 50,
        category: str = "AI & Technology",
        keywords: Optional[List[str]] = None,
        batch_id: str = ""
    ) -> List[Dict[str, Any]]:
        """Strategy C: INVENTED (Neologisms & Blends) routed to canonical InventedBrandEngine"""
        cands = await self.multi_engine.invented_engine.generate(concept, category, count=target_count)
        active_batch = batch_id or f"batch_{int(time.time())}"
        from quality_engine.morphology_classifier import MorphologyClassifier
        for c in cands:
            label = c["domain"][:-4]
            c.setdefault("semantic_concept", concept)
            c.setdefault("source_keywords", keywords or [])
            c.setdefault("generation_model", c.get("generator_model", "invented_brand_engine"))
            c.setdefault("generation_prompt_version", "v2.75b")
            c.setdefault("naming_template", MorphologyClassifier.infer_template(label))
            c.setdefault("language", "en")
            c.setdefault("generation_batch_id", active_batch)
        return cands

    async def generate_semantic_brandable(
        self,
        concept: str,
        target_count: int = 50,
        category: str = "AI & Technology",
        keywords: Optional[List[str]] = None,
        batch_id: str = ""
    ) -> List[Dict[str, Any]]:
        """Strategy D: SEMANTIC_BRANDABLE (Metaphorical / Evocative)"""
        prompt = f"""
You are a creative naming director for Fortune 500 tech ventures.
Concept: "{concept}"
Category: "{category}"

Generate evocative SEMANTIC BRANDABLE .com domains that use metaphor, emotional resonance, and abstract concepts.
Examples: BlueShift.com, IronClad.com, TrueNorth.com, ApexLogic.com, ClearScope.com, DeepCurrent.com.
Requirements:
1. Strong imagery and memorable metaphorical meaning.
2. CRITICAL ANTI-SATURATION RULES:
   - Prohibit repeating prefixes across candidates.
   - Prohibit word-glue compounds (no dockterm, bindrule, stilltether).
3. Output {target_count} candidates as a comma-separated list of lowercase .com domains.
No numbering or markdown.
"""
        model_name = "router/domain_generation"
        try:
            raw_text = await self.router.execute_task("domain_generation", prompt, temperature=0.75, max_tokens=1200)
            candidates = self._clean_candidates(raw_text, "SEMANTIC_BRANDABLE", concept, model_name, category, keywords, batch_id)
        except Exception as e:
            logger.warning(f"AI SEMANTIC_BRANDABLE generation error: {e}")
            candidates = []
        return candidates

    async def generate_keyword_brandable(
        self,
        concept: str,
        target_count: int = 40,
        category: str = "AI & Technology",
        keywords: Optional[List[str]] = None,
        batch_id: str = ""
    ) -> List[Dict[str, Any]]:
        """Strategy E: KEYWORD_BRANDABLE (Anchor keyword + premium affixes)"""
        prompt = f"""
You are a domain investment and brand positioning strategist.
Concept: "{concept}"
Category: "{category}"

Generate KEYWORD BRANDABLE .com domain names combining a clear industry anchor with a brandable tech affix.
CRITICAL RULES:
1. DO NOT repeat the same prefix across candidates (e.g. no sdkura, sdkloom, sdkgrid, sdkwave; max ONE candidate starting with any prefix).
2. Use crisp, high-prestige affixes with natural phonetic balance.
3. Output {target_count} candidates as a comma-separated list of lowercase .com domains.
No numbering or markdown.
"""
        model_name = "router/domain_generation"
        try:
            raw_text = await self.router.execute_task("domain_generation", prompt, temperature=0.7, max_tokens=1000)
            candidates = self._clean_candidates(raw_text, "KEYWORD_BRANDABLE", concept, model_name, category, keywords, batch_id)
        except Exception as e:
            logger.warning(f"AI KEYWORD_BRANDABLE generation error: {e}")
            candidates = []
        return candidates

    async def generate_trend_based(
        self,
        concept: str,
        target_count: int = 50,
        category: str = "AI & Technology",
        keywords: Optional[List[str]] = None,
        batch_id: str = ""
    ) -> List[Dict[str, Any]]:
        """Strategy F: TREND_BASED (Tied to real-time market movements)"""
        prompt = f"""
You are a frontier technology analyst and venture scout.
Concept: "{concept}"
Category: "{category}"

Generate forward-looking TREND-BASED .com domain candidates that capture the cutting-edge market momentum of this concept.
Focus on emerging paradigms (autonomous intelligence, decentralized rails, spatial computing, green energy compute).
Requirements:
1. Fresh, modern, future-proof naming with diverse structural morphologies.
2. Output {target_count} candidates as a comma-separated list of lowercase .com domains.
No numbering or markdown.
"""
        model_name = "router/domain_generation"
        try:
            raw_text = await self.router.execute_task("domain_generation", prompt, temperature=0.75, max_tokens=1200)
            candidates = self._clean_candidates(raw_text, "TREND_BASED", concept, model_name, category, keywords, batch_id)
        except Exception as e:
            logger.warning(f"AI TREND_BASED generation error: {e}")
            candidates = []
        return candidates

    async def generate_prefix_suffix(
        self,
        concept: str,
        target_count: int = 50,
        category: str = "AI & Technology",
        keywords: Optional[List[str]] = None,
        batch_id: str = ""
    ) -> List[Dict[str, Any]]:
        """Strategy G: PREFIX_SUFFIX"""
        return await self.multi_engine.prefix_suffix_engine.generate(concept, category, count=target_count)

    async def generate_all_strategies(
        self,
        concepts: Any,
        target_total: int = 1500,
        strategy_stats: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Executes all 7 naming strategies across concepts, ensuring dynamic refill if any strategy underperforms.
        Supports both string concepts and rich concept dictionaries with full traceability.
        For large target budgets (>= 500), delegates to MultiEngineOrchestrator to produce 1500-3000 candidates
        with dynamically balanced quotas across ONE_WORD, INVENTED, SEMANTIC, COMPOUND, PREFIX_SUFFIX, TREND, KEYWORD_BRANDABLE.
        """
        # Ensure concepts is a list
        concept_list = concepts if isinstance(concepts, list) else [concepts]

        if target_total >= 500:
            logger.info(f"[STRATEGY-GEN] Delegating to MultiEngineOrchestrator (Target Total: {target_total})...")
            return await self.multi_engine.generate_all(concept_list, target_total=target_total, strategy_stats=strategy_stats)

        all_candidates: List[Dict[str, Any]] = []
        seen_domains: Set[str] = set()
        active_batch_id = f"batch_{int(time.time())}"

        for concept_entry in concept_list:
            if isinstance(concept_entry, dict):
                concept_text = concept_entry.get("concept", "")
                category = concept_entry.get("category", "AI & Technology")
                keywords = concept_entry.get("keywords", [])
            else:
                concept_text = str(concept_entry)
                category = "AI & Technology"
                keywords = []

            logger.info(f"[STRATEGY-GEN] Generating multi-strategy candidates for: '{concept_text}' ({category})")
            
            # Execute all naming strategies concurrently for maximum throughput & error isolation
            strategy_tasks = [
                self.generate_one_word(concept_text, target_count=50, category=category, keywords=keywords, batch_id=active_batch_id),
                self.generate_compound(concept_text, target_count=60, category=category, keywords=keywords, batch_id=active_batch_id),
                self.generate_invented(concept_text, target_count=50, category=category, keywords=keywords, batch_id=active_batch_id),
                self.generate_semantic_brandable(concept_text, target_count=50, category=category, keywords=keywords, batch_id=active_batch_id),
                self.generate_keyword_brandable(concept_text, target_count=40, category=category, keywords=keywords, batch_id=active_batch_id),
                self.generate_trend_based(concept_text, target_count=50, category=category, keywords=keywords, batch_id=active_batch_id),
                self.generate_prefix_suffix(concept_text, target_count=40, category=category, keywords=keywords, batch_id=active_batch_id)
            ]
            results = await asyncio.gather(*strategy_tasks, return_exceptions=True)

            for strat_result in results:
                if isinstance(strat_result, list):
                    for item in strat_result:
                        d = item["domain"]
                        if d not in seen_domains:
                            seen_domains.add(d)
                            all_candidates.append(item)
                elif isinstance(strat_result, Exception):
                    logger.warning(f"[STRATEGY-GEN] Strategy failed with exception: {strat_result}")

        # Dynamic refill check
        strategy_counts = {}
        for c in all_candidates:
            strat = c["generation_strategy"]
            strategy_counts[strat] = strategy_counts.get(strat, 0) + 1

        logger.info(f"[STRATEGY-GEN] Raw generated distribution across strategies: {strategy_counts} (Total: {len(all_candidates)})")
        return all_candidates
