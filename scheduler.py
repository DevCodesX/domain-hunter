import os
import time
import json
import asyncio
import datetime
import logging
import re
import copy
from typing import Optional, Dict, Any, List, Set
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from router import ModelRouter
from availability import (
    AvailabilityEngine,
    AvailabilityStatus,
    AvailabilityResult,
    REAL_REGISTRY_PROVIDERS,
    MOCK_REGISTRY_PROVIDERS,
    is_production_mode,
    normalize_and_validate_candidate
)

# Phase 1 & 3: Quality Engine Modules
from quality_engine import (
    QualityFeatureExtractor,
    OneWordQualityEngine,
    NamingTypeClassifier,
    NamingStrategyGenerator,
    QualityScorer,
    AIQualityEvaluator,
    DiversityEngine,
    FinalJudge,
    FINAL_RESULT_COUNT,
    MAX_AI_EVAL_CANDIDATES,
    BuyerIntelligenceEngine,
    QualityTierEngine,
    MultiEngineOrchestrator,
    EvolutionaryGenerator,
    MultiModelDomainEvaluator
)

# Phase 4: Self-Learning & Feedback Learning Modules
from learning_engine import (
    LearningStore,
    TrainingFeaturePipeline,
    StatisticalRanker,
    StrategyOptimizer,
    RouterPerformanceTracker
)

# Phase 2: IP / Trademark / Existing Brand Risk Engine Modules
from risk_engine import (
    TrademarkRiskEngine,
    ExistingBrandEngine,
    NegativeSemanticScreening,
    IPDecisionEngine,
    RiskLevel
)

# Phase 2.5: Opportunity & Semantic Expansion Engine Modules
from opportunity_engine import (
    ConceptDiscoveryEngine,
    MatrixOpportunityGenerator,
    MultilingualEngine,
    RadioTestScorer,
    CategoryFitScorer,
    OpportunityScorer,
    MARKET_CATEGORIES,
    MAX_CATEGORY_CONCENTRATION
)

logger = logging.getLogger("Scheduler")
STATE_FILE = "job_state.json"

PIPELINE_STAGES = [
    "research",
    "concept_extraction",
    "candidate_generation",
    "candidate_validation",
    "availability_check",
    "premium_check",
    "quality_filter",
    "scoring",
    "final_selection",
    "saving_results",
    "completed"
]

def get_job_state() -> Dict[str, Any]:
    default_state = {
        "latest_results": None,
        "current_job": {
            "status": "idle",
            "stage": "idle",
            "candidates_generated": 0,
            "checked": 0,
            "available_standard": 0,
            "registered": 0,
            "premium": 0,
            "unknown": 0,
            "completed": True
        }
    }
    if not os.path.exists(STATE_FILE):
        return default_state
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Purge any legacy unverified, registered, or mock domains if present in latest_results
            latest = data.get("latest_results")
            if latest and isinstance(latest, dict) and "results" in latest:
                cleaned_results = [
                    d for d in latest["results"]
                    if d.get("availability_status") == "AVAILABLE_STANDARD"
                    and d.get("availability_provider") not in MOCK_REGISTRY_PROVIDERS
                    and "mock" not in str(d.get("availability_provider", "")).lower()
                ]
                if len(cleaned_results) != len(latest["results"]):
                    latest["results"] = cleaned_results
            return data
    except Exception as e:
        logger.error(f"Error reading {STATE_FILE}: {e}")
        return default_state

def save_job_state(state: Dict[str, Any]):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving {STATE_FILE}: {e}")

class DomainHunterPipeline:
    def __init__(self, router: ModelRouter, http_client, availability_engine: Optional[AvailabilityEngine] = None):
        self.router = router
        self.http_client = http_client
        if is_production_mode():
            if availability_engine is not None:
                engine_cls = availability_engine.__class__.__name__
                if "mock" in engine_cls.lower() or getattr(availability_engine, "provider", "") in MOCK_REGISTRY_PROVIDERS:
                    logger.critical(
                        f"[SECURITY-ALERT] Attempted to inject mock availability engine '{engine_cls}' in production mode! "
                        "Rejecting mock engine and falling closed to authoritative Verisign RDAP AvailabilityEngine."
                    )
                    self.availability_engine = AvailabilityEngine(http_client)
                else:
                    self.availability_engine = availability_engine
            else:
                self.availability_engine = AvailabilityEngine(http_client)
        else:
            self.availability_engine = availability_engine or AvailabilityEngine(http_client)
        self.is_running = False
        self._lock = asyncio.Lock()

        # Initialize Phase 1 Quality Engine components
        self.feature_extractor = QualityFeatureExtractor()
        self.one_word_engine = OneWordQualityEngine(self.feature_extractor)
        self.naming_classifier = NamingTypeClassifier(self.one_word_engine)
        self.strategy_generator = NamingStrategyGenerator(self.router)
        self.quality_scorer = QualityScorer()
        self.ai_evaluator = AIQualityEvaluator(self.router)  # legacy compatibility
        self.multi_model_evaluator = MultiModelDomainEvaluator(self.router)
        self.diversity_engine = DiversityEngine()

        # Initialize Phase 2 IP / Trademark Risk components
        self.brand_engine = ExistingBrandEngine()
        self.negative_screening = NegativeSemanticScreening()
        self.trademark_engine = TrademarkRiskEngine(
            brand_engine=self.brand_engine,
            negative_screening=self.negative_screening
        )

        # Initialize Phase 2.5 Opportunity & Semantic Expansion Engine
        self.concept_discovery_engine = ConceptDiscoveryEngine(self.router)
        self.matrix_generator = MatrixOpportunityGenerator(self.strategy_generator, self.router)
        self.multilingual_engine = MultilingualEngine()

        # Initialize Phase 3 & 4 Components
        self.buyer_intelligence_engine = BuyerIntelligenceEngine()
        self.quality_tier_engine = QualityTierEngine()
        self.evolutionary_generator = EvolutionaryGenerator(self.feature_extractor)
        self.learning_store = LearningStore()
        self.ranker = StatisticalRanker()
        self.router_tracker = RouterPerformanceTracker(self.learning_store)

    async def run_domain_hunt(self, trigger: str = "manual", geo: str = "US", lang: str = "en") -> Dict[str, Any]:
        """
        Unified pipeline integrating:
        - Real-time Trend & Concept Research
        - Multi-Strategy Candidate Generation (ONE_WORD, COMPOUND, INVENTED, etc.)
        - Phase 1: Quality Engine & Structural Validation
        - Authoritative Registry Availability & Premium Checks
        - Phase 2: Trademark / IP / Existing Brand Risk Engine
        - LLM Subjective Evaluation & Rich Quality Scoring
        - Semantic Diversity Selection
        - Persisting to Supabase and Local Storage
        """
        async with self._lock:
            if self.is_running:
                logger.warning("Pipeline already running, rejecting concurrent execution.")
                raise RuntimeError("already_running")
            self.is_running = True

        state = get_job_state()
        job_id = str(int(time.time()))
        scan_id = f"hunt_{job_id}"

        job_state = {
            "job_id": job_id,
            "scan_id": scan_id,
            "trigger": trigger,
            "status": "running",
            "stage": "research",
            "candidates_generated": 0,
            "checked": 0,
            "available_standard": 0,
            "registered": 0,
            "premium": 0,
            "unknown": 0,
            "completed": False,
            "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "error": None
        }
        state["current_job"] = job_state
        save_job_state(state)

        funnel_stats = {
            "raw_generated": 0,
            "structural_passed": 0,
            "checked": 0,
            "available_standard": 0,
            "registered": 0,
            "premium": 0,
            "ip_screened": 0,
            "ip_passed": 0,
            "ip_critical_rejected": 0,
            "ai_evaluated": 0,
            "multi_model_evaluated": 0,
            "multi_model_summary": {},
            "consensus_pass": 0,
            "quality_floor_pass": 0,
            "learned_ranked": 0,
            "diversity_input": 0,
            "diversity_selected": 0,
            "final": 0,
            "funnel_rejections": {"availability": 0, "ip": 0, "deterministic_quality": 0, "consensus": 0, "quality_floor": 0, "diversity": 0},
            # Section 6 explicit production metrics:
            "one_word_generated": 0,
            "one_word_available": 0,
            "one_word_final": 0,
            "compound_generated": 0,
            "compound_available": 0,
            "invented_generated": 0,
            "invented_available": 0,
            "foreign_generated": 0,
            "foreign_available": 0,
            "score_integrity_audit": {},
            "one_word_funnel": {
                "raw_one_word": 0,
                "structural_valid_one_word": 0,
                "available_one_word": 0,
                "non_premium_one_word": 0,
                "ip_safe_one_word": 0,
                "quality_pass_one_word": 0,
                "final_one_word": 0,
                # Backward compatibility aliases
                "generated": 0,
                "structural_passed": 0,
                "checked": 0,
                "available_standard": 0,
                "ip_passed": 0,
                "final": 0
            },
            "length_distribution": {
                "ONE_WORD": {"4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "9": 0, "10+": 0},
                "INVENTED": {"4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "9": 0, "10+": 0},
                "COMPOUND": {"4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "9": 0, "10+": 0},
                "TOTAL": {"4": 0, "5": 0, "6": 0, "7": 0, "8": 0, "9": 0, "10+": 0}
            },
            "pattern_saturation_summary": {}
        }

        def update_stage(stage_name: str, **kwargs):
            job_state["stage"] = stage_name
            for k, v in kwargs.items():
                job_state[k] = v
            save_job_state(state)
            logger.info(f"[PIPELINE-STAGE] stage={stage_name} info={kwargs}")

        try:
            # ==========================================
            # STAGE 1: research
            # ==========================================
            update_stage("research")
            import xmltodict

            trends_context = []
            try:
                res_general = await self.http_client.get(f"https://trends.google.com/trending/rss?geo={geo.upper()}", timeout=8.0)
                if res_general.status_code == 200:
                    parsed = xmltodict.parse(res_general.content)
                    items = parsed.get("rss", {}).get("channel", {}).get("item", [])
                    if not isinstance(items, list): items = [items]
                    titles = [item.get("title") for item in items[:4] if item.get("title")]
                    if titles: trends_context.append(f"General Trends: {', '.join(titles)}")
            except Exception as e:
                logger.warning(f"Trend RSS fetch error: {e}")

            categories = ["TECHNOLOGY", "BUSINESS", "STARTUP"]
            for cat in categories:
                try:
                    url = f"https://news.google.com/rss/headlines/section/topic/{cat}?hl={lang}-{geo.upper()}&gl={geo.upper()}&ceid={geo.upper()}:{lang}"
                    res = await self.http_client.get(url, timeout=8.0)
                    if res.status_code == 200:
                        parsed = xmltodict.parse(res.content)
                        items = parsed.get("rss", {}).get("channel", {}).get("item", [])
                        if not isinstance(items, list): items = [items]
                        titles = [item.get("title").rsplit(" - ", 1)[0] for item in items[:3] if item.get("title")]
                        if titles: trends_context.append(f"{cat} Trends: {', '.join(titles)}")
                except Exception:
                    pass

            if not trends_context:
                trends_context.append("AI Agents, Autonomous Workflow Automation, Predictive Intelligence, Sustainable Tech Infrastructure")

            context_str = "\n".join(trends_context)

            # ==========================================
            # STAGE 2: concept_extraction (Phase 2.5 Multi-Source Opportunity Discovery)
            # ==========================================
            update_stage("concept_extraction")
            concept_objects = await self.concept_discovery_engine.discover_concepts(
                trending_context=trends_context,
                target_count=10
            )
            concepts = [c["concept"] for c in concept_objects]
            logger.info(f"[STAGE 2] Discovered {len(concept_objects)} diverse concepts across market opportunity universe.")

            # ==========================================
            # STAGE 3: candidate_generation (Phase 3 Multi-Engine & Matrix Generation)
            # ==========================================
            update_stage("candidate_generation")
            # Fetch past strategy performance to guide dynamic quotas
            strategy_stats = self.learning_store.get_strategy_performance()
            # Generates candidates across Market Categories × 7 Naming Strategies × Multilingual Engine
            raw_strategy_records = await self.matrix_generator.generate_matrix_candidates(
                concepts=concept_objects,
                target_total=1950
            )

            # Evolutionary generation pass to enrich linguistic variety
            if len(raw_strategy_records) >= 20:
                mutations = self.evolutionary_generator.generate_mutations(raw_strategy_records[:30], mutation_count_per_seed=2)
                raw_strategy_records.extend(mutations)

            funnel_stats["raw_generated"] = len(raw_strategy_records)
            funnel_stats["one_word_generated"] = sum(
                1 for rec in raw_strategy_records if rec.get("generation_strategy") == "ONE_WORD"
            )
            funnel_stats["compound_generated"] = sum(
                1 for rec in raw_strategy_records if rec.get("generation_strategy") == "COMPOUND"
            )
            funnel_stats["invented_generated"] = sum(
                1 for rec in raw_strategy_records if rec.get("generation_strategy") == "INVENTED"
            )
            funnel_stats["semantic_generated"] = sum(
                1 for rec in raw_strategy_records if rec.get("generation_strategy") in ["SEMANTIC", "SEMANTIC_BRANDABLE"]
            )
            funnel_stats["prefix_suffix_generated"] = sum(
                1 for rec in raw_strategy_records if rec.get("generation_strategy") == "PREFIX_SUFFIX"
            )
            funnel_stats["trend_generated"] = sum(
                1 for rec in raw_strategy_records if rec.get("generation_strategy") in ["TREND", "TREND_BASED"]
            )
            funnel_stats["keyword_generated"] = sum(
                1 for rec in raw_strategy_records if rec.get("generation_strategy") == "KEYWORD_BRANDABLE"
            )
            funnel_stats["foreign_generated"] = sum(
                1 for rec in raw_strategy_records if rec.get("naming_type") == "REAL_FOREIGN_WORD"
            )
            funnel_stats["strategy_distribution"] = {
                "ONE_WORD": funnel_stats["one_word_generated"],
                "INVENTED": funnel_stats["invented_generated"],
                "SEMANTIC": funnel_stats["semantic_generated"],
                "COMPOUND": funnel_stats["compound_generated"],
                "PREFIX_SUFFIX": funnel_stats["prefix_suffix_generated"],
                "TREND": funnel_stats["trend_generated"],
                "KEYWORD_BRANDABLE": funnel_stats["keyword_generated"]
            }
            funnel_stats["one_word_funnel"]["generated"] = funnel_stats["one_word_generated"] + funnel_stats["foreign_generated"]
            logger.info(
                f"[STAGE 3] Generated {len(raw_strategy_records)} raw candidates across 7 strategies. "
                f"(Distribution: {funnel_stats['strategy_distribution']})"
            )

            # ==========================================
            # STAGE 4: candidate_validation (PHASE 1: Quality Engine & Structural Validation)
            # ==========================================
            update_stage("candidate_validation")
            validated_candidates: List[Dict[str, Any]] = []
            seen_domains: Set[str] = set()

            for rec in raw_strategy_records:
                domain_raw = rec.get("domain", "")
                norm, err = normalize_and_validate_candidate(domain_raw)
                if not norm or norm in seen_domains:
                    continue

                # Local deterministic structural feature extraction
                features = self.feature_extractor.extract_features(norm)
                # Hard filter: Reject only clearly bad candidates (random123, aaaaaa, unpronounceable gibberish)
                if not features["passes_hard_filter"]:
                    logger.debug(f"[HARD-FILTER-REJECT] {norm}: {features.get('hard_rejection_reason')}")
                    continue

                # Linguistic classification (single authoritative source for naming_type)
                naming_info = self.naming_classifier.classify(norm)
                # If designated as REAL_FOREIGN_WORD by multilingual engine, preserve it!
                if rec.get("naming_type") == "REAL_FOREIGN_WORD":
                    naming_info["naming_type"] = "REAL_FOREIGN_WORD"

                one_word_eval = self.one_word_engine.compute_one_word_score(norm)
                cand_id = f"cand_{scan_id}_{len(validated_candidates)+1:04d}"

                rec_enriched = {
                    **rec,
                    "candidate_id": cand_id,
                    "run_id": scan_id,
                    "scan_id": scan_id,
                    "domain": norm,
                    "naming_type": naming_info["naming_type"],
                    "structural_features": features,
                    "naming_type_info": naming_info,
                    "one_word_features": one_word_eval
                }
                seen_domains.add(norm)
                validated_candidates.append(rec_enriched)

            funnel_stats["structural_passed"] = len(validated_candidates)
            funnel_stats["one_word_funnel"]["structural_passed"] = sum(
                1 for c in validated_candidates
                if c.get("naming_type_info", {}).get("naming_type") in ["ONE_WORD", "REAL_WORD", "REAL_FOREIGN_WORD"]
                or c.get("generation_strategy") == "ONE_WORD"
            )
            job_state["candidates_generated"] = len(validated_candidates)
            save_job_state(state)
            logger.info(
                f"[STAGE 4] {len(validated_candidates)} candidates passed structural validation. "
                f"(One-words passed: {funnel_stats['one_word_funnel']['structural_passed']})"
            )

            # ==========================================
            # STAGE 5: availability_check (DoH + Verisign RDAP)
            # ==========================================
            # STAGE 4.5: pre_availability_ranking (Stratified Diversity & Heuristic Quality)
            # ==========================================
            from quality_engine.pre_availability import rank_and_stratify_candidates
            from quality_engine.invented_quality import get_availability_pipeline_config

            avail_cfg = get_availability_pipeline_config()
            preferred_available = int(avail_cfg.get("preferred_available", 45))
            max_registry_checks = int(avail_cfg.get("max_registry_checks", 600))
            batch_initial = int(avail_cfg.get("batch_initial", 300))
            batch_step = int(avail_cfg.get("batch_step", 150))

            logger.info(
                f"[STAGE 4.5] Running pre-availability ranking & stratified diversity selection "
                f"across {len(validated_candidates)} validated candidates (preferred available: {preferred_available}, max checks: {max_registry_checks})..."
            )
            ranked_candidates = rank_and_stratify_candidates(
                validated_candidates,
                target_total=max_registry_checks
            )

            # ==========================================
            # STAGE 5: availability_check (Dynamic Two-Threshold Batched Registry Checks)
            # ==========================================
            update_stage("availability_check", candidates_generated=len(validated_candidates))

            checked_count = 0
            reg_count = 0
            avail_count = 0
            prem_count = 0
            unk_count = 0

            availability_results: Dict[str, AvailabilityResult] = {}

            async def on_check_progress(batch_idx: int, batch_total: int, res: AvailabilityResult):
                nonlocal checked_count, reg_count, avail_count, prem_count, unk_count
                checked_count += 1
                if res.status == AvailabilityStatus.REGISTERED:
                    reg_count += 1
                elif res.status == AvailabilityStatus.AVAILABLE_STANDARD:
                    avail_count += 1
                elif res.status == AvailabilityStatus.PREMIUM:
                    prem_count += 1
                else:
                    unk_count += 1

                job_state["checked"] = checked_count
                job_state["registered"] = reg_count
                job_state["available_standard"] = avail_count
                job_state["premium"] = prem_count
                job_state["unknown"] = unk_count
                if checked_count % 5 == 0 or checked_count == len(ranked_candidates):
                    save_job_state(state)

            # Dynamic Two-Threshold Registry Scanning:
            # Batch 1: Initial slice (e.g. 300 candidates) checked in full (no premature stop at 45).
            # If available < preferred_available (45):
            #   Batch 2: Add 150 candidates (total 450)
            # If still < preferred_available (45):
            #   Batch 3: Add 150 candidates (total 600 max)
            curr_offset = 0
            curr_batch_size = min(batch_initial, len(ranked_candidates), max_registry_checks)

            while curr_offset < len(ranked_candidates) and curr_offset < max_registry_checks:
                batch_candidates = ranked_candidates[curr_offset : curr_offset + curr_batch_size]
                batch_domains = [c["domain"] for c in batch_candidates]

                logger.info(
                    f"[STAGE 5] Checking batch of {len(batch_domains)} domains "
                    f"(checks so far: {checked_count}/{max_registry_checks}, available: {avail_count}/{preferred_available})..."
                )

                batch_res = await self.availability_engine.check_batch(
                    batch_domains,
                    on_progress=on_check_progress
                )
                availability_results.update(batch_res)
                curr_offset += len(batch_domains)

                # Stop if preferred goal reached or max registry checks ceiling reached
                if avail_count >= preferred_available:
                    logger.info(
                        f"[STAGE 5] Preferred goal achieved ({avail_count} >= {preferred_available} available standard). "
                        f"Finished batch through {curr_offset} total checks."
                    )
                    break

                if curr_offset >= max_registry_checks:
                    logger.info(
                        f"[STAGE 5] Reached max_registry_checks limit ({max_registry_checks}). Concluding availability check."
                    )
                    break

                # Prepare next incremental batch
                curr_batch_size = min(batch_step, max_registry_checks - curr_offset, len(ranked_candidates) - curr_offset)
                if curr_batch_size <= 0:
                    break

            funnel_stats["checked"] = checked_count
            funnel_stats["available_standard"] = avail_count
            funnel_stats["registered"] = reg_count
            funnel_stats["premium"] = prem_count

            # ==========================================
            # STAGE 6: premium_check
            # ==========================================
            update_stage("premium_check")
            # Collect candidates that are verified AVAILABLE_STANDARD and not registered/premium
            standard_available_pool: List[Dict[str, Any]] = []
            for c in validated_candidates:
                d = c["domain"]
                res = availability_results.get(d)
                if res and res.status == AvailabilityStatus.AVAILABLE_STANDARD and res.is_accepted():
                    c["availability_result"] = res
                    standard_available_pool.append(c)

            funnel_stats["one_word_available"] = sum(
                1 for c in standard_available_pool
                if c.get("naming_type_info", {}).get("naming_type") in ["ONE_WORD", "REAL_WORD"]
                or c.get("generation_strategy") == "ONE_WORD"
            )
            funnel_stats["compound_available"] = sum(
                1 for c in standard_available_pool
                if c.get("naming_type_info", {}).get("naming_type") == "COMPOUND"
                or c.get("generation_strategy") == "COMPOUND"
            )
            funnel_stats["invented_available"] = sum(
                1 for c in standard_available_pool
                if c.get("naming_type_info", {}).get("naming_type") == "INVENTED"
                or c.get("generation_strategy") == "INVENTED"
            )
            funnel_stats["foreign_available"] = sum(
                1 for c in standard_available_pool
                if c.get("naming_type_info", {}).get("naming_type") == "REAL_FOREIGN_WORD"
                or c.get("naming_type") == "REAL_FOREIGN_WORD"
            )
            funnel_stats["one_word_funnel"]["available_standard"] = funnel_stats["one_word_available"] + funnel_stats["foreign_available"]

            logger.info(
                f"[STAGE 6] Standard available candidates after availability & premium check: {len(standard_available_pool)} "
                f"(One-word: {funnel_stats['one_word_available']}, Compound: {funnel_stats['compound_available']}, "
                f"Invented: {funnel_stats['invented_available']}, Foreign: {funnel_stats['foreign_available']})"
            )

            # Algorithmic targeted refill if available candidates are critically low
            if len(standard_available_pool) < 5:
                logger.info("Fewer than 5 available domains, running rapid synthetic compound generation...")
                refill_prefixes = ["get", "use", "meta", "nova", "sync", "flow", "apex", "omni", "vibe"]
                refill_suffixes = ["labs", "hq", "base", "flow", "stack", "pulse", "craft", "nest", "loop", "grid", "sync", "node"]
                
                concept_words = []
                for c in concepts:
                    concept_words.extend([w.lower() for w in re.findall(r'[a-zA-Z]{4,}', c)])

                refill_list = []
                for w in set(concept_words)[:6]:
                    for p in refill_prefixes[:2]:
                        refill_list.append(f"{p}{w}.com")
                    for s in refill_suffixes[:3]:
                        refill_list.append(f"{w}{s}.com")

                cleaned_refills = []
                for v in refill_list:
                    norm, err = normalize_and_validate_candidate(v)
                    if norm and norm not in seen_domains:
                        seen_domains.add(norm)
                        features = self.feature_extractor.extract_features(norm)
                        if features["passes_hard_filter"]:
                            cleaned_refills.append({
                                "domain": norm,
                                "generation_strategy": "COMPOUND",
                                "source_concept": concepts[0] if concepts else "Tech & AI",
                                "generator_model": "synthetic_compound_refill",
                                "generation_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                "structural_features": features,
                                "naming_type_info": self.naming_classifier.classify(norm),
                                "one_word_features": self.one_word_engine.compute_one_word_score(norm)
                            })

                if cleaned_refills:
                    refill_domains = [c["domain"] for c in cleaned_refills]
                    refill_res = await self.availability_engine.check_batch(refill_domains, on_progress=on_check_progress)
                    availability_results.update(refill_res)
                    for c in cleaned_refills:
                        r = refill_res.get(c["domain"])
                        if r and r.status == AvailabilityStatus.AVAILABLE_STANDARD and r.is_accepted():
                            c["availability_result"] = r
                            standard_available_pool.append(c)

            # ==========================================
            # STAGE 7: quality_filter (PHASE 2: IP / TRADEMARK / BRAND RISK HARD GATE)
            # ==========================================
            update_stage("quality_filter")
            ip_screened_pool: List[Dict[str, Any]] = []
            funnel_stats["ip_screened"] = len(standard_available_pool)

            for cand in standard_available_pool:
                d = cand["domain"]
                concept = cand.get("source_concept", "")
                
                # Screen IP / Trademark / Existing Brand
                ip_report = await self.trademark_engine.screen_candidate(d, category_context=concept)
                cand["ip_report"] = ip_report

                # Hard reject CRITICAL IP risk candidates!
                if ip_report.ip_risk_level == RiskLevel.CRITICAL:
                    funnel_stats["ip_critical_rejected"] += 1
                    logger.warning(f"[IP-RISK-HARD-REJECT] {d} rejected due to CRITICAL IP risk: {ip_report.reasons}")
                    continue

                ip_screened_pool.append(cand)

            funnel_stats["ip_passed"] = len(ip_screened_pool)
            funnel_stats["one_word_funnel"]["ip_passed"] = sum(
                1 for c in ip_screened_pool
                if c.get("naming_type_info", {}).get("naming_type") in ["ONE_WORD", "REAL_FOREIGN_WORD"]
                or c.get("generation_strategy") == "ONE_WORD"
            )
            logger.info(f"[STAGE 7] Candidates passing IP clearance/review gate: {len(ip_screened_pool)}")

            # ==========================================
            # STAGE 8: scoring (Phase 2.75B Pattern Saturation, Phonetics, & High-Resolution Quality Scoring)
            # ==========================================
            update_stage("scoring")
            from quality_engine.pattern_saturation import PatternSaturationDetector
            from quality_engine.phonetic_engine import PhoneticEngine
            from quality_engine.morphology_classifier import MorphologyClassifier

            # 1. Run Pattern Saturation Detector across the entire pool (Requirement 1)
            pool_domains = [c["domain"] for c in ip_screened_pool]
            saturation_analysis = PatternSaturationDetector.analyze_run_saturation(pool_domains)
            cand_sat_map = saturation_analysis.get("candidate_saturation", {})
            funnel_stats["pattern_saturation_summary"] = {
                "top_prefixes": saturation_analysis.get("top_prefixes", []),
                "top_suffixes": saturation_analysis.get("top_suffixes", []),
                "saturated_patterns": saturation_analysis.get("saturated_patterns", []),
                "run_pattern_diversity": saturation_analysis.get("run_pattern_diversity", 100.0)
            }

            # 2. Cluster candidates by pronunciation (Requirement 2)
            phonetic_cluster_map = PhoneticEngine.get_candidate_cluster_map(pool_domains)

            # Stage 1 is the existing deterministic/pre-availability ranking. The multi-model layer
            # is only invoked for the serious available/IP-cleared pool; it never chooses raw candidates.
            stage1_size = int(self.multi_model_evaluator.config.get("stage1_pool_size", MAX_AI_EVAL_CANDIDATES))
            exploration_ratio = float(self.multi_model_evaluator.config.get("exploration_ratio", 0.10))
            exploration_count = max(0, min(stage1_size - 1, int(round(stage1_size * exploration_ratio))))
            exploit_count = max(0, stage1_size - exploration_count)
            exploit_pool = ip_screened_pool[:exploit_count]
            selected_domains = {c["domain"] for c in exploit_pool}
            exploration_pool = []
            for candidate in ip_screened_pool[exploit_count:]:
                if len(exploration_pool) >= exploration_count:
                    break
                ntype = str(candidate.get("naming_type_info", {}).get("naming_type", candidate.get("naming_type", ""))).upper()
                if ntype == "INVENTED" and candidate["domain"] not in selected_domains:
                    exploration_pool.append(candidate)
                    selected_domains.add(candidate["domain"])
            top_eval_pool = exploit_pool + exploration_pool
            mm_context = []
            for c in top_eval_pool:
                mm_context.append({
                    "domain": c["domain"],
                    "source_concept": c.get("source_concept", ""),
                    "market_category": c.get("market_category", "AI & Technology"),
                    "naming_type": c.get("naming_type_info", {}).get("naming_type", "INVENTED"),
                    "availability_status": c.get("availability_result").status.value if c.get("availability_result") else None,
                    "availability_verified": bool(c.get("availability_result").availability_verified) if c.get("availability_result") else False,
                    "ip_risk_level": c.get("ip_report").ip_risk_level.value if c.get("ip_report") else None,
                    "ip_check_status": getattr(c.get("ip_report"), "ip_check_status", None),
                })
            multi_eval_result = await self.multi_model_evaluator.evaluate_batch(mm_context, context={"concept": concepts[0] if concepts else ""}) if mm_context else {"candidates": {}, "summary": {}}
            multi_evaluations = multi_eval_result.get("candidates", {})
            funnel_stats["multi_model_evaluated"] = len(multi_evaluations)
            funnel_stats["ai_evaluated"] = len(multi_evaluations)
            funnel_stats["multi_model_summary"] = multi_eval_result.get("summary", {})

            scored_candidates: List[Dict[str, Any]] = []
            for cand in ip_screened_pool:
                d = cand["domain"]
                label = cand.get("structural_features", {}).get("label", d.replace(".com", "").strip().lower())
                ai_eval = None
                res: AvailabilityResult = cand["availability_result"]
                ip_report = cand["ip_report"]
                
                # Retrieve saturation and phonetic signals
                cand_sat = cand_sat_map.get(label, {})
                pattern_div_score = cand_sat.get("pattern_diversity_score", 100.0)
                prefix_freq = cand_sat.get("prefix_freq", 1)
                suffix_freq = cand_sat.get("suffix_freq", 1)
                phon_cluster_id = phonetic_cluster_map.get(d, PhoneticEngine.get_composite_phonetic_key(label))
                morph_type = MorphologyClassifier.classify(label)
                artifact_score = MorphologyClassifier.calculate_ai_naming_artifact_score(label)
                naming_template = cand.get("naming_template") or MorphologyClassifier.infer_template(label)

                # Calculate multi-dimensional quality scores with Phase 2.75B criteria & trend fit fix
                score_res = self.quality_scorer.score_candidate(
                    domain=d,
                    structural_features=cand["structural_features"],
                    one_word_features=cand["one_word_features"],
                    naming_type_info=cand["naming_type_info"],
                    ai_evaluation=None,
                    multi_model_evaluation=({**multi_evaluations.get(d, {}), "_config": self.multi_model_evaluator.config} if d in multi_evaluations else None),
                    concept=cand.get("source_concept", ""),
                    market_category=cand.get("market_category", "AI & Technology"),
                    concept_trend_relevance=float(cand.get("opportunity_score", 85.0)),
                    category_opportunity_score=float(cand.get("opportunity_score", 85.0)),
                    pattern_diversity_score=pattern_div_score,
                    ai_naming_artifact_score=artifact_score,
                    morphology_type=morph_type,
                    phonetic_cluster_id=phon_cluster_id
                )

                naming_type = cand["naming_type_info"].get("naming_type", "INVENTED")

                # Phase 2.75 Final Judge: 10 commercial criteria evaluation
                judge_assessment = FinalJudge.evaluate(
                    domain=d,
                    quality_score=score_res["quality_score"],
                    natural_brand_score=score_res["natural_brand_score"],
                    startup_naturalness_score=score_res["startup_naturalness_score"],
                    radio_test_score=score_res["radio_test_score"],
                    buyer_clarity={
                        "buyer_clarity_score": score_res["buyer_clarity_score"],
                        "startup_fit": score_res["startup_fit"]
                    },
                    word_glue={
                        "is_word_glue": score_res["is_word_glue"],
                        "word_glue_penalty": score_res["word_glue_penalty"]
                    },
                    ai_feel={
                        "ai_generated_feel_score": score_res["ai_generated_feel_score"],
                        "is_flagged": score_res["ai_generated_feel_score"] >= 50
                    },
                    market_category=cand.get("market_category", "AI & Technology")
                )

                # Phase 3: Candidate-Specific Buyer Intelligence Analysis
                buyer_intel = self.buyer_intelligence_engine.analyze_candidate(
                    domain_or_label=d,
                    market_category=cand.get("market_category", "AI & Technology"),
                    naming_type=naming_type,
                    concept=cand.get("source_concept", "")
                )

                # Build explainable candidate metadata
                explanation = IPDecisionEngine.build_candidate_explanation(
                    domain=d,
                    quality_score=score_res["quality_score"],
                    quality_breakdown=score_res["quality_breakdown"],
                    naming_type=naming_type,
                    structural_features=cand["structural_features"],
                    one_word_features=cand["one_word_features"],
                    ip_risk=ip_report
                )

                reasons = list(explanation["reasons"])
                source_lang = cand.get("source_language", "en")
                if source_lang != "en" and cand.get("literal_meaning"):
                    reasons.append(f"Verified {source_lang} word: '{cand.get('literal_meaning')}'")
                if score_res.get("natural_brand_score", 0) >= 80:
                    reasons.append(f"High natural brand quality ({score_res['natural_brand_score']}/100)")
                if score_res.get("is_word_glue"):
                    reasons.append(f"Generic word-glue penalty (-{score_res['word_glue_penalty']} pts)")
                if score_res.get("pattern_diversity_score", 100) < 100:
                    reasons.append(f"Pattern saturation penalty applied (score: {score_res['pattern_diversity_score']})")
                if score_res.get("startup_fit"):
                    reasons.append(f"Commercial Fit: {score_res['startup_fit']}")

                cand_id = cand.get("candidate_id") or f"cand_{scan_id}_{len(scored_candidates)+1:04d}"
                f_scores = score_res.get("quality_breakdown", {}).get("_float_scores", {})
                eval_status = ai_eval.get("evaluation_status", "DETERMINISTIC_EVALUATED") if isinstance(ai_eval, dict) else "DETERMINISTIC_EVALUATED"
                eval_provider = ai_eval.get("provider", "deterministic_linguistic_v2.75") if isinstance(ai_eval, dict) else "deterministic_linguistic_v2.75"
                eval_model = ai_eval.get("model", "phonetic_sonority_model") if isinstance(ai_eval, dict) else "phonetic_sonority_model"
                fallback_used = ai_eval.get("fallback_used", True) if isinstance(ai_eval, dict) else True

                trace_log = {
                    "domain": d,
                    "candidate_id": cand_id,
                    "generation_strategy": cand.get("generation_strategy", "OTHER"),
                    "naming_type": naming_type,
                    "quality_score": score_res["quality_score"],
                    "brandability_score": score_res["brandability_score"],
                    "memorability_score": f_scores.get("memorability", score_res["quality_breakdown"].get("memorability")),
                    "pronunciation_score": f_scores.get("pronunciation", score_res["quality_breakdown"].get("pronunciation")),
                    "simplicity_score": f_scores.get("simplicity", score_res["quality_breakdown"].get("simplicity")),
                    "distinctiveness_score": f_scores.get("distinctiveness", score_res["quality_breakdown"].get("distinctiveness")),
                    "candidate_trend_fit_score": score_res["candidate_trend_fit_score"],
                    "candidate_commercial_fit": score_res["candidate_commercial_fit"],
                    "buyer_clarity": score_res["buyer_clarity_score"],
                    "concept_trend_score": score_res["concept_trend_score"],
                    "category_opportunity_score": score_res["category_opportunity_score"],
                    "scoring_status": eval_status,
                    "scoring_provider": eval_provider,
                    "scoring_model": eval_model,
                    "fallback_used": fallback_used
                }
                logger.info(f"[CANDIDATE-SCORE-TRACE] {json.dumps(trace_log)}")

                full_record = {
                    "candidate_id": cand_id,
                    "run_id": scan_id,
                    "domain": d,
                    "domain_name": d,
                    "category": cand.get("market_category") or cand.get("source_concept") or (concepts[0] if concepts else "Tech & AI"),
                    "reason": f"Verified available .com ({naming_type}) for {cand.get('market_category') or 'Tech & AI'}.",
                    "availability_status": res.status.value,
                    "availability_provider": res.provider,
                    "availability_verified": res.availability_verified,
                    "availability_check_status": res.availability_check_status,
                    "premium_status": res.premium_status,
                    "premium_provider": res.premium_provider or res.provider,
                    "is_registered": res.is_registered,
                    "is_premium": res.is_premium,
                    "registration_available": res.registration_available,
                    "checked_at": res.checked_at,
                    "availability_checked_at": res.checked_at,
                    "overall_score": score_res["overall_score"],
                    "quality_score": score_res["quality_score"],
                    "brandability_score": score_res["brandability_score"],
                    "trend_score": score_res["trend_score"],
                    "commercial_score": score_res["commercial_score"],
                    "quality_breakdown": copy.deepcopy(score_res["quality_breakdown"]),
                    "naming_type": naming_type,
                    "generation_strategy": cand.get("generation_strategy", "OTHER"),
                    "source_concept": cand.get("source_concept", ""),
                    "generator_model": cand.get("generator_model", ""),
                    "generation_prompt_version": cand.get("generation_prompt_version", "v2.75b"),
                    "generation_batch_id": cand.get("generation_batch_id", ""),
                    "source_category": cand.get("source_category") or cand.get("market_category", "AI & Technology"),
                    "source_keywords": list(cand.get("source_keywords", [])),
                    "naming_template": naming_template,
                    "ip_risk_level": ip_report.ip_risk_level.value,
                    "ip_check_status": getattr(ip_report, "ip_check_status", "CHECKED"),
                    "exact_match_count": getattr(ip_report, "exact_match_count", 0),
                    "similar_match_count": getattr(ip_report, "similar_match_count", 0),
                    "brand_match_count": getattr(ip_report, "brand_match_count", 0),
                    "ip_provider": getattr(ip_report, "provider", "USPTO / Curated Brand Engine"),
                    "ip_evidence": getattr(ip_report, "evidence", []),
                    "ip_checked_at": getattr(ip_report, "checked_at", res.checked_at),
                    "ip_disclaimer": "IP/trademark screening is a risk signal, not legal advice or legal clearance.",
                    "ip_risk_score": ip_report.ip_risk_score,
                    "ip_risk": copy.deepcopy(explanation["ip_risk"]),
                    "decision": explanation["decision"],
                    "reasons": list(reasons),
                    "scan_id": scan_id,
                    # Phase 2.5 Opportunity & Semantic Expansion fields
                    "market_category": cand.get("market_category", "AI & Technology"),
                    "subcategory": cand.get("subcategory", "Core Platform"),
                    "concept_source": cand.get("concept_source", "EVERGREEN_COMMERCIAL_NICHES"),
                    "semantic_concept": cand.get("semantic_concept", "GENERAL_COMMERCIAL"),
                    "source_language": source_lang,
                    "original_word": cand.get("original_word") or cand.get("source_word") or label,
                    "original_meaning": cand.get("original_meaning") or cand.get("literal_meaning") or "",
                    "translation": cand.get("translation") or cand.get("english_meaning") or cand.get("literal_meaning") or "",
                    "pronunciation": cand.get("pronunciation") or str(score_res.get("pronunciation_score", "")),
                    "romanization": cand.get("romanization") or label,
                    "literal_meaning": cand.get("literal_meaning"),
                    "english_meaning": cand.get("english_meaning"),
                    "linguistic_confidence": cand.get("linguistic_confidence", 1.0),
                    "radio_test_score": score_res["radio_test_score"],
                    "category_fit": copy.deepcopy(cand.get("category_fit", {})),
                    "opportunity_score": cand.get("opportunity_score", 75),
                    "atom": copy.deepcopy(cand.get("atom") or {}),
                    "final_rank_score": None,
                    # Phase 2.75 Naming Intelligence Refinement fields
                    "natural_brand_score": score_res["natural_brand_score"],
                    "compound_naturalness_score": score_res["compound_naturalness_score"],
                    "buyer_clarity_score": score_res["buyer_clarity_score"],
                    "buyer_count": score_res["buyer_count"],
                    "buyer_industries": list(score_res["buyer_industries"]),
                    "startup_fit": score_res["startup_fit"],
                    "startup_naturalness_score": score_res["startup_naturalness_score"],
                    "concept_trend_score": score_res["concept_trend_score"],
                    "candidate_trend_fit_score": score_res["candidate_trend_fit_score"],
                    "candidate_commercial_fit": score_res["candidate_commercial_fit"],
                    "category_opportunity_score": score_res["category_opportunity_score"],
                    "word_glue_penalty": score_res["word_glue_penalty"],
                    "ai_generated_feel_score": score_res["ai_generated_feel_score"],
                    "pattern_diversity_score": score_res["pattern_diversity_score"],
                    "prefix_frequency": prefix_freq,
                    "suffix_frequency": suffix_freq,
                    "phonetic_cluster_id": phon_cluster_id,
                    "morphology_type": morph_type,
                    "ai_naming_artifact_score": score_res["ai_naming_artifact_score"],
                    "final_judge_assessment": judge_assessment,
                    "multi_model_review": copy.deepcopy(multi_evaluations.get(d, {})),
                    "consensus": copy.deepcopy(multi_evaluations.get(d, {}).get("consensus", {})),
                    "linguistic_judge": copy.deepcopy(multi_evaluations.get(d, {}).get("linguistic_judge", {})),
                    "brand_judge": copy.deepcopy(multi_evaluations.get(d, {}).get("brand_judge", {})),
                    "commercial_judge": copy.deepcopy(multi_evaluations.get(d, {}).get("commercial_judge", {})),
                    "red_team_judge": copy.deepcopy(multi_evaluations.get(d, {}).get("red_team_judge", {})),
                    "judge_agreement": multi_evaluations.get(d, {}).get("judge_agreement"),
                    "judge_disagreement": copy.deepcopy(multi_evaluations.get(d, {}).get("judge_disagreement", {})),
                    "consensus_confidence": multi_evaluations.get(d, {}).get("consensus_confidence"),
                    "outlier_detected": multi_evaluations.get(d, {}).get("outlier_detected", False),
                    "gibberish_risk_score": multi_evaluations.get(d, {}).get("gibberish_risk_score"),
                    "gibberish_quality_band": multi_evaluations.get(d, {}).get("gibberish_quality_band"),
                    "short_but_meaningless": multi_evaluations.get(d, {}).get("short_but_meaningless", False),
                    "score_trace": trace_log,
                    # Phase 3 Buyer Intelligence Fields
                    "buyer_categories": buyer_intel["buyer_categories"],
                    "primary_buyer": buyer_intel["primary_buyer"],
                    "secondary_buyers": buyer_intel["secondary_buyers"],
                    "potential_product_categories": buyer_intel["potential_product_categories"],
                    "saas_applicability": buyer_intel["saas_applicability"],
                    "startup_applicability": buyer_intel["startup_applicability"],
                    "enterprise_applicability": buyer_intel["enterprise_applicability"],
                    "ecommerce_applicability": buyer_intel["ecommerce_applicability"],
                    "fintech_applicability": buyer_intel["fintech_applicability"],
                    "ai_applicability": buyer_intel["ai_applicability"],
                    "developer_tool_applicability": buyer_intel["developer_tool_applicability"],
                    "geographic_potential": buyer_intel["geographic_potential"],
                    "commercial_archetype": buyer_intel["commercial_archetype"]
                }
                scored_candidates.append(full_record)

            # Score Distribution Guard & Cluster Detection (Requirement 7)
            from quality_engine.score_guard import ScoreDistributionGuard
            score_integrity_audit = ScoreDistributionGuard.audit_scored_batch(scored_candidates)
            funnel_stats["score_integrity_audit"] = score_integrity_audit
            logger.info(
                f"[STAGE 8-SCORE-GUARD] Status: {score_integrity_audit['integrity_status']}, "
                f"Unique Overall: {score_integrity_audit['unique_overall_scores']}, "
                f"Unique Brand: {score_integrity_audit['unique_brandability_scores']}, "
                f"Clusters (>=3): {score_integrity_audit['cluster_count']}"
            )
            if score_integrity_audit["has_identical_clustering"]:
                logger.warning(
                    f"[SCORING_INTEGRITY_WARNING] {score_integrity_audit['cluster_count']} identical score clusters detected! "
                    f"Clusters: {score_integrity_audit['identical_score_clusters']}"
                )

            # Update one-word funnel quality pass count
            funnel_stats["one_word_funnel"]["quality_pass_one_word"] = sum(
                1 for sc in scored_candidates
                if (sc.get("naming_type") in ["ONE_WORD", "REAL_FOREIGN_WORD"] or sc.get("generation_strategy") == "ONE_WORD")
                and sc.get("quality_score", 0) >= 68
            )

            # Populate length distribution across ONE_WORD, INVENTED, COMPOUND
            for sc in scored_candidates:
                lbl = sc.get("domain", "").replace(".com", "").strip()
                l = len(lbl)
                l_key = "10+" if l >= 10 else str(l)
                m = sc.get("morphology_type", "INVENTED")
                bucket = "INVENTED"
                if m in ["REAL_WORD", "FOREIGN_WORD", "ONE_WORD"]:
                    bucket = "ONE_WORD"
                elif m == "COMPOUND":
                    bucket = "COMPOUND"
                elif m in ["PREFIX_SUFFIX", "HYBRID", "SEMANTIC_BRANDABLE", "INVENTED"]:
                    bucket = "INVENTED"

                if l_key in funnel_stats["length_distribution"].get(bucket, {}):
                    funnel_stats["length_distribution"][bucket][l_key] += 1
                if l_key in funnel_stats["length_distribution"]["TOTAL"]:
                    funnel_stats["length_distribution"]["TOTAL"][l_key] += 1

            # ==========================================
            # STAGE 9: final_selection (Diversity Engine & Final Judge Gate)
            # ==========================================
            update_stage("final_selection")

            # Section 12 & Section 8 Hard Safety Invariants:
            # A candidate may enter final opportunities ONLY IF verified by an authoritative provider.
            safe_scored_candidates = []
            for c in scored_candidates:
                d = c.get("domain", "")
                res_obj = c.get("availability_result")
                prov = c.get("availability_provider") or (getattr(res_obj, "provider", None) if res_obj else None)
                status_val = c.get("availability_status") or (getattr(res_obj, "status", None).value if res_obj else None)
                verified = c.get("availability_verified") if "availability_verified" in c else getattr(res_obj, "availability_verified", False)
                check_status = c.get("availability_check_status") if "availability_check_status" in c else getattr(res_obj, "availability_check_status", "UNVERIFIED")

                if is_production_mode():
                    # 1. Provider must not be mock
                    if not prov or prov in MOCK_REGISTRY_PROVIDERS or "mock" in str(prov).lower():
                        logger.critical(
                            f"[SAFETY-ASSERTION-REJECT] Candidate {d} uses mock provider '{prov}' in production! Rejecting."
                        )
                        continue
                    # 2. Provider must be an authoritative registry provider
                    if prov not in REAL_REGISTRY_PROVIDERS:
                        logger.critical(
                            f"[SAFETY-ASSERTION-REJECT] Candidate {d} provider '{prov}' is not in REAL_REGISTRY_PROVIDERS! Rejecting."
                        )
                        continue
                    # 3. Availability must be explicitly verified
                    if not verified:
                        logger.critical(
                            f"[SAFETY-ASSERTION-REJECT] Candidate {d} availability_verified is False in production! Rejecting."
                        )
                        continue
                    # 4. Check status must be VERIFIED
                    if check_status != "VERIFIED":
                        logger.critical(
                            f"[SAFETY-ASSERTION-REJECT] Candidate {d} availability_check_status '{check_status}' != VERIFIED! Rejecting."
                        )
                        continue

                # Hard invariants regardless of environment
                if status_val != AvailabilityStatus.AVAILABLE_STANDARD.value and status_val != "AVAILABLE_STANDARD":
                    logger.warning(f"[SAFETY-ASSERTION-REJECT] Candidate {d} status '{status_val}' != AVAILABLE_STANDARD! Rejecting.")
                    continue
                if c.get("is_registered", False) or not c.get("registration_available", True):
                    logger.warning(f"[SAFETY-ASSERTION-REJECT] Candidate {d} is_registered=True! Rejecting.")
                    continue
                if c.get("is_premium", False) or c.get("premium_status") == "PREMIUM":
                    logger.warning(f"[SAFETY-ASSERTION-REJECT] Candidate {d} premium_status=PREMIUM! Rejecting.")
                    continue

                safe_scored_candidates.append(c)

            funnel_stats["funnel_rejections"]["availability"] = max(0, int(funnel_stats.get("checked", 0)) - int(funnel_stats.get("available_standard", 0)))
            funnel_stats["funnel_rejections"]["ip"] = max(0, int(funnel_stats.get("ip_screened", 0)) - int(funnel_stats.get("ip_passed", 0)))

            # =============================================================
            # STAGE 9A: consensus + quality floors + learned ranking
            # Diversity is deliberately AFTER these gates.
            # =============================================================
            mm_cfg = self.multi_model_evaluator.config
            consensus_candidates: List[Dict[str, Any]] = []
            for c in safe_scored_candidates:
                review = c.get("multi_model_review") or {}
                consensus = c.get("consensus") or {}
                evaluated = bool(review)
                verdict = str(consensus.get("verdict", "REVIEW")).upper()
                confidence = float(c.get("consensus_confidence") or consensus.get("confidence") or 0.0)
                consensus_score = float(consensus.get("consensus_score") or 0.0)
                if bool(mm_cfg.get("enabled", True)) and not evaluated:
                    c["selection_rejection_stage"] = "MULTI_MODEL_EVALUATED"
                    continue
                if evaluated and (verdict == "REJECT" or consensus_score < float(mm_cfg.get("arbiter_review_min_score", 60.0))):
                    c["selection_rejection_stage"] = "CONSENSUS_PASS"
                    continue
                if evaluated and confidence < float(mm_cfg.get("min_consensus_confidence", 55.0)):
                    c["selection_rejection_stage"] = "CONSENSUS_PASS"
                    continue
                consensus_candidates.append(c)
            funnel_stats["consensus_pass"] = len(consensus_candidates)
            funnel_stats["funnel_rejections"]["consensus"] = max(0, len(safe_scored_candidates) - len(consensus_candidates))

            quality_floor_candidates: List[Dict[str, Any]] = []
            for c in consensus_candidates:
                qb = c.get("quality_breakdown", {}) or {}
                fs = qb.get("_float_scores", {}) if isinstance(qb, dict) else {}
                pron = float(fs.get("pronunciation", c.get("pronunciation_score", 0.0)) or 0.0)
                brand = float(fs.get("brandability", c.get("brandability_score", 0.0)) or 0.0)
                comm = float(fs.get("commercial", c.get("commercial_score", 0.0)) or 0.0)
                linguistic = float((c.get("consensus") or {}).get("final_linguistic_quality") or (c.get("consensus") or {}).get("linguistic_quality") or pron)
                quality = float(c.get("quality_score", 0.0) or 0.0)
                floors_ok = (
                    quality >= float(mm_cfg.get("final_quality_floor", 68.0))
                    and brand >= float(mm_cfg.get("final_brand_floor", 60.0))
                    and comm >= float(mm_cfg.get("final_commercial_floor", 58.0))
                    and linguistic >= float(mm_cfg.get("final_linguistic_floor", 60.0))
                )
                if c.get("short_but_meaningless") or c.get("gibberish_quality_band") == "LIKELY_GIBBERISH":
                    floors_ok = False
                if not floors_ok:
                    c["selection_rejection_stage"] = "QUALITY_FLOOR_PASS"
                    continue
                c["quality_floor_components"] = {"quality": quality, "brand": brand, "commercial": comm, "linguistic": linguistic, "pronunciation": pron}
                quality_floor_candidates.append(c)
            funnel_stats["quality_floor_pass"] = len(quality_floor_candidates)
            funnel_stats["funnel_rejections"]["deterministic_quality"] = max(0, len(consensus_candidates) - len(quality_floor_candidates))

            # Phase 4 learning must influence rank BEFORE diversity.
            learned_score_map: Dict[str, float] = {}
            for cand in quality_floor_candidates:
                d = cand.get("domain") or cand.get("domain_name", "")
                l_score, l_status, l_version = self.ranker.predict_preference(cand)
                if l_score is not None:
                    learned_score_map[d] = l_score
                cand["learned_preference_score"] = l_score
                cand["learning_status"] = l_status
                cand["model_version"] = l_version
                consensus = cand.get("consensus") or {}
                weights = mm_cfg.get("final_rank_weights", {})
                deterministic_quality = float(cand.get("quality_score", 0.0) or 0.0)
                linguistic_quality = float(consensus.get("final_linguistic_quality") or consensus.get("linguistic_quality") or deterministic_quality)
                brand_quality = float(consensus.get("final_brand_quality") or consensus.get("brand_quality") or cand.get("brandability_score", 0.0))
                commercial_quality = float(consensus.get("final_commercial_quality") or consensus.get("commercial_quality") or cand.get("commercial_score", 0.0))
                buyer_quality = float(consensus.get("final_buyer_quality") or consensus.get("buyer_quality") or cand.get("buyer_clarity_score", 0.0))
                semantic_quality = float(consensus.get("final_semantic_quality") or consensus.get("semantic_quality") or cand.get("quality_breakdown", {}).get("semantic", 0.0))
                atom = cand.get("atom") or {}
                atom_signal = atom.get("atom_domain_score", atom.get("atom_market_signal", atom.get("atom_appraisal")))
                try:
                    atom_signal = float(atom_signal) if atom_signal is not None else 50.0
                except (TypeError, ValueError):
                    atom_signal = 50.0
                learning_signal = float(l_score) * 100.0 if l_score is not None else 50.0
                pattern = float(cand.get("pattern_diversity_score", 100.0) or 100.0)
                red_pen = float(consensus.get("red_team_penalty", 0.0) or 0.0)
                disagreement_pen = float((cand.get("judge_disagreement") or {}).get("disagreement_penalty", 0.0) or 0.0)
                invented_pen = float(cand.get("invented_penalty", 0.0) or 0.0)
                if (cand.get("invented_subtype") == "UNANCHORED" or cand.get("invented_quality_tier") in ["WEAK", "EXTREMELY_WEAK"]):
                    invented_pen += 6.0
                raw_rank = (
                    deterministic_quality * float(weights.get("deterministic", 0.27)) +
                    linguistic_quality * float(weights.get("linguistic", 0.11)) +
                    brand_quality * float(weights.get("brand", 0.13)) +
                    commercial_quality * float(weights.get("commercial", 0.13)) +
                    buyer_quality * float(weights.get("buyer", 0.09)) +
                    semantic_quality * float(weights.get("semantic", 0.08)) +
                    atom_signal * float(weights.get("atom", 0.06)) +
                    learning_signal * float(weights.get("learning", 0.07)) +
                    pattern * float(weights.get("pattern_diversity", 0.06))
                )
                final_rank = raw_rank - red_pen - disagreement_pen - min(12.0, invented_pen * 0.35) - max(0.0, (100.0 - pattern) * 0.08)
                c["final_rank_score"] = round(max(5.0, min(100.0, final_rank)), 3)
                c["selection_reasons"] = list(c.get("selection_reasons") or []) + [
                    f"final_rank_score={c['final_rank_score']:.1f}",
                    f"consensus_confidence={float(c.get('consensus_confidence') or 0):.1f}"
                ]
            funnel_stats["learned_ranked"] = len(quality_floor_candidates)

            # =============================================================
            # STAGE 9B: bounded diversity selection
            # =============================================================
            diversity_input = sorted(quality_floor_candidates, key=lambda c: float(c.get("final_rank_score", 0.0)), reverse=True)
            funnel_stats["diversity_input"] = len(diversity_input)
            penalized_candidates = self.diversity_engine.apply_diversity_penalties(diversity_input)
            final_selection = self.diversity_engine.select_diverse_candidates(
                penalized_candidates,
                limit=min(FINAL_RESULT_COUNT, len(penalized_candidates)),
                min_quality_threshold=int(float(mm_cfg.get("final_quality_floor", 68.0)))
            )
            funnel_stats["diversity_selected"] = len(final_selection)
            funnel_stats["funnel_rejections"]["diversity"] = max(0, len(diversity_input) - len(final_selection))
            funnel_stats["final"] = len(final_selection)
            funnel_stats["one_word_funnel"]["final_one_word"] = sum(
                1 for c in final_selection
                if c.get("naming_type") in ["ONE_WORD", "REAL_WORD", "REAL_FOREIGN_WORD"] or c.get("generation_strategy") == "ONE_WORD"
            )
            funnel_stats["one_word_funnel"]["final"] = funnel_stats["one_word_funnel"]["final_one_word"]
            funnel_stats["one_word_final"] = funnel_stats["one_word_funnel"]["final_one_word"]

            # Phase 3 Quality Tiers & Opportunity Explanations
            tiered_results = self.quality_tier_engine.organize_tiers(
                final_selection,
                learned_scores=learned_score_map
            )
            tier_a = tiered_results["tier_a"]
            tier_b = tiered_results["tier_b"]
            watchlist = tiered_results["watchlist"]

            for fd in final_selection:
                fd["is_final_selected"] = True

            # Category Observability & Distribution
            final_cat_counts: Dict[str, int] = {}
            for fd in final_selection:
                c_name = fd.get("market_category", "Unknown")
                final_cat_counts[c_name] = final_cat_counts.get(c_name, 0) + 1
            funnel_stats["final_category_distribution"] = final_cat_counts
            logger.info(
                f"[STAGE 9] Final diverse opportunities selected: {len(final_selection)} "
                f"(Tier A: {len(tier_a)}, Tier B: {len(tier_b)}, Watchlist: {len(watchlist)}). "
                f"Category distribution: {final_cat_counts}. "
                f"One-words in final: {funnel_stats['one_word_funnel']['final']}"
            )

            # ==========================================
            # STAGE 10: saving_results (Supabase + Local Storage)
            # ==========================================
            update_stage("saving_results")

            # 1. Supabase Persistence
            try:
                from main import get_supabase
                sb = get_supabase()
                if sb:
                    # Save final verified domains
                    if final_selection:
                        supabase_records = []
                        for fd in final_selection:
                            supabase_records.append({
                                "candidate_id": fd.get("candidate_id"),
                                "run_id": fd.get("run_id", scan_id),
                                "domain_name": fd["domain_name"],
                                "category": fd["category"],
                                "availability_status": fd["availability_status"],
                                "availability_provider": fd["availability_provider"],
                                "availability_verified": fd.get("availability_verified", True),
                                "availability_check_status": fd.get("availability_check_status", "VERIFIED"),
                                "availability_checked_at": fd.get("availability_checked_at") or fd.get("checked_at"),
                                "premium_status": fd.get("premium_status", "NOT_PREMIUM"),
                                "premium_provider": fd.get("premium_provider", fd["availability_provider"]),
                                "is_registered": fd["is_registered"],
                                "is_premium": fd["is_premium"],
                                "registration_available": fd["registration_available"],
                                "checked_at": fd["checked_at"],
                                "overall_score": fd["overall_score"],
                                "brandability_score": fd["brandability_score"],
                                "trend_score": fd["trend_score"],
                                "commercial_score": fd["commercial_score"],
                                "scan_id": fd["scan_id"],
                                "naming_type": fd["naming_type"],
                                "quality_score": fd["quality_score"],
                                "quality_breakdown": fd["quality_breakdown"],
                                "ip_risk_level": fd["ip_risk_level"],
                                "ip_check_status": fd.get("ip_check_status", "CHECKED"),
                                "ip_risk_score": fd["ip_risk_score"],
                                "generation_strategy": fd["generation_strategy"],
                                "source_concept": fd["source_concept"],
                                "generator_model": fd["generator_model"],
                                "ip_evidence": fd["ip_risk"],
                                "decision": fd["decision"],
                                "reasons": fd["reasons"],
                                # Phase 2.5 columns
                                "market_category": fd.get("market_category", "AI_STARTUPS"),
                                "subcategory": fd.get("subcategory", "Core Platform"),
                                "concept_source": fd.get("concept_source", "EVERGREEN_COMMERCIAL_NICHES"),
                                "semantic_concept": fd.get("semantic_concept", "GENERAL_COMMERCIAL"),
                                "source_language": fd.get("source_language", "en"),
                                "original_word": fd.get("original_word"),
                                "original_meaning": fd.get("original_meaning"),
                                "translation": fd.get("translation"),
                                "pronunciation": fd.get("pronunciation"),
                                "romanization": fd.get("romanization"),
                                "literal_meaning": fd.get("literal_meaning"),
                                "english_meaning": fd.get("english_meaning"),
                                "linguistic_confidence": fd.get("linguistic_confidence", 1.0),
                                "radio_test_score": fd.get("radio_test_score", 80),
                                "category_fit": fd.get("category_fit", {}),
                                "opportunity_score": fd.get("opportunity_score", 75),
                                # Phase 2.75 columns
                                "natural_brand_score": fd.get("natural_brand_score", 75),
                                "compound_naturalness_score": fd.get("compound_naturalness_score", 75),
                                "buyer_clarity_score": fd.get("buyer_clarity_score", 75),
                                "buyer_count": fd.get("buyer_count", 3),
                                "buyer_industries": fd.get("buyer_industries", []),
                                "startup_fit": fd.get("startup_fit", ""),
                                "startup_naturalness_score": fd.get("startup_naturalness_score", 75),
                                "concept_trend_score": fd.get("concept_trend_score", 80),
                                "candidate_trend_fit_score": fd.get("candidate_trend_fit_score", 80),
                                "candidate_commercial_fit": fd.get("candidate_commercial_fit", 75),
                                "category_opportunity_score": fd.get("category_opportunity_score", 85),
                                "word_glue_penalty": fd.get("word_glue_penalty", 0),
                                "ai_generated_feel_score": fd.get("ai_generated_feel_score", 20),
                                "final_judge_assessment": fd.get("final_judge_assessment", {}),
                                # Phase 2.75B columns
                                "pattern_diversity_score": fd.get("pattern_diversity_score", 100.0),
                                "prefix_frequency": fd.get("prefix_frequency", 1),
                                "suffix_frequency": fd.get("suffix_frequency", 1),
                                "phonetic_cluster_id": fd.get("phonetic_cluster_id", ""),
                                "morphology_type": fd.get("morphology_type", "INVENTED"),
                                "ai_naming_artifact_score": fd.get("ai_naming_artifact_score", 20.0),
                                "naming_template": fd.get("naming_template", "STANDARD"),
                                "generation_prompt_version": fd.get("generation_prompt_version", "v2.75b"),
                                "generation_batch_id": fd.get("generation_batch_id", "")
                            })
                        
                        is_test_run = (trigger == "test_audit" or not is_production_mode() or os.getenv("ALLOW_MOCK_REGISTRY", "false").lower() == "true")
                        # Section 9 Hard Invariant: NEVER save mock registry records to production Supabase
                        clean_supabase_records = [
                            r for r in supabase_records
                            if r.get("availability_provider") not in MOCK_REGISTRY_PROVIDERS
                            and "mock" not in str(r.get("availability_provider", "")).lower()
                            and r.get("availability_verified") is True
                        ]

                        if is_test_run:
                            logger.info(f"[TEST-MODE] Test run triggered ({trigger}). Skipping insertion into production Supabase final_domains.")
                        elif clean_supabase_records:
                            sb.table("final_domains").insert(clean_supabase_records).execute()
                            logger.info(f"Persisted {len(clean_supabase_records)} verified records to Supabase final_domains.")

                    # Save generation run audit record
                    try:
                        run_record = {
                            "run_id": scan_id,
                            "trigger": trigger,
                            "status": "completed",
                            "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            "stats": funnel_stats,
                            "concepts": concepts
                        }
                        sb.table("domain_generation_runs").insert(run_record).execute()
                    except Exception as run_err:
                        logger.debug(f"Run audit insert error: {run_err}")

                    # Save candidate audit records (sample batch to avoid payload overload)
                    try:
                        candidate_inserts = []
                        for sc in scored_candidates[:50]:
                            candidate_inserts.append({
                                "candidate_id": sc.get("candidate_id"),
                                "run_id": sc.get("run_id", scan_id),
                                "domain": sc["domain_name"],
                                "generation_strategy": sc["generation_strategy"],
                                "source_concept": sc["source_concept"],
                                "generator_model": sc["generator_model"],
                                "naming_type": sc["naming_type"],
                                "availability_status": sc["availability_status"],
                                "is_registered": sc["is_registered"],
                                "is_premium": sc["is_premium"],
                                "quality_score": sc["quality_score"],
                                "quality_breakdown": sc["quality_breakdown"],
                                "ip_risk_level": sc["ip_risk_level"],
                                "ip_check_status": sc.get("ip_check_status", "CHECKED"),
                                "ip_risk_score": sc["ip_risk_score"],
                                "decision": sc["decision"],
                                "reasons": sc["reasons"],
                                # Phase 2.5 columns
                                "market_category": sc.get("market_category", "AI_STARTUPS"),
                                "subcategory": sc.get("subcategory", "Core Platform"),
                                "concept_source": sc.get("concept_source", "EVERGREEN_COMMERCIAL_NICHES"),
                                "semantic_concept": sc.get("semantic_concept", "GENERAL_COMMERCIAL"),
                                "source_language": sc.get("source_language", "en"),
                                "original_word": sc.get("original_word"),
                                "original_meaning": sc.get("original_meaning"),
                                "translation": sc.get("translation"),
                                "pronunciation": sc.get("pronunciation"),
                                "romanization": sc.get("romanization"),
                                "literal_meaning": sc.get("literal_meaning"),
                                "english_meaning": sc.get("english_meaning"),
                                "linguistic_confidence": sc.get("linguistic_confidence", 1.0),
                                "radio_test_score": sc.get("radio_test_score", 80),
                                "category_fit": sc.get("category_fit", {}),
                                "opportunity_score": sc.get("opportunity_score", 75),
                                # Phase 2.75 columns
                                "natural_brand_score": sc.get("natural_brand_score", 75),
                                "compound_naturalness_score": sc.get("compound_naturalness_score", 75),
                                "buyer_clarity_score": sc.get("buyer_clarity_score", 75),
                                "startup_naturalness_score": sc.get("startup_naturalness_score", 75),
                                "concept_trend_score": sc.get("concept_trend_score", 80),
                                "candidate_trend_fit_score": sc.get("candidate_trend_fit_score", 80),
                                "candidate_commercial_fit": sc.get("candidate_commercial_fit", 75),
                                "category_opportunity_score": sc.get("category_opportunity_score", 85),
                                "word_glue_penalty": sc.get("word_glue_penalty", 0),
                                "ai_generated_feel_score": sc.get("ai_generated_feel_score", 20),
                                "final_judge_assessment": sc.get("final_judge_assessment", {}),
                                # Phase 2.75B columns
                                "pattern_diversity_score": sc.get("pattern_diversity_score", 100.0),
                                "prefix_frequency": sc.get("prefix_frequency", 1),
                                "suffix_frequency": sc.get("suffix_frequency", 1),
                                "phonetic_cluster_id": sc.get("phonetic_cluster_id", ""),
                                "morphology_type": sc.get("morphology_type", "INVENTED"),
                                "ai_naming_artifact_score": sc.get("ai_naming_artifact_score", 20.0),
                                "naming_template": sc.get("naming_template", "STANDARD"),
                                "generation_prompt_version": sc.get("generation_prompt_version", "v2.75b"),
                                "generation_batch_id": sc.get("generation_batch_id", "")
                            })
                        if candidate_inserts:
                            sb.table("domain_candidates").insert(candidate_inserts).execute()
                    except Exception as cand_err:
                        logger.debug(f"Candidate audit insert error: {cand_err}")

            except Exception as sbe:
                logger.error(f"Supabase persistence error: {sbe}")

            # 2. Local job_state.json & Phase 4 Learning Persistence
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

            # Phase 4 Candidate History & Learning Store
            self.learning_store.save_candidate_records(scored_candidates, run_id=scan_id)

            # Phase 4 Strategy Performance Telemetry
            strategy_stats = StrategyOptimizer.calculate_strategy_performance(
                scored_candidates,
                feedback=self.learning_store.get_feedback()
            )
            self.learning_store.update_strategy_performance(strategy_stats)

            # Phase 4 Generation Run Record
            self.learning_store.save_generation_run({
                "run_id": scan_id,
                "run_date": now_iso,
                "concept_count": len(concepts),
                "candidate_count": len(raw_strategy_records),
                "strategy_distribution": funnel_stats.get("strategy_distribution", {}),
                "availability_count": avail_count,
                "premium_count": prem_count,
                "ip_blocked_count": funnel_stats.get("ip_critical_rejected", 0),
                "final_count": len(final_selection)
            })

            is_test_run = (trigger == "test_audit" or not is_production_mode() or os.getenv("ALLOW_MOCK_REGISTRY", "false").lower() == "true")
            if is_test_run:
                logger.info(f"[TEST-MODE] Preserving production latest_results in {STATE_FILE} during test run ({trigger}).")
                state["test_audit_results"] = {
                    "run_date": now_iso,
                    "status": "completed",
                    "scan_id": scan_id,
                    "stats": funnel_stats,
                    "results": final_selection,
                    "tier_a": tier_a,
                    "tier_b": tier_b,
                    "watchlist": watchlist,
                    "strategy_performance": strategy_stats,
                    "learning_status": self.ranker.get_status(),
                    "model_version": self.ranker.metadata.get("version", "v0"),
                    "sample_count": self.ranker.metadata.get("training_sample_count", 0),
                    "scored_candidates": scored_candidates
                }
            else:
                state["latest_results"] = {
                    "run_date": now_iso,
                    "status": "completed",
                    "concepts": concepts,
                    "scan_id": scan_id,
                    "stats": {
                        "generated": job_state["candidates_generated"],
                        "checked": job_state["checked"],
                        "available_standard": job_state["available_standard"],
                        "registered": job_state["registered"],
                        "premium": job_state["premium"],
                        "funnel": funnel_stats,
                        "final": len(final_selection)
                    },
                    "results": final_selection,
                    "tier_a": tier_a,
                    "tier_b": tier_b,
                    "watchlist": watchlist,
                    "strategy_performance": strategy_stats,
                    "learning_status": self.ranker.get_status(),
                    "model_version": self.ranker.metadata.get("version", "v0"),
                    "sample_count": self.ranker.metadata.get("training_sample_count", 0),
                    "scored_candidates": scored_candidates
                }

            # ==========================================
            # STAGE 11: completed
            # ==========================================
            job_state["status"] = "completed"
            job_state["stage"] = "completed"
            job_state["completed"] = True
            job_state["completed_at"] = now_iso
            save_job_state(state)
            logger.info(
                f"[PIPELINE-COMPLETE] Run {scan_id} finished. "
                f"RAW: {funnel_stats['raw_generated']}, "
                f"STRUCTURAL_PASS: {funnel_stats['structural_passed']}, "
                f"CHECKED: {funnel_stats['checked']}, "
                f"AVAILABLE_STANDARD: {funnel_stats['available_standard']}, "
                f"IP_PASSED: {funnel_stats['ip_passed']}, "
                f"AI_EVALUATED: {funnel_stats['ai_evaluated']}, "
                f"FINAL: {len(final_selection)}"
            )

            if is_test_run:
                return {
                    "run_date": now_iso,
                    "status": "completed",
                    "scan_id": scan_id,
                    "stats": funnel_stats,
                    "results": final_selection,
                    "scored_candidates": scored_candidates
                }
            return state["latest_results"]

        except Exception as e:
            logger.error(f"Domain Hunter Pipeline failed: {e}", exc_info=True)
            job_state["status"] = "failed"
            job_state["completed"] = True
            job_state["error"] = str(e)
            job_state["completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            save_job_state(state)
            raise e

        finally:
            self.is_running = False

def setup_scheduler(router: ModelRouter, http_client, availability_engine: Optional[AvailabilityEngine] = None):
    scheduler = AsyncIOScheduler()
    pipeline = DomainHunterPipeline(router, http_client, availability_engine)

    enabled = os.getenv("DAILY_HUNT_ENABLED", "true").lower() == "true"
    hour = int(os.getenv("DAILY_HUNT_HOUR", "3"))
    minute = int(os.getenv("DAILY_HUNT_MINUTE", "0"))
    timezone = os.getenv("DAILY_HUNT_TIMEZONE", "Africa/Cairo")

    async def scheduled_hunt_wrapper():
        logger.info("[SCHEDULER] Triggering daily scheduled domain hunt...")
        try:
            await pipeline.run_domain_hunt(trigger="scheduled")
        except Exception as e:
            logger.error(f"[SCHEDULER] Daily hunt execution error: {e}")

    if enabled:
        scheduler.add_job(
            scheduled_hunt_wrapper,
            CronTrigger(hour=hour, minute=minute, timezone=timezone),
            id="daily_hunt"
        )
        scheduler.start()
        logger.info(f"Scheduler active: daily hunt at {hour:02d}:{minute:02d} {timezone}")

    return scheduler, pipeline
