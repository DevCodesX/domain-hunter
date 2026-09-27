"""
Learning Store (Phase 4)
Handles persistence and querying for:
- domain_candidates
- domain_scores
- domain_checks
- domain_feedback
- generation_runs
- model_performance
- strategy_performance

Seamlessly integrates with Supabase cloud tables when available,
while maintaining a zero-dependency, durable local JSON store (learning_data.json)
so self-learning works in all environments (offline, local, test, production).
"""

import os
import json
import time
import logging
import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger("LearningStore")
LOCAL_STORE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "learning_data.json")


class LearningStore:
    def __init__(self, supabase_client=None, store_path: str = LOCAL_STORE_PATH, db_path: str = None):
        self.sb = supabase_client
        # db_path is an alias for store_path (test compatibility)
        self.store_path = db_path if db_path is not None else store_path
        self._init_local_store()

    def _init_local_store(self):
        if not os.path.exists(self.store_path):
            initial_data = {
                "domain_candidates": [],
                "domain_scores": [],
                "domain_checks": [],
                "domain_feedback": [],
                "generation_runs": [],
                "model_performance": [],
                "strategy_performance": {}
            }
            try:
                with open(self.store_path, "w", encoding="utf-8") as f:
                    json.dump(initial_data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Failed to initialize {self.store_path}: {e}")

    def _read_local_store(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self.store_path):
                with open(self.store_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error reading local store {self.store_path}: {e}")
        return {
            "domain_candidates": [],
            "domain_scores": [],
            "domain_checks": [],
            "domain_feedback": [],
            "generation_runs": [],
            "model_performance": [],
            "strategy_performance": {}
        }

    def _write_local_store(self, data: Dict[str, Any]):
        try:
            with open(self.store_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error writing local store {self.store_path}: {e}")

    # =========================================================================
    # 1. CANDIDATES & AUDIT PERSISTENCE
    # =========================================================================
    def save_candidate_records(
        self,
        candidates: List[Dict[str, Any]],
        run_id: str
    ):
        """
        Persists domain_candidates, domain_scores, and domain_checks records.
        """
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        local_data = self._read_local_store()

        cand_rows = []
        score_rows = []
        check_rows = []

        for c in candidates:
            cand_id = c.get("candidate_id") or f"cand_{run_id}_{len(local_data['domain_candidates']) + len(cand_rows) + 1:04d}"
            domain = c.get("domain") or c.get("domain_name", "")
            if not domain:
                continue

            # Candidate record
            cand_row = {
                "id": cand_id,
                "candidate_id": cand_id,
                "run_id": run_id,
                "domain": domain,
                "generation_strategy": c.get("generation_strategy", "INVENTED"),
                "source_concept": c.get("source_concept", ""),
                "source_language": c.get("source_language", "en"),
                "original_word": c.get("original_word", domain.replace(".com", "")),
                "original_meaning": c.get("original_meaning", ""),
                "semantic_concept": c.get("semantic_concept", "GENERAL_COMMERCIAL"),
                "naming_type": c.get("naming_type", "INVENTED"),
                "naming_subtype": c.get("naming_template") or c.get("morphology_type", "INVENTED"),
                "created_at": now_iso
            }
            cand_rows.append(cand_row)

            # Scores record
            q_break = c.get("quality_breakdown", {})
            f_scores = q_break.get("_float_scores", {}) if isinstance(q_break, dict) else {}
            score_row = {
                "candidate_id": cand_id,
                "domain": domain,
                "brandability": float(f_scores.get("brandability", c.get("brandability_score", 0))),
                "memorability": float(f_scores.get("memorability", 0)),
                "pronunciation": float(f_scores.get("pronunciation", 0)),
                "simplicity": float(f_scores.get("simplicity", 0)),
                "distinctiveness": float(f_scores.get("distinctiveness", 0)),
                "commercial_fit": float(f_scores.get("commercial", c.get("commercial_score", 0))),
                "candidate_trend_fit": float(f_scores.get("trend", c.get("trend_score", 0))),
                "buyer_clarity": float(c.get("buyer_clarity_score", 0)),
                "startup_naturalness": float(c.get("startup_naturalness_score", 0)),
                "overall_score": float(c.get("overall_score") or c.get("quality_score") or 0),
                "model": c.get("generator_model", "deterministic"),
                "provider": c.get("availability_provider", "local"),
                "model_version": c.get("generation_prompt_version", "v3.0"),
                "scored_at": now_iso
            }
            score_rows.append(score_row)

            # Checks record
            check_row = {
                "candidate_id": cand_id,
                "domain": domain,
                "availability_status": c.get("availability_status", "UNKNOWN"),
                "availability_verified": bool(c.get("availability_verified", False)),
                "availability_provider": c.get("availability_provider", "verisign_rdap"),
                "availability_checked_at": c.get("availability_checked_at") or c.get("checked_at") or now_iso,
                "premium_status": c.get("premium_status", "STANDARD"),
                "premium_provider": c.get("premium_provider", "verisign_rdap"),
                "ip_risk_level": c.get("ip_risk_level", "LOW"),
                "ip_check_status": c.get("ip_check_status", "CHECKED"),
                "existing_brand_status": "CLEAR" if c.get("ip_risk_level") in ["LOW", "NOT_CHECKED"] else "FLAGGED",
                "checked_at": now_iso
            }
            check_rows.append(check_row)

        # Update local storage
        local_data["domain_candidates"].extend(cand_rows)
        local_data["domain_scores"].extend(score_rows)
        local_data["domain_checks"].extend(check_rows)
        self._write_local_store(local_data)

        # Sync to Supabase if client available
        if self.sb:
            try:
                self.sb.table("domain_candidates").insert(cand_rows[:50]).execute()
            except Exception as e:
                logger.debug(f"Supabase candidate insert note: {e}")
            try:
                self.sb.table("domain_scores").insert(score_rows[:50]).execute()
            except Exception as e:
                logger.debug(f"Supabase scores insert note: {e}")
            try:
                self.sb.table("domain_checks").insert(check_rows[:50]).execute()
            except Exception as e:
                logger.debug(f"Supabase checks insert note: {e}")

        logger.info(f"[LEARNING-STORE] Persisted {len(cand_rows)} candidate records for run {run_id}.")

    # =========================================================================
    # 2. GENERATION RUNS PERSISTENCE
    # =========================================================================
    def save_generation_run(self, run_data: Dict[str, Any]):
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        local_data = self._read_local_store()

        row = {
            "id": run_data.get("run_id") or run_data.get("id") or f"run_{int(time.time())}",
            "run_date": run_data.get("run_date", now_iso),
            "concept_count": int(run_data.get("concept_count", 0)),
            "candidate_count": int(run_data.get("candidate_count", 0)),
            "strategy_distribution": run_data.get("strategy_distribution", {}),
            "availability_count": int(run_data.get("availability_count", 0)),
            "premium_count": int(run_data.get("premium_count", 0)),
            "ip_blocked_count": int(run_data.get("ip_blocked_count", 0)),
            "final_count": int(run_data.get("final_count", 0)),
            "created_at": now_iso
        }

        local_data["generation_runs"].append(row)
        self._write_local_store(local_data)

        if self.sb:
            try:
                self.sb.table("generation_runs").insert([row]).execute()
            except Exception as e:
                logger.debug(f"Supabase generation_runs insert note: {e}")

    # =========================================================================
    # 3. USER FEEDBACK PERSISTENCE
    # =========================================================================
    def record_feedback(
        self,
        candidate_id: str,
        user_action: str,
        rejection_reason: Optional[str] = None,
        notes: Optional[str] = None,
        domain: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Records user feedback:
        user_action in: VIEWED, SHORTLISTED, REJECTED, FAVORITED, PURCHASED, IGNORED
        """
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        local_data = self._read_local_store()

        # Sanitize action — accept both short and long forms
        action = user_action.upper().strip()
        # Normalize short forms to canonical forms
        action_aliases = {
            "SHORTLIST": "SHORTLISTED",
            "REJECT": "REJECTED",
            "FAVORITE": "FAVORITED",
            "PURCHASE": "PURCHASED",
            "IGNORE": "IGNORED",
            "VIEW": "VIEWED"
        }
        action = action_aliases.get(action, action)
        valid_actions = {"VIEWED", "SHORTLISTED", "REJECTED", "FAVORITED", "PURCHASED", "IGNORED"}
        if action not in valid_actions:
            action = "VIEWED"

        feedback_entry = {
            "id": f"fb_{int(time.time() * 1000)}",
            "candidate_id": candidate_id,
            "domain": domain or "",
            "user_action": action,
            "rejection_reason": rejection_reason,
            "notes": notes,
            "created_at": now_iso
        }

        local_data["domain_feedback"].append(feedback_entry)
        self._write_local_store(local_data)

        if self.sb:
            try:
                self.sb.table("domain_feedback").insert([feedback_entry]).execute()
            except Exception as e:
                logger.debug(f"Supabase feedback insert note: {e}")

        logger.info(f"[FEEDBACK] Recorded feedback for {candidate_id} ({domain}): {action} {rejection_reason or ''}")
        return feedback_entry

    def get_feedback(self, limit: int = 1000) -> List[Dict[str, Any]]:
        local_data = self._read_local_store()
        feedbacks = local_data.get("domain_feedback", [])
        return feedbacks[-limit:]

    def get_feedback_count(self) -> int:
        local_data = self._read_local_store()
        return len(local_data.get("domain_feedback", []))

    def get_feedback_summary(self) -> Dict[str, Any]:
        """
        Returns aggregated feedback summary with counts per action type
        and a breakdown of rejection reasons.
        """
        feedbacks = self.get_feedback()
        summary: Dict[str, Any] = {
            "total": len(feedbacks),
            "shortlist": 0,
            "shortlisted": 0,
            "favorite": 0,
            "favorited": 0,
            "reject": 0,
            "rejected": 0,
            "viewed": 0,
            "purchased": 0,
            "ignored": 0,
            "reasons": {}
        }
        for fb in feedbacks:
            action = fb.get("user_action", "").upper().strip()
            if action in ["SHORTLISTED", "SHORTLIST"]:
                summary["shortlist"] += 1
                summary["shortlisted"] += 1
            elif action in ["FAVORITED", "FAVORITE"]:
                summary["favorite"] += 1
                summary["favorited"] += 1
            elif action in ["REJECTED", "REJECT"]:
                summary["reject"] += 1
                summary["rejected"] += 1
                reason = fb.get("rejection_reason")
                if reason:
                    summary["reasons"][reason] = summary["reasons"].get(reason, 0) + 1
            elif action == "VIEWED":
                summary["viewed"] += 1
            elif action == "PURCHASED":
                summary["purchased"] += 1
            elif action == "IGNORED":
                summary["ignored"] += 1
        return summary

    # =========================================================================
    # 4. TRAINING DATASET ACCESS
    # =========================================================================
    def get_all_records(self) -> Dict[str, Any]:
        return self._read_local_store()

    # =========================================================================
    # 5. MODEL & STRATEGY PERFORMANCE PERSISTENCE
    # =========================================================================
    def update_model_performance(self, model_perf_record: Dict[str, Any]):
        local_data = self._read_local_store()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        model_perf_record["updated_at"] = now_iso

        # Update or append
        existing = local_data.get("model_performance", [])
        key = f"{model_perf_record.get('provider')}:{model_perf_record.get('model')}:{model_perf_record.get('task_type')}"
        
        updated = False
        for i, row in enumerate(existing):
            row_key = f"{row.get('provider')}:{row.get('model')}:{row.get('task_type')}"
            if row_key == key:
                existing[i] = model_perf_record
                updated = True
                break
        if not updated:
            existing.append(model_perf_record)

        local_data["model_performance"] = existing
        self._write_local_store(local_data)

        if self.sb:
            try:
                self.sb.table("model_performance").upsert([model_perf_record]).execute()
            except Exception as e:
                logger.debug(f"Supabase model_performance upsert note: {e}")

    def get_model_performance(self) -> List[Dict[str, Any]]:
        local_data = self._read_local_store()
        return local_data.get("model_performance", [])

    def update_strategy_performance(self, stats: Dict[str, Dict[str, Any]]):
        local_data = self._read_local_store()
        local_data["strategy_performance"] = stats
        self._write_local_store(local_data)

    def get_strategy_performance(self) -> Dict[str, Dict[str, Any]]:
        local_data = self._read_local_store()
        return local_data.get("strategy_performance", {})
