"""
Multi-model, multi-layer domain quality evaluation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import statistics
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from quality_engine.config import get_multi_model_evaluation_config
from quality_engine.invented_quality import InventedQualityEvaluator
from quality_engine.quality_improvements import compute_phonotactic_naturalness, extract_label

logger = logging.getLogger("MultiModelDomainEvaluator")

ROLE_NAMES = ("linguistic", "brand", "commercial", "red_team")
QUALITY_SCORE_KEYS = {
    "linguistic": "linguistic_naturalness",
    "brand": "brand_strength",
    "commercial": "commercial_strength",
    "red_team": "red_team_score",
}

def _clamp(value: Any, low: float = 0.0, high: float = 100.0) -> Optional[float]:
    try:
        if value is None:
            return None
        numeric = float(value)
        if math.isnan(numeric) or math.isinf(numeric):
            return None
        return round(max(low, min(high, numeric)), 3)
    except (TypeError, ValueError):
        return None

def _list(value: Any) -> List[str]:
    return [str(v).strip() for v in value if str(v).strip()][:12] if isinstance(value, list) else []

def _repair_json_once(text: str) -> Optional[Dict[str, Any]]:
    value = (text or "").strip()
    value = re.sub(r"^\x60\x60\x60(?:json)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*\x60\x60\x60$", "", value).strip()
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end <= start:
        return None
    candidate = re.sub(r",\s*([}\]])", r"\1", value[start:end + 1])
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None

def robust_statistics(scores: Sequence[float], disagreement_threshold: float = 22.0) -> Dict[str, Any]:
    clean = [float(s) for s in scores if _clamp(s) is not None]
    if not clean:
        return {"median": None, "trimmed_mean": None, "stddev": None, "range": None, "judge_agreement": 0.0, "high_disagreement": True, "outlier_detected": False}
    ordered = sorted(clean)
    median = statistics.median(ordered)
    trimmed = statistics.mean(ordered[1:-1]) if len(ordered) >= 4 else median
    stddev = statistics.pstdev(clean) if len(clean) > 1 else 0.0
    score_range = max(clean) - min(clean)
    agreement = max(0.0, min(100.0, 100.0 - (stddev * 2.2) - (score_range * 0.20)))
    outlier = False
    if len(clean) >= 4:
        mad = statistics.median([abs(x - median) for x in clean])
        outlier = mad > 0 and any(abs(x - median) > (3.5 * mad) for x in clean)
    return {
        "median": round(median, 3),
        "trimmed_mean": round(trimmed, 3),
        "stddev": round(stddev, 3),
        "range": round(score_range, 3),
        "judge_agreement": round(agreement, 3),
        "high_disagreement": score_range >= disagreement_threshold or stddev >= disagreement_threshold * 0.45,
        "outlier_detected": outlier,
    }

class MultiModelDomainEvaluator:
    def __init__(self, router: Any, config: Optional[Dict[str, Any]] = None) -> None:
        self.router = router
        self.config = config or get_multi_model_evaluation_config()
        self.role_profiles = self._resolve_role_profiles()
        self.call_budget = int(self.config.get("call_budget", int(os.getenv("MULTI_MODEL_CALL_BUDGET", "120"))))
        self.call_count = 0
        self.runtime_stats = {
            role: {"success": 0, "failed": 0, "fallback_used": 0, "calls": 0, "latency_ms": []}
            for role in (*ROLE_NAMES, "arbiter")
        }

    def _resolve_role_profiles(self) -> Dict[str, List[Dict[str, str]]]:
        profiles: Dict[str, List[Dict[str, str]]] = {}
        role_map = self.config.get("role_task_map", {})
        role_index = self.config.get("role_profile_index", {})
        for role in (*ROLE_NAMES, "arbiter"):
            task = role_map.get(role)
            configured = list(getattr(self.router, "task_profiles", {}).get(task or "", []))
            if not configured:
                profiles[role] = []
                continue
            allowed = {(str(p.get("provider")), str(p.get("model"))) for p in configured}
            env_provider = os.getenv(f"MULTI_MODEL_{role.upper()}_PROVIDER")
            env_model = os.getenv(f"MULTI_MODEL_{role.upper()}_MODEL")
            selected: List[Dict[str, str]] = []
            if env_provider and env_model and (env_provider, env_model) in allowed:
                selected.append({"provider": env_provider, "model": env_model})
            idx = max(0, min(int(role_index.get(role, 0)), len(configured) - 1))
            preferred = configured[idx]
            preferred_pair = {"provider": str(preferred["provider"]), "model": str(preferred["model"])}
            if preferred_pair not in selected:
                selected.append(preferred_pair)
            for item in configured:
                pair = {"provider": str(item["provider"]), "model": str(item["model"])}
                if pair not in selected:
                    selected.append(pair)
            profiles[role] = selected
        return profiles

    async def _call_profile(self, role: str, profile: Dict[str, str], prompt: str, temperature: float, max_tokens: int) -> Dict[str, Any]:
        if self.call_count >= self.call_budget:
            raise RuntimeError("multi_model_call_budget_exhausted")
        self.call_count += 1
        self.runtime_stats[role]["calls"] += 1
        started = time.perf_counter()
        provider, model = profile["provider"], profile["model"]
        try:
            if not hasattr(self.router, "execute_profile"):
                raise RuntimeError("router_profile_execution_not_supported")
            result = await asyncio.wait_for(
                self.router.execute_profile(
                    provider=provider,
                    model=model,
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    max_retries=int(self.config.get("judge_max_retries", 1)),
                ),
                timeout=float(self.config.get("request_timeout_seconds", 25)),
            )
            raw = result.get("content", "") if isinstance(result, dict) else str(result)
            latency_ms = float(result.get("latency_ms", (time.perf_counter() - started) * 1000)) if isinstance(result, dict) else (time.perf_counter() - started) * 1000
            self.runtime_stats[role]["success"] += 1
            self.runtime_stats[role]["latency_ms"].append(round(latency_ms, 2))
            return {"status": "SUCCESS", "provider": provider, "model": model, "latency_ms": round(latency_ms, 2), "fallback_used": False, "raw_output": raw}
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            self.runtime_stats[role]["failed"] += 1
            self.runtime_stats[role]["latency_ms"].append(round(latency_ms, 2))
            logger.warning("[MULTI-MODEL-FAIL] role=%s provider=%s model=%s latency=%.2fms error=%s", role, provider, model, latency_ms, str(exc)[:240])
            raise

    def _parse_json(self, raw: str) -> Optional[Dict[str, Any]]:
        if hasattr(self.router, "extract_json_safe"):
            try:
                parsed = self.router.extract_json_safe(raw)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return _repair_json_once(raw)

    def _candidate_evidence(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        domain = str(candidate.get("domain") or candidate.get("domain_name") or "").lower()
        label = extract_label(domain)
        naming_type = str(candidate.get("morphology_type") or candidate.get("naming_type") or "INVENTED")
        invented = candidate.get("invented_analysis")
        if not isinstance(invented, dict):
            if naming_type.upper() == "INVENTED":
                try:
                    invented = InventedQualityEvaluator.get_instance().evaluate_candidate(label)
                except Exception:
                    invented = {}
            else:
                invented = {}
        phon = compute_phonotactic_naturalness(label)
        deterministic = candidate.get("deterministic") if isinstance(candidate.get("deterministic"), dict) else {}
        deterministic.setdefault("phonotactic_naturalness", phon)
        deterministic.setdefault("severe_phonotactic_violation", not phon.get("passes_threshold", False))
        return {
            "domain": domain,
            "label": label,
            "concept": candidate.get("source_concept") or candidate.get("concept") or "",
            "market_category": candidate.get("market_category") or candidate.get("category") or "AI & Technology",
            "naming_type": naming_type,
            "invented_subtype": candidate.get("invented_subtype") or invented.get("invented_subtype"),
            "invented_quality_score": candidate.get("invented_quality_score", invented.get("invented_quality_score")),
            "lexical_anchors": (candidate.get("lexical_anchors") or invented.get("lexical_anchors") or [])[:8],
            "phonetic_anchors": (candidate.get("phonetic_anchors") or invented.get("phonetic_anchors") or [])[:8],
            "semantic_anchors": (candidate.get("semantic_anchors") or invented.get("semantic_anchors") or [])[:8],
            "semantic_anchor_score": candidate.get("semantic_anchor_score", invented.get("semantic_anchor_score")),
            "brandability_heuristic_score": candidate.get("brandability_heuristic_score", invented.get("brandability_heuristic_score")),
            "deterministic_pronunciation": candidate.get("pronunciation_score", candidate.get("pronunciation")),
            "hear_to_spell": candidate.get("hear_to_spell_score", candidate.get("radio_test_score")),
            "phonetic_warnings": deterministic.get("phonotactic_naturalness", {}).get("flagged_transitions", []),
            "phonotactic_naturalness": deterministic.get("phonotactic_naturalness", {}),
            "availability_status": candidate.get("availability_status"),
            "availability_verified": candidate.get("availability_verified"),
            "ip_risk_level": candidate.get("ip_risk_level"),
            "ip_check_status": candidate.get("ip_check_status"),
            "atom": self._normalize_atom(candidate.get("atom") or {}),
        }

    @staticmethod
    def _normalize_atom(atom: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(atom, dict):
            return {}
        return {k: atom[k] for k in (
            "atom_domain_score", "atom_appraisal", "atom_market_signal",
            "atom_positive_signals", "atom_negative_signals", "appraisal_status"
        ) if k in atom}

    def _role_prompt(self, role: str, candidates: Sequence[Dict[str, Any]]) -> str:
        payload = json.dumps([self._candidate_evidence(c) for c in candidates], ensure_ascii=False, indent=2)
        common = """
You are one independent expert in a domain-name evaluation panel.
Evaluate ONLY the responsibility assigned to your role.
Do not use conclusions or scores from other evaluators.
Deterministic metadata is factual evidence.

Do NOT reward:
- shortness by itself
- .com by itself
- pronounceability by itself
- two syllables by itself
- vowel endings by themselves
- modern-tech appearance
- uniqueness by itself

DO reward:
- intentionality
- meaningful association
- natural linguistic structure
- memorability
- spelling predictability
- commercial plausibility
- buyer breadth
- strong brand identity
- conceptual flexibility
- evidence-backed strength

A short pronounceable random string is NOT automatically an intentional coined brand.
Return STRICT JSON only.
"""
        instructions = {
            "linguistic": """
ROLE: LINGUISTIC NATURALNESS JUDGE.
Evaluate English phonotactic naturalness, syllable quality, sonority, consonant transitions,
vowel patterns, morphology, lexical familiarity, semantic anchors, spelling predictability,
hear-to-spell, native-speaker plausibility, and coined intentionality.
Explicitly distinguish a pronounceable random string from an intentional coined name.
""",
            "brand": """
ROLE: BRAND STRATEGY JUDGE.
Act as an experienced naming director. Evaluate memorability, visual/verbal identity,
distinctiveness, brand architecture, startup plausibility, emotional resonance, recall,
hear-to-spell, longevity, category flexibility, and professional human-selection plausibility.
Do NOT treat inventedness as a positive by itself.
""",
            "commercial": """
ROLE: COMMERCIAL / BUYER JUDGE.
Evaluate buyer clarity, buyer breadth, commercial flexibility, category fit, market breadth,
brand extension potential, startup/enterprise suitability, semantic relevance, and resale flexibility.
Explicitly determine who could realistically buy the domain. Vague buyer logic lowers scores.
""",
            "red_team": """
ROLE: ADVERSARIAL RED-TEAM CRITIC.
TRY TO KILL THE CANDIDATE. Search for gibberish, forced AI naming, accidental/undesirable meanings,
awkward pronunciation, hard spelling, generic startup formulas, generic suffixes/prefixes,
narrow niche dependence, trademark-like resemblance, typo risk, weak buyer clarity, weak commercial rationale,
and "short but meaningless". Higher red_team_score means the candidate survived objections better.
""",
        }[role]
        return common + instructions + "\nINPUT FACTS:\n" + payload + f"""

OUTPUT JSON:
{{"evaluations":[{{"domain":"...","<role-specific fields>":0-100,...}}]}}
"""

    def _required_fields(self, role: str) -> Tuple[str, ...]:
        return {
            "linguistic": (
                "linguistic_naturalness", "lexical_familiarity", "phonetic_naturalness",
                "spelling_predictability", "semantic_anchor_quality", "coined_intentionality", "gibberish_probability"
            ),
            "brand": (
                "brand_strength", "memorability", "identity_strength", "startup_naturalness",
                "distinctiveness", "brand_longevity", "ai_generated_feel"
            ),
            "commercial": (
                "commercial_strength", "buyer_clarity", "buyer_breadth", "category_fit",
                "market_breadth", "resale_flexibility"
            ),
            "red_team": (
                "red_team_score", "gibberish_risk", "ai_pattern_risk", "spelling_risk",
                "commercial_weakness", "semantic_weakness"
            ),
        }[role]

    def _normalize_role_response(self, role: str, parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw = parsed.get("evaluations")
        if not isinstance(raw, list):
            return []
        required = self._required_fields(role)
        normalized: List[Dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            domain = str(item.get("domain", "")).lower().strip()
            if not domain:
                continue
            out = {"domain": domain}
            valid = True
            for key in required:
                value = _clamp(item.get(key))
                if value is None:
                    valid = False
                    break
                out[key] = value
            if not valid:
                continue
            for key in ("critical_flags", "commercial_risk_flags", "critical_objections", "kill_reasons"):
                out[key] = _list(item.get(key))
            out["verdict"] = str(item.get("verdict", "REVIEW")).upper()
            if out["verdict"] not in {"KEEP", "REVIEW", "REJECT"}:
                out["verdict"] = "REVIEW"
            out["reason"] = str(item.get("reason", "")).strip()[:1200]
            normalized.append(out)
        return normalized

    async def _invoke_role_batch(self, role: str, candidates: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        if not candidates:
            return {}
        cfg = self.config.get(role, {}) if isinstance(self.config.get(role), dict) else {}
        temperature = float(cfg.get("temperature", {"linguistic": 0.1, "brand": 0.2, "commercial": 0.2, "red_team": 0.1}.get(role, 0.1)))
        max_tokens = int(cfg.get("max_tokens", 2200))
        profiles = self.role_profiles.get(role, [])
        if not profiles:
            return {
                str(c.get("domain", "")).lower(): {
                    "status": "FAILED", "provider": None, "model": None, "latency_ms": None,
                    "fallback_used": False, "raw_output": None, "parsed": None, "error": "no_router_profile"
                } for c in candidates
            }
        prompt = self._role_prompt(role, candidates)
        last_error = "role_failed"
        for index, profile in enumerate(profiles):
            try:
                response = await self._call_profile(role, profile, prompt, temperature, max_tokens)
                parsed = self._parse_json(response.get("raw_output", ""))
                if parsed is None:
                    raise ValueError("malformed_json")
                items = self._normalize_role_response(role, parsed)
                if not items:
                    raise ValueError("schema_validation_failed")
                response["parsed_response"] = parsed
                mapped = {
                    item["domain"]: {**response, "fallback_used": index > 0, "parsed": item}
                    for item in items
                }
                for c in candidates:
                    domain = str(c.get("domain", "")).lower()
                    if domain not in mapped:
                        mapped[domain] = {
                            "status": "FAILED", "provider": response.get("provider"),
                            "model": response.get("model"), "latency_ms": response.get("latency_ms"),
                            "fallback_used": index > 0, "raw_output": response.get("raw_output"),
                            "parsed": None, "error": "missing_domain_in_response"
                        }
                if index > 0:
                    self.runtime_stats[role]["fallback_used"] += 1
                return mapped
            except Exception as exc:
                last_error = str(exc)
                continue
        return {
            str(c.get("domain", "")).lower(): {
                "status": "FAILED", "provider": None, "model": None, "latency_ms": None,
                "fallback_used": len(profiles) > 1, "raw_output": None,
                "parsed": None, "error": last_error
            } for c in candidates
        }

    def _aggregate_candidate(self, candidate: Dict[str, Any], traces: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        roles = {role: traces.get(role, {}) for role in ROLE_NAMES}
        parsed = {
            role: roles[role].get("parsed")
            for role in ROLE_NAMES
            if roles[role].get("status") == "SUCCESS" and isinstance(roles[role].get("parsed"), dict)
        }
        role_scores = [
            float(parsed[role][QUALITY_SCORE_KEYS[role]])
            for role in ROLE_NAMES
            if role in parsed and parsed[role].get(QUALITY_SCORE_KEYS[role]) is not None
        ]
        stats = robust_statistics(role_scores, float(self.config.get("disagreement_threshold", 22.0)))
        missing = len(ROLE_NAMES) - len(role_scores)
        disagreement_penalty = min(
            25.0,
            float(stats.get("stddev") or 0.0) * float(self.config.get("disagreement_penalty_factor", 0.35))
        )
        missing_penalty = missing * float(self.config.get("missing_judge_penalty", 6.0))
        red_score = parsed.get("red_team", {}).get("red_team_score")
        red_penalty = 0.0
        if red_score is not None and float(red_score) < float(self.config.get("red_team_low_score", 55.0)):
            red_penalty = min(
                20.0,
                (float(self.config.get("red_team_low_score", 55.0)) - float(red_score))
                * float(self.config.get("red_team_penalty_factor", 0.20)),
            )
        consensus = stats.get("median")
        confidence = max(
            0.0,
            min(
                100.0,
                float(stats.get("judge_agreement") or 0.0)
                - missing_penalty
                - disagreement_penalty * 0.75,
            ),
        )
        invented_subtype = str(candidate.get("invented_subtype") or candidate.get("invented_analysis", {}).get("invented_subtype") or "")
        semantic_det = _clamp(candidate.get("semantic_anchor_score") or candidate.get("invented_analysis", {}).get("semantic_anchor_score"))
        semantic_quality = _clamp(parsed.get("linguistic", {}).get("semantic_anchor_quality")) or semantic_det
        gibberish_values = [
            parsed.get("linguistic", {}).get("gibberish_probability"),
            parsed.get("red_team", {}).get("gibberish_risk"),
        ]
        gibberish_values = [float(v) for v in gibberish_values if v is not None]
        gibberish_risk = statistics.median(gibberish_values) if gibberish_values else (70.0 if invented_subtype == "UNANCHORED" else 35.0)
        if invented_subtype == "UNANCHORED":
            gibberish_risk += 15.0
        if semantic_det is not None and semantic_det < 45:
            gibberish_risk += 8.0
        gibberish_risk += min(10.0, disagreement_penalty * 0.5)
        severe_phonetic = bool((candidate.get("deterministic") or {}).get("severe_phonotactic_violation", False))
        if severe_phonetic:
            gibberish_risk += 18.0
            confidence = min(confidence, 35.0)
        gibberish_risk = max(0.0, min(100.0, gibberish_risk))
        if gibberish_risk >= float(self.config.get("gibberish_likely_threshold", 70.0)):
            gibberish_band = "LIKELY_GIBBERISH"
        elif gibberish_risk > float(self.config.get("gibberish_acceptable_max", 40.0)):
            gibberish_band = "WEAK_COINED"
        elif gibberish_risk > float(self.config.get("gibberish_strong_coined_max", 20.0)):
            gibberish_band = "ACCEPTABLE_COINED"
        else:
            gibberish_band = "STRONG_COINED"

        label = extract_label(candidate.get("domain") or candidate.get("domain_name", ""))
        commercial_quality = _clamp(parsed.get("commercial", {}).get("commercial_strength"))
        short_meaningless = (
            len(label) <= int(self.config.get("short_meaningless_max_length", 7))
            and invented_subtype == "UNANCHORED"
            and float(semantic_quality or 0) <= float(self.config.get("short_meaningless_semantic_max", 50.0))
            and float(commercial_quality or 0) <= float(self.config.get("short_meaningless_commercial_max", 60.0))
        )
        preliminary = None
        if consensus is not None:
            preliminary = float(consensus) - disagreement_penalty - missing_penalty - red_penalty
            if short_meaningless:
                preliminary -= 15.0
            if severe_phonetic:
                preliminary = min(preliminary, float(self.config.get("deterministic_severe_phonetic_ceiling", 59)))
            if invented_subtype == "UNANCHORED":
                preliminary = min(preliminary, float(self.config.get("unanchored_final_ceiling", 64)))
        return {
            "domain": str(candidate.get("domain") or candidate.get("domain_name") or "").lower(),
            "linguistic_judge": roles["linguistic"],
            "brand_judge": roles["brand"],
            "commercial_judge": roles["commercial"],
            "red_team_judge": roles["red_team"],
            "judge_agreement": stats.get("judge_agreement", 0.0),
            "judge_disagreement": {
                "stddev": stats.get("stddev"), "range": stats.get("range"),
                "high_disagreement": stats.get("high_disagreement", True),
                "disagreement_penalty": round(disagreement_penalty, 3),
                "missing_judges": missing,
            },
            "consensus_confidence": round(confidence, 3),
            "outlier_detected": bool(stats.get("outlier_detected", False)),
            "consensus": {
                "robust_median": consensus,
                "robust_trimmed_mean": stats.get("trimmed_mean"),
                "consensus_score": _clamp(preliminary),
                "confidence": round(confidence, 3),
                "agreement": stats,
                "red_team_score": _clamp(red_score),
                "red_team_penalty": round(red_penalty, 3),
                "linguistic_quality": _clamp(parsed.get("linguistic", {}).get("linguistic_naturalness")),
                "brand_quality": _clamp(parsed.get("brand", {}).get("brand_strength")),
                "commercial_quality": commercial_quality,
                "buyer_quality": _clamp(parsed.get("commercial", {}).get("buyer_clarity")),
                "semantic_quality": semantic_quality,
                "gibberish_risk": round(gibberish_risk, 3),
                "ai_pattern_risk": _clamp(parsed.get("brand", {}).get("ai_generated_feel")) or _clamp(parsed.get("red_team", {}).get("ai_pattern_risk")) or 50.0,
                "arbiter_status": "PENDING",
                "verdict": "REVIEW",
            },
            "gibberish_risk_score": round(gibberish_risk, 3),
            "gibberish_quality_band": gibberish_band,
            "short_but_meaningless": short_meaningless,
            "selection_reasons": [
                f"Independent robust consensus: {preliminary:.1f}" if preliminary is not None else "No AI consensus available",
                f"Consensus confidence: {confidence:.1f}",
            ],
        }

    def _arbiter_prompt(self, candidate: Dict[str, Any], normalized: Dict[str, Any]) -> str:
        expert_outputs = {
            role: {
                "status": normalized.get(f"{role}_judge", {}).get("status"),
                "provider": normalized.get(f"{role}_judge", {}).get("provider"),
                "model": normalized.get(f"{role}_judge", {}).get("model"),
                "parsed": normalized.get(f"{role}_judge", {}).get("parsed"),
                "raw_output_excerpt": (normalized.get(f"{role}_judge", {}).get("raw_output") or "")[:2400],
            }
            for role in ROLE_NAMES
        }
        evidence = self._candidate_evidence(candidate)
        domain = str(candidate.get("domain") or candidate.get("domain_name") or "").lower()
        return f"""
You are the CONSENSUS ARBITER.
Do NOT average scores blindly. Resolve disagreement using evidence convergence.
Identify strongest evidence, strongest objection, inflated scores, and whether to keep the candidate.

Deterministic facts are authoritative:
- severe phonotactic violations cannot be overruled
- absent semantic anchors cannot be silently reinterpreted
- availability must be verified for final eligibility
- IP safety must remain a hard gate
- hard pronunciation floors remain hard
Atom is external market evidence, not a replacement for internal quality.

CANDIDATE:
{json.dumps(evidence, ensure_ascii=False, indent=2)}

INDEPENDENT EXPERT OUTPUTS:
{json.dumps(expert_outputs, ensure_ascii=False, indent=2)}

Do not reward shortness, .com, pronounceability, two syllables, vowel endings,
modern-tech appearance, or uniqueness by themselves.
Semantic quality for invented names must be evidence-backed.
A strong red-team objection can reduce confidence and rank even when other judges are positive.

Return STRICT JSON:
{{
  "domain": "{domain}",
  "consensus_score": 0-100,
  "confidence": 0-100,
  "final_brand_quality": 0-100,
  "final_linguistic_quality": 0-100,
  "final_commercial_quality": 0-100,
  "final_buyer_quality": 0-100,
  "final_semantic_quality": 0-100,
  "final_gibberish_risk": 0-100,
  "final_ai_pattern_risk": 0-100,
  "major_strengths": [],
  "major_weaknesses": [],
  "critical_flags": [],
  "verdict": "STRONG_KEEP|KEEP|REVIEW|REJECT",
  "reason": "..."
}}
"""

    async def _run_arbiter(self, candidate: Dict[str, Any], normalized: Dict[str, Any]) -> Dict[str, Any]:
        profiles = self.role_profiles.get("arbiter", [])
        cfg = self.config.get("arbiter", {}) if isinstance(self.config.get("arbiter"), dict) else {}
        if not profiles:
            normalized["consensus"]["arbiter_status"] = "FAILED"
            return normalized
        last_error = "arbiter_failed"
        for index, profile in enumerate(profiles):
            try:
                response = await self._call_profile(
                    "arbiter", profile, self._arbiter_prompt(candidate, normalized),
                    float(cfg.get("temperature", 0.1)), int(cfg.get("max_tokens", 1600))
                )
                parsed = self._parse_json(response.get("raw_output", ""))
                domain = str(candidate.get("domain") or candidate.get("domain_name") or "").lower()
                if not parsed or str(parsed.get("domain", "")).lower() != domain:
                    raise ValueError("arbiter_schema_error")
                for key in (
                    "consensus_score", "confidence", "final_brand_quality", "final_linguistic_quality",
                    "final_commercial_quality", "final_buyer_quality", "final_semantic_quality",
                    "final_gibberish_risk", "final_ai_pattern_risk"
                ):
                    normalized["consensus"][key] = _clamp(parsed.get(key))
                normalized["consensus"]["major_strengths"] = _list(parsed.get("major_strengths"))
                normalized["consensus"]["major_weaknesses"] = _list(parsed.get("major_weaknesses"))
                normalized["consensus"]["critical_flags"] = _list(parsed.get("critical_flags"))
                normalized["consensus"]["verdict"] = str(parsed.get("verdict", "REVIEW")).upper()
                if normalized["consensus"]["verdict"] not in {"STRONG_KEEP", "KEEP", "REVIEW", "REJECT"}:
                    normalized["consensus"]["verdict"] = "REVIEW"
                normalized["consensus"]["reason"] = str(parsed.get("reason", "")).strip()[:1600]
                normalized["consensus"]["arbiter_status"] = "SUCCESS"
                normalized["consensus_confidence"] = _clamp(normalized["consensus"].get("confidence")) or normalized["consensus_confidence"]
                normalized["arbiter_trace"] = {
                    "status": "SUCCESS", "provider": response.get("provider"),
                    "model": response.get("model"), "latency_ms": response.get("latency_ms"),
                    "fallback_used": index > 0, "raw_output": response.get("raw_output"), "parsed": parsed,
                }
                invented_subtype = str(candidate.get("invented_subtype") or candidate.get("invented_analysis", {}).get("invented_subtype") or "")
                if invented_subtype == "UNANCHORED":
                    normalized["consensus"]["consensus_score"] = min(
                        float(normalized["consensus"].get("consensus_score") or 0),
                        float(self.config.get("unanchored_final_ceiling", 64)),
                    )
                if bool((candidate.get("deterministic") or {}).get("severe_phonotactic_violation", False)):
                    normalized["consensus"]["consensus_score"] = min(
                        float(normalized["consensus"].get("consensus_score") or 0),
                        float(self.config.get("deterministic_severe_phonetic_ceiling", 59)),
                    )
                return normalized
            except Exception as exc:
                last_error = str(exc)
                continue
        normalized["consensus"]["arbiter_status"] = "FAILED"
        normalized["consensus"]["arbiter_error"] = last_error
        return normalized

    async def evaluate_candidate(self, domain: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        result = await self.evaluate_batch([{"domain": domain, **(context or {})}], context=context)
        return result.get("candidates", {}).get(str(domain).lower(), {})

    async def evaluate_batch(self, candidates: Sequence[Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not candidates:
            return {"candidates": {}, "summary": self._summary()}
        if not bool(self.config.get("enabled", True)):
            return {"candidates": {}, "summary": self._summary(disabled=True)}
        prepared: List[Dict[str, Any]] = []
        for item in candidates:
            if isinstance(item, str):
                prepared.append({"domain": item, **(context or {})})
            elif isinstance(item, dict):
                merged = dict(context or {})
                merged.update(item)
                prepared.append(merged)
        batch_size = max(1, int(self.config.get("judge_batch_size", 5)))
        chunks = [prepared[i:i + batch_size] for i in range(0, len(prepared), batch_size)]

        async def run_role(role: str) -> Tuple[str, Dict[str, Dict[str, Any]]]:
            results = await asyncio.gather(
                *(self._invoke_role_batch(role, chunk) for chunk in chunks),
                return_exceptions=True,
            )
            merged: Dict[str, Dict[str, Any]] = {}
            for idx, result in enumerate(results):
                if isinstance(result, Exception):
                    for c in chunks[idx]:
                        domain = str(c.get("domain", "")).lower()
                        merged[domain] = {
                            "status": "FAILED", "provider": None, "model": None, "latency_ms": None,
                            "fallback_used": False, "raw_output": None, "parsed": None, "error": str(result)
                        }
                else:
                    merged.update(result)
            return role, merged

        enabled_roles = [role for role in ROLE_NAMES if not isinstance(self.config.get(role), dict) or bool(self.config.get(role, {}).get("enabled", True))]
        role_results = await asyncio.gather(*(run_role(role) for role in enabled_roles), return_exceptions=True)
        by_role: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for result in role_results:
            if not isinstance(result, Exception):
                role, data = result
                by_role[role] = data

        output: Dict[str, Dict[str, Any]] = {}
        for candidate in prepared:
            domain = str(candidate.get("domain", "")).lower()
            traces = {
                role: by_role.get(role, {}).get(domain, {
                    "status": "FAILED", "provider": None, "model": None, "latency_ms": None,
                    "fallback_used": False, "raw_output": None, "parsed": None, "error": "role_unavailable"
                })
                for role in ROLE_NAMES
            }
            output[domain] = self._aggregate_candidate(candidate, traces)

        arbiter_pool = sorted(
            output.values(),
            key=lambda x: float(x.get("consensus", {}).get("consensus_score") or 0.0),
            reverse=True
        )[:max(0, int(self.config.get("arbiter_pool_size", 20)))]
        prepared_map = {str(c.get("domain", "")).lower(): c for c in prepared}
        if arbiter_pool and bool(self.config.get("arbiter_enabled", True)):
            arbiter_results = await asyncio.gather(
                *(self._run_arbiter(prepared_map[item["domain"]], item) for item in arbiter_pool),
                return_exceptions=True,
            )
            for result in arbiter_results:
                if not isinstance(result, Exception):
                    output[result["domain"]] = result
        return {"candidates": output, "summary": self._summary()}

    def _summary(self, disabled: bool = False) -> Dict[str, Any]:
        return {
            "enabled": bool(self.config.get("enabled", True)) and not disabled,
            "call_count": self.call_count,
            "call_budget": self.call_budget,
            "roles": {
                role: {
                    "success": stat["success"], "failed": stat["failed"],
                    "fallback_used": stat["fallback_used"], "calls": stat["calls"],
                    "avg_latency_ms": round(statistics.mean(stat["latency_ms"]), 2) if stat["latency_ms"] else None,
                }
                for role, stat in self.runtime_stats.items()
            },
        }
