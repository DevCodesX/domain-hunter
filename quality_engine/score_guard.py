"""
Phase 2.75B Production Integrity Guard: Score Distribution & Cluster Guard
Calculates statistical distribution metrics across a scored candidate pool:
- unique_overall_scores
- unique_brandability_scores
- unique_trend_scores
- unique_commercial_scores
- mean, median, standard_deviation, min, max
- identical_score_clusters (>= 3 unrelated candidates sharing identical brandability, trend, and commercial scores)

If >= 3 unrelated candidates share identical scores, marks:
SCORING_INTEGRITY_WARNING
Exposed in GET /api/quality/debug_report.
"""

import statistics
import collections
from typing import List, Dict, Any, Tuple

class ScoreDistributionGuard:
    """
    Evaluates batch score distributions to ensure genuine, candidate-specific
    floating-point score separation without artificial clustering.
    """

    @classmethod
    def audit_scored_batch(cls, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Conducts post-scoring distribution analysis and cluster detection.
        """
        if not candidates:
            return {
                "candidate_count": 0,
                "integrity_status": "PASS",
                "has_identical_clustering": False,
                "identical_score_clusters": [],
                "unique_overall_scores": 0,
                "unique_brandability_scores": 0,
                "unique_trend_scores": 0,
                "unique_commercial_scores": 0,
                "brand_distribution": cls._calc_stats([]),
                "trend_distribution": cls._calc_stats([]),
                "commercial_distribution": cls._calc_stats([]),
                "overall_distribution": cls._calc_stats([])
            }

        brand_scores: List[float] = []
        trend_scores: List[float] = []
        comm_scores: List[float] = []
        overall_scores: List[float] = []

        # Map tuple of (brand, trend, commercial) to list of domains
        tuple_clusters: Dict[Tuple[float, float, float], List[str]] = collections.defaultdict(list)

        for c in candidates:
            domain = c.get("domain") or c.get("domain_name", "")
            q_breakdown = c.get("quality_breakdown") or {}
            f_scores = q_breakdown.get("_float_scores") or {}

            # High-resolution floating point score
            brand = float(f_scores.get("brandability", c.get("brandability_score", 0.0)))
            trend = float(f_scores.get("trend", c.get("trend_score", 0.0)))
            comm = float(f_scores.get("commercial", c.get("commercial_score", 0.0)))
            overall = float(f_scores.get("overall_score", c.get("overall_score", c.get("quality_score", 0.0))))

            b_rounded = round(brand, 2)
            t_rounded = round(trend, 2)
            c_rounded = round(comm, 2)
            o_rounded = round(overall, 2)

            brand_scores.append(b_rounded)
            trend_scores.append(t_rounded)
            comm_scores.append(c_rounded)
            overall_scores.append(o_rounded)

            score_key = (b_rounded, t_rounded, c_rounded)
            tuple_clusters[score_key].append(domain)

        # Detect identical score clusters (>= 3 candidates sharing identical brand, trend, and comm)
        identical_clusters = []
        for (b, t, c_val), domains in tuple_clusters.items():
            if len(domains) >= 3:
                identical_clusters.append({
                    "brandability": b,
                    "trend": t,
                    "commercial": c_val,
                    "cluster_size": len(domains),
                    "domains": domains
                })

        has_clustering = len(identical_clusters) > 0
        integrity_status = "SCORING_INTEGRITY_WARNING" if has_clustering else "PASS"

        brand_stats = cls._calc_stats(brand_scores)
        trend_stats = cls._calc_stats(trend_scores)
        comm_stats = cls._calc_stats(comm_scores)
        overall_stats = cls._calc_stats(overall_scores)

        return {
            "candidate_count": len(candidates),
            "integrity_status": integrity_status,
            "has_identical_clustering": has_clustering,
            "cluster_count": len(identical_clusters),
            "identical_score_clusters": identical_clusters,
            "unique_overall_scores": overall_stats["unique_scores"],
            "unique_brandability_scores": brand_stats["unique_scores"],
            "unique_trend_scores": trend_stats["unique_scores"],
            "unique_commercial_scores": comm_stats["unique_scores"],
            "brand_distribution": brand_stats,
            "trend_distribution": trend_stats,
            "commercial_distribution": comm_stats,
            "overall_distribution": overall_stats
        }

    @staticmethod
    def _calc_stats(arr: List[float]) -> Dict[str, Any]:
        if not arr:
            return {
                "unique_scores": 0,
                "mean": 0.0,
                "median": 0.0,
                "standard_deviation": 0.0,
                "min": 0.0,
                "max": 0.0
            }
        unique_c = len(set(arr))
        mean_val = statistics.mean(arr)
        median_val = statistics.median(arr)
        stdev_val = statistics.stdev(arr) if len(arr) > 1 else 0.0
        return {
            "unique_scores": unique_c,
            "mean": round(mean_val, 2),
            "median": round(median_val, 2),
            "standard_deviation": round(stdev_val, 2),
            "min": round(min(arr), 2),
            "max": round(max(arr), 2)
        }
