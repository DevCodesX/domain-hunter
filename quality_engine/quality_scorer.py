"""
QualityScorer: Comprehensive multi-dimensional scoring model.
Phase 2.75B Revised:
- High Score Resolution (floats stored internally to eliminate artificial score clustering)
- Separate Concept Trend Score from Candidate Trend Fit Score
- Separate Category Opportunity Score from Candidate Commercial Fit
- Pattern Saturation Penalty & AI-Naming Artifact Score Integration
- Morphology and Phonetic Cluster ID Tracking
- True Brandability Evaluation
"""

import re
import math
from typing import Dict, Any, Optional
from quality_engine.config import get_quality_weights
from quality_engine.brand_refinement import (
    WordGlueDetector,
    AIGeneratedFeelDetector,
    CompoundNaturalnessScorer,
    BuyerClarityScorer,
    CandidateTrendFitScorer
)
from quality_engine.morphology_classifier import MorphologyClassifier
from quality_engine.phonetic_engine import PhoneticEngine
from quality_engine.ai_evaluator import compute_deterministic_linguistic_evaluation
from quality_engine.invented_quality import calculate_invented_semantic_relevance



class QualityScorer:
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or get_quality_weights()

    @staticmethod
    def _apply_soft_ceiling(val: float, ceiling: float, span: float = 6.0) -> float:
        """
        Compresses values approaching or exceeding the ceiling monotonically,
        strictly capping below or at ceiling while preserving candidate-specific micro-variance.
        """
        if val <= ceiling - span:
            return round(val, 3)
        excess = max(0.0, val - (ceiling - span))
        compressed = (ceiling - span) + span * (1.0 - math.exp(-excess / max(0.1, span)))
        return round(min(ceiling, compressed), 3)

    def score_candidate(
        self,
        domain: str,
        structural_features: Dict[str, Any],
        one_word_features: Dict[str, Any],
        naming_type_info: Dict[str, Any],
        ai_evaluation: Optional[Dict[str, Any]] = None,
        concept: str = "",
        market_category: str = "AI & Technology",
        concept_trend_relevance: float = 85.0,
        category_opportunity_score: float = 85.0,
        pattern_diversity_score: float = 100.0,
        ai_naming_artifact_score: Optional[float] = None,
        morphology_type: Optional[str] = None,
        phonetic_cluster_id: Optional[str] = None,
        multi_model_evaluation: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Calculates all sub-scores and the aggregated quality_score with high floating-point resolution.
        Integrates deterministic linguistic signals, word-glue detection, AI-feel detection,
        pattern diversity penalties, and subjective AI evaluations.
        """
        label = structural_features.get("label", domain.replace(".com", "").strip().lower())
        char_len = structural_features.get("char_length", len(label))
        naming_type = naming_type_info.get("naming_type", "INVENTED")

        # Section 8: Explicit failure handling — never assign high default scores if scoring fails
        if ai_evaluation and (ai_evaluation.get("status") == "SCORING_FAILED" or ai_evaluation.get("evaluation_status") == "SCORING_FAILED"):
            return {
                "domain": domain,
                "status": "SCORING_FAILED",
                "evaluation_status": "SCORING_FAILED",
                "quality_score": 0,
                "overall_score": 0.0,
                "brandability_score": 0.0,
                "trend_score": 0.0,
                "commercial_score": 0.0,
                "natural_brand_score": 0.0,
                "compound_naturalness_score": 0.0,
                "buyer_clarity_score": 0.0,
                "startup_naturalness_score": 0.0,
                "candidate_trend_fit_score": 0.0,
                "concept_trend_score": float(concept_trend_relevance),
                "candidate_commercial_fit": 0.0,
                "category_opportunity_score": float(category_opportunity_score),
                "radio_test_score": 0.0,
                "word_glue_penalty": 0.0,
                "ai_generated_feel_score": 100.0,
                "pattern_diversity_score": pattern_diversity_score,
                "buyer_count": 0,
                "buyer_industries": [],
                "startup_fit": "Scoring Failed",
                "is_word_glue": False,
                "word_glue_details": {},
                "morphology_type": morphology_type or "UNKNOWN",
                "phonetic_cluster_id": phonetic_cluster_id or "UNKNOWN",
                "ai_naming_artifact_score": 0.0,
                "quality_breakdown": {
                    "natural_brand": 0,
                    "brandability": 0,
                    "memorability": 0,
                    "pronunciation": 0,
                    "simplicity": 0,
                    "commercial": 0,
                    "buyer_clarity": 0,
                    "startup_naturalness": 0,
                    "trend": 0,
                    "concept_trend": int(round(concept_trend_relevance)),
                    "candidate_trend_fit": 0,
                    "candidate_commercial_fit": 0,
                    "category_opportunity": int(round(category_opportunity_score)),
                    "semantic": 0,
                    "distinctiveness": 0,
                    "radio_test": 0,
                    "compound_naturalness": 0,
                    "ai_generated_feel": 100,
                    "word_glue_penalty": 0,
                    "pattern_diversity": int(round(pattern_diversity_score)),
                    "ai_naming_artifact": 0,
                    "invented_subtype": None,
                    "invented_quality_tier": None,
                    "invented_quality_score": 0.0,
                    "lexical_proximity_score": 0.0,
                    "phonetic_proximity_score": 0.0,
                    "semantic_anchor_score": 0.0,
                    "brandability_heuristic_score": 0.0,
                    "_float_scores": {
                        "overall_score": 0.0,
                        "brandability": 0.0,
                        "commercial": 0.0,
                        "trend": 0.0,
                        "memorability": 0.0,
                        "pronunciation": 0.0,
                        "simplicity": 0.0,
                        "distinctiveness": 0.0,
                        "invented_quality_score": 0.0,
                        "lexical_proximity_score": 0.0,
                        "phonetic_proximity_score": 0.0,
                        "semantic_anchor_score": 0.0,
                        "brandability_heuristic_score": 0.0
                    }
                },
                "invented_subtype": None,
                "invented_quality_tier": None,
                "invented_quality_score": 0.0,
                "invented_penalty": 0.0,
                "lexical_proximity_score": 0.0,
                "lexical_anchors": [],
                "phonetic_proximity_score": 0.0,
                "phonetic_anchors": [],
                "semantic_anchor_score": 0.0,
                "semantic_anchors": [],
                "anchor_frequency": 0.0,
                "brandability_heuristic_score": 0.0,
                "brandability_subscores": {}
            }

        # Candidate-level deterministic acoustic & linguistic evaluation
        det_eval = compute_deterministic_linguistic_evaluation(label, concept)
        pron_base = float(det_eval.get("pronunciation", structural_features.get("pronounceability_score", 70.0)))
        simplicity_base = float(det_eval.get("simplicity", structural_features.get("spelling_simplicity", 75.0)))
        memorability_base = float(det_eval.get("memorability", structural_features.get("estimated_memorability", 75.0)))
        distinct_base = float(det_eval.get("distinctiveness", 85.0))
        brandability_base = float(det_eval.get("brandability", 85.0))

        # Morphology & Phonetics
        if not morphology_type:
            morphology_type = MorphologyClassifier.classify(label)
        if not phonetic_cluster_id:
            phonetic_cluster_id = PhoneticEngine.get_composite_phonetic_key(label)
        if ai_naming_artifact_score is None:
            ai_naming_artifact_score = MorphologyClassifier.calculate_ai_naming_artifact_score(label)

        # PHASE 1 (REVISED): Multi-Signal Anchoring for INVENTED morphology
        invented_eval = None
        if morphology_type == "INVENTED" or naming_type == "INVENTED":
            from quality_engine.invented_quality import InventedQualityEvaluator
            invented_eval = InventedQualityEvaluator.get_instance().evaluate_candidate(label)

        # =========================================================================
        # 1. PHASE 2.75 LINGUISTIC DETECTORS & SCORERS
        # =========================================================================
        # A. Word-Glue Detection (generic adjective+noun / verb+noun penalty)
        glue_res = WordGlueDetector.detect_word_glue(label)
        is_word_glue = glue_res["is_word_glue"]
        word_glue_penalty = float(glue_res["word_glue_penalty"])

        # B. AI-Generated Feel Detection (synthetic consonant stuffing, forced suffixes)
        ai_feel_detector = AIGeneratedFeelDetector.evaluate_ai_feel(label)
        detector_feel = float(ai_feel_detector["ai_generated_feel_score"])
        if ai_evaluation and "ai_generated_feel" in ai_evaluation:
            ai_generated_feel_score = (detector_feel * 0.4) + (float(ai_evaluation["ai_generated_feel"]) * 0.6)
        else:
            ai_generated_feel_score = detector_feel
        ai_generated_feel_score = round(max(5.0, min(95.0, ai_generated_feel_score)), 2)

        # C. Compound Naturalness (evaluates syllable harmony, consonant collision, rhythm)
        compound_res = CompoundNaturalnessScorer.calculate_compound_naturalness(label, glue_info=glue_res)
        compound_naturalness_score = float(compound_res["compound_naturalness_score"])

        # D. Candidate-Specific Trend Fit vs Concept Trend Score (Requirement 7 & Part M)
        is_unanchored_inv = bool(naming_type == "INVENTED" and (not invented_eval or invented_eval.get("invented_subtype") == "UNANCHORED"))
        trend_res = CandidateTrendFitScorer.calculate_trend_fit(
            domain_or_label=label,
            concept=concept,
            concept_trend_relevance=concept_trend_relevance,
            market_category=market_category,
            is_unanchored_invented=is_unanchored_inv
        )
        concept_trend_score = float(trend_res["concept_trend_score"])
        candidate_trend_fit_score = float(trend_res["candidate_trend_fit_score"])
        blended_trend_score = float(trend_res["blended_trend_score"])

        # E. Candidate Commercial Fit vs Category Opportunity Score (Requirement 7 & Part L)
        buyer_res = BuyerClarityScorer.evaluate_buyer_clarity(
            label,
            market_category=market_category,
            invented_eval=invented_eval,
            naming_type=naming_type
        )
        buyer_clarity_score = float(buyer_res["buyer_clarity_score"])
        candidate_commercial_fit = float(buyer_res.get("candidate_commercial_fit", buyer_clarity_score))
        buyer_count = buyer_res["buyer_count"]
        buyer_industries = buyer_res["buyer_industries"]
        startup_fit = buyer_res["startup_fit"]

        # INVENTED commercial evidence must be semantic/buyer-evidence based, not length based.
        # The old BuyerClarityScorer starts from a short-name baseline; cap that proxy for
        # unanchored/weak invented candidates so length cannot manufacture commercial value.
        if invented_eval:
            inv_tier = invented_eval.get("invented_quality_tier")
            inv_semantic = float(invented_eval.get("semantic_anchor_score", 0.0) or 0.0)
            if inv_tier == "EXTREMELY_WEAK" or invented_eval.get("invented_subtype") == "UNANCHORED":
                candidate_commercial_fit = min(candidate_commercial_fit, 52.0 + min(6.0, inv_semantic * 0.08))
                buyer_clarity_score = min(buyer_clarity_score, 55.0 + min(5.0, inv_semantic * 0.08))
            elif inv_tier == "WEAK":
                candidate_commercial_fit = min(candidate_commercial_fit, 62.0 + min(6.0, inv_semantic * 0.06))
                buyer_clarity_score = min(buyer_clarity_score, 66.0 + min(5.0, inv_semantic * 0.05))

        if ai_evaluation and "buyer_clarity_score" in ai_evaluation:
            buyer_blend = 0.30 if invented_eval else 0.45
            buyer_clarity_score = (buyer_clarity_score * (1.0 - buyer_blend)) + (float(ai_evaluation["buyer_clarity_score"]) * buyer_blend)
        if ai_evaluation and ai_evaluation.get("startup_fit"):
            startup_fit = ai_evaluation["startup_fit"]
        buyer_clarity_score = round(max(10.0, min(100.0, buyer_clarity_score)), 2)

        # Commercial Score: Track both domain candidate_commercial_fit and macro category_opportunity_score
        category_opp_score = round(max(30.0, min(100.0, float(category_opportunity_score))), 3)
        base_commercial = (candidate_commercial_fit * 0.70) + (category_opp_score * 0.30)
        if ai_evaluation and "commercial_potential" in ai_evaluation:
            commercial_blend = 0.30 if invented_eval else 0.45
            commercial_score = (base_commercial * (1.0 - commercial_blend)) + (float(ai_evaluation["commercial_potential"]) * commercial_blend)
        else:
            commercial_score = base_commercial
            if naming_type in ["ONE_WORD", "REAL_WORD", "FOREIGN_WORD", "REAL_FOREIGN_WORD"]:
                commercial_score += 4.5
            if char_len <= 7 and (naming_type != "INVENTED" or (invented_eval and invented_eval.get("invented_subtype") != "UNANCHORED")):
                commercial_score += 3.0
            if invented_eval and invented_eval.get("invented_subtype") == "UNANCHORED":
                commercial_score -= 6.0
        commercial_score = round(max(10.0, min(100.0, commercial_score)), 3)

        # =========================================================================
        # 2. CORE PHONETIC & STRUCTURAL SCORING
        # =========================================================================
        # Pronunciation Score (0-100)
        ai_pron = ai_evaluation.get("pronunciation") if ai_evaluation else None
        if ai_pron is not None:
            pronunciation_score = (pron_base * 0.4) + (float(ai_pron) * 0.6)
        else:
            pronunciation_score = pron_base
        pronunciation_score = round(max(10.0, min(100.0, pronunciation_score)), 3)

        # Simplicity Score (0-100)
        ai_simp = ai_evaluation.get("simplicity") if ai_evaluation else None
        if ai_simp is not None:
            simplicity_score = (simplicity_base * 0.4) + (float(ai_simp) * 0.6)
        else:
            simplicity_score = simplicity_base
        simplicity_score = round(max(10.0, min(100.0, simplicity_score)), 3)

        # Radio Test Score (0-100)
        ai_radio = ai_evaluation.get("radio_test_score") if ai_evaluation else None
        if ai_radio is not None:
            radio_test_score = (pronunciation_score * 0.25) + (simplicity_score * 0.25) + (float(ai_radio) * 0.5)
        else:
            radio_test_score = (pronunciation_score * 0.5) + (simplicity_score * 0.5)
        if char_len > 10:
            radio_test_score -= (char_len - 10) * 3.0
        radio_test_score = round(max(10.0, min(100.0, radio_test_score)), 3)

        # Memorability Score (0-100)
        ai_mem = ai_evaluation.get("memorability") if ai_evaluation else None
        if ai_mem is not None:
            memorability_score = (memorability_base * 0.4) + (float(ai_mem) * 0.6)
        else:
            len_bonus = max(0.0, (10 - char_len) * 2.2) if char_len <= 10 else -((char_len - 12) * 2.5)
            memorability_score = memorability_base + len_bonus
        if is_word_glue:
            memorability_score -= 8.5
        memorability_score = round(max(10.0, min(100.0, memorability_score)), 3)

        # =========================================================================
        # 3. BRAND, STARTUP & NATURALNESS SCORING
        # =========================================================================
        # Natural Brand Score: Distinguishes natural brands from artificial word glue
        base_natural = (pronunciation_score * 0.35) + (simplicity_score * 0.35) + (memorability_score * 0.30)
        if naming_type in ["ONE_WORD", "REAL_WORD", "FOREIGN_WORD", "REAL_FOREIGN_WORD"]:
            base_natural += 8.5
        elif naming_type == "COMPOUND":
            base_natural = (base_natural * 0.4) + (compound_naturalness_score * 0.6)

        ai_nat = ai_evaluation.get("natural_brand_score") if ai_evaluation else None
        if ai_nat is not None:
            natural_brand_score = (base_natural * 0.35) + (float(ai_nat) * 0.65)
        else:
            natural_brand_score = base_natural

        # Penalize artificial word glue
        natural_brand_score -= (word_glue_penalty * 0.85)

        # Penalize high AI synthetic feel
        if ai_generated_feel_score > 35.0:
            natural_brand_score -= (ai_generated_feel_score - 35.0) * 0.45
        natural_brand_score = round(max(10.0, min(100.0, natural_brand_score)), 3)

        # Startup Naturalness Score: Would a real US startup / software company select this?
        ai_startup = ai_evaluation.get("startup_naturalness_score") if ai_evaluation else None
        if ai_startup is not None:
            startup_naturalness_score = (float(ai_startup) * 0.6) + (natural_brand_score * 0.4)
        else:
            startup_naturalness_score = (natural_brand_score * 0.65) + (buyer_clarity_score * 0.35)

        if is_word_glue:
            startup_naturalness_score -= (word_glue_penalty * 0.70)
        if invented_eval and invented_eval.get("invented_subtype") == "UNANCHORED":
            startup_naturalness_score -= 8.0
        startup_naturalness_score = round(max(10.0, min(100.0, startup_naturalness_score)), 3)

        # Brandability Score (0-100) - Part J & Part N
        ai_brand = ai_evaluation.get("brandability") if (ai_evaluation and ai_evaluation.get("ai_evaluated")) else None
        if naming_type == "INVENTED" and invented_eval:
            # Calibrate INVENTED candidates: anchor brandability to the multi-signal heuristic composite
            # Part N: AI cannot override deterministic anchor status
            det_brand = float(invented_eval.get("anchor_adjusted_brandability_score") or invented_eval.get("brandability_heuristic_score") or brandability_base)
            if ai_brand is not None:
                bounded_ai = min(float(ai_brand), det_brand + 12.0)
                brandability_score = round((det_brand * 0.70) + (bounded_ai * 0.30), 3)
            else:
                brandability_score = round((det_brand * 0.85) + (brandability_base * 0.15), 3)
        else:
            if ai_brand is not None:
                brandability_score = float(ai_brand)
            else:
                brandability_score = brandability_base

        brandability_score -= (word_glue_penalty * 0.50)
        # Apply AI naming artifact penalty if high synthetic feel
        if ai_naming_artifact_score > 25.0:
            brandability_score -= (ai_naming_artifact_score - 25.0) * 0.30
        brandability_score = round(max(10.0, min(100.0, brandability_score)), 3)

        # Semantic Relevance Score (0-100) - Part K
        ai_flex = ai_evaluation.get("category_flexibility") if (ai_evaluation and ai_evaluation.get("ai_evaluated")) else None
        if naming_type == "INVENTED" and invented_eval:
            det_sem = calculate_invented_semantic_relevance(
                invented_eval,
                concept=concept,
                market_category=market_category
            )
            if ai_flex is not None:
                # Bounded by deterministic anchor reality
                bounded_flex = min(float(ai_flex), det_sem + 12.0) if invented_eval.get("invented_subtype") == "UNANCHORED" else float(ai_flex)
                semantic_relevance_score = round((det_sem * 0.65) + (bounded_flex * 0.35), 3)
            else:
                semantic_relevance_score = det_sem
        else:
            if ai_flex is not None:
                semantic_relevance_score = float(ai_flex)
            else:
                base_sem = 85.0 if naming_type in ["ONE_WORD", "REAL_WORD", "FOREIGN_WORD", "REAL_FOREIGN_WORD", "COMPOUND", "SEMANTIC_BRANDABLE"] else 78.0
                sem_jitter = (distinct_base * 0.1) - (ai_feel_detector.get("ai_generated_feel_score", 15.0) * 0.05)
                semantic_relevance_score = round(max(10.0, min(100.0, base_sem + sem_jitter)), 3)

        # Distinctiveness Score (0-100)
        ai_dist = ai_evaluation.get("distinctiveness") if (ai_evaluation and ai_evaluation.get("ai_evaluated")) else None
        if ai_dist is not None:
            distinctiveness_score = float(ai_dist)
        else:
            distinctiveness_score = distinct_base
        if is_word_glue:
            distinctiveness_score -= 15.0
        distinctiveness_score = round(max(10.0, min(100.0, distinctiveness_score)), 3)

        # =========================================================================
        # MULTI-MODEL CALIBRATION
        # Independent judges enrich deterministic scores; they never replace hard evidence.
        # =========================================================================
        if isinstance(multi_model_evaluation, dict):
            consensus = multi_model_evaluation.get("consensus", {}) if isinstance(multi_model_evaluation.get("consensus"), dict) else {}
            cfg = multi_model_evaluation.get("_config", {}) if isinstance(multi_model_evaluation.get("_config"), dict) else {}
            def _mm(value, default=None):
                try:
                    return float(value) if value is not None else default
                except (TypeError, ValueError):
                    return default
            inv_subtype = invented_eval.get("invented_subtype") if invented_eval else None
            ai_brand = _mm(consensus.get("final_brand_quality") or consensus.get("brand_quality"))
            ai_comm = _mm(consensus.get("final_commercial_quality") or consensus.get("commercial_quality"))
            ai_buyer = _mm(consensus.get("final_buyer_quality") or consensus.get("buyer_quality"))
            ai_sem = _mm(consensus.get("final_semantic_quality") or consensus.get("semantic_quality"))
            ai_ling = _mm(consensus.get("final_linguistic_quality") or consensus.get("linguistic_quality"))
            ai_gib = _mm(consensus.get("final_gibberish_risk") or consensus.get("gibberish_risk"), 0.0)
            confidence = _mm(multi_model_evaluation.get("consensus_confidence"), 0.0)
            blend = float(cfg.get("invented_ai_blend", 0.35)) if inv_subtype else float(cfg.get("non_invented_ai_blend", 0.45))
            if inv_subtype in {"UNANCHORED", "WEAK"}:
                blend = min(blend, 0.25)
            if confidence < float(cfg.get("min_consensus_confidence", 55.0)):
                blend *= max(0.0, confidence / max(1.0, float(cfg.get("min_consensus_confidence", 55.0))))
            if ai_brand is not None:
                brandability_score = (brandability_score * (1.0 - blend)) + (ai_brand * blend)
            if ai_comm is not None:
                commercial_score = (commercial_score * (1.0 - blend)) + (ai_comm * blend)
                candidate_commercial_fit = (candidate_commercial_fit * (1.0 - blend)) + (ai_comm * blend)
            if ai_buyer is not None:
                buyer_clarity_score = (buyer_clarity_score * (1.0 - blend)) + (ai_buyer * blend)
            if ai_sem is not None and inv_subtype not in {"UNANCHORED", "WEAK"}:
                semantic_relevance_score = (semantic_relevance_score * (1.0 - min(blend, 0.25))) + (ai_sem * min(blend, 0.25))
            if ai_ling is not None:
                natural_brand_score = (natural_brand_score * (1.0 - min(blend, 0.30))) + (ai_ling * min(blend, 0.30))
            if ai_gib >= 70.0:
                brandability_score -= min(15.0, (ai_gib - 70.0) * 0.35)
                commercial_score -= min(12.0, (ai_gib - 70.0) * 0.25)
            red_team_score = _mm(consensus.get("red_team_score"))
            if red_team_score is not None and red_team_score < float(cfg.get("red_team_low_score", 55.0)):
                penalty = min(15.0, (float(cfg.get("red_team_low_score", 55.0)) - red_team_score) * float(cfg.get("red_team_penalty_factor", 0.20)))
                brandability_score -= penalty
                commercial_score -= penalty * 0.75
            # Deterministic hard facts cap subjective enrichment.
            if invented_eval and inv_subtype == "UNANCHORED":
                brandability_score = self._apply_soft_ceiling(brandability_score, float(cfg.get("unanchored_final_ceiling", 64.0)))
                commercial_score = self._apply_soft_ceiling(commercial_score, float(cfg.get("unanchored_commercial_ceiling", 58.0)))
                semantic_relevance_score = self._apply_soft_ceiling(semantic_relevance_score, float(cfg.get("short_meaningless_semantic_max", 50.0)))
            elif invented_eval and invented_eval.get("invented_quality_tier") == "WEAK":
                brandability_score = self._apply_soft_ceiling(brandability_score, float(cfg.get("weak_final_ceiling", 72.0)))
                commercial_score = self._apply_soft_ceiling(commercial_score, float(cfg.get("weak_commercial_ceiling", 68.0)))
            if bool(multi_model_evaluation.get("short_but_meaningless")):
                brandability_score = self._apply_soft_ceiling(brandability_score, 58.0, span=4.0)
                commercial_score = self._apply_soft_ceiling(commercial_score, 55.0, span=4.0)
                semantic_relevance_score = self._apply_soft_ceiling(semantic_relevance_score, 45.0, span=4.0)
            if bool(multi_model_evaluation.get("pronounceable_not_brandable")):
                brandability_score = self._apply_soft_ceiling(brandability_score, 56.0, span=4.0)
                commercial_score = self._apply_soft_ceiling(commercial_score, 54.0, span=4.0)
            brandability_score = round(max(10.0, min(100.0, brandability_score)), 3)
            commercial_score = round(max(10.0, min(100.0, commercial_score)), 3)
            candidate_commercial_fit = round(max(10.0, min(100.0, candidate_commercial_fit)), 3)
            buyer_clarity_score = round(max(10.0, min(100.0, buyer_clarity_score)), 3)
            semantic_relevance_score = round(max(10.0, min(100.0, semantic_relevance_score)), 3)
            natural_brand_score = round(max(10.0, min(100.0, natural_brand_score)), 3)

        # =========================================================================
        # 4. AGGREGATED QUALITY SCORE (Requirement 12: Recalculate strictly from candidate-level features)
        # =========================================================================
        w = self.weights
        composite = (
            (natural_brand_score * w.get("natural_brand", 0.12)) +
            (brandability_score * w.get("brandability", 0.15)) +
            (memorability_score * w.get("memorability", 0.10)) +
            (pronunciation_score * w.get("pronunciation", 0.08)) +
            (simplicity_score * w.get("simplicity", 0.07)) +
            (candidate_commercial_fit * w.get("commercial", 0.13)) +
            (buyer_clarity_score * w.get("buyer_clarity", 0.08)) +
            (startup_naturalness_score * w.get("startup_naturalness", 0.08)) +
            (candidate_trend_fit_score * w.get("trend", 0.07)) +
            (semantic_relevance_score * w.get("semantic", 0.05)) +
            (distinctiveness_score * w.get("distinctiveness", 0.07))
        )

        # Apply Pattern Saturation Penalty
        pattern_pen = 0.0
        if pattern_diversity_score < 100.0:
            pattern_pen = (100.0 - pattern_diversity_score) * 0.35
            composite -= pattern_pen

        # Apply AI Naming Artifact Penalty
        artifact_pen = 0.0
        if ai_naming_artifact_score > 30.0:
            artifact_pen = (ai_naming_artifact_score - 30.0) * 0.30
            composite -= artifact_pen

        # Apply Invented Quality Soft Penalty
        if invented_eval and invented_eval.get("invented_penalty", 0.0) > 0:
            composite -= float(invented_eval["invented_penalty"])

        # =========================================================================
        # QUALITY CEILINGS (NO HIGH SCORE WITHOUT EVIDENCE)
        # =========================================================================
        from quality_engine.config import get_quality_ceilings_config, get_compound_quality_config
        ceilings_cfg = get_quality_ceilings_config()
        compound_cfg = get_compound_quality_config()

        # 1. Ceilings for INVENTED candidates based on anchor subtype & quality tier
        if naming_type == "INVENTED" or morphology_type == "INVENTED":
            inv_sub = invented_eval.get("invented_subtype", "UNANCHORED") if invented_eval else "UNANCHORED"
            inv_tier = invented_eval.get("invented_quality_tier", "WEAK") if invented_eval else "WEAK"

            if inv_tier == "STRONG":
                target_ceil_key = "STRONG"
            elif inv_sub in ["LEXICAL_ANCHORED", "SEMANTIC_ANCHORED", "PHONETIC_ANCHORED"] or inv_tier == "MODERATE":
                target_ceil_key = "MODERATE"
            elif inv_tier == "WEAK":
                target_ceil_key = "WEAK"
            else:
                target_ceil_key = "UNANCHORED"

            c_dict = ceilings_cfg.get(target_ceil_key, {})
            max_brand = float(c_dict.get("max_brandability", 98.0))
            max_comm = float(c_dict.get("max_commercial_score", 98.0))
            max_sem = float(c_dict.get("max_semantic_relevance", 98.0))
            max_trend = float(c_dict.get("max_trend_score", 98.0))
            max_overall = float(c_dict.get("max_overall_quality", 98.0))

            brandability_score = self._apply_soft_ceiling(brandability_score, max_brand)
            natural_brand_score = self._apply_soft_ceiling(natural_brand_score, max_brand)
            commercial_score = self._apply_soft_ceiling(commercial_score, max_comm)
            candidate_commercial_fit = self._apply_soft_ceiling(candidate_commercial_fit, max_comm)
            buyer_clarity_score = self._apply_soft_ceiling(buyer_clarity_score, max_comm)
            semantic_relevance_score = self._apply_soft_ceiling(semantic_relevance_score, max_sem)
            candidate_trend_fit_score = self._apply_soft_ceiling(candidate_trend_fit_score, max_trend)
            blended_trend_score = self._apply_soft_ceiling(blended_trend_score, max_trend)
            composite = self._apply_soft_ceiling(composite, max_overall)

        # 2. Ceilings for Contradictory Modifier Compounds (e.g. syncLow, apexLow, primeLow)
        if is_word_glue and glue_res.get("glue_type") == "CONTRADICTORY_MODIFIER_GLUE":
            max_c_overall = float(compound_cfg.get("max_contradictory_overall", 60.0))
            max_c_comm = float(compound_cfg.get("max_contradictory_commercial", 50.0))
            max_c_nat = float(compound_cfg.get("max_contradictory_naturalness", 45.0))
            composite = min(composite, max_c_overall)
            commercial_score = min(commercial_score, max_c_comm)
            candidate_commercial_fit = min(candidate_commercial_fit, max_c_comm)
            compound_naturalness_score = min(compound_naturalness_score, max_c_nat)

        overall_score = round(max(5.0, min(99.0, composite)), 3)
        quality_score = int(round(overall_score))

        breakdown = {
            "natural_brand": int(round(natural_brand_score)),
            "brandability": int(round(brandability_score)),
            "memorability": int(round(memorability_score)),
            "pronunciation": int(round(pronunciation_score)),
            "simplicity": int(round(simplicity_score)),
            "commercial": int(round(commercial_score)),
            "buyer_clarity": int(round(buyer_clarity_score)),
            "startup_naturalness": int(round(startup_naturalness_score)),
            "trend": int(round(blended_trend_score)),
            "concept_trend": int(round(concept_trend_score)),
            "candidate_trend_fit": int(round(candidate_trend_fit_score)),
            "candidate_commercial_fit": int(round(candidate_commercial_fit)),
            "category_opportunity": int(round(category_opp_score)),
            "semantic": int(round(semantic_relevance_score)),
            "distinctiveness": int(round(distinctiveness_score)),
            "radio_test": int(round(radio_test_score)),
            "compound_naturalness": int(round(compound_naturalness_score)),
            "ai_generated_feel": int(round(ai_generated_feel_score)),
            "word_glue_penalty": int(round(word_glue_penalty)),
            "pattern_diversity": int(round(pattern_diversity_score)),
            "ai_naming_artifact": int(round(ai_naming_artifact_score)),
            "invented_subtype": invented_eval.get("invented_subtype") if invented_eval else None,
            "invented_quality_tier": invented_eval.get("invented_quality_tier") if invented_eval else None,
            "invented_quality_score": invented_eval.get("invented_quality_score") if invented_eval else None,
            "lexical_proximity_score": invented_eval.get("lexical_proximity_score") if invented_eval else None,
            "phonetic_proximity_score": invented_eval.get("phonetic_proximity_score") if invented_eval else None,
            "semantic_anchor_score": invented_eval.get("semantic_anchor_score") if invented_eval else None,
            "brandability_heuristic_score": invented_eval.get("brandability_heuristic_score") if invented_eval else None,
            # High-resolution floating point values (stored internally without early rounding)
            "_float_scores": {
                "overall_score": overall_score,
                "natural_brand": natural_brand_score,
                "brandability": brandability_score,
                "commercial": commercial_score,
                "candidate_commercial_fit": candidate_commercial_fit,
                "category_opportunity": category_opp_score,
                "trend": blended_trend_score,
                "concept_trend": concept_trend_score,
                "candidate_trend_fit": candidate_trend_fit_score,
                "buyer_clarity": buyer_clarity_score,
                "startup_naturalness": startup_naturalness_score,
                "memorability": memorability_score,
                "pronunciation": pronunciation_score,
                "simplicity": simplicity_score,
                "distinctiveness": distinctiveness_score,
                "pattern_diversity": pattern_diversity_score,
                "ai_naming_artifact": ai_naming_artifact_score,
                "invented_quality_score": invented_eval.get("invented_quality_score") if invented_eval else None,
                "lexical_proximity_score": invented_eval.get("lexical_proximity_score") if invented_eval else None,
                "phonetic_proximity_score": invented_eval.get("phonetic_proximity_score") if invented_eval else None,
                "semantic_anchor_score": invented_eval.get("semantic_anchor_score") if invented_eval else None,
                "brandability_heuristic_score": invented_eval.get("brandability_heuristic_score") if invented_eval else None
            }
        }

        # Return a completely fresh score dictionary (no shared references)
        return {
            "quality_score": quality_score,
            "overall_score": overall_score,
            "brandability_score": brandability_score,
            "commercial_score": commercial_score,
            "trend_score": blended_trend_score,
            "natural_brand_score": natural_brand_score,
            "startup_naturalness_score": startup_naturalness_score,
            "radio_test_score": radio_test_score,
            "buyer_clarity_score": buyer_clarity_score,
            "buyer_count": buyer_count,
            "buyer_industries": list(buyer_industries),
            "startup_fit": startup_fit,
            "concept_trend_score": concept_trend_score,
            "candidate_trend_fit_score": candidate_trend_fit_score,
            "candidate_commercial_fit": candidate_commercial_fit,
            "category_opportunity_score": category_opp_score,
            "pattern_diversity_score": pattern_diversity_score,
            "ai_naming_artifact_score": ai_naming_artifact_score,
            "morphology_type": morphology_type,
            "phonetic_cluster_id": phonetic_cluster_id,
            "compound_naturalness_score": compound_naturalness_score,
            "word_glue_penalty": word_glue_penalty,
            "ai_generated_feel_score": ai_generated_feel_score,
            "is_word_glue": is_word_glue,
            "word_glue_details": dict(glue_res),
            "invented_subtype": invented_eval.get("invented_subtype") if invented_eval else None,
            "invented_quality_tier": invented_eval.get("invented_quality_tier") if invented_eval else None,
            "invented_quality_score": invented_eval.get("invented_quality_score") if invented_eval else None,
            "invented_penalty": float(invented_eval.get("invented_penalty", 0.0)) if invented_eval else 0.0,
            "lexical_proximity_score": invented_eval.get("lexical_proximity_score") if invented_eval else None,
            "lexical_anchors": list(invented_eval.get("lexical_anchors", [])) if invented_eval else [],
            "phonetic_proximity_score": invented_eval.get("phonetic_proximity_score") if invented_eval else None,
            "phonetic_anchors": list(invented_eval.get("phonetic_anchors", [])) if invented_eval else [],
            "semantic_anchor_score": invented_eval.get("semantic_anchor_score") if invented_eval else None,
            "semantic_anchors": list(invented_eval.get("semantic_anchors", [])) if invented_eval else [],
            "anchor_frequency": invented_eval.get("anchor_frequency") if invented_eval else None,
            "brandability_heuristic_score": invented_eval.get("brandability_heuristic_score") if invented_eval else None,
            "raw_brandability_heuristic_score": invented_eval.get("raw_brandability_heuristic_score") if invented_eval else None,
            "anchor_adjusted_brandability_score": invented_eval.get("anchor_adjusted_brandability_score") if invented_eval else None,
            "brandability_anchor_factor": invented_eval.get("brandability_anchor_factor") if invented_eval else None,
            "brandability_subscores": dict(invented_eval.get("brandability_subscores", {})) if invented_eval else {},
            "semantic_relevance_score": semantic_relevance_score,
            "quality_breakdown": breakdown
        }
