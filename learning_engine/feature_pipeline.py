"""
Training Dataset Feature Pipeline (Phase 4)
Extracts 21 structured features from candidates for the local statistical ranker:
- length
- word_count
- syllables
- vowel_ratio
- phonetic_score
- naming_type
- naming_subtype
- dictionary_status
- brandability
- memorability
- pronunciation
- simplicity
- distinctiveness
- commercial_fit
- trend_fit
- buyer_clarity
- startup_naturalness
- generation_strategy
- semantic_distance
- ip_risk
- existing_brand_status

Target:
user_positive (1 for SHORTLISTED, FAVORITED, PURCHASED; 0 for REJECTED; etc.)
Note: IP risk is extracted as an informational feature but is NEVER the learned optimization target.
"""

import re
from typing import Dict, Any, List, Tuple, Optional
import numpy as np


class TrainingFeaturePipeline:
    """
    Transforms candidate metadata and user feedback into vectorized training matrices (X, y).
    """

    FEATURE_VERSION = "feat_v3.0"

    NAMING_TYPE_ENCODING: Dict[str, int] = {
        "ONE_WORD": 1,
        "REAL_WORD": 1,
        "REAL_FOREIGN_WORD": 2,
        "FOREIGN_WORD": 2,
        "COMPOUND": 3,
        "INVENTED": 4,
        "PREFIX_SUFFIX": 5,
        "HYBRID": 6,
        "SEMANTIC_BRANDABLE": 7,
        "RANDOM": 0,
        "OTHER": 0
    }

    STRATEGY_ENCODING: Dict[str, int] = {
        "ONE_WORD": 1,
        "INVENTED": 2,
        "SEMANTIC": 3,
        "COMPOUND": 4,
        "PREFIX_SUFFIX": 5,
        "TREND": 6,
        "KEYWORD_BRANDABLE": 7,
        "OTHER": 0
    }

    IP_RISK_ENCODING: Dict[str, int] = {
        "LOW": 0,
        "NOT_CHECKED": 0,
        "MEDIUM": 1,
        "HIGH": 2,
        "CRITICAL": 3
    }

    FEATURE_NAMES: List[str] = [
        "length",
        "word_count",
        "syllables",
        "vowel_ratio",
        "phonetic_score",
        "naming_type_code",
        "naming_subtype_code",
        "dictionary_status",
        "brandability",
        "memorability",
        "pronunciation",
        "simplicity",
        "distinctiveness",
        "commercial_fit",
        "trend_fit",
        "buyer_clarity",
        "startup_naturalness",
        "generation_strategy_code",
        "semantic_distance",
        "ip_risk_code",
        "existing_brand_status_code"
    ]

    @classmethod
    def extract_candidate_features(cls, candidate: Dict[str, Any], score_rec: Optional[Dict[str, Any]] = None, check_rec: Optional[Dict[str, Any]] = None) -> List[float]:
        """
        Extracts a single numerical feature vector from candidate records.
        """
        domain = candidate.get("domain") or candidate.get("domain_name", "")
        label = domain.lower().replace(".com", "").strip()

        # 1. Structural features
        length = float(len(label))
        words_split = re.findall(r"[a-z]+", label)
        word_count = float(len(words_split)) if words_split else 1.0

        vowels = sum(1 for ch in label if ch in "aeiou")
        vowel_ratio = float(vowels / len(label)) if len(label) > 0 else 0.4
        
        # Approximate syllables count
        syllables = float(max(1, len(re.findall(r"[aeiouy]+", label))))

        # Pronunciation & phonetics
        phonetic_score = float(candidate.get("radio_test_score") or (80.0 if vowel_ratio >= 0.3 else 50.0))

        # Categorical codes
        nt = str(candidate.get("naming_type", "INVENTED")).upper()
        naming_type_code = float(cls.NAMING_TYPE_ENCODING.get(nt, 4))
        naming_subtype_code = float(len(label) % 5)

        # Dictionary status
        is_dict = 1.0 if nt in ["ONE_WORD", "REAL_WORD", "COMPOUND"] else 0.0

        # Score features
        s_data = score_rec or candidate
        q_break = s_data.get("quality_breakdown", {})
        f_scores = q_break.get("_float_scores", {}) if isinstance(q_break, dict) else {}

        brandability = float(f_scores.get("brandability", s_data.get("brandability", s_data.get("brandability_score", 70.0))))
        memorability = float(f_scores.get("memorability", 70.0))
        pronunciation = float(f_scores.get("pronunciation", 70.0))
        simplicity = float(f_scores.get("simplicity", 70.0))
        distinctiveness = float(f_scores.get("distinctiveness", 70.0))
        commercial_fit = float(f_scores.get("commercial", s_data.get("commercial_fit", s_data.get("commercial_score", 70.0))))
        trend_fit = float(f_scores.get("trend", s_data.get("candidate_trend_fit", s_data.get("trend_score", 70.0))))
        buyer_clarity = float(s_data.get("buyer_clarity", s_data.get("buyer_clarity_score", 70.0)))
        startup_naturalness = float(s_data.get("startup_naturalness", s_data.get("startup_naturalness_score", 70.0)))

        # Strategy code
        strat = str(candidate.get("generation_strategy", "INVENTED")).upper()
        strat_code = float(cls.STRATEGY_ENCODING.get(strat, 0))

        # Semantic distance (approximated 0.0 to 1.0)
        sem_dist = float(candidate.get("semantic_distance", 0.35))

        # IP check & brand status
        c_data = check_rec or candidate
        ip_lvl = str(c_data.get("ip_risk_level", "LOW")).upper()
        ip_risk_code = float(cls.IP_RISK_ENCODING.get(ip_lvl, 0))
        brand_stat = 1.0 if c_data.get("existing_brand_status") == "FLAGGED" else 0.0

        return [
            length,
            word_count,
            syllables,
            vowel_ratio,
            phonetic_score,
            naming_type_code,
            naming_subtype_code,
            is_dict,
            brandability,
            memorability,
            pronunciation,
            simplicity,
            distinctiveness,
            commercial_fit,
            trend_fit,
            buyer_clarity,
            startup_naturalness,
            strat_code,
            sem_dist,
            ip_risk_code,
            brand_stat
        ]

    @classmethod
    def build_dataset_from_store(
        cls,
        store_data: Dict[str, Any]
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """
        Constructs (X, y, candidate_ids) from stored candidates and user feedback.
        Only candidates with explicit feedback or clear positive/negative labels are included.
        Failed models or unverified candidates are cleanly excluded.
        """
        candidates = store_data.get("domain_candidates", [])
        scores = {s.get("candidate_id"): s for s in store_data.get("domain_scores", [])}
        checks = {c.get("candidate_id"): c for c in store_data.get("domain_checks", [])}
        feedback = store_data.get("domain_feedback", [])

        # Map feedback to target label:
        # SHORTLISTED, FAVORITED, PURCHASED -> 1.0
        # REJECTED -> 0.0
        # VIEWED / IGNORED without positive action -> ignored or 0.0
        feedback_by_cand: Dict[str, List[str]] = {}
        for fb in feedback:
            cid = fb.get("candidate_id")
            act = fb.get("user_action", "").upper()
            if cid:
                feedback_by_cand.setdefault(cid, []).append(act)

        X_list = []
        y_list = []
        ids_list = []

        for cand in candidates:
            cid = cand.get("candidate_id") or cand.get("id")
            if not cid:
                continue

            actions = feedback_by_cand.get(cid, [])
            if not actions:
                continue

            # Determine label
            if any(a in ["SHORTLISTED", "FAVORITED", "PURCHASED"] for a in actions):
                target = 1.0
            elif "REJECTED" in actions:
                target = 0.0
            else:
                continue

            s_rec = scores.get(cid)
            c_rec = checks.get(cid)

            # Exclude failed models from training data (Invariant 19)
            if s_rec and (s_rec.get("status") == "FAILED" or s_rec.get("model_failure") is True):
                continue

            feat_vec = cls.extract_candidate_features(cand, s_rec, c_rec)
            X_list.append(feat_vec)
            y_list.append(target)
            ids_list.append(cid)

        if not X_list:
            return np.empty((0, len(cls.FEATURE_NAMES))), np.empty((0,)), []

        return np.array(X_list, dtype=np.float32), np.array(y_list, dtype=np.float32), ids_list

    @classmethod
    def create_training_dataset(
        cls,
        candidates: List[Dict[str, Any]],
        feedback_records: List[Dict[str, Any]]
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Creates training dataset directly from candidate dicts and feedback records.
        
        Args:
            candidates: List of candidate dicts with scoring fields
            feedback_records: List of dicts with 'candidate_id' and 'user_action'
        
        Returns:
            (X, y) where X is feature matrix and y is binary labels
        """
        # Build feedback lookup
        feedback_map: Dict[str, str] = {}
        for fb in feedback_records:
            cid = fb.get("candidate_id", "")
            action = fb.get("user_action", "").upper()
            feedback_map[cid] = action

        X_list = []
        y_list = []

        for cand in candidates:
            cid = cand.get("id") or cand.get("candidate_id", "")
            action = feedback_map.get(cid, "")
            if not action:
                continue

            # Determine label
            if action in ["SHORTLISTED", "FAVORITED", "FAVORITE", "PURCHASED", "SHORTLIST"]:
                label = 1
            elif action in ["REJECTED", "REJECT"]:
                label = 0
            else:
                continue

            feat_vec = cls.extract_candidate_features(cand)
            X_list.append(feat_vec)
            y_list.append(label)

        if not X_list:
            return np.empty((0, len(cls.FEATURE_NAMES))), np.empty((0,))

        return np.array(X_list, dtype=np.float32), np.array(y_list, dtype=np.int32)
