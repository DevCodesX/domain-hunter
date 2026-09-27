"""
Pattern Saturation & Run-Level Diversity Engine
Detects structural saturation within a generation run:
- Repeated prefixes (e.g. sdk*, agen*, cap*, mas*, tax*, remit*)
- Repeated suffixes (e.g. *-ync, *-lux, *-vio, *-loom, *-grid, *-wave)
- Repeated stems and morphemes
- Naming template saturation

Calculates prefix_frequency, suffix_frequency, stem_frequency, pattern_frequency,
and computes pattern_diversity_score (0-100) to penalize overrepresented patterns.
"""

import re
from typing import Dict, List, Tuple, Any, Set
from collections import Counter


class PatternSaturationDetector:
    """
    Analyzes an entire pool of generated candidates for a run,
    extracts structural affixes and morphemes, and calculates
    saturation statistics and per-candidate diversity penalties.
    """

    # Common recognized tech/business prefixes of 2 to 5 characters
    COMMON_TECH_PREFIXES = {
        "sdk", "api", "dev", "ops", "rev", "fin", "tax", "pay", "bio",
        "bot", "app", "web", "net", "sys", "geo", "doc", "law", "med",
        "agen", "flow", "data", "code", "sync", "mesh", "node", "core",
        "flex", "beam", "cast", "loom", "grid", "wave", "volt", "flux",
        "omni", "meta", "poly", "auto", "tele", "hyper", "super", "micro"
    }

    # Common suffixes of 2 to 5 characters
    COMMON_TECH_SUFFIXES = {
        "sync", "grid", "flow", "loom", "wave", "mesh", "node", "core",
        "rail", "line", "path", "cast", "beam", "link", "hive", "port",
        "base", "dock", "post", "gate", "mind", "pulse", "craft", "forge",
        "lux", "vio", "vos", "ync", "lix", "rix", "vix", "qor", "tra",
        "ura", "ora", "ira", "era", "ara", "ex", "ix", "ox", "io", "ia",
        "vera", "vira"
    }

    @classmethod
    def extract_affixes(cls, domain_or_label: str) -> Dict[str, Any]:
        """
        Extracts prefixes, suffixes, and morphemes from a domain name.
        """
        label = domain_or_label.lower().replace(".com", "").strip()
        length = len(label)

        # Detect prefix (check 4, 3, 5, 2 char lengths)
        detected_prefix = ""
        for p_len in (4, 3, 5, 2):
            cand_p = label[:p_len]
            if cand_p in cls.COMMON_TECH_PREFIXES:
                detected_prefix = cand_p
                break

        # Detect suffix (check 4, 3, 5, 2 char lengths from right)
        detected_suffix = ""
        for s_len in (4, 3, 5, 2):
            cand_s = label[-s_len:]
            if cand_s in cls.COMMON_TECH_SUFFIXES:
                detected_suffix = cand_s
                break

        # Stem is remainder
        stem = label
        if detected_prefix and label.startswith(detected_prefix):
            stem = stem[len(detected_prefix):]
        if detected_suffix and stem.endswith(detected_suffix) and len(stem) > len(detected_suffix):
            stem = stem[:-len(detected_suffix)]

        # Classify template archetype
        if detected_prefix and detected_suffix and len(label) > (len(detected_prefix) + len(detected_suffix)):
            template = f"PREFIX_{detected_prefix.upper()}+SUFFIX_{detected_suffix.upper()}"
        elif detected_prefix:
            template = f"PREFIX_{detected_prefix.upper()}+STEM"
        elif detected_suffix:
            template = f"STEM+SUFFIX_{detected_suffix.upper()}"
        else:
            template = "UNIFIED_ROOT"

        return {
            "label": label,
            "prefix": detected_prefix,
            "suffix": detected_suffix,
            "stem": stem if stem else label,
            "template": template
        }

    @classmethod
    def analyze_run_saturation(cls, candidates: List[Any]) -> Dict[str, Any]:
        """
        Analyzes the full pool of candidates in a generation run.
        Computes frequencies across all candidates.
        """
        def get_name(c):
            if isinstance(c, dict):
                return c.get("domain_name") or c.get("domain", "")
            return getattr(c, "domain_name", getattr(c, "domain", str(c)))

        affix_records = []
        prefix_counter = Counter()
        suffix_counter = Counter()
        stem_counter = Counter()
        template_counter = Counter()

        for cand in candidates:
            name = get_name(cand)
            extracted = cls.extract_affixes(name)
            affix_records.append(extracted)

            if extracted["prefix"]:
                prefix_counter[extracted["prefix"]] += 1
            if extracted["suffix"]:
                suffix_counter[extracted["suffix"]] += 1
            if extracted["stem"] and len(extracted["stem"]) >= 3:
                stem_counter[extracted["stem"]] += 1
            template_counter[extracted["template"]] += 1

        total = max(1, len(candidates))

        run_stats = {
            "total_candidates": total,
            "prefix_counts": dict(prefix_counter.most_common(20)),
            "suffix_counts": dict(suffix_counter.most_common(20)),
            "stem_counts": dict(stem_counter.most_common(20)),
            "template_counts": dict(template_counter.most_common(20)),
            "prefix_frequencies": {k: v / total for k, v in prefix_counter.items()},
            "suffix_frequencies": {k: v / total for k, v in suffix_counter.items()},
            "top_prefixes": prefix_counter.most_common(10),
            "top_suffixes": suffix_counter.most_common(10),
            "records": affix_records
        }

        # Calculate candidate saturation mapping for immediate O(1) lookup
        cand_saturation = {}
        for cand in candidates:
            c_name = get_name(cand)
            c_label = c_name.lower().replace(".com", "").strip()
            eval_res = cls.evaluate_candidate_diversity(c_label, run_stats)
            cand_saturation[c_label] = {
                "prefix_freq": eval_res["prefix_frequency"],
                "suffix_freq": eval_res["suffix_frequency"],
                "stem_freq": eval_res["stem_frequency"],
                "pattern_freq": eval_res["pattern_frequency"],
                "pattern_diversity_score": eval_res["pattern_diversity_score"],
                "prefix": eval_res["prefix"],
                "suffix": eval_res["suffix"],
                "is_saturated": eval_res["is_saturated"],
                "reasons": eval_res["reasons"]
            }
            cand_saturation[c_name] = cand_saturation[c_label]

        run_stats["candidate_saturation"] = cand_saturation
        return run_stats

    @classmethod
    def evaluate_candidate_diversity(
        cls,
        domain_or_label: str,
        run_stats: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Evaluates a single candidate within the context of the run.
        Calculates prefix_frequency, suffix_frequency, stem_frequency, pattern_frequency,
        and computes pattern_diversity_score (0-100).
        """
        extracted = cls.extract_affixes(domain_or_label)
        p = extracted["prefix"]
        s = extracted["suffix"]
        stem = extracted["stem"]
        tmpl = extracted["template"]

        p_count = run_stats.get("prefix_counts", {}).get(p, 1) if p else 1
        s_count = run_stats.get("suffix_counts", {}).get(s, 1) if s else 1
        stem_count = run_stats.get("stem_counts", {}).get(stem, 1) if stem else 1
        tmpl_count = run_stats.get("template_counts", {}).get(tmpl, 1)

        total = max(1, run_stats.get("total_candidates", 1))

        # Base diversity score starts at 100
        score = 100.0
        reasons: List[str] = []

        # Progressive penalty for prefix saturation
        # If prefix appears > 1 time, penalize based on count
        if p and p_count >= 2:
            p_penalty = min(35.0, (p_count - 1) * 7.5)
            score -= p_penalty
            reasons.append(f"Prefix '{p}' saturated in run ({p_count} occurrences, -{p_penalty:.1f} pts)")

        # Progressive penalty for suffix saturation
        if s and s_count >= 2:
            s_penalty = min(25.0, (s_count - 1) * 5.0)
            score -= s_penalty
            reasons.append(f"Suffix '{s}' saturated in run ({s_count} occurrences, -{s_penalty:.1f} pts)")

        # Severe penalty for stem repetition
        if stem and stem_count >= 2:
            stem_penalty = min(30.0, (stem_count - 1) * 12.0)
            score -= stem_penalty
            reasons.append(f"Stem '{stem}' repeated ({stem_count} occurrences, -{stem_penalty:.1f} pts)")

        # Template saturation penalty
        if tmpl_count >= 3 and tmpl != "UNIFIED_ROOT":
            tmpl_penalty = min(20.0, (tmpl_count - 2) * 4.0)
            score -= tmpl_penalty
            reasons.append(f"Template '{tmpl}' overused in run ({tmpl_count} occurrences, -{tmpl_penalty:.1f} pts)")

        final_score = round(max(15.0, min(100.0, score)), 2)

        return {
            "pattern_diversity_score": final_score,
            "prefix_frequency": p_count,
            "suffix_frequency": s_count,
            "stem_frequency": stem_count,
            "pattern_frequency": tmpl_count,
            "prefix": p,
            "suffix": s,
            "stem": stem,
            "naming_template": tmpl,
            "is_saturated": final_score < 75.0,
            "reasons": reasons
        }
