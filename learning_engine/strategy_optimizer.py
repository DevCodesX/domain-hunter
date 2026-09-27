"""
Strategy Performance & Dynamic Allocation Optimizer (Phase 3 & Phase 4)
Calculates per-strategy performance metrics:
- generated_count
- valid_count
- available_count
- premium_count
- high_quality_count
- high_ip_risk_count
- final_selected_count
- average_quality_score
- average_commercial_score
- average_brandability
- acceptance_rate

Implements dynamic budget rebalancing with:
- 75% exploitation budget to high-performing strategies
- 25% exploration budget to prevent strategy starvation / stagnation
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("StrategyOptimizer")

DEFAULT_STRATEGIES = [
    "ONE_WORD",
    "INVENTED",
    "SEMANTIC",
    "COMPOUND",
    "PREFIX_SUFFIX",
    "TREND",
    "KEYWORD_BRANDABLE"
]


class StrategyOptimizer:
    """
    Computes generation strategy yields and calculates dynamic candidate quotas.
    """

    @classmethod
    def calculate_strategy_performance(
        cls,
        candidates: List[Dict[str, Any]],
        feedback: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Aggregates run metrics per generation strategy.
        """
        stats: Dict[str, Dict[str, Any]] = {}
        for s in DEFAULT_STRATEGIES:
            stats[s] = {
                "generated_count": 0,
                "valid_count": 0,
                "available_count": 0,
                "premium_count": 0,
                "high_quality_count": 0,
                "high_ip_risk_count": 0,
                "final_selected_count": 0,
                "user_positive_count": 0,
                "user_negative_count": 0,
                "total_quality_score": 0.0,
                "total_commercial_score": 0.0,
                "total_brandability": 0.0,
                "average_quality_score": 0.0,
                "average_commercial_score": 0.0,
                "average_brandability": 0.0,
                "acceptance_rate": 0.0,
                "yield_rate": 0.0
            }

        # Build feedback map
        fb_map: Dict[str, List[str]] = {}
        if feedback:
            for fb in feedback:
                cid = fb.get("candidate_id") or fb.get("domain")
                act = fb.get("user_action", "").upper()
                if cid:
                    fb_map.setdefault(cid, []).append(act)

        for c in candidates:
            strat = c.get("generation_strategy", "INVENTED")
            if strat not in stats:
                stats[strat] = {
                    "generated_count": 0,
                    "valid_count": 0,
                    "available_count": 0,
                    "premium_count": 0,
                    "high_quality_count": 0,
                    "high_ip_risk_count": 0,
                    "final_selected_count": 0,
                    "user_positive_count": 0,
                    "user_negative_count": 0,
                    "total_quality_score": 0.0,
                    "total_commercial_score": 0.0,
                    "total_brandability": 0.0,
                    "average_quality_score": 0.0,
                    "average_commercial_score": 0.0,
                    "average_brandability": 0.0,
                    "acceptance_rate": 0.0,
                    "yield_rate": 0.0
                }

            st = stats[strat]
            st["generated_count"] += 1
            st["valid_count"] += 1

            # Availability
            avail_status = c.get("availability_status")
            if avail_status == "AVAILABLE_STANDARD":
                st["available_count"] += 1
            elif avail_status == "PREMIUM" or c.get("is_premium"):
                st["premium_count"] += 1

            # Quality & Scores
            q_score = float(c.get("quality_score") or c.get("overall_score") or 0.0)
            comm_score = float(c.get("commercial_score") or 0.0)
            brand_score = float(c.get("brandability_score") or 0.0)

            st["total_quality_score"] += q_score
            st["total_commercial_score"] += comm_score
            st["total_brandability"] += brand_score

            if q_score >= 75.0:
                st["high_quality_count"] += 1

            # IP Risk
            if c.get("ip_risk_level") in ["HIGH", "CRITICAL"]:
                st["high_ip_risk_count"] += 1

            # Final Selection
            if c.get("is_final_selected") or c.get("quality_tier") in ["TIER_A", "TIER_B"]:
                st["final_selected_count"] += 1

            # User Feedback
            cid = c.get("candidate_id") or c.get("domain")
            actions = fb_map.get(cid, [])
            if any(a in ["SHORTLISTED", "FAVORITED", "PURCHASED"] for a in actions):
                st["user_positive_count"] += 1
            elif "REJECTED" in actions:
                st["user_negative_count"] += 1

        # Calculate averages and acceptance rate
        for strat, st in stats.items():
            gen = st["generated_count"]
            if gen > 0:
                st["average_quality_score"] = round(st["total_quality_score"] / gen, 2)
                st["average_commercial_score"] = round(st["total_commercial_score"] / gen, 2)
                st["average_brandability"] = round(st["total_brandability"] / gen, 2)
                st["yield_rate"] = round((st["available_count"] / gen) * 100.0, 2)
                # Acceptance rate: final candidates / generated
                st["acceptance_rate"] = round((st["final_selected_count"] / gen) * 100.0, 2)

        return stats

    @classmethod
    def rebalance_quotas(
        cls,
        current_stats: Dict[str, Dict[str, Any]],
        target_budget: int = 1950,
        exploration_ratio: float = 0.25
    ) -> Dict[str, int]:
        """
        Rebalances generation quotas for the next run.
        Uses exploration/exploitation:
        - (1 - exploration_ratio): Exploitation pool (weighted by acceptance rate and quality)
        - exploration_ratio: Exploration pool (distributed equally across all strategies)
        """
        strategies = list(current_stats.keys()) if current_stats else DEFAULT_STRATEGIES
        num_strats = len(strategies)

        exploration_budget = int(target_budget * exploration_ratio)
        base_per_strat = exploration_budget // num_strats

        exploitation_budget = target_budget - exploration_budget

        weights: Dict[str, float] = {}
        for s in strategies:
            st = current_stats.get(s, {})
            acc = float(st.get("acceptance_rate", 1.0))
            avg_q = float(st.get("average_quality_score", 70.0)) / 100.0
            pos = float(st.get("user_positive_count", 0))
            w = max(0.05, (acc * 0.5) + (avg_q * 0.3) + (pos * 0.2))
            weights[s] = w

        sum_w = sum(weights.values()) or 1.0
        allocated_quotas: Dict[str, int] = {}

        for s in strategies:
            strat_exploit = int(exploitation_budget * (weights[s] / sum_w))
            allocated_quotas[s] = max(40, base_per_strat + strat_exploit)

        # Normalize to target_budget
        diff = target_budget - sum(allocated_quotas.values())
        if "INVENTED" in allocated_quotas:
            allocated_quotas["INVENTED"] += diff
        else:
            first_k = next(iter(allocated_quotas))
            allocated_quotas[first_k] += diff

        return allocated_quotas

    @classmethod
    def calculate_performance(
        cls,
        generated: int = 0,
        available: int = 0,
        accepted: int = 0
    ) -> Dict[str, float]:
        """
        Calculates yield rate and acceptance rate for a single strategy.
        yield_rate = available / generated
        acceptance_rate = accepted / available
        """
        yield_rate = (available / generated) if generated > 0 else 0.0
        acceptance_rate = (accepted / available) if available > 0 else 0.0
        return {
            "yield_rate": round(yield_rate, 4),
            "acceptance_rate": round(acceptance_rate, 4),
            "generated": generated,
            "available": available,
            "accepted": accepted
        }

    @classmethod
    def rebalance_quotas(
        cls,
        perf_data: Dict[str, Dict[str, Any]],
        exploration_floor: float = 0.04
    ) -> Dict[str, float]:
        """
        Returns normalized weight dict (values sum to 1.0) for strategy allocation.
        Each strategy gets at least `exploration_floor` weight to prevent starvation.
        
        perf_data keys: strategy names
        perf_data values: dicts with 'generated', 'available', 'accepted' counts
        """
        strategies = list(perf_data.keys())
        num_strats = len(strategies)

        raw_scores: Dict[str, float] = {}
        for s in strategies:
            st = perf_data[s]
            gen = float(st.get("generated", 1))
            avail = float(st.get("available", 0))
            accepted = float(st.get("accepted", 0))
            # Composite performance: 60% yield + 40% acceptance
            yield_rate = (avail / gen) if gen > 0 else 0.0
            accept_rate = (accepted / avail) if avail > 0 else 0.0
            raw_scores[s] = max(0.001, (yield_rate * 0.6) + (accept_rate * 0.4))

        total_raw = sum(raw_scores.values())

        # Allocate weights with exploration floor
        weights: Dict[str, float] = {}
        exploitable_budget = 1.0 - (exploration_floor * num_strats)

        for s in strategies:
            exploit_share = exploitable_budget * (raw_scores[s] / total_raw) if total_raw > 0 else (exploitable_budget / num_strats)
            weights[s] = round(exploration_floor + exploit_share, 6)

        # Normalize to exactly 1.0
        weight_sum = sum(weights.values())
        if weight_sum > 0:
            for s in strategies:
                weights[s] = round(weights[s] / weight_sum, 6)

        # Final normalization correction
        correction = 1.0 - sum(weights.values())
        if strategies:
            weights[strategies[0]] += correction

        return weights
