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

try:
    from router import get_model_fallback_chain
except ImportError:
    def get_model_fallback_chain(m: str) -> List[str]:
        return ["qwen/qwen3.7-max:free", "mistralai/mistral-large-2512"]

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


def detect_short_but_meaningless(
    label: str,
    length: int,
    pronunciation: float,
    semantic_anchor: float,
    commercial_clarity: float
) -> bool:
    """
    Part 25: SHORT_BUT_MEANINGLESS Detector.
    Triggers when length is strong and pronunciation is acceptable, but semantic
    evidence is weak and commercial clarity is weak/absent.
    """
    return (
        length <= 7
        and pronunciation >= 70.0
        and semantic_anchor <= 35.0
        and commercial_clarity <= 40.0
    )


def detect_pronounceable_not_brandable(
    pronunciation: float,
    semantic_anchor: float,
    brand_score: float,
    red_team_score: float,
    atom_score: Optional[float] = None
) -> bool:
    """
    Part 26: PRONOUNCEABLE_NOT_BRANDABLE Detector.
    Catches candidates with high phonetic balance/pronunciation, but weak semantic anchor,
    weak brand judge score, negative red team evaluation, and low independent Atom score.
    """
    return (
        pronunciation >= 74.0
        and semantic_anchor <= 45.0
        and (brand_score <= 60.0 or red_team_score <= 55.0 or red_team_score >= 65.0)
        and (atom_score is None or float(atom_score) <= 7.5)
    )


class MultiModelDomainEvaluator:
    def __init__(self, router: Any, config: Optional[Dict[str, Any]] = None) -> None:
        self.router = router
        self.config = config or get_multi_model_evaluation_config()
        self.role_profiles = self._resolve_role_profiles()
        self.call_budget = int(self.config.get("call_budget", int(os.getenv("MULTI_MODEL_CALL_BUDGET", "2500"))))
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
        keys = (
            "atom_domain_score", "atom_appraisal_value", "atom_appraisal_normalized",
            "atom_appraisal", "atom_market_signal", "status", "appraisal_status",
            "positive_signals", "negative_signals", "atom_positive_signals", "atom_negative_signals",
            "tld_taken_count", "tm_conflicts", "category", "internal_atom_gap", "calibration_flags"
        )
        return {k: atom[k] for k in keys if k in atom and atom[k] is not None}

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

    async def _execute_profile_with_fallback(
        self,
        role: str,
        profile: Dict[str, str],
        prompt: str,
        temperature: float,
        max_tokens: int,
        candidates: Sequence[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Executes a single model profile with dedicated per-model fallback:
        model A -> fallback A1 -> fallback A2 while all other models continue normally.
        """
        orig_model = profile.get("model", "")
        provider = profile.get("provider", "xkiro")
        chain = [orig_model] + get_model_fallback_chain(orig_model)
        
        last_error = "unknown_error"
        for idx, model_candidate in enumerate(chain):
            attempt_profile = {"provider": provider, "model": model_candidate}
            try:
                response = await self._call_profile(role, attempt_profile, prompt, temperature, max_tokens)
                parsed = self._parse_json(response.get("raw_output", ""))
                if parsed is None:
                    raise ValueError(f"malformed_json from {model_candidate}")
                items = self._normalize_role_response(role, parsed)
                if not items:
                    raise ValueError(f"schema_validation_failed from {model_candidate}")
                
                fallback_used = (idx > 0)
                if fallback_used:
                    self.runtime_stats[role]["fallback_used"] += 1
                
                mapped_items = {item["domain"]: item for item in items}
                return {
                    "status": "SUCCESS",
                    "original_model": orig_model,
                    "model_used": model_candidate,
                    "provider": provider,
                    "fallback_used": fallback_used,
                    "fallbacks_attempted": idx,
                    "latency_ms": response.get("latency_ms"),
                    "items": mapped_items,
                    "error": None
                }
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "[PER-MODEL-FALLBACK] role=%s primary=%s attempted=%s (step %d/%d) failed: %s",
                    role, orig_model, model_candidate, idx + 1, len(chain), last_error[:160]
                )
                continue
                
        return {
            "status": "FAILED",
            "original_model": orig_model,
            "model_used": orig_model,
            "provider": provider,
            "fallback_used": True if len(chain) > 1 else False,
            "fallbacks_attempted": len(chain) - 1,
            "latency_ms": None,
            "items": {},
            "error": last_error
        }

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
        # Execute ALL configured profiles concurrently with per-model fallback.
        # Do NOT stop after the first success. Every available model contributes.
        tasks = [
            self._execute_profile_with_fallback(role, profile, prompt, temperature, max_tokens, candidates)
            for profile in profiles
        ]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        mapped: Dict[str, Dict[str, Any]] = {}
        for c in candidates:
            d = str(c.get("domain", "")).lower()
            candidate_successful_evals = []
            candidate_failed_models = []
            candidate_succeeded_models = []
            candidate_fallbacks_count = 0

            for outcome in outcomes:
                if isinstance(outcome, Exception) or not isinstance(outcome, dict):
                    continue
                orig_m = outcome.get("original_model")
                used_m = outcome.get("model_used")
                if outcome.get("status") == "SUCCESS" and d in outcome.get("items", {}):
                    item = outcome["items"][d]
                    candidate_successful_evals.append({
                        "model": used_m,
                        "original_model": orig_m,
                        "eval": item,
                        "fallback_used": outcome.get("fallback_used", False)
                    })
                    candidate_succeeded_models.append(used_m)
                    if outcome.get("fallback_used"):
                        candidate_fallbacks_count += 1
                else:
                    candidate_failed_models.append(orig_m)

            if candidate_successful_evals:
                # Robust median aggregation across all completing models for this role
                aggregated_parsed = {"domain": d}
                for field in self._required_fields(role):
                    field_vals = [
                        e["eval"][field] for e in candidate_successful_evals
                        if field in e["eval"] and e["eval"][field] is not None
                    ]
                    if field_vals:
                        aggregated_parsed[field] = round(statistics.median(field_vals), 3)
                    else:
                        aggregated_parsed[field] = None

                all_crit_flags = sorted(list({
                    flag for e in candidate_successful_evals
                    for flag in e["eval"].get("critical_flags", [])
                }))
                all_kill_reasons = sorted(list({
                    k for e in candidate_successful_evals
                    for k in e["eval"].get("kill_reasons", [])
                }))
                all_crit_obj = sorted(list({
                    o for e in candidate_successful_evals
                    for o in e["eval"].get("critical_objections", [])
                }))
                aggregated_parsed["critical_flags"] = all_crit_flags
                aggregated_parsed["kill_reasons"] = all_kill_reasons
                aggregated_parsed["critical_objections"] = all_crit_obj

                verdicts = [e["eval"].get("verdict", "REVIEW") for e in candidate_successful_evals]
                reject_count = sum(1 for v in verdicts if v == "REJECT")
                keep_count = sum(1 for v in verdicts if v in ["KEEP", "STRONG_KEEP"])
                if reject_count > len(verdicts) / 2:
                    aggregated_parsed["verdict"] = "REJECT"
                elif keep_count > len(verdicts) / 2:
                    aggregated_parsed["verdict"] = "KEEP"
                else:
                    aggregated_parsed["verdict"] = "REVIEW"

                reasons = [e["eval"].get("reason", "") for e in candidate_successful_evals if e["eval"].get("reason")]
                aggregated_parsed["reason"] = " | ".join(reasons[:3])[:1200]

                mapped[d] = {
                    "status": "SUCCESS",
                    "provider": "xkiro_pool",
                    "model": candidate_succeeded_models[0] if candidate_succeeded_models else "xkiro_pool",
                    "models_expected": len(profiles),
                    "models_called": len(profiles),
                    "models_succeeded": len(candidate_succeeded_models),
                    "models_failed": len(candidate_failed_models),
                    "succeeded_models": candidate_succeeded_models,
                    "failed_models": candidate_failed_models,
                    "fallback_used": candidate_fallbacks_count > 0,
                    "fallbacks_used_count": candidate_fallbacks_count,
                    "latency_ms": None,
                    "raw_output": f"Pool evaluated {len(candidate_successful_evals)} independent models",
                    "parsed": aggregated_parsed,
                    "model_evaluations": candidate_successful_evals,
                    "error": None
                }
            else:
                mapped[d] = {
                    "status": "FAILED",
                    "provider": "xkiro_pool",
                    "model": None,
                    "models_expected": len(profiles),
                    "models_called": len(profiles),
                    "models_succeeded": 0,
                    "models_failed": len(profiles),
                    "succeeded_models": [],
                    "failed_models": [p.get("model") for p in profiles],
                    "fallback_used": False,
                    "fallbacks_used_count": 0,
                    "latency_ms": None,
                    "raw_output": None,
                    "parsed": None,
                    "model_evaluations": [],
                    "error": "all_models_in_role_failed"
                }

        return mapped

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

        # Multi-model pool coverage tracking across all 4 expert roles
        total_unique_expected = {p["model"] for r in ROLE_NAMES for p in self.role_profiles.get(r, [])}
        models_expected_count = len(total_unique_expected) if total_unique_expected else 57
        unique_succeeded_models = {
            m for r in ROLE_NAMES
            for m in traces.get(r, {}).get("succeeded_models", [])
        }
        unique_failed_models = {
            m for r in ROLE_NAMES
            for m in traces.get(r, {}).get("failed_models", [])
            if m not in unique_succeeded_models
        }
        total_fallbacks_used = sum(
            traces.get(r, {}).get("fallbacks_used_count", 0)
            for r in ROLE_NAMES
        )
        models_succeeded_count = len(unique_succeeded_models)
        models_failed_count = len(unique_failed_models)
        coverage_pct = round((models_succeeded_count / models_expected_count * 100.0), 1) if models_expected_count > 0 else 0.0
        coverage_status = "MODEL_COVERAGE_COMPLETE" if coverage_pct >= 100.0 else "MODEL_COVERAGE_INCOMPLETE"

        domain = str(candidate.get("domain") or candidate.get("domain_name") or "").lower()

        # Log exact required single-domain telemetry
        telemetry_log = (
            f"\nDOMAIN: {domain}\n"
            f"Expected models: {models_expected_count}\n"
            f"Completed models: {models_succeeded_count}\n"
            f"Fallbacks: {total_fallbacks_used}\n"
            f"Coverage: {coverage_pct:.1f}%\n"
            f"Status: {coverage_status}"
        )
        logger.info(telemetry_log)
        print(telemetry_log, flush=True)

        deterministic_fallback = False
        if not role_scores:
            # All models failed or no AI role succeeded: use deterministic evaluation fallback (Requirement 4)
            deterministic_fallback = True
            logger.warning("[MULTI-MODEL-FALLBACK-DETERMINISTIC] All models failed for %s. Using deterministic evaluation fallback.", domain)
            det_q = float(candidate.get("quality_score") or candidate.get("overall_score") or 68.0)
            consensus = round(det_q, 1)
            confidence = min(60.0, max(50.0, det_q))
            stats = {
                "median": consensus, "trimmed_mean": consensus, "stddev": 0.0,
                "range": 0.0, "judge_agreement": 75.0, "high_disagreement": False, "outlier_detected": False
            }
            disagreement_penalty = 0.0
            missing_penalty = 0.0
            red_score = 70.0
            red_penalty = 0.0
            missing = 0
        else:
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
            and (invented_subtype == "UNANCHORED" or not candidate.get("semantic_anchors"))
            and float(semantic_quality or 0) <= float(self.config.get("short_meaningless_semantic_max", 50.0))
            and float(commercial_quality or 0) <= float(self.config.get("short_meaningless_commercial_max", 60.0))
        )
        pron_score = float(candidate.get("pronunciation_score") or candidate.get("pronunciation") or (candidate.get("deterministic") or {}).get("pronunciation", 70.0))
        brand_judge_score = _clamp(parsed.get("brand", {}).get("brand_strength")) or 50.0
        atom_val = (candidate.get("atom") or {}).get("atom_domain_score") or candidate.get("atom_domain_score")
        pronounceable_not_brandable = (
            pron_score >= 74.0
            and len(label) <= 8
            and float(semantic_quality or 0) <= 45.0
            and (brand_judge_score <= 60.0 or (red_score is not None and float(red_score) <= 55.0))
            and (atom_val is None or float(atom_val) <= 7.5)
        )
        preliminary = None
        if consensus is not None:
            preliminary = float(consensus) - disagreement_penalty - missing_penalty - red_penalty
            if short_meaningless:
                preliminary -= 15.0
            if pronounceable_not_brandable:
                preliminary -= 18.0
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
            "models_expected": models_expected_count,
            "models_called": models_expected_count,
            "models_succeeded": models_succeeded_count,
            "models_failed": models_failed_count,
            "fallbacks_used": total_fallbacks_used,
            "model_coverage_pct": coverage_pct,
            "model_coverage_status": coverage_status,
            "deterministic_fallback": deterministic_fallback,
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
                "atom_alignment": 80.0,
                "model_agreement": stats.get("judge_agreement", 0.0),
                "arbiter_status": "PENDING",
                "verdict": "REVIEW",
            },
            "gibberish_risk_score": round(gibberish_risk, 3),
            "gibberish_quality_band": gibberish_band,
            "short_but_meaningless": short_meaningless,
            "pronounceable_not_brandable": pronounceable_not_brandable,
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
  "atom_alignment": 0-100,
  "model_agreement": 0-100,
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
                    "final_gibberish_risk", "final_ai_pattern_risk", "atom_alignment", "model_agreement"
                ):
                    val = _clamp(parsed.get(key))
                    if val is not None:
                        normalized["consensus"][key] = val
                normalized["consensus"]["major_strengths"] = _list(parsed.get("major_strengths") or parsed.get("strengths"))
                normalized["consensus"]["major_weaknesses"] = _list(parsed.get("major_weaknesses") or parsed.get("weaknesses"))
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

    async def evaluate_judges_batch(self, candidates: Sequence[Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executes the 4 expert judges (Linguistic, Brand, Commercial, Red Team) independently in batch.
        Produces robust preliminary consensus without running the Arbiter.
        """
        if not candidates:
            return {"candidates": {}, "prepared_map": {}, "summary": self._summary()}
        if not bool(self.config.get("enabled", True)):
            return {"candidates": {}, "prepared_map": {}, "summary": self._summary(disabled=True)}

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
        prepared_map = {str(c.get("domain", "")).lower(): c for c in prepared}
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

        return {"candidates": output, "prepared_map": prepared_map, "summary": self._summary()}

    async def run_arbiters_for_pool(
        self,
        prepared_map: Dict[str, Dict[str, Any]],
        candidates_eval: Dict[str, Dict[str, Any]],
        pool_size: Optional[int] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Runs Consensus Arbiter for the top candidate pool (which can now include Atom appraisal data).
        """
        if not bool(self.config.get("arbiter_enabled", True)) or not bool(self.config.get("arbiter", {}).get("enabled", True)):
            return candidates_eval

        limit = pool_size if pool_size is not None else int(self.config.get("arbiter_pool_size", 20))
        arbiter_pool = sorted(
            candidates_eval.values(),
            key=lambda x: float(x.get("consensus", {}).get("consensus_score") or 0.0),
            reverse=True
        )[:max(0, limit)]

        if arbiter_pool:
            arbiter_results = await asyncio.gather(
                *(self._run_arbiter(prepared_map.get(item["domain"], {"domain": item["domain"]}), item) for item in arbiter_pool),
                return_exceptions=True,
            )
            for result in arbiter_results:
                if not isinstance(result, Exception) and isinstance(result, dict) and "domain" in result:
                    candidates_eval[result["domain"]] = result

        return candidates_eval

    async def evaluate_batch(self, candidates: Sequence[Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Runs the complete multi-model pipeline: 4 expert judges followed by Arbiter."""
        judges_res = await self.evaluate_judges_batch(candidates, context=context)
        candidates_map = judges_res.get("candidates", {})
        prepared_map = judges_res.get("prepared_map", {})
        if candidates_map and bool(self.config.get("arbiter_enabled", True)):
            candidates_map = await self.run_arbiters_for_pool(prepared_map, candidates_map)
        return {"candidates": candidates_map, "summary": self._summary()}

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
