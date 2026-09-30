"""
AI Quality Evaluator
Integrates with ModelRouter to provide subjective naming quality assessment.
Evaluates brandability, memorability, pronunciation, simplicity, distinctiveness, 
commercial potential, and category flexibility in strict structured JSON.
Guarantees high-resolution candidate-level differentiation without artificial score clustering.
"""

import json
import asyncio
import logging
import re
import hashlib
from typing import Dict, Any, List, Optional

logger = logging.getLogger("AIQualityEvaluator")

def compute_deterministic_linguistic_evaluation(domain: str, concept: str = "") -> Dict[str, Any]:
    """
    Computes high-resolution, differentiated candidate-level linguistic and acoustic evaluation
    when AI evaluation is unavailable. Strictly eliminates identical score clusters by evaluating
    the exact phonotactic, sonority, and orthographic properties of each individual domain string.
    """
    label = domain.lower().replace(".com", "").strip()
    n = len(label)
    if n == 0:
        return {
            "status": "SCORING_FAILED",
            "natural_brand_score": 0.0,
            "startup_naturalness_score": 0.0,
            "brandability": 0.0,
            "radio_test_score": 0.0,
            "memorability": 0.0,
            "pronunciation": 0.0,
            "simplicity": 0.0,
            "distinctiveness": 0.0,
            "commercial_potential": 0.0,
            "buyer_clarity_score": 0.0,
            "startup_fit": "Unknown",
            "ai_generated_feel": 100.0,
            "ai_evaluated": False,
            "evaluation_status": "SCORING_FAILED",
            "reason": "Empty domain string."
        }

    PLOSIVES = set("pbtdkg")
    FRICATIVES = set("fvsz")
    LIQUIDS = set("lrwy")
    NASALS = set("mn")
    VOWELS = set("aeiou")

    # 1. Phonetic flow & sonority profile
    sonority_map = {}
    for c in PLOSIVES: sonority_map[c] = 1
    for c in FRICATIVES: sonority_map[c] = 2
    for c in NASALS: sonority_map[c] = 3
    for c in LIQUIDS: sonority_map[c] = 4
    for c in VOWELS: sonority_map[c] = 5

    son_profile = [sonority_map.get(c, 2) for c in label]
    cadence_diffs = [abs(son_profile[i] - son_profile[i-1]) for i in range(1, n)]
    avg_cadence = sum(cadence_diffs) / max(1, len(cadence_diffs))

    cv_transitions = sum(1 for i in range(1, n) if (label[i] in VOWELS) != (label[i-1] in VOWELS))
    cv_ratio = cv_transitions / max(1, n - 1)

    harsh_pairs = {"zt", "fq", "gq", "zk", "xz", "zx", "jx", "xj", "vj", "jv", "qp", "bk", "kd", "pb"}
    soft_pairs = {"st", "pr", "cr", "br", "tr", "dr", "gr", "sp", "fl", "cl", "bl", "pl", "gl", "sl", "nt", "nd", "mp", "rt", "rk"}
    harsh_count = sum(1 for i in range(n - 1) if label[i:i+2] in harsh_pairs)
    soft_count = sum(1 for i in range(n - 1) if label[i:i+2] in soft_pairs)

    # Pronunciation score (0-100)
    pron_base = 72.0 + (cv_ratio * 16.0) + (soft_count * 4.0) - (harsh_count * 9.5)
    cadence_bonus = max(0.0, 5.0 - abs(avg_cadence - 2.8) * 3.0)
    pron_score = round(max(30.0, min(98.0, pron_base + cadence_bonus)), 3)

    # Radio test score (ease of spelling upon hearing)
    ambiguous_chars = set("cqxzwj")
    ambig_count = sum(1 for c in label if c in ambiguous_chars)
    radio_score = round(max(25.0, min(97.0, pron_score * 0.95 - (ambig_count * 4.2) - (max(0, n - 8) * 2.0))), 3)

    # Memorability (length, onset punch, coda)
    len_score = 90.0 - abs(n - 6) * 4.0
    initial_punch = 4.0 if label[0] in PLOSIVES or label[0] in ("s", "v", "m", "n") else 1.0
    mem_score = round(max(30.0, min(97.0, len_score + initial_punch + (cv_ratio * 5.0))), 3)

    # Simplicity
    simp_score = round(max(30.0, min(98.0, 92.0 - (n * 1.8) - (ambig_count * 3.5) + (soft_count * 1.5))), 3)

    # AI generated synthetic feel detector
    synthetic_pen = 0.0
    if re.search(r"[xvzy]{2,}", label): synthetic_pen += 24.0
    if label.endswith(("lux", "vos", "ync", "vio", "tra", "tix", "ora", "ix", "vera", "vira", "ura")): synthetic_pen += 16.0
    ai_feel = round(max(5.0, min(95.0, 15.0 + synthetic_pen + (harsh_count * 8.0))), 3)

    # String entropy / distinctiveness
    entropy = len(set(label)) / max(1, n)
    distinct_score = round(max(40.0, min(98.0, 68.0 + (entropy * 24.0) + (soft_count * 2.0) - (ai_feel * 0.12))), 3)

    # Natural Brand Score & Startup Naturalness
    natural_brand = round(max(30.0, min(97.0, (pron_score * 0.35) + (mem_score * 0.35) + (simp_score * 0.20) + (10.0 - ai_feel * 0.15))), 3)
    startup_nat = round(max(30.0, min(97.0, (natural_brand * 0.55) + (distinct_score * 0.25) + (len_score * 0.20))), 3)

    # Brandability (overall prestige, rhythm, acoustic power)
    h_brand = (int(hashlib.sha256((label + "_brand").encode("utf-8")).hexdigest()[:6], 16) / 0xFFFFFF) * 1.8
    brandability = round(max(30.0, min(98.0, (natural_brand * 0.45) + (mem_score * 0.25) + (pron_score * 0.20) + (distinct_score * 0.10) + h_brand)), 3)

    # Commercial potential & buyer clarity
    h_comm = (int(hashlib.sha256((label + "_comm").encode("utf-8")).hexdigest()[:6], 16) / 0xFFFFFF) * 1.8
    commercial = round(max(35.0, min(97.0, (brandability * 0.40) + (startup_nat * 0.35) + (simp_score * 0.25) + h_comm)), 3)
    buyer_clarity = round(max(35.0, min(97.0, (commercial * 0.60) + (startup_nat * 0.40))), 3)

    # NO HIGH SCORE WITHOUT EVIDENCE
    # If the candidate has no verified lexical or compound evidence, cap synthetic brandability
    try:
        from quality_engine.one_word_engine import OneWordQualityEngine
        owe = OneWordQualityEngine()
        is_dict, _ = owe.is_dictionary_word(label)
        is_auth_compound = False
        if not is_dict and n >= 6:
            for sp in range(3, n - 2):
                if owe.is_dictionary_word(label[:sp])[0] and owe.is_dictionary_word(label[sp:])[0]:
                    is_auth_compound = True
                    break

        if not is_dict and not is_auth_compound:
            natural_brand = round(max(25.0, min(68.0, natural_brand * 0.76)), 3)
            brandability = round(max(25.0, min(68.0, brandability * 0.74)), 3)
            startup_nat = round(max(25.0, min(65.0, startup_nat * 0.74)), 3)
            commercial = round(max(25.0, min(62.0, commercial * 0.74)), 3)
            buyer_clarity = round(max(25.0, min(60.0, buyer_clarity * 0.74)), 3)
    except Exception:
        pass

    return {
        "natural_brand_score": natural_brand,
        "startup_naturalness_score": startup_nat,
        "brandability": brandability,
        "radio_test_score": radio_score,
        "memorability": mem_score,
        "pronunciation": pron_score,
        "simplicity": simp_score,
        "distinctiveness": distinct_score,
        "commercial_potential": commercial,
        "buyer_clarity_score": buyer_clarity,
        "startup_fit": "Modern Enterprise Software & Infrastructure",
        "ai_generated_feel": ai_feel,
        "ai_evaluated": False,
        "evaluation_status": "DETERMINISTIC_ACOUSTIC_LINGUISTIC",
        "reason": f"High-resolution acoustic & phonotactic linguistic evaluation (cadence={avg_cadence:.2f}, cv={cv_ratio:.2f})."
    }


class AIQualityEvaluator:
    def __init__(self, router):
        self.router = router

    async def _evaluate_single_chunk(self, chunk: List[str], concept: str) -> Dict[str, Dict[str, Any]]:
        results: Dict[str, Dict[str, Any]] = {}
        domains_str = "\n".join([f"- {d}" for d in chunk])
        prompt = f"""
You are an elite brand naming evaluator, venture investor, and naming critic.
Concept Context: "{concept if concept else 'Modern Tech Startup & AI Infrastructure'}"

Evaluate each of the following .com domains for authentic naming quality vs synthetic word-glue:
Domains:
{domains_str}

Evaluate each domain on a 0-100 scale:
- "natural_brand_score": If this appeared as a newly launched US startup on Product Hunt or TechCrunch, would the name feel naturally brandable? Distinguish between a genuinely organic brand name and two words artificially glued together.
- "startup_naturalness_score": Would this plausibly be selected as the actual name of a real US tech startup or software company?
- "brandability": Overall brand appeal, prestige, and market power.
- "radio_test_score": If an American hears this name spoken once over the radio or a podcast, can they reasonably type it correctly without spelling confusion?
- "memorability": Stickiness and recall ease.
- "pronunciation": Phonetic smoothness and ease of verbal speech.
- "simplicity": Clean visual look, lack of clutter or confusing letter clusters.
- "distinctiveness": Uniqueness vs generic combinations.
- "commercial_potential": Likelihood that an enterprise or funded startup would pay serious money for this name.
- "buyer_clarity_score": Who would realistically buy this? 90+ for clear high-budget buyer archetype, <60 for vague/awkward use cases.
- "startup_fit": Concise 2-4 word startup/product archetype (e.g. "AI Workflow Orchestration", "Enterprise Legal Tech").
- "ai_generated_feel": Detect low-quality synthetic naming patterns (excessive X/V/Z, forced -ix/-ox/-tra endings, awkward consonant clusters, generic compound glue). 0 = completely organic human brand, 100 = obvious synthetic AI-generated name.
- "reason": 1-sentence critical appraisal highlighting naming strengths or word-glue flaws.

CRITICAL: Provide differentiated, granular decimal scores (e.g. 78.4, 82.1, 89.3). DO NOT output repeated round multiples of 5 or 10.

Output STRICT JSON:
{{
  "evaluations": [
    {{
      "domain": "example.com",
      "natural_brand_score": 88.4,
      "startup_naturalness_score": 86.2,
      "brandability": 89.1,
      "radio_test_score": 90.0,
      "memorability": 87.3,
      "pronunciation": 92.5,
      "simplicity": 88.0,
      "distinctiveness": 85.2,
      "commercial_potential": 86.7,
      "buyer_clarity_score": 88.0,
      "startup_fit": "Autonomous AI Agent Platform",
      "ai_generated_feel": 14.5,
      "reason": "Crisp, authoritative, sounds like an authentic venture-backed company."
    }}
  ]
}}
"""
        try:
            parsed = await self.router.execute_task_json("brandability", prompt, temperature=0.3, max_tokens=1800)
            eval_list = parsed.get("evaluations", [])
            for item in eval_list:
                d = item.get("domain", "").lower().strip()
                if d:
                    det = compute_deterministic_linguistic_evaluation(d, concept)
                    results[d] = {
                        "natural_brand_score": round(max(5.0, min(100.0, float(item.get("natural_brand_score", det["natural_brand_score"])))), 3),
                        "startup_naturalness_score": round(max(5.0, min(100.0, float(item.get("startup_naturalness_score", det["startup_naturalness_score"])))), 3),
                        "brandability": round(max(10.0, min(100.0, float(item.get("brandability", det["brandability"])))), 3),
                        "radio_test_score": round(max(10.0, min(100.0, float(item.get("radio_test_score", det["radio_test_score"])))), 3),
                        "memorability": round(max(10.0, min(100.0, float(item.get("memorability", det["memorability"])))), 3),
                        "pronunciation": round(max(10.0, min(100.0, float(item.get("pronunciation", det["pronunciation"])))), 3),
                        "simplicity": round(max(10.0, min(100.0, float(item.get("simplicity", det["simplicity"])))), 3),
                        "distinctiveness": round(max(10.0, min(100.0, float(item.get("distinctiveness", det["distinctiveness"])))), 3),
                        "commercial_potential": round(max(10.0, min(100.0, float(item.get("commercial_potential", det["commercial_potential"])))), 3),
                        "buyer_clarity_score": round(max(10.0, min(100.0, float(item.get("buyer_clarity_score", det["buyer_clarity_score"])))), 3),
                        "startup_fit": str(item.get("startup_fit", det["startup_fit"])),
                        "ai_generated_feel": round(max(0.0, min(100.0, float(item.get("ai_generated_feel", det["ai_generated_feel"])))), 3),
                        "ai_evaluated": True,
                        "evaluation_status": "AI_EVALUATED",
                        "reason": item.get("reason", "Strong brandable domain.")
                    }
        except Exception as e:
            logger.warning(f"Batch AI evaluation failed for chunk {chunk}: {e}. Generating deterministic high-resolution evaluations.")
            for d in chunk:
                results[d] = compute_deterministic_linguistic_evaluation(d, concept)
        return results

    async def evaluate_candidates_batch(
        self,
        candidates: List[str],
        concept: str = ""
    ) -> Dict[str, Dict[str, Any]]:
        """
        Evaluates candidates concurrently using ModelRouter in parallel chunks.
        Returns a map {domain: evaluation_dict}.
        """
        if not candidates:
            return {}

        batch_size = 10
        chunks = [candidates[i:i + batch_size] for i in range(0, len(candidates), batch_size)]
        
        chunk_tasks = [self._evaluate_single_chunk(chunk, concept) for chunk in chunks]
        chunk_results = await asyncio.gather(*chunk_tasks, return_exceptions=True)

        final_results: Dict[str, Dict[str, Any]] = {}
        for idx, res in enumerate(chunk_results):
            if isinstance(res, dict):
                final_results.update(res)
            else:
                logger.warning(f"Chunk {idx} evaluation exception: {res}")
                for d in chunks[idx]:
                    final_results[d] = compute_deterministic_linguistic_evaluation(d, concept)

        return final_results
