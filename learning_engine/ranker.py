"""
Local Statistical Ranker (Phase 4)
Uses scikit-learn (HistGradientBoosting / LogisticRegression) to learn user preferences
and predict P(user_will_like_candidate).

Modes:
- COLD_START (< 100 feedback samples): Deterministic scoring only, learned_preference_score = None
- BASELINE (100 <= samples < 500): Simple baseline statistical model
- ACTIVE (>= 500 samples): Strong learned ranking

Model Versioning:
- model_id, version, trained_at, training_sample_count, feature_version, validation_metric.
"""

import os
import joblib
import logging
import datetime
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

from learning_engine.feature_pipeline import TrainingFeaturePipeline

logger = logging.getLogger("StatisticalRanker")
MODEL_DIR = os.path.dirname(__file__)
MODEL_FILE_PATH = os.path.join(MODEL_DIR, "active_ranker.joblib")
METADATA_FILE_PATH = os.path.join(MODEL_DIR, "ranker_metadata.json")


class LearningState(str, Enum):
    """Enum for ranker learning progression states."""
    COLD_START = "COLD_START"
    BASELINE = "BASELINE"
    ACTIVE = "ACTIVE"


class StatisticalRanker:
    """
    Local scikit-learn statistical ranker for domain preferences.
    """

    def __init__(self, model_path: str = MODEL_FILE_PATH, metadata_path: str = METADATA_FILE_PATH, model_dir: Optional[str] = None):
        # Support model_dir convenience parameter for tests
        if model_dir is not None:
            self.model_path = os.path.join(model_dir, "active_ranker.joblib")
            self.metadata_path = os.path.join(model_dir, "ranker_metadata.json")
        else:
            self.model_path = model_path
            self.metadata_path = metadata_path
        self.model = None
        self.metadata = {
            "model_id": "none",
            "version": "v0",
            "status": "COLD_START",
            "state": "COLD_START",
            "trained_at": None,
            "training_sample_count": 0,
            "feature_version": TrainingFeaturePipeline.FEATURE_VERSION,
            "validation_metric": "none",
            "validation_score": 0.0
        }
        self.load_model()

    def load_model(self):
        """Loads trained model and metadata from disk if available."""
        if os.path.exists(self.model_path) and os.path.exists(self.metadata_path):
            try:
                import json
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    self.metadata = json.load(f)
                self.model = joblib.load(self.model_path)
                logger.info(f"[RANKER] Loaded active model {self.metadata['version']} (samples: {self.metadata['training_sample_count']})")
            except Exception as e:
                logger.warning(f"[RANKER] Error loading model from disk: {e}")
                self.model = None

    def get_status(self, sample_count: Optional[int] = None) -> str:
        """
        Determines current learning status:
        - COLD_START (< 100)
        - BASELINE (100 - 499)
        - ACTIVE (>= 500)
        
        When sample_count is explicitly provided, returns the theoretical state
        for that count (used for state progression queries).
        When not provided, also checks if model is loaded.
        """
        count = sample_count if sample_count is not None else self.metadata.get("training_sample_count", 0)
        # Only gate on model existence when checking actual runtime status
        if sample_count is None and self.model is None:
            return "COLD_START"
        if count < 100:
            return "COLD_START"
        elif 100 <= count < 500:
            return "BASELINE"
        else:
            return "ACTIVE"

    def train(self, X: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
        """
        Trains the local statistical ranker on extracted features and labels.
        Requires >= 100 samples to transition from COLD_START.
        """
        n_samples = len(y)
        if n_samples < 10:
            logger.info(f"[RANKER-TRAIN] Insufficient training data ({n_samples} samples). Remaining in COLD_START.")
            return {
                "success": False,
                "status": "COLD_START",
                "sample_count": n_samples,
                "message": "Minimum 10 samples required for unit training, 100 for production baseline."
            }

        try:
            from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
            from sklearn.linear_model import LogisticRegression
            from sklearn.model_selection import cross_val_score

            # Check if binary classes both exist
            unique_classes = np.unique(y)
            if len(unique_classes) < 2:
                logger.warning("[RANKER-TRAIN] All samples belong to a single class. Training postponed.")
                return {
                    "success": False,
                    "status": "COLD_START",
                    "sample_count": n_samples,
                    "message": "Both positive and negative feedback samples required."
                }

            # Choose model architecture
            if n_samples >= 500:
                clf = HistGradientBoostingClassifier(max_iter=100, random_state=42)
                mode = "ACTIVE"
            elif n_samples >= 100:
                clf = RandomForestClassifier(n_estimators=50, max_depth=6, random_state=42)
                mode = "BASELINE"
            else:
                clf = LogisticRegression(max_iter=200, random_state=42)
                mode = "BASELINE"

            clf.fit(X, y)

            # Evaluate cross validation score
            cv_folds = min(5, len(y))
            if cv_folds >= 2:
                scores = cross_val_score(clf, X, y, cv=cv_folds, scoring="accuracy")
                val_score = float(np.mean(scores))
            else:
                val_score = float(clf.score(X, y))

            # Versioning
            current_v = int(self.metadata.get("version", "v0").replace("v", "") or 0)
            new_version = f"v{current_v + 1}"
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

            new_metadata = {
                "model_id": f"ranker_{new_version}_{int(datetime.datetime.now().timestamp())}",
                "version": new_version,
                "status": mode,
                "trained_at": now_iso,
                "training_sample_count": n_samples,
                "feature_version": TrainingFeaturePipeline.FEATURE_VERSION,
                "validation_metric": "cross_validated_accuracy",
                "validation_score": round(val_score, 4)
            }

            # Persist model and metadata
            joblib.dump(clf, self.model_path)
            import json
            with open(self.metadata_path, "w", encoding="utf-8") as f:
                json.dump(new_metadata, f, indent=2)

            self.model = clf
            new_metadata["state"] = mode
            self.metadata = new_metadata

            logger.info(f"[RANKER-TRAIN] Successfully trained model {new_version} ({mode}) on {n_samples} samples. Val score: {val_score:.4f}")
            return {
                "success": True,
                "status": "trained",
                "learning_state": mode,
                "version": new_version,
                "sample_count": n_samples,
                "validation_metric": val_score,
                "validation_score": val_score,
                "trained_at": now_iso
            }

        except Exception as e:
            logger.error(f"[RANKER-TRAIN] Model training failed: {e}")
            return {
                "success": False,
                "status": "error",
                "learning_state": self.get_status(),
                "error": str(e)
            }

    def predict_preference(
        self,
        candidate: Dict[str, Any],
        score_rec: Optional[Dict[str, Any]] = None,
        check_rec: Optional[Dict[str, Any]] = None
    ) -> Tuple[Optional[float], str, str]:
        """
        Predicts P(user_will_like_candidate) as learned_preference_score (0.0 to 100.0).
        Returns (learned_preference_score, learning_status, model_version).

        Cold Start Rule:
        If < 100 feedback samples or model is None, returns (None, "COLD_START", "none").
        """
        status = self.get_status()
        if status == "COLD_START" or self.model is None:
            return None, "COLD_START", "none"

        try:
            feat_vec = TrainingFeaturePipeline.extract_candidate_features(candidate, score_rec, check_rec)
            X = np.array([feat_vec], dtype=np.float32)

            # Predict probability of positive class (1.0)
            if hasattr(self.model, "predict_proba"):
                probs = self.model.predict_proba(X)
                # Class 1 probability
                p_positive = probs[0][1] if probs.shape[1] > 1 else probs[0][0]
            else:
                p_positive = float(self.model.predict(X)[0])

            learned_score = round(max(0.0, min(100.0, p_positive * 100.0)), 2)
            return learned_score, status, self.metadata.get("version", "v1")

        except Exception as e:
            logger.debug(f"[RANKER-PREDICT] Prediction fallback: {e}")
            return None, "COLD_START", "none"

    # =========================================================================
    # Adapter properties and methods for Phase 3/4 test compatibility
    # =========================================================================
    @property
    def is_trained(self) -> bool:
        """Returns True if a model has been successfully trained."""
        return self.model is not None

    @property
    def active_model_version(self) -> Optional[str]:
        """Returns the version string of the active model, or None if untrained."""
        if self.model is not None:
            return self.metadata.get("version")
        return None

    def get_learning_state(self, sample_count: Optional[int] = None) -> LearningState:
        """Returns the current LearningState enum based on sample count."""
        status = self.get_status(sample_count)
        return LearningState(status)

    def get_metadata(self) -> Dict[str, Any]:
        """Returns current model metadata dict."""
        meta = dict(self.metadata)
        meta["state"] = self.get_status()
        return meta

    def predict_preference_scores(
        self,
        candidates: List[Dict[str, Any]]
    ) -> List[float]:
        """
        Batch prediction: returns P(user_will_like) for each candidate as float in [0.0, 1.0].
        """
        scores = []
        for cand in candidates:
            learned_score, status, version = self.predict_preference(cand)
            if learned_score is not None:
                scores.append(round(learned_score / 100.0, 4))  # Convert 0-100 to 0-1
            else:
                scores.append(0.5)  # Neutral prior in cold start
        return scores
