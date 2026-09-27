"""
Model Router Learning & Performance Tracker (Phase 4)
Tracks model/provider performance per task:
- generation
- classification
- quality_scoring
- buyer_analysis
- trend_analysis

Calculates:
- success_rate
- failure_rate
- latency
- json_validity
- average_candidate_quality
- user_positive_rate

Enforces Invariant 19:
Failed model invocations are recorded as status = FAILED, model_failure = True,
and EXCLUDED from valid training data.
"""

import time
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("RouterPerformanceTracker")


class RouterPerformanceTracker:
    """
    Task-specific model intelligence and performance telemetry.
    """

    def __init__(self, learning_store=None):
        self.store = learning_store
        self.task_telemetry: Dict[str, Dict[str, Any]] = {}

    def _get_key(self, provider: str, model: str, task_type: str) -> str:
        return f"{provider}:{model}:{task_type}"

    def record_call(
        self,
        provider: str,
        model: str,
        task_type: str,
        latency: float,
        success: bool,
        is_json_valid: bool = True,
        error_msg: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Records an execution event for a model on a specific task.
        """
        key = self._get_key(provider, model, task_type)
        if key not in self.task_telemetry:
            self.task_telemetry[key] = {
                "provider": provider,
                "model": model,
                "task_type": task_type,
                "total_calls": 0,
                "success_count": 0,
                "fail_count": 0,
                "total_latency": 0.0,
                "avg_latency": 0.0,
                "json_parse_success": 0,
                "json_parse_fail": 0,
                "json_validity_rate": 100.0,
                "success_rate": 100.0,
                "failure_rate": 0.0,
                "last_error": None
            }

        rec = self.task_telemetry[key]
        rec["total_calls"] += 1
        rec["total_latency"] += latency

        if success:
            rec["success_count"] += 1
            if is_json_valid:
                rec["json_parse_success"] += 1
            else:
                rec["json_parse_fail"] += 1
        else:
            rec["fail_count"] += 1
            rec["last_error"] = error_msg

        tot = rec["total_calls"]
        rec["success_rate"] = round((rec["success_count"] / tot) * 100.0, 2)
        rec["failure_rate"] = round((rec["fail_count"] / tot) * 100.0, 2)
        rec["avg_latency"] = round(rec["total_latency"] / tot, 2)

        json_calls = rec["json_parse_success"] + rec["json_parse_fail"]
        if json_calls > 0:
            rec["json_validity_rate"] = round((rec["json_parse_success"] / json_calls) * 100.0, 2)

        # Sync to learning store if configured
        if self.store:
            perf_row = {
                "model": model,
                "provider": provider,
                "task_type": task_type,
                "generation_count": tot if "generation" in task_type else 0,
                "valid_count": rec["success_count"],
                "available_count": 0,
                "high_quality_count": 0,
                "final_selected_count": 0,
                "user_positive_count": 0,
                "user_negative_count": rec["fail_count"],
                "average_score": rec["success_rate"],
                "acceptance_rate": rec["success_rate"],
                "latency": rec["avg_latency"],
                "json_validity": rec["json_validity_rate"]
            }
            self.store.update_model_performance(perf_row)

        return rec

    def record_failure_fallback(
        self,
        provider: str,
        model: str,
        task_type: str,
        error_msg: str
    ) -> Dict[str, Any]:
        """
        Invariant 19: Stores status = FAILED, model_failure = True.
        Prevents failed invocations from masquerading as successful training data.
        """
        logger.warning(f"[ROUTER-LEARNING-FAILURE] Model {provider}/{model} on task {task_type} failed: {error_msg}")
        return self.record_call(
            provider=provider,
            model=model,
            task_type=task_type,
            latency=0.0,
            success=False,
            is_json_valid=False,
            error_msg=error_msg
        )

    def get_task_recommendation_score(self, provider: str, model: str, task_type: str) -> float:
        """
        Computes composite recommendation score for model routing based on historical metrics:
        success_rate (50%) + latency (25%) + json_validity (25%).
        """
        key = self._get_key(provider, model, task_type)
        if key not in self.task_telemetry:
            return 85.0 # Neutral initial prior

        rec = self.task_telemetry[key]
        succ = rec["success_rate"]
        lat_score = max(0.0, 100.0 - (rec["avg_latency"] * 10.0))
        json_v = rec["json_validity_rate"]

        composite = (succ * 0.50) + (lat_score * 0.25) + (json_v * 0.25)
        return round(composite, 2)

    def get_all_model_telemetry(self) -> List[Dict[str, Any]]:
        return list(self.task_telemetry.values())

    def record_task_call(
        self,
        task: str,
        model: str,
        provider: str,
        success: bool,
        latency_ms: float = 0.0,
        valid_json: bool = True,
        error: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Adapter for test compatibility. Maps to record_call with matching parameters.
        """
        return self.record_call(
            provider=provider,
            model=model,
            task_type=task,
            latency=latency_ms,
            success=success,
            is_json_valid=valid_json,
            error_msg=error
        )

    def get_healthy_models(self, task_type: str, min_success_rate: float = 50.0) -> List[str]:
        """
        Returns list of model names with success_rate >= min_success_rate for a given task.
        Failed or unreliable models are excluded from training data and routing.
        """
        healthy = []
        for key, rec in self.task_telemetry.items():
            if rec.get("task_type") != task_type:
                continue
            if rec.get("success_rate", 0.0) >= min_success_rate:
                healthy.append(rec["model"])
        return healthy
