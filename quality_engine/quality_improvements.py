import copy
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from quality_engine.config import (
    CLICHE_BASE_PENALTY,
    CLICHE_REPEAT_PENALTY_STEP,
    CLICHE_SUFFIX_ROOTS,
    FINAL_ROOT_CAP_TIER_A,
    FINAL_ROOT_CAP_TIER_AB,
    KNOWN_PREFIXES,
    KNOWN_SUFFIXES,
    MAX_CANDIDATE_LENGTH,
    MAX_COMPOUND_ROOTS,
    PHONOTACTIC_BAD_BIGRAMS,
    PHONOTACTIC_BAD_TRIGRAMS,
    PHONOTACTIC_MINIMUM_AVERAGE_SCORE,
    PHONOTACTIC_MINIMUM_WEAKEST_SCORE,
    RECOGNIZED_SEMANTIC_ROOTS,
    SEMANTIC_ROOT_BONUS
)

_ROOT_LEXICON = sorted(
    {
        *RECOGNIZED_SEMANTIC_ROOTS,
        *KNOWN_PREFIXES,
        *KNOWN_SUFFIXES,
        "cloud",
        "nest",
        "trend",
        "alpha",
        "index",
        "flow",
        "stack",
        "data",
        "bridge",
        "signal",
        "point"
    },
    key=len,
    reverse=True
)

_UNNATURAL_ENDINGS = {"kn", "qn", "vn", "fq", "wz", "okn", "skn"}


def extract_label(domain_or_label: str) -> str:
    value = (domain_or_label or "").strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = re.sub(r"^www\.", "", value)
    value = value.split("/")[0].split(":")[0]
    if "." in value:
        value = value.split(".")[0]
    return value


def canonicalize_domain(domain_or_label: str) -> str:
    label = extract_label(domain_or_label)
    try:
        ascii_label = label.encode("idna").decode("ascii")
    except Exception:
        ascii_label = label
    if not ascii_label:
        return ""
    return f"{ascii_label}.com"


def _count_root_segments(label: str) -> int:
    if not label:
        return 0

    best: Dict[int, int] = {0: 0}
    for idx in range(len(label)):
        if idx not in best:
            continue
        for token in _ROOT_LEXICON:
            if label.startswith(token, idx):
                end = idx + len(token)
                count = best[idx] + 1
                if end not in best or count < best[end]:
                    best[end] = count
    return best.get(len(label), 1)


def passes_candidate_assembly(label: str) -> Tuple[bool, Optional[str], int]:
    clean = extract_label(label)
    root_count = _count_root_segments(clean)

    if len(clean) > MAX_CANDIDATE_LENGTH:
        return False, "candidate_exceeds_shared_length_cap", root_count
    if root_count > MAX_COMPOUND_ROOTS:
        return False, "candidate_exceeds_max_root_count", root_count
    return True, None, root_count


def detect_cliche_suffix(label: str) -> Optional[str]:
    clean = extract_label(label)
    for suffix in sorted(CLICHE_SUFFIX_ROOTS, key=len, reverse=True):
        if clean.endswith(suffix) and len(clean) > len(suffix):
            return suffix
    return None


def detect_semantic_root(label: str) -> Optional[str]:
    clean = extract_label(label)
    matches = [
        root for root in sorted(RECOGNIZED_SEMANTIC_ROOTS, key=len, reverse=True)
        if root in clean
    ]
    return matches[0] if matches else None


def compute_phonotactic_naturalness(label: str) -> Dict[str, Any]:
    clean = extract_label(label)
    if len(clean) < 2:
        return {
            "average_score": 0.0,
            "weakest_transition": 0.0,
            "passes_threshold": False,
            "flagged_transitions": ["too_short"]
        }

    transition_scores: List[float] = []
    flagged: List[str] = []

    for i in range(len(clean) - 1):
        bigram = clean[i:i + 2]
        score = PHONOTACTIC_BAD_BIGRAMS.get(bigram, 1.0)
        transition_scores.append(score)
        if score < 0.4:
            flagged.append(bigram)

    for i in range(len(clean) - 2):
        trigram = clean[i:i + 3]
        score = PHONOTACTIC_BAD_TRIGRAMS.get(trigram, 1.0)
        transition_scores.append(score)
        if score < 0.4:
            flagged.append(trigram)

    if clean.endswith(tuple(_UNNATURAL_ENDINGS)):
        transition_scores.append(0.05)
        flagged.append(f"ending:{clean[-3:]}")

    if "q" in clean and "qu" not in clean:
        transition_scores.append(0.02)
        flagged.append("q_without_u")

    average = sum(transition_scores) / max(1, len(transition_scores))
    weakest = min(transition_scores) if transition_scores else 1.0
    passes = average >= PHONOTACTIC_MINIMUM_AVERAGE_SCORE and weakest >= PHONOTACTIC_MINIMUM_WEAKEST_SCORE

    return {
        "average_score": round(average, 3),
        "weakest_transition": round(weakest, 3),
        "passes_threshold": passes,
        "flagged_transitions": flagged
    }


class BatchClicheTracker:
    @staticmethod
    def apply_penalties(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        suffix_counts: Dict[str, int] = {}
        updated: List[Dict[str, Any]] = []

        for candidate in candidates:
            item = copy.deepcopy(candidate)
            label = extract_label(item.get("domain") or item.get("domain_name", ""))
            suffix = detect_cliche_suffix(label)
            base_penalty = CLICHE_BASE_PENALTY if suffix else 0.0

            repeat_penalty = 0.0
            if suffix:
                suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
                repeat_penalty = max(0.0, (suffix_counts[suffix] - 1) * CLICHE_REPEAT_PENALTY_STEP)

            total_penalty = base_penalty + repeat_penalty
            if total_penalty > 0:
                overall = float(item.get("overall_score") or item.get("quality_score") or 0.0)
                item["overall_score"] = round(max(5.0, overall - total_penalty), 3)
                item["quality_score"] = int(round(item["overall_score"]))
                qb = item.get("quality_breakdown")
                if isinstance(qb, dict):
                    qb["cliche_suffix_penalty"] = int(round(total_penalty))
                    qb.setdefault("_float_scores", {})
                    qb["_float_scores"]["overall_score"] = item["overall_score"]

            item["cliche_suffix"] = suffix
            item["cliche_suffix_penalty"] = round(total_penalty, 2)
            item["cliche_repeat_penalty"] = round(repeat_penalty, 2)
            updated.append(item)

        return updated


class AffixFrequencyTracker:
    @staticmethod
    def extract_signatures(candidate: Dict[str, Any]) -> Dict[str, str]:
        label = extract_label(candidate.get("domain") or candidate.get("domain_name", ""))
        suffix = detect_cliche_suffix(label)
        if not suffix:
            for known_suffix in sorted(KNOWN_SUFFIXES, key=len, reverse=True):
                if label.endswith(known_suffix) and len(label) > len(known_suffix):
                    suffix = known_suffix
                    break

        prefix = ""
        for known_prefix in sorted(KNOWN_PREFIXES, key=len, reverse=True):
            if label.startswith(known_prefix) and len(label) > len(known_prefix):
                prefix = known_prefix
                break

        root = label
        if suffix and len(label) > len(suffix):
            root = label[:-len(suffix)]
        elif prefix and len(label) > len(prefix):
            root = label[len(prefix):]

        return {
            "root_signature": root,
            "affix_signature": suffix or prefix or ""
        }

    @classmethod
    def annotate_candidates(cls, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        root_counts: Dict[str, int] = {}
        affix_counts: Dict[str, int] = {}
        ordered = sorted(
            candidates,
            key=lambda c: float(c.get("overall_score") or c.get("quality_score") or 0.0),
            reverse=True
        )
        updated: List[Dict[str, Any]] = []

        for candidate in ordered:
            item = copy.deepcopy(candidate)
            signatures = cls.extract_signatures(item)
            root = signatures["root_signature"]
            affix = signatures["affix_signature"]

            root_counts[root] = root_counts.get(root, 0) + 1
            if affix:
                affix_counts[affix] = affix_counts.get(affix, 0) + 1

            max_tier = "TIER_A"
            if root_counts[root] > FINAL_ROOT_CAP_TIER_AB:
                max_tier = "TIER_C"
            elif root_counts[root] > FINAL_ROOT_CAP_TIER_A:
                max_tier = "TIER_B"

            item.update(signatures)
            item["root_frequency_in_run"] = root_counts[root]
            item["affix_frequency_in_run"] = affix_counts.get(affix, 0)
            item["max_quality_tier"] = max_tier
            if max_tier != "TIER_A":
                item["tier_cap_reason"] = f"Shared root '{root}' exceeded final export cap"
            updated.append(item)

        return updated


class GlobalDomainDeduplicator:
    @staticmethod
    def dedupe_candidates(
        candidates: List[Dict[str, Any]],
        persisted_domains: Optional[Iterable[str]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, List[str]]]:
        persisted = {canonicalize_domain(d) for d in (persisted_domains or []) if canonicalize_domain(d)}
        seen: Set[str] = set()
        removed = {"duplicates": [], "persisted": []}
        deduped: List[Dict[str, Any]] = []

        for candidate in candidates:
            domain = candidate.get("domain") or candidate.get("domain_name", "")
            canonical = canonicalize_domain(domain)
            if not canonical:
                continue
            if canonical in persisted:
                removed["persisted"].append(canonical)
                continue
            if canonical in seen:
                removed["duplicates"].append(canonical)
                continue

            seen.add(canonical)
            item = copy.deepcopy(candidate)
            item["domain"] = canonical
            item["domain_name"] = canonical
            deduped.append(item)

        return deduped, removed


def build_semantic_value_metadata(label: str) -> Dict[str, Any]:
    semantic_root = detect_semantic_root(label)
    return {
        "semantic_root": semantic_root,
        "semantic_root_bonus": SEMANTIC_ROOT_BONUS if semantic_root else 0.0,
        "has_semantic_root": semantic_root is not None
    }
