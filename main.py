import os
import time
import json
import re
import asyncio
import urllib.parse
import collections
import logging
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import httpx
import xmltodict
try:
    from pytrends.request import TrendReq
except ImportError:
    TrendReq = None
from pydantic import BaseModel
from dotenv import load_dotenv
import datetime
import io
import csv

from router import ModelRouter
from scheduler import setup_scheduler, get_job_state
from availability import (
    AvailabilityEngine,
    AvailabilityStatus,
    AvailabilityResult,
    REAL_REGISTRY_PROVIDERS,
    MOCK_REGISTRY_PROVIDERS,
    is_production_mode
)
from quality_engine.config import get_quality_weights, DEFAULT_STRATEGY_TARGETS, MIN_QUALITY_SCORE
from risk_engine.models import RiskLevel
from learning_engine import (
    LearningStore,
    TrainingFeaturePipeline,
    StatisticalRanker,
    StrategyOptimizer
)

class InMemoryLogHandler(logging.Handler):
    def __init__(self, capacity=400):
        super().__init__()
        self.buffer = collections.deque(maxlen=capacity)
    
    def emit(self, record):
        try:
            msg = self.format(record)
            entry = {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "level": record.levelname,
                "name": record.name,
                "message": msg,
                "raw_message": record.getMessage()
            }
            self.buffer.append(entry)
        except Exception:
            pass

log_handler = InMemoryLogHandler()
log_handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
logger = logging.getLogger("Main")
logger.addHandler(log_handler)
logging.getLogger().addHandler(log_handler)
logging.getLogger("Scheduler").addHandler(log_handler)
logging.getLogger("AvailabilityEngine").addHandler(log_handler)
logging.getLogger("ModelRouter").addHandler(log_handler)

# Seed with initial core startup logs
log_handler.buffer.append({
    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "level": "INFO",
    "name": "System",
    "message": "Domain Hunter 2.0 Command Center core initialized",
    "raw_message": "Domain Hunter 2.0 Command Center core initialized"
})

try:
    from supabase import create_client, Client
except ImportError:
    Client = None
    create_client = None

load_dotenv(override=True)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Optional['Client'] = None
if SUPABASE_URL and SUPABASE_KEY and create_client:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        log_handler.buffer.append({
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": "INFO",
            "name": "Supabase",
            "message": "Supabase client connected to cloud persistence",
            "raw_message": "Supabase client connected to cloud persistence"
        })
    except Exception as e:
        print(f"Supabase init error: {e}")

app = FastAPI(title="Domain Hunter API")
router = ModelRouter()

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

http_client = httpx.AsyncClient(timeout=15.0)
availability_engine = AvailabilityEngine(http_client)
scheduler = None
job_runner = None

async def check_domains_availability(domains: list[str]) -> dict:
    """
    Normalized batch availability check through AvailabilityEngine.
    Returns {domain: bool} where True ONLY if status == AVAILABLE_STANDARD.
    """
    results = await availability_engine.check_batch(domains)
    return {d: res.is_accepted() for d, res in results.items()}

@app.on_event("startup")
async def startup_event():
    global scheduler, job_runner
    scheduler, job_runner = setup_scheduler(router, http_client, availability_engine)

@app.on_event("shutdown")
async def shutdown_event():
    await http_client.aclose()
    await router.client.aclose()
    if scheduler:
        scheduler.shutdown()

@app.get("/", response_class=HTMLResponse)
@app.get("/hunt", response_class=HTMLResponse)
@app.get("/history", response_class=HTMLResponse)
@app.get("/analytics", response_class=HTMLResponse)
@app.get("/scanner", response_class=HTMLResponse)
@app.get("/export", response_class=HTMLResponse)
@app.get("/providers", response_class=HTMLResponse)
@app.get("/logs", response_class=HTMLResponse)
@app.get("/settings", response_class=HTMLResponse)
@app.get("/domains/history", response_class=HTMLResponse)
async def serve_frontend():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

@app.get("/api/health/providers")
async def health_providers():
    intel_health = router.intelligence.get_providers_health()
    providers_info = {
        "nvidia": {
            "name": "NVIDIA NIM",
            "status": "online" if os.getenv("NVIDIA_API_KEY") else "unconfigured",
            "models": ["nvidia/nemotron-3-super-120b-a12b", "deepseek-ai/deepseek-v4.1-flash", "glm-5.3-flash"],
            "roles": ["Trend Research", "Brandability", "Final Scoring"],
            "concurrency": int(os.getenv("NVIDIA_CONCURRENCY", "5")),
            "stats": intel_health.get("nvidia", {})
        },
        "xkiro": {
            "name": "xKiro AI",
            "status": "online" if os.getenv("XKIRO_API_KEY") else "unconfigured",
            "models": ["qwen/qwen3.8-max:free"],
            "roles": ["Domain Generation", "Candidate Judge"],
            "concurrency": int(os.getenv("XKIRO_CONCURRENCY", "5")),
            "stats": intel_health.get("xkiro", {})
        },
        "openrouter": {
            "name": "OpenRouter Gateway",
            "status": "online" if os.getenv("OPENROUTER_API_KEY") else "standby",
            "models": ["openrouter/auto"],
            "roles": ["Fallback Router"],
            "concurrency": int(os.getenv("OPENROUTER_CONCURRENCY", "5")),
            "stats": intel_health.get("openrouter", {})
        },
        "verisign_rdap": {
            "name": "Verisign RDAP",
            "status": "online",
            "type": "authoritative_registry",
            "role": "Official Authoritative Registry for .com domains",
            "endpoint": "https://rdap.verisign.com/com/v1/domain/"
        },
        "cloudflare_dns": {
            "name": "Cloudflare DoH",
            "status": "online",
            "type": "dns_nameserver",
            "role": "Fast Pre-filter via DNS Nameservers",
            "endpoint": "https://cloudflare-dns.com/dns-query"
        },
        "supabase": {
            "name": "Supabase Cloud",
            "status": "connected" if get_supabase() else "unconfigured",
            "type": "database",
            "role": "Verified Domain Storage & Historical Query Engine"
        }
    }
    return {
        "status": "ok",
        "providers": intel_health,
        "providers_info": providers_info,
        "availability_provider": "verisign_rdap"
    }

@app.get("/api/logs")
async def get_system_logs(limit: int = 100):
    logs = list(log_handler.buffer)[-limit:]
    logs.reverse()
    return {"success": True, "logs": logs}

@app.get("/api/settings")
async def get_settings():
    return {
        "success": True,
        "schedule": {
            "enabled": os.getenv("DAILY_HUNT_ENABLED", "true").lower() == "true",
            "hour": int(os.getenv("DAILY_HUNT_HOUR", "3")),
            "minute": int(os.getenv("DAILY_HUNT_MINUTE", "0")),
            "timezone": os.getenv("DAILY_HUNT_TIMEZONE", "Africa/Cairo")
        },
        "pipeline": {
            "target_tld": ".com",
            "batch_candidates": 135,
            "final_selection_limit": 10,
            "availability_timeout": 8.0,
            "cooldown_seconds": int(os.getenv("PROVIDER_COOLDOWN_SECONDS", "1800"))
        },
        "quality_engine": {
            "weights": get_quality_weights(),
            "strategy_targets": DEFAULT_STRATEGY_TARGETS,
            "min_quality_score": MIN_QUALITY_SCORE
        },
        "risk_engine": {
            "trademark_provider": "USPTO Official API",
            "curated_brands_count": 60,
            "risk_levels": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
            "critical_risk_rejection": True
        },
        "system": {
            "app_name": "Domain Hunter",
            "subtitle": "AI Domain Intelligence Command Center",
            "version": "2.0.0",
            "authoritative_registry": "Verisign RDAP",
            "supabase_configured": bool(SUPABASE_URL and SUPABASE_KEY)
        }
    }

class BatchScanRequest(BaseModel):
    domains: List[str]

@app.post("/api/availability/scan")
async def scan_domains_availability(req: BatchScanRequest):
    if not req.domains:
        return {"success": True, "results": []}
    
    cleaned_domains = []
    for raw in req.domains[:50]:
        d = raw.strip().lower()
        if d:
            if not d.endswith(".com"):
                d = f"{d}.com"
            cleaned_domains.append(d)
            
    results_map = await availability_engine.check_batch(cleaned_domains)
    output = []
    for d in cleaned_domains:
        res = results_map.get(d)
        if res:
            output.append({
                "domain": res.domain,
                "status": res.status.value,
                "provider": res.provider,
                "is_registered": res.is_registered,
                "is_premium": res.is_premium,
                "registration_available": res.registration_available,
                "checked_at": res.checked_at,
                "rejection_reason": res.rejection_reason
            })
    return {"success": True, "results": output}

@app.get("/api/domains/latest")
async def get_latest_domains():
    """
    Phase 18 & Section 11: Final Output Contract.
    Must return ONLY verified AVAILABLE_STANDARD opportunities belonging strictly to the CURRENT/latest run.
    Never mixes candidates from previous runs.
    """
    state = get_job_state()
    latest = state.get("latest_results") or {}
    current_scan_id = latest.get("scan_id")

    sb = get_supabase()
    if sb:
        try:
            target_scan_id = current_scan_id
            if not target_scan_id:
                recent_rec = sb.table("final_domains").select("scan_id").order("created_at", desc=True).limit(1).execute()
                if recent_rec.data:
                    target_scan_id = recent_rec.data[0].get("scan_id")

            def is_verified_opportunity(d: dict) -> bool:
                prov = (d.get("availability_provider") or "verisign_rdap").strip().lower()
                is_mock = prov in MOCK_REGISTRY_PROVIDERS or "mock" in prov or "test" in prov
                if is_production_mode() and is_mock:
                    return False
                if is_production_mode() and prov not in REAL_REGISTRY_PROVIDERS:
                    return False
                return (
                    d.get("availability_status") == "AVAILABLE_STANDARD"
                    and not d.get("is_registered", False)
                    and not d.get("is_premium", False)
                    and d.get("premium_status") != "PREMIUM"
                    and not is_mock
                )

            verified_data = []
            if target_scan_id:
                domains_res = (
                    sb.table("final_domains")
                    .select("*")
                    .eq("scan_id", target_scan_id)
                    .eq("availability_status", "AVAILABLE_STANDARD")
                    .order("overall_score", desc=True)
                    .execute()
                )
                verified_data = [d for d in domains_res.data if is_verified_opportunity(d)]

            if not verified_data and latest.get("results"):
                verified_data = [d for d in latest.get("results", []) if is_verified_opportunity(d)]

            for item in verified_data:
                if not item.get("domain") and item.get("domain_name"):
                    item["domain"] = item["domain_name"]
                elif not item.get("domain_name") and item.get("domain"):
                    item["domain_name"] = item["domain"]

            if not verified_data:
                return {"status": "idle", "scan": None, "domains": []}

            latest_date_str = verified_data[0].get("created_at") or latest.get("run_date")
            return {
                "status": "success",
                "scan": {
                    "id": target_scan_id or verified_data[0].get("scan_id", "latest_verified_batch"),
                    "completed_at": latest_date_str,
                    "domains_found": len(verified_data),
                    "concepts": latest.get("concepts", [])
                },
                "domains": verified_data
            }
        except Exception as e:
            logger.error(f"Failed to query latest domains from Supabase: {e}")
            if latest.get("results"):
                verified = [d for d in latest.get("results", []) if is_verified_opportunity(d)]
                return {
                    "status": "success",
                    "scan": {
                        "id": current_scan_id or "local_fallback_batch",
                        "completed_at": latest.get("run_date"),
                        "domains_found": len(verified),
                        "concepts": latest.get("concepts", [])
                    },
                    "domains": verified
                }
            return JSONResponse(status_code=500, content={"error": f"Query failed: {str(e)}"})
    else:
        def is_verified_opportunity(d: dict) -> bool:
            prov = (d.get("availability_provider") or "verisign_rdap").strip().lower()
            is_mock = prov in MOCK_REGISTRY_PROVIDERS or "mock" in prov or "test" in prov
            if is_production_mode() and is_mock:
                return False
            if is_production_mode() and prov not in REAL_REGISTRY_PROVIDERS:
                return False
            return (
                d.get("availability_status") == "AVAILABLE_STANDARD"
                and not d.get("is_registered", False)
                and not d.get("is_premium", False)
                and d.get("premium_status") != "PREMIUM"
                and not is_mock
            )

        if not latest or not latest.get("results"):
            return {"status": "idle", "scan": None, "domains": []}
        verified = [d for d in latest.get("results", []) if is_verified_opportunity(d)]
        return {
            "status": "success",
            "scan": {
                "id": current_scan_id or "local_json_batch",
                "completed_at": latest.get("run_date"),
                "domains_found": len(verified),
                "concepts": latest.get("concepts", [])
            },
            "domains": verified
        }

@app.get("/api/domains/status")
async def get_job_status():
    """
    Phase 10: Reliable job status endpoint tracking pipeline stages and counters.
    """
    state = get_job_state()
    current = state.get("current_job", {})
    latest = state.get("latest_results", {})
    
    return {
        "status": current.get("status", "idle"),
        "stage": current.get("stage", "idle"),
        "candidates_generated": current.get("candidates_generated", 0),
        "checked": current.get("checked", 0),
        "available_standard": current.get("available_standard", 0),
        "registered": current.get("registered", 0),
        "premium": current.get("premium", 0),
        "unknown": current.get("unknown", 0),
        "completed": current.get("completed", True),
        "last_run": latest.get("run_date") if latest else None,
        "next_run": "Scheduled via APScheduler",
        "domains_found": len(latest.get("results", [])) if latest else 0,
        "job_id": current.get("job_id"),
        "error": current.get("error")
    }

@app.post("/api/domains/run")
async def run_manual_job(background_tasks: BackgroundTasks):
    """
    Phase 9 & 17: Manual domain hunt trigger.
    Shares the exact same pipeline as the daily scheduled run.
    Rejects duplicate execution with HTTP 409 if already running.
    """
    if job_runner and job_runner.is_running:
        current = get_job_state().get("current_job", {})
        return JSONResponse(
            status_code=409, 
            content={
                "status": "already_running",
                "job_id": current.get("job_id", "active_hunt"),
                "message": "A domain hunt is currently in progress."
            }
        )
        
    if job_runner:
        background_tasks.add_task(job_runner.run_domain_hunt, trigger="manual")
        job_id = str(int(time.time()))
        return {
            "status": "started",
            "job_id": job_id
        }
        
    return JSONResponse(status_code=500, content={"status": "error", "message": "Job runner not initialized."})

# =========================================================================
# Phase 1 & 2 Intelligence Endpoints
# =========================================================================
@app.get("/api/quality/config")
async def get_quality_configuration():
    return {
        "success": True,
        "weights": get_quality_weights(),
        "strategy_targets": DEFAULT_STRATEGY_TARGETS,
        "min_quality_score": MIN_QUALITY_SCORE
    }

@app.get("/api/quality/stats")
async def get_quality_pipeline_stats():
    state = get_job_state()
    latest = state.get("latest_results", {})
    stats = latest.get("stats", {})
    return {
        "success": True,
        "run_date": latest.get("run_date"),
        "stats": stats,
        "funnel": stats.get("funnel", {})
    }

@app.get("/api/quality/debug_report")
async def get_quality_debug_report():
    """
    Requirements 7, 13 & 14: Debug report exposing candidate-level scoring breakdown,
    IP screening status, statistical score distribution metrics, and identical score cluster guard.
    """
    from quality_engine.score_guard import ScoreDistributionGuard
    state = get_job_state()
    latest = state.get("latest_results", {})
    candidates = latest.get("results", [])

    guard_audit = ScoreDistributionGuard.audit_scored_batch(candidates)

    debug_candidates = []
    for c in candidates:
        domain = c.get("domain") or c.get("domain_name", "")
        q_breakdown = c.get("quality_breakdown") or {}
        f_scores = q_breakdown.get("_float_scores") or {}

        brand = float(f_scores.get("brandability", c.get("brandability_score", 0.0)))
        trend = float(f_scores.get("trend", c.get("trend_score", 0.0)))
        comm = float(f_scores.get("commercial", c.get("commercial_score", 0.0)))
        overall = float(f_scores.get("overall_score", c.get("overall_score", c.get("quality_score", 0.0))))

        trace = c.get("score_trace") or {}

        debug_candidates.append({
            "domain": domain,
            "candidate_id": c.get("candidate_id", ""),
            "naming_type": c.get("naming_type", "INVENTED"),
            "generation_strategy": c.get("generation_strategy", "OTHER"),
            "quality_score": c.get("quality_score", int(round(overall))),
            "overall_score": overall,
            "brandability_score": brand,
            "trend_score": trend,
            "commercial_score": comm,
            "memorability_score": float(f_scores.get("memorability", q_breakdown.get("memorability", 0.0))),
            "pronunciation_score": float(f_scores.get("pronunciation", q_breakdown.get("pronunciation", 0.0))),
            "simplicity_score": float(f_scores.get("simplicity", q_breakdown.get("simplicity", 0.0))),
            "distinctiveness_score": float(f_scores.get("distinctiveness", q_breakdown.get("distinctiveness", 0.0))),
            "candidate_trend_fit_score": float(f_scores.get("candidate_trend_fit", c.get("candidate_trend_fit_score", trend))),
            "candidate_commercial_fit": float(f_scores.get("candidate_commercial_fit", c.get("candidate_commercial_fit", comm))),
            "buyer_clarity": float(f_scores.get("buyer_clarity", c.get("buyer_clarity_score", 0.0))),
            "concept_trend_score": float(c.get("concept_trend_score", 0.0)),
            "category_opportunity_score": float(c.get("category_opportunity_score", 0.0)),
            "scoring_status": trace.get("scoring_status", "DETERMINISTIC_EVALUATED"),
            "scoring_provider": trace.get("scoring_provider", "deterministic_linguistic_v2.75"),
            "scoring_model": trace.get("scoring_model", "phonetic_sonority_model"),
            "fallback_used": trace.get("fallback_used", True),
            "ip_risk_level": c.get("ip_risk_level", "NOT_CHECKED"),
            "ip_check_status": c.get("ip_check_status", "NOT_CHECKED")
        })

    return {
        "success": True,
        "run_date": latest.get("run_date"),
        "scan_id": latest.get("scan_id"),
        "scoring_integrity_status": guard_audit["integrity_status"],
        "has_identical_clustering": guard_audit["has_identical_clustering"],
        "identical_score_clusters": guard_audit["identical_score_clusters"],
        "distribution_metrics": guard_audit,
        "candidates": debug_candidates
    }

@app.get("/api/domains/research")
async def get_domains_research():
    state = get_job_state()
    latest = state.get("latest_results", {})
    concepts = latest.get("concepts", [])
    return {
        "success": True,
        "concepts": concepts
    }

@app.get("/api/domains/generate")
async def get_domains_generate():
    state = get_job_state()
    latest = state.get("latest_results", {})
    results = latest.get("results", [])
    return {
        "success": True,
        "candidates": results,
        "count": len(results)
    }

@app.get("/api/domains/{domain_or_id}/quality")
async def get_domain_quality(domain_or_id: str):
    domain_clean = domain_or_id.lower().strip()
    state = get_job_state()
    latest = state.get("latest_results", {})
    for d in latest.get("results", []):
        if d.get("domain") == domain_clean or d.get("domain_name") == domain_clean or str(d.get("id")) == domain_or_id:
            return {
                "success": True,
                "domain": d.get("domain_name", domain_clean),
                "quality_score": d.get("quality_score", d.get("overall_score")),
                "quality_breakdown": d.get("quality_breakdown", {}),
                "multi_model_review": d.get("multi_model_review", {}),
                "consensus": d.get("consensus", {}),
                "consensus_confidence": d.get("consensus_confidence"),
                "gibberish_risk_score": d.get("gibberish_risk_score"),
                "gibberish_quality_band": d.get("gibberish_quality_band"),
                "short_but_meaningless": d.get("short_but_meaningless", False),
                "final_rank_score": d.get("final_rank_score"),
                "naming_type": d.get("naming_type", "INVENTED")
            }
    sb = get_supabase()
    if sb:
        try:
            res = sb.table("final_domains").select("*").ilike("domain_name", f"%{domain_clean}%").limit(1).execute()
            if res.data:
                d = res.data[0]
                return {
                    "success": True,
                    "domain": d.get("domain_name"),
                    "quality_score": d.get("quality_score", d.get("overall_score")),
                    "quality_breakdown": d.get("quality_breakdown", {}),
                    "naming_type": d.get("naming_type", "INVENTED")
                }
        except Exception:
            pass
    return JSONResponse(status_code=404, content={"success": False, "error": f"Domain '{domain_or_id}' not found"})

@app.get("/api/domains/{domain_or_id}/risk")
async def get_domain_risk(domain_or_id: str):
    domain_clean = domain_or_id.lower().strip()
    state = get_job_state()
    latest = state.get("latest_results", {})
    for d in latest.get("results", []):
        if d.get("domain") == domain_clean or d.get("domain_name") == domain_clean or str(d.get("id")) == domain_or_id:
            return {
                "success": True,
                "domain": d.get("domain_name", domain_clean),
                "ip_risk": d.get("ip_risk", {
                    "level": d.get("ip_risk_level", "LOW"),
                    "score": d.get("ip_risk_score", 10),
                    "evidence": []
                }),
                "decision": d.get("decision", "PASS")
            }
    sb = get_supabase()
    if sb:
        try:
            res = sb.table("final_domains").select("*").ilike("domain_name", f"%{domain_clean}%").limit(1).execute()
            if res.data:
                d = res.data[0]
                return {
                    "success": True,
                    "domain": d.get("domain_name"),
                    "ip_risk": d.get("ip_evidence") or {
                        "level": d.get("ip_risk_level", "LOW"),
                        "score": d.get("ip_risk_score", 10),
                        "evidence": []
                    },
                    "decision": d.get("decision", "PASS")
                }
        except Exception:
            pass
    return JSONResponse(status_code=404, content={"success": False, "error": f"Domain '{domain_or_id}' not found"})

@app.get("/api/domains/{domain_or_id}/explanation")
async def get_domain_explanation(domain_or_id: str):
    domain_clean = domain_or_id.lower().strip()
    state = get_job_state()
    latest = state.get("latest_results", {})
    for d in latest.get("results", []):
        if d.get("domain") == domain_clean or d.get("domain_name") == domain_clean or str(d.get("id")) == domain_or_id:
            return {
                "success": True,
                "domain": d.get("domain_name", domain_clean),
                "quality_score": d.get("quality_score", d.get("overall_score")),
                "quality_breakdown": d.get("quality_breakdown", {}),
                "naming_type": d.get("naming_type", "INVENTED"),
                "ip_risk": d.get("ip_risk", {}),
                "decision": d.get("decision", "PASS"),
                "reasons": d.get("reasons", []),
                "market_category": d.get("market_category"),
                "subcategory": d.get("subcategory"),
                "concept_source": d.get("concept_source"),
                "semantic_concept": d.get("semantic_concept"),
                "source_language": d.get("source_language", "en"),
                "literal_meaning": d.get("literal_meaning"),
                "english_meaning": d.get("english_meaning"),
                "linguistic_confidence": d.get("linguistic_confidence"),
                "radio_test_score": d.get("radio_test_score"),
                "category_fit": d.get("category_fit"),
                "opportunity_score": d.get("opportunity_score")
            }
    sb = get_supabase()
    if sb:
        try:
            res = sb.table("final_domains").select("*").ilike("domain_name", f"%{domain_clean}%").limit(1).execute()
            if res.data:
                d = res.data[0]
                return {
                    "success": True,
                    "domain": d.get("domain_name"),
                    "quality_score": d.get("quality_score", d.get("overall_score")),
                    "quality_breakdown": d.get("quality_breakdown", {}),
                    "naming_type": d.get("naming_type", "INVENTED"),
                    "ip_risk": d.get("ip_evidence") or {},
                    "decision": d.get("decision", "PASS"),
                    "reasons": d.get("reasons", []),
                    "market_category": d.get("market_category"),
                    "subcategory": d.get("subcategory"),
                    "concept_source": d.get("concept_source"),
                    "semantic_concept": d.get("semantic_concept"),
                    "source_language": d.get("source_language", "en"),
                    "literal_meaning": d.get("literal_meaning"),
                    "english_meaning": d.get("english_meaning"),
                    "linguistic_confidence": d.get("linguistic_confidence"),
                    "radio_test_score": d.get("radio_test_score"),
                    "category_fit": d.get("category_fit"),
                    "opportunity_score": d.get("opportunity_score")
                }
        except Exception:
            pass
    return JSONResponse(status_code=404, content={"success": False, "error": f"Domain '{domain_or_id}' not found"})

@app.get("/api/domains/{domain_or_id}/opportunity")
async def get_domain_opportunity(domain_or_id: str):
    """
    Phase 2.5: Returns opportunity, category fit, and multilingual metadata for a domain.
    """
    domain_clean = domain_or_id.lower().strip()
    state = get_job_state()
    latest = state.get("latest_results", {})
    for d in latest.get("results", []):
        if d.get("domain") == domain_clean or d.get("domain_name") == domain_clean or str(d.get("id")) == domain_or_id:
            return {
                "success": True,
                "domain": d.get("domain_name", domain_clean),
                "market_category": d.get("market_category"),
                "subcategory": d.get("subcategory"),
                "concept_source": d.get("concept_source"),
                "semantic_concept": d.get("semantic_concept"),
                "source_language": d.get("source_language", "en"),
                "literal_meaning": d.get("literal_meaning"),
                "english_meaning": d.get("english_meaning"),
                "linguistic_confidence": d.get("linguistic_confidence"),
                "radio_test_score": d.get("radio_test_score"),
                "category_fit": d.get("category_fit", {}),
                "opportunity_score": d.get("opportunity_score", 0)
            }
    sb = get_supabase()
    if sb:
        try:
            res = sb.table("final_domains").select("*").ilike("domain_name", f"%{domain_clean}%").limit(1).execute()
            if res.data:
                d = res.data[0]
                return {
                    "success": True,
                    "domain": d.get("domain_name"),
                    "market_category": d.get("market_category"),
                    "subcategory": d.get("subcategory"),
                    "concept_source": d.get("concept_source"),
                    "semantic_concept": d.get("semantic_concept"),
                    "source_language": d.get("source_language", "en"),
                    "literal_meaning": d.get("literal_meaning"),
                    "english_meaning": d.get("english_meaning"),
                    "linguistic_confidence": d.get("linguistic_confidence"),
                    "radio_test_score": d.get("radio_test_score"),
                    "category_fit": d.get("category_fit", {}),
                    "opportunity_score": d.get("opportunity_score", 0)
                }
        except Exception:
            pass
    return JSONResponse(status_code=404, content={"success": False, "error": f"Domain '{domain_or_id}' not found"})

# =========================================================================
# Phase 3 & 4 Learning, Feedback & Tiers Endpoints
# =========================================================================
class FeedbackRequest(BaseModel):
    candidate_id: str
    domain: Optional[str] = None
    user_action: str  # VIEWED, SHORTLISTED, REJECTED, FAVORITED, PURCHASED, IGNORED
    rejection_reason: Optional[str] = None
    notes: Optional[str] = None

@app.post("/api/feedback")
async def record_user_feedback(req: FeedbackRequest):
    ls = getattr(job_runner, "learning_store", None) or LearningStore(supabase_client=get_supabase())
    entry = ls.record_feedback(
        candidate_id=req.candidate_id,
        user_action=req.user_action,
        rejection_reason=req.rejection_reason,
        notes=req.notes,
        domain=req.domain
    )
    return {"success": True, "feedback": entry}

@app.get("/api/feedback")
async def get_all_feedback(limit: int = 200):
    ls = getattr(job_runner, "learning_store", None) or LearningStore(supabase_client=get_supabase())
    records = ls.get_feedback(limit=limit)
    return {"success": True, "count": len(records), "feedback": records}

@app.get("/api/feedback/summary")
async def get_feedback_summary():
    ls = getattr(job_runner, "learning_store", None) or LearningStore(supabase_client=get_supabase())
    feedbacks = ls.get_feedback(limit=5000)
    
    action_counts = {}
    reason_counts = {}
    for fb in feedbacks:
        act = fb.get("user_action", "VIEWED")
        action_counts[act] = action_counts.get(act, 0) + 1
        r = fb.get("rejection_reason")
        if r:
            reason_counts[r] = reason_counts.get(r, 0) + 1
            
    return {
        "success": True,
        "total_feedback": len(feedbacks),
        "actions": action_counts,
        "rejection_reasons": reason_counts,
        "shortlisted": action_counts.get("SHORTLISTED", 0),
        "favorited": action_counts.get("FAVORITED", 0),
        "rejected": action_counts.get("REJECTED", 0),
        "purchased": action_counts.get("PURCHASED", 0)
    }

@app.get("/api/learning/status")
async def get_learning_status():
    ranker = getattr(job_runner, "ranker", None) or StatisticalRanker()
    ls = getattr(job_runner, "learning_store", None) or LearningStore(supabase_client=get_supabase())
    fb_count = ls.get_feedback_count()
    status = ranker.get_status(sample_count=fb_count)
    return {
        "success": True,
        "learning_status": status,
        "model_version": ranker.metadata.get("version", "v0"),
        "model_id": ranker.metadata.get("model_id", "none"),
        "feedback_sample_count": fb_count,
        "training_sample_count": ranker.metadata.get("training_sample_count", 0),
        "feature_version": ranker.metadata.get("feature_version", "feat_v3.0"),
        "validation_metric": ranker.metadata.get("validation_metric", "none"),
        "validation_score": ranker.metadata.get("validation_score", 0.0),
        "trained_at": ranker.metadata.get("trained_at")
    }

@app.post("/api/learning/train")
async def train_ranker_model():
    ranker = getattr(job_runner, "ranker", None) or StatisticalRanker()
    ls = getattr(job_runner, "learning_store", None) or LearningStore(supabase_client=get_supabase())
    store_data = ls.get_all_records()
    X, y, ids = TrainingFeaturePipeline.build_dataset_from_store(store_data)
    
    if len(y) < 10:
        return {
            "success": False,
            "status": "COLD_START",
            "sample_count": len(y),
            "message": f"Insufficient feedback samples ({len(y)}). Minimum 10 required for training, 100 for baseline."
        }
        
    train_res = ranker.train(X, y)
    return {"success": train_res.get("success", False), "result": train_res}

@app.get("/api/analytics/strategies")
async def get_strategy_analytics():
    state = get_job_state()
    latest = state.get("latest_results", {})
    ls = getattr(job_runner, "learning_store", None) or LearningStore(supabase_client=get_supabase())
    strat_perf = ls.get_strategy_performance() or latest.get("strategy_performance", {})
    return {
        "success": True,
        "strategies": strat_perf
    }

@app.get("/api/analytics/models")
async def get_model_analytics():
    ls = getattr(job_runner, "learning_store", None) or LearningStore(supabase_client=get_supabase())
    model_perf = ls.get_model_performance()
    return {
        "success": True,
        "models": model_perf
    }

@app.get("/api/domains/tiers")
async def get_domain_tiers():
    state = get_job_state()
    latest = state.get("latest_results", {})
    return {
        "success": True,
        "scan_id": latest.get("scan_id"),
        "run_date": latest.get("run_date"),
        "tier_a": latest.get("tier_a", []),
        "tier_b": latest.get("tier_b", []),
        "watchlist": latest.get("watchlist", [])
    }

# Legacy Endpoints (Left for other app features if needed)
rss_cache = {}
CACHE_TTL = 300

def get_cached_rss(key: str):
    if key in rss_cache:
        data, timestamp = rss_cache[key]
        if time.time() - timestamp < CACHE_TTL: return data
    return None

def set_cached_rss(key: str, data: dict):
    rss_cache[key] = (data, time.time())

@app.get("/api/suggest")
async def get_google_suggest(q: str, hl: str = "ar", gl: str = "eg"):
    url = "https://suggestqueries.google.com/complete/search"
    params = {"client": "firefox", "q": q, "hl": hl, "gl": gl}
    try:
        response = await http_client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return {"query": data[0], "suggestions": data[1]}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e), "success": False})

@app.get("/api/trends/rss")
async def get_google_trends_rss(geo: str = "EG"):
    cache_key = f"rss_{geo.upper()}"
    cached = get_cached_rss(cache_key)
    if cached:
        cached["cached"] = True
        return cached

    url = "https://trends.google.com/trending/rss"
    params = {"geo": geo.upper()}
    try:
        for attempt in range(3):
            try:
                response = await http_client.get(url, params=params)
                response.raise_for_status()
                break
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise e

        parsed_xml = xmltodict.parse(response.content)
        items = parsed_xml.get("rss", {}).get("channel", {}).get("item", [])
        if not isinstance(items, list): items = [items]
            
        trends = []
        for item in items:
            trends.append({
                "title": item.get("title"),
                "traffic": item.get("ht:approx_traffic"),
                "description": item.get("description"),
                "pubDate": item.get("pubDate"),
                "news": item.get("ht:news_item")
            })
        result = {"success": True, "geo": geo, "trends": trends, "cached": False}
        set_cached_rss(cache_key, result)
        return result
    except Exception as e:
        return JSONResponse(status_code=503, content={"success": False, "source": "google_news_rss", "error_type": "UPSTREAM_UNAVAILABLE", "message": str(e)})

@app.get("/api/trends/category")
async def get_category_trends(geo: str = "US", lang: str = "en", topic: str = "TECHNOLOGY"):
    cache_key = f"cat_{geo.upper()}_{topic.upper()}"
    cached = get_cached_rss(cache_key)
    if cached:
        cached["cached"] = True
        return cached

    url = f"https://news.google.com/rss/headlines/section/topic/{topic.upper()}?hl={lang}-{geo.upper()}&gl={geo.upper()}&ceid={geo.upper()}:{lang}"
    try:
        for attempt in range(3):
            try:
                response = await http_client.get(url)
                response.raise_for_status()
                break
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise e

        parsed_xml = xmltodict.parse(response.content)
        items = parsed_xml.get("rss", {}).get("channel", {}).get("item", [])
        if not isinstance(items, list): items = [items]
            
        trends = []
        for item in items:
            title = item.get("title", "")
            clean_title = title.rsplit(" - ", 1)[0] if " - " in title else title
            trends.append({
                "title": clean_title,
                "original_title": title,
                "link": item.get("link"),
                "pubDate": item.get("pubDate")
            })
        result = {"success": True, "geo": geo, "topic": topic, "trends": trends, "cached": False}
        set_cached_rss(cache_key, result)
        return result
    except Exception as e:
        return JSONResponse(status_code=503, content={"success": False, "source": "google_news_rss", "error_type": "UPSTREAM_UNAVAILABLE", "message": str(e)})

@app.get("/api/trends/pytrends")
async def get_pytrends_data(geo: str = "EG", keyword: Optional[str] = None):
    def _fetch():
        pytrends = TrendReq(hl='ar-EG', tz=360)
        time.sleep(2)
        result = {}
        geo_to_country = {
            "EG": "egypt", "SA": "saudi_arabia", "US": "united_states",
            "AE": "united_arab_emirates", "GB": "united_kingdom", "CA": "canada",
            "AU": "australia", "DE": "germany"
        }
        country = geo_to_country.get(geo.upper(), "egypt")
        try:
            trending_df = pytrends.trending_searches(pn=country)
            result['trending_searches'] = trending_df[0].tolist() if not trending_df.empty else []
        except Exception as e:
            result['trending_searches_error'] = str(e)
            
        if keyword:
            time.sleep(2)
            pytrends.build_payload(kw_list=[keyword], geo=geo.upper(), timeframe='now 7-d')
            related_df = pytrends.related_queries()
            if keyword in related_df and related_df[keyword]:
                top = related_df[keyword].get('top')
                rising = related_df[keyword].get('rising')
                result['related_queries'] = {
                    'top': top.to_dict('records') if top is not None and not top.empty else [],
                    'rising': rising.to_dict('records') if rising is not None and not rising.empty else []
                }
        return result
        
    try:
        result = await asyncio.to_thread(_fetch)
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

class ExportRequest(BaseModel):
    format: str
    selection: str
    selected_ids: List[int] = []
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    search: Optional[str] = None
    category: Optional[str] = None
    sort: str = "newest"

def get_supabase():
    global supabase
    if supabase is None:
        try:
            from supabase import create_client
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_KEY")
            if url and key:
                supabase = create_client(url, key)
        except Exception:
            pass
    return supabase

@app.get("/api/domains/history")
async def get_domain_history(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
    sort: str = "newest",
    page: int = 1,
    limit: int = 50
):
    sb = get_supabase()
    if not sb:
        return JSONResponse(status_code=500, content={"error": "Supabase not configured"})

    def _fetch():
        query = sb.table("final_domains").select("*", count="exact")

        if search:
            query = query.ilike("domain_name", f"%{search}%")
        if category:
            query = query.eq("category", category)
        if from_date:
            query = query.gte("created_at", from_date)
        if to_date:
            query = query.lte("created_at", to_date)
            
        if sort == "newest":
            query = query.order("created_at", desc=True)
        elif sort == "oldest":
            query = query.order("created_at", desc=False)
        else:
            query = query.order("created_at", desc=True)

        start = (page - 1) * limit
        end = start + limit - 1
        query = query.range(start, end)
        
        return query.execute()

    try:
        res = await asyncio.to_thread(_fetch)
        return {
            "success": True,
            "data": res.data,
            "total": res.count,
            "page": page,
            "limit": limit
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/domains/history/stats")
async def get_domain_stats():
    sb = get_supabase()
    if not sb:
        return JSONResponse(status_code=500, content={"error": "Supabase not configured"})
    
    def _fetch_stats():
        now = datetime.datetime.now(datetime.timezone.utc)
        d24 = (now - datetime.timedelta(days=1)).isoformat()
        d7 = (now - datetime.timedelta(days=7)).isoformat()
        d30 = (now - datetime.timedelta(days=30)).isoformat()
        
        c24 = sb.table("final_domains").select("id", count="exact").gte("created_at", d24).range(0, 0).execute().count
        c7 = sb.table("final_domains").select("id", count="exact").gte("created_at", d7).range(0, 0).execute().count
        c30 = sb.table("final_domains").select("id", count="exact").gte("created_at", d30).range(0, 0).execute().count
        ctotal = sb.table("final_domains").select("id", count="exact").range(0, 0).execute().count
        
        return {
            "last_24h": c24,
            "last_7d": c7,
            "last_30d": c30,
            "total": ctotal
        }
    
    try:
        stats = await asyncio.to_thread(_fetch_stats)
        return {"success": True, "stats": stats}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/domains/export")
async def export_domains(req: ExportRequest):
    sb = get_supabase()
    if not sb:
        return JSONResponse(status_code=500, content={"error": "Supabase not configured"})
        
    def _fetch_all():
        query = sb.table("final_domains").select("*")
        if req.selection == "selected" and req.selected_ids:
            query = query.in_("id", req.selected_ids)
        else:
            if req.search: query = query.ilike("domain_name", f"%{req.search}%")
            if req.category: query = query.eq("category", req.category)
            if req.from_date: query = query.gte("created_at", req.from_date)
            if req.to_date: query = query.lte("created_at", req.to_date)
            
            if req.sort == "newest": query = query.order("created_at", desc=True)
            elif req.sort == "oldest": query = query.order("created_at", desc=False)
        
        all_data = []
        page_size = 1000
        current_start = 0
        while True:
            res = query.range(current_start, current_start + page_size - 1).execute()
            all_data.extend(res.data)
            if len(res.data) < page_size:
                break
            current_start += page_size
        return all_data

    try:
        data = await asyncio.to_thread(_fetch_all)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
        
    if req.format == "json":
        return JSONResponse(content=data)
        
    elif req.format == "txt":
        content = "\n".join([d.get("domain_name", "") for d in data])
        return StreamingResponse(io.StringIO(content), media_type="text/plain", headers={"Content-Disposition": "attachment; filename=export.txt"})
        
    elif req.format == "csv":
        output = io.StringIO()
        output.write('\ufeff')
        writer = csv.writer(output)
        writer.writerow(["ID", "Domain", "Category", "Discovered At"])
        for d in data:
            writer.writerow([d.get("id"), d.get("domain_name"), d.get("category"), d.get("created_at")])
        output.seek(0)
        return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=export.csv"})
        
    elif req.format == "xlsx":
        try:
            import openpyxl
        except ImportError:
            return JSONResponse(status_code=500, content={"error": "openpyxl not installed"})
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Domains"
        headers = ["ID", "Domain", "Category", "Discovered At"]
        ws.append(headers)
        for d in data:
            ts = d.get("created_at")
            if ts and isinstance(ts, str) and ts.endswith("Z"):
                ts = ts.replace("Z", "")
            elif ts and isinstance(ts, str) and "+" in ts:
                ts = ts.split("+")[0]
            ws.append([d.get("id"), d.get("domain_name"), d.get("category"), ts])
        
        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(cell.value)
                except: pass
            ws.column_dimensions[column].width = max_length + 2
            
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=export.xlsx"})
        
    else:
        return JSONResponse(status_code=400, content={"error": "Invalid format"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
