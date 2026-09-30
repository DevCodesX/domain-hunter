"""
Atom Domain Appraisal Service
=============================
Integrates with the official Atom Domain Appraisal API:
GET https://www.atom.com/api/marketplace/domain-appraisal?domain=<DOMAIN>

Provides:
1. Server-side credential management with masking and zero secret leakage.
2. Real-time provider health tracking (latency, auth, reachable, quota).
3. Defensive response normalization (score, appraisal value, signals, market data).
4. Monotonic bounded appraisal normalization (0-100 log transformation).
5. 24-hour persistent caching with TTL management.
6. Diversified pre-selection candidate pool to prevent strategy monopolization.
7. Fail-closed final publication gating: candidates must be validated before reaching Tier A/B.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import math
import os
import re
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

logger = logging.getLogger("AtomAppraisalService")

ATOM_APPRAISAL_ENDPOINT = "https://www.atom.com/api/marketplace/domain-appraisal"
DEFAULT_CACHE_TTL_HOURS = 24
DEFAULT_MAX_APPRAISALS_PER_RUN = 10
DEFAULT_MIN_DOMAIN_SCORE = 8.0
DEFAULT_TIER_A_MIN_DOMAIN_SCORE = 8.5
DEFAULT_REVIEW_RANGE_MIN = 7.0
DEFAULT_RANK_WEIGHT = 0.12


class AtomProviderHealthStatus(str, Enum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    CONFIGURED = "CONFIGURED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    AUTH_ERROR = "AUTH_ERROR"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    TIMEOUT = "TIMEOUT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"


class AtomProviderHealth(BaseModel):
    provider: str = "ATOM"
    enabled: bool = True
    configured: bool = False
    reachable: bool = False
    authenticated: bool = False
    appraisal_scope_available: bool = False
    status: str = AtomProviderHealthStatus.NOT_CONFIGURED.value
    latency_ms: Optional[float] = None
    daily_limit: Optional[int] = None
    used_today: int = 0
    remaining_today: Optional[int] = None
    last_success_at: Optional[str] = None
    last_error_at: Optional[str] = None
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump() if hasattr(self, "model_dump") else self.dict()


class AtomAppraisalResult(BaseModel):
    provider: str = "ATOM"
    status: str = "ATOM_PENDING"  # SUCCESS, ATOM_PENDING, ATOM_UNVALIDATED, ATOM_REJECTED, etc.
    domain: str
    atom_domain_score: Optional[float] = None  # 0.0 - 10.0 scale
    atom_appraisal_value: Optional[float] = None  # Raw USD value
    atom_appraisal_normalized: Optional[float] = None  # 0.0 - 100.0 log bounded
    positive_signals: List[str] = Field(default_factory=list)
    negative_signals: List[str] = Field(default_factory=list)
    tld_taken_count: Optional[int] = None
    tm_conflicts: Optional[int] = None
    confidence: Optional[float] = None
    category: Optional[str] = None
    root_word_info: Optional[Dict[str, Any]] = None
    market_data: Optional[Dict[str, Any]] = None
    checked_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    cache_hit: bool = False
    raw_response: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump() if hasattr(self, "model_dump") else self.dict()

    def is_successful(self) -> bool:
        return self.status == "SUCCESS" and self.atom_domain_score is not None

    def passes_minimum_score(self, min_score: float = DEFAULT_MIN_DOMAIN_SCORE) -> bool:
        if not self.is_successful():
            return False
        return float(self.atom_domain_score or 0.0) >= min_score

    def passes_tier_a_score(self, min_tier_a: float = DEFAULT_TIER_A_MIN_DOMAIN_SCORE) -> bool:
        if not self.is_successful():
            return False
        return float(self.atom_domain_score or 0.0) >= min_tier_a


def normalize_atom_appraisal(value: Optional[float]) -> float:
    """
    Transforms raw appraisal dollar value into a bounded monotonic 0-100 score.
    Uses a smooth logarithmic transformation so multi-million valuations do not
    dominate the overall ranking while preserving valuation order.
    
    Examples:
      $0      -> 0.0
      $100    -> 14.8
      $500    -> 27.4
      $1,500  -> 36.0
      $5,000  -> 45.4
      $20,000 -> 56.2
      $100,000 -> 68.8
      $1,000,000 -> 86.8
      $5,000,000+ -> ~99 - 100
    """
    if value is None:
        return 0.0
    try:
        val = float(value)
        if val <= 0.0 or math.isnan(val) or math.isinf(val):
            return 0.0
        # Smooth log10 curve anchored at $15 minimum base
        score = 18.0 * math.log10(max(1.0, val / 15.0))
        return round(max(0.0, min(100.0, score)), 2)
    except (TypeError, ValueError):
        return 0.0


def calculate_atom_calibration(
    internal_overall_score: float,
    internal_brandability: float,
    internal_commercial_score: float,
    atom_domain_score: Optional[float],
    atom_appraisal_value: Optional[float]
) -> Dict[str, Any]:
    """
    Compares internal model/deterministic evaluation with external Atom market appraisal.
    Detects overvaluation, undervaluation, and calculates alignment gap.
    """
    atom_score_100 = (atom_domain_score * 10.0) if atom_domain_score is not None else None
    gap: Optional[float] = None
    flags: List[str] = []

    if atom_score_100 is not None:
        gap = round(internal_overall_score - atom_score_100, 2)
        if gap >= 20.0 or (internal_overall_score >= 85.0 and (atom_domain_score or 0.0) <= 6.5):
            flags.append("INTERNAL_OVERVALUATION_RISK")
        elif gap <= -15.0 or ((atom_domain_score or 0.0) >= 9.0 and internal_overall_score <= 70.0):
            flags.append("INTERNAL_UNDEREVALUATION_RISK")

        if abs(gap) <= 8.0:
            flags.append("ATOM_ALIGNMENT_STRONG")
        elif abs(gap) >= 18.0:
            flags.append("ATOM_ALIGNMENT_WEAK")

    return {
        "internal_overall_score": round(internal_overall_score, 2),
        "internal_brandability": round(internal_brandability, 2),
        "internal_commercial_score": round(internal_commercial_score, 2),
        "atom_domain_score": atom_domain_score,
        "atom_appraisal_value": atom_appraisal_value,
        "atom_score_100": round(atom_score_100, 2) if atom_score_100 is not None else None,
        "internal_atom_gap": gap,
        "calibration_flags": flags,
    }


class AtomAppraisalCache:
    """Persistent on-disk and in-memory cache for Atom appraisal results."""

    def __init__(self, cache_file: Optional[Path] = None, ttl_hours: int = DEFAULT_CACHE_TTL_HOURS):
        self.ttl_seconds = ttl_hours * 3600
        self.cache_file = cache_file or Path("data/atom_appraisal_cache.json")
        self._memory: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                now = time.time()
                # Prune expired items
                self._memory = {
                    k: v for k, v in data.items()
                    if v.get("expires_at_epoch", 0) > now
                }
            except Exception as e:
                logger.warning(f"Failed to load Atom cache: {e}")
                self._memory = {}

    def _save(self) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self._memory, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save Atom cache: {e}")

    def get(self, domain: str) -> Optional[AtomAppraisalResult]:
        key = domain.strip().lower()
        cached = self._memory.get(key)
        if not cached:
            return None
        if cached.get("expires_at_epoch", 0) <= time.time():
            self._memory.pop(key, None)
            return None
        res_data = dict(cached.get("result", {}))
        res_data["cache_hit"] = True
        return AtomAppraisalResult(**res_data)

    def set(self, domain: str, result: AtomAppraisalResult) -> None:
        key = domain.strip().lower()
        now = time.time()
        expires = now + self.ttl_seconds
        res_dict = result.model_dump() if hasattr(result, "model_dump") else result.dict()
        self._memory[key] = {
            "expires_at_epoch": expires,
            "result": res_dict,
            "cached_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        self._save()

    def clear(self) -> None:
        self._memory.clear()
        if self.cache_file.exists():
            try:
                self.cache_file.unlink()
            except Exception:
                pass


class AtomAppraisalService:
    """
    Production-grade client for the Atom Domain Appraisal API.
    Guarantees:
    - Never prints API tokens or secrets in logs.
    - Defensive parsing of response formats.
    - Quota-aware rate control.
    - Fail-closed validation for final candidate output.
    """

    _instance: Optional["AtomAppraisalService"] = None

    @classmethod
    def get_instance(cls, http_client: Optional[httpx.AsyncClient] = None) -> "AtomAppraisalService":
        if cls._instance is None:
            cls._instance = cls(http_client=http_client)
        elif http_client is not None and cls._instance._external_client is None:
            cls._instance._external_client = http_client
        return cls._instance

    def __init__(
        self,
        api_token: Optional[str] = None,
        user_id: Optional[str] = None,
        base_url: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        cache_ttl_hours: Optional[int] = None,
    ):
        self.api_token = (api_token if api_token is not None else (os.getenv("ATOM_API_TOKEN") or os.getenv("ATOM_API_KEY") or "")).strip()
        self.user_id = (user_id if user_id is not None else (os.getenv("ATOM_USER_ID") or "")).strip()
        self.base_url = (base_url if base_url is not None else (os.getenv("ATOM_APPRAISAL_URL") or ATOM_APPRAISAL_ENDPOINT)).strip()
        self.enabled = os.getenv("ATOM_ENABLED", "true").lower() == "true"
        self.required_for_final = os.getenv("ATOM_REQUIRED_FOR_FINAL", "true").lower() == "true"

        ttl = int(os.getenv("ATOM_CACHE_TTL_HOURS", str(cache_ttl_hours or DEFAULT_CACHE_TTL_HOURS)))
        self.cache = AtomAppraisalCache(ttl_hours=ttl)
        self.max_appraisals_per_run = int(os.getenv("ATOM_MAX_APPRAISALS_PER_RUN", str(DEFAULT_MAX_APPRAISALS_PER_RUN)))
        self.min_domain_score = float(os.getenv("ATOM_MIN_DOMAIN_SCORE", str(DEFAULT_MIN_DOMAIN_SCORE)))
        self.tier_a_min_score = float(os.getenv("ATOM_TIER_A_MIN_DOMAIN_SCORE", str(DEFAULT_TIER_A_MIN_DOMAIN_SCORE)))
        self.review_min_score = float(os.getenv("ATOM_REVIEW_RANGE_MIN", str(DEFAULT_REVIEW_RANGE_MIN)))

        self._external_client = http_client
        self._client: Optional[httpx.AsyncClient] = None
        self._semaphore = asyncio.Semaphore(4)

        # Health & Telemetry State
        self.health = AtomProviderHealth(
            enabled=self.enabled,
            configured=bool(self.api_token and self.api_token not in ["your_atom_token_here", "PLACEHOLDER"]),
            status=(
                AtomProviderHealthStatus.CONFIGURED.value
                if bool(self.api_token and self.api_token not in ["your_atom_token_here", "PLACEHOLDER"])
                else AtomProviderHealthStatus.NOT_CONFIGURED.value
            )
        )
        self._quota_used_today = 0
        self._quota_date_utc = datetime.datetime.now(datetime.timezone.utc).date()

    def _get_client(self) -> httpx.AsyncClient:
        if self._external_client is not None:
            return self._external_client
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def aclose(self) -> None:
        """Close internally managed httpx client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    def _clean_token(self) -> str:
        tok = self.api_token.strip()
        if not tok or tok in ["your_atom_token_here", "PLACEHOLDER"] or tok.startswith("ضع"):
            return ""
        return tok

    def is_configured(self) -> bool:
        return bool(self._clean_token())

    def _get_headers(self) -> Dict[str, str]:
        tok = self._clean_token()
        headers = {
            "Accept": "application/json",
            "User-Agent": "DomainHunter/2.0 (Domain Investment System)",
        }
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
            headers["api-key"] = tok
        if self.user_id:
            headers["X-User-Id"] = self.user_id
        return headers

    def _check_and_reset_daily_counter(self) -> None:
        today = datetime.datetime.now(datetime.timezone.utc).date()
        if today != self._quota_date_utc:
            self._quota_date_utc = today
            self._quota_used_today = 0
            self.health.used_today = 0

    def get_health_status(self) -> Dict[str, Any]:
        """Returns sanitized health dictionary safe for frontend display."""
        self._check_and_reset_daily_counter()
        h = self.health.model_copy() if hasattr(self.health, "model_copy") else self.health.copy()
        h.configured = self.is_configured()
        h.used_today = self._quota_used_today
        return h.model_dump() if hasattr(h, "model_dump") else h.dict()

    async def check_health(self, test_domain: str = "cloudflow.com", force: bool = False) -> AtomProviderHealth:
        """
        Executes a real lightweight health check against the Atom appraisal endpoint.
        Never fabricates success. Masks all credentials.
        """
        self._check_and_reset_daily_counter()
        if not self.is_configured():
            self.health.status = AtomProviderHealthStatus.NOT_CONFIGURED.value
            self.health.configured = False
            self.health.reachable = False
            self.health.authenticated = False
            self.health.appraisal_scope_available = False
            self.health.last_error = "API token not configured"
            return self.health

        self.health.status = AtomProviderHealthStatus.CONNECTING.value
        started = time.perf_counter()
        client = self._get_client()

        try:
            params = {
                "domain_name": test_domain,
                "domain": test_domain,
            }
            tok = self._clean_token()
            if tok:
                params["api_token"] = tok
            if self.user_id:
                params["user_id"] = self.user_id

            response = await client.get(self.base_url, params=params, headers=self._get_headers())
            latency = round((time.perf_counter() - started) * 1000, 2)
            self.health.latency_ms = latency

            if response.status_code == 200:
                try:
                    data = response.json()
                    msg = str(data.get("message", "")).lower() if isinstance(data, dict) else ""
                    if "api token" in msg or "userid" in msg or "unauthorized" in msg:
                        self.health.status = AtomProviderHealthStatus.AUTH_ERROR.value
                        self.health.reachable = True
                        self.health.authenticated = False
                        self.health.appraisal_scope_available = False
                        self.health.last_error = data.get("message")
                        self.health.last_error_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    elif "domain name is required" in msg:
                        self.health.status = AtomProviderHealthStatus.INVALID_RESPONSE.value
                        self.health.last_error = "Atom API reported missing domain name parameter"
                        self.health.last_error_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    else:
                        self.health.status = AtomProviderHealthStatus.CONNECTED.value
                        self.health.reachable = True
                        self.health.authenticated = True
                        self.health.appraisal_scope_available = True
                        self.health.last_success_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
                        self.health.last_error = None
                        self.health.last_error_at = None

                        # If Atom returns rate limit or quota headers, record them
                        if "x-ratelimit-limit" in response.headers:
                            try:
                                self.health.daily_limit = int(response.headers["x-ratelimit-limit"])
                            except ValueError:
                                pass
                        if "x-ratelimit-remaining" in response.headers:
                            try:
                                self.health.remaining_today = int(response.headers["x-ratelimit-remaining"])
                            except ValueError:
                                pass
                except Exception:
                    self.health.status = AtomProviderHealthStatus.INVALID_RESPONSE.value
                    self.health.last_error = "Atom response was not valid JSON"
                    self.health.last_error_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            elif response.status_code in (401, 403):
                self.health.status = (
                    AtomProviderHealthStatus.AUTH_ERROR.value
                    if response.status_code == 401
                    else AtomProviderHealthStatus.FORBIDDEN.value
                )
                self.health.reachable = True
                self.health.authenticated = False
                self.health.appraisal_scope_available = False
                self.health.last_error = f"Authentication failed (HTTP {response.status_code})"
                self.health.last_error_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            elif response.status_code == 429:
                self.health.status = AtomProviderHealthStatus.RATE_LIMITED.value
                self.health.reachable = True
                self.health.last_error = "Rate limit or appraisal quota exceeded"
                self.health.last_error_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            else:
                self.health.status = AtomProviderHealthStatus.PROVIDER_ERROR.value
                self.health.reachable = True
                self.health.last_error = f"Atom returned unexpected HTTP {response.status_code}"
                self.health.last_error_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

        except httpx.TimeoutException:
            self.health.status = AtomProviderHealthStatus.TIMEOUT.value
            self.health.reachable = False
            self.health.last_error = "Connection timed out"
            self.health.last_error_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        except Exception as exc:
            self.health.status = AtomProviderHealthStatus.PROVIDER_ERROR.value
            self.health.reachable = False
            self.health.last_error = f"Network connection error: {type(exc).__name__}"
            self.health.last_error_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

        return self.health

    def _parse_atom_response(self, domain: str, raw: Dict[str, Any]) -> AtomAppraisalResult:
        """
        Defensively parses raw Atom API response JSON into a normalized object.
        Supports current official schema variations safely without throwing.
        """
        data = raw if isinstance(raw, dict) else {}
        if "data" in data and isinstance(data["data"], dict):
            # Nested payload wrapper support
            data = {**data, **data["data"]}

        # 1. Domain Score (0.0 to 10.0 scale)
        raw_score = (
            data.get("domain_score")
            or data.get("score")
            or data.get("atom_domain_score")
            or data.get("atom_score")
            or data.get("appraisal_score")
        )
        domain_score: Optional[float] = None
        if raw_score is not None:
            try:
                s = float(raw_score)
                # If score is given on 0-100 scale, normalize to 0-10
                if s > 10.0:
                    s = s / 10.0
                domain_score = round(max(0.0, min(10.0, s)), 2)
            except (TypeError, ValueError):
                domain_score = None

        if domain_score is None and ("message" in data or "error" in data):
            msg = str(data.get("message") or data.get("error"))
            status = "AUTH_ERROR" if ("token" in msg.lower() or "userid" in msg.lower() or "unauthorized" in msg.lower()) else "PROVIDER_ERROR"
            return AtomAppraisalResult(
                provider="ATOM",
                status=status,
                domain=domain.strip().lower(),
                error_message=msg,
                raw_response=raw,
            )

        # 2. Estimated Value (USD)
        raw_val = (
            data.get("atom_appraisal")
            or data.get("estimated_value")
            or data.get("appraisal_value")
            or data.get("appraisal")
            or data.get("valuation")
            or data.get("value")
        )
        est_val: Optional[float] = None
        if raw_val is not None:
            try:
                # Remove dollar signs or commas if returned as string
                cleaned_val = re.sub(r"[^\d.]", "", str(raw_val))
                if cleaned_val:
                    est_val = round(float(cleaned_val), 2)
            except (TypeError, ValueError):
                est_val = None

        # 3. Positive & Negative Signals
        positives: List[str] = []
        raw_pos = (
            data.get("positive_signals")
            or data.get("positives")
            or data.get("strengths")
            or data.get("pros")
            or []
        )
        if isinstance(raw_pos, list):
            positives = [str(p).strip() for p in raw_pos if str(p).strip()][:15]

        negatives: List[str] = []
        raw_neg = (
            data.get("negative_signals")
            or data.get("negatives")
            or data.get("weaknesses")
            or data.get("cons")
            or []
        )
        if isinstance(raw_neg, list):
            negatives = [str(n).strip() for n in raw_neg if str(n).strip()][:15]

        # 4. Optional Market & Structural Signals
        tld_count = None
        if "tld_taken_count" in data:
            try:
                tld_count = int(data["tld_taken_count"])
            except (TypeError, ValueError):
                pass
        elif "registered_tlds" in data and isinstance(data["registered_tlds"], (list, int)):
            tld_count = len(data["registered_tlds"]) if isinstance(data["registered_tlds"], list) else data["registered_tlds"]

        tm_conflicts = None
        if "tm_conflicts" in data or "trademark_conflicts" in data:
            try:
                tm_conflicts = int(data.get("tm_conflicts", data.get("trademark_conflicts", 0)))
            except (TypeError, ValueError):
                pass

        conf = None
        if "confidence" in data:
            try:
                conf = float(data["confidence"])
            except (TypeError, ValueError):
                pass

        cat = data.get("category") or data.get("market_category")
        root_info = data.get("root_word_info") or data.get("root_word")
        market_data = data.get("market_data") or data.get("comparables") or data.get("comparable_sales")

        norm_appraisal = normalize_atom_appraisal(est_val)

        return AtomAppraisalResult(
            provider="ATOM",
            status="SUCCESS",
            domain=domain.strip().lower(),
            atom_domain_score=domain_score,
            atom_appraisal_value=est_val,
            atom_appraisal_normalized=norm_appraisal,
            positive_signals=positives,
            negative_signals=negatives,
            tld_taken_count=tld_count,
            tm_conflicts=tm_conflicts,
            confidence=conf,
            category=str(cat) if cat else None,
            root_word_info=root_info if isinstance(root_info, dict) else None,
            market_data=market_data if isinstance(market_data, dict) else None,
            cache_hit=False,
            raw_response=raw,
            error_message=None,
        )

    async def appraise_domain(self, domain: str, use_cache: bool = True) -> AtomAppraisalResult:
        """
        Appraises a single domain via Atom Domain Appraisal API with caching and error handling.
        Returns normalized AtomAppraisalResult. Never raises exceptions.
        """
        clean_domain = domain.strip().lower()
        if not clean_domain.endswith(".com"):
            clean_domain = f"{clean_domain}.com"

        # Check Cache
        if use_cache:
            cached = self.cache.get(clean_domain)
            if cached is not None:
                return cached

        # Check Enabled Status
        if not self.enabled:
            return AtomAppraisalResult(
                status="DISABLED",
                domain=clean_domain,
                error_message="Atom appraisal integration is disabled",
            )

        # Check Configuration
        if not self.is_configured():
            res = AtomAppraisalResult(
                status="NOT_CONFIGURED",
                domain=clean_domain,
                error_message="Atom API credentials are not configured",
            )
            return res

        self._check_and_reset_daily_counter()

        # Check Quota
        if self.health.daily_limit is not None and self._quota_used_today >= self.health.daily_limit:
            self.health.status = AtomProviderHealthStatus.QUOTA_EXHAUSTED.value
            return AtomAppraisalResult(
                status="QUOTA_EXHAUSTED",
                domain=clean_domain,
                error_message="Atom daily appraisal quota has been reached",
            )

        # Execute network call with retry and semaphore control
        async with self._semaphore:
            client = self._get_client()
            params = {
                "domain_name": clean_domain,
                "domain": clean_domain,
            }
            tok = self._clean_token()
            if tok:
                params["api_token"] = tok
            if self.user_id:
                params["user_id"] = self.user_id

            headers = self._get_headers()
            last_err = ""

            for attempt in range(2):
                try:
                    started = time.perf_counter()
                    resp = await client.get(self.base_url, params=params, headers=headers)
                    latency = round((time.perf_counter() - started) * 1000, 2)
                    self.health.latency_ms = latency

                    if resp.status_code == 200:
                        try:
                            raw = resp.json()
                            result = self._parse_atom_response(clean_domain, raw)
                            if result.status == "AUTH_ERROR":
                                self.health.status = AtomProviderHealthStatus.AUTH_ERROR.value
                                self.health.authenticated = False
                                self.health.last_error = result.error_message
                                return result
                            if result.is_successful():
                                self._quota_used_today += 1
                                self.health.used_today = self._quota_used_today
                                self.health.last_success_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
                                self.cache.set(clean_domain, result)
                            return result
                        except Exception as parse_err:
                            return AtomAppraisalResult(
                                status="INVALID_RESPONSE",
                                domain=clean_domain,
                                error_message=f"Failed to parse Atom response: {parse_err}",
                            )

                    elif resp.status_code in (401, 403):
                        self.health.status = AtomProviderHealthStatus.AUTH_ERROR.value
                        return AtomAppraisalResult(
                            status="AUTH_ERROR",
                            domain=clean_domain,
                            error_message=f"Atom API authentication failed (HTTP {resp.status_code})",
                        )

                    elif resp.status_code == 429:
                        self.health.status = AtomProviderHealthStatus.RATE_LIMITED.value
                        return AtomAppraisalResult(
                            status="RATE_LIMITED",
                            domain=clean_domain,
                            error_message="Atom API rate limit or quota exceeded (HTTP 429)",
                        )

                    elif resp.status_code >= 500:
                        last_err = f"Atom server error HTTP {resp.status_code}"
                        if attempt == 0:
                            await asyncio.sleep(0.5)
                            continue

                    else:
                        return AtomAppraisalResult(
                            status="PROVIDER_ERROR",
                            domain=clean_domain,
                            error_message=f"Atom returned unexpected HTTP {resp.status_code}",
                        )

                except httpx.TimeoutException:
                    last_err = "Atom request timed out"
                    if attempt == 0:
                        await asyncio.sleep(0.5)
                        continue
                except Exception as exc:
                    last_err = f"Atom network error: {type(exc).__name__}"
                    if attempt == 0:
                        await asyncio.sleep(0.5)
                        continue

            return AtomAppraisalResult(
                status="TIMEOUT" if "timed out" in last_err else "PROVIDER_ERROR",
                domain=clean_domain,
                error_message=last_err,
            )

    async def appraise_batch(
        self,
        domains: Sequence[str],
        max_budget: Optional[int] = None,
        use_cache: bool = True
    ) -> Dict[str, AtomAppraisalResult]:
        """
        Appraises a batch of domains up to the budget limit.
        Respects configured concurrency and returns mapping {domain: AtomAppraisalResult}.
        """
        budget = max_budget if max_budget is not None else self.max_appraisals_per_run
        targets = list(domains)[:budget]
        if not targets:
            return {}

        results: Dict[str, AtomAppraisalResult] = {}
        tasks = [self.appraise_domain(d, use_cache=use_cache) for d in targets]
        batch_outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        for d, outcome in zip(targets, batch_outcomes):
            norm_d = d.strip().lower()
            if not norm_d.endswith(".com"):
                norm_d = f"{norm_d}.com"
            if isinstance(outcome, Exception):
                results[norm_d] = AtomAppraisalResult(
                    status="PROVIDER_ERROR",
                    domain=norm_d,
                    error_message=str(outcome),
                )
            else:
                results[norm_d] = outcome

        return results

    def select_candidates_for_atom(
        self,
        candidates: List[Dict[str, Any]],
        max_budget: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Part 8 — Diversified Pre-Selection Pool for Atom Appraisal.
        Never sends simply first N candidates.
        Allocates quota across naming strategies:
        REAL_WORD, COMPOUND, SEMANTIC, STRONG_INVENTED, MODERATE_INVENTED, PREFIX_SUFFIX, OTHER.
        Prevents INVENTED from monopolizing Atom calls.
        """
        budget = max_budget if max_budget is not None else self.max_appraisals_per_run
        if not candidates or budget <= 0:
            return []

        buckets: Dict[str, List[Dict[str, Any]]] = {
            "REAL_WORD": [],
            "COMPOUND": [],
            "SEMANTIC": [],
            "STRONG_INVENTED": [],
            "MODERATE_INVENTED": [],
            "PREFIX_SUFFIX": [],
            "OTHER": []
        }

        for c in candidates:
            # Only consider candidates that survived internal availability & IP hard gates
            if c.get("availability_status") not in ("AVAILABLE_STANDARD", None):
                continue
            if c.get("ip_risk_level") in ("CRITICAL", "HIGH"):
                continue

            strat = str(c.get("generation_strategy") or "").upper()
            nt = str(c.get("naming_type") or c.get("morphology_type") or "").upper()
            inv_sub = str(c.get("invented_subtype") or "").upper()
            inv_tier = str(c.get("invented_quality_tier") or "").upper()

            if nt in ("ONE_WORD", "REAL_WORD") or strat == "ONE_WORD":
                buckets["REAL_WORD"].append(c)
            elif nt == "COMPOUND" or strat == "COMPOUND":
                buckets["COMPOUND"].append(c)
            elif nt in ("SEMANTIC", "SEMANTIC_BRANDABLE") or strat in ("SEMANTIC", "SEMANTIC_BRANDABLE"):
                buckets["SEMANTIC"].append(c)
            elif nt == "INVENTED" or strat == "INVENTED":
                if inv_tier == "STRONG" or inv_sub in ("LEXICAL_ANCHORED", "SEMANTIC_ANCHORED", "HYBRID_ANCHORED"):
                    buckets["STRONG_INVENTED"].append(c)
                elif inv_tier == "MODERATE" or inv_sub in ("PHONETIC_ANCHORED", "MODERATE_ANCHORED"):
                    buckets["MODERATE_INVENTED"].append(c)
                else:
                    # Weak/unanchored goes to other with low priority
                    buckets["OTHER"].append(c)
            elif strat in ("PREFIX_SUFFIX", "AFFIX"):
                buckets["PREFIX_SUFFIX"].append(c)
            else:
                buckets["OTHER"].append(c)

        # Sort each bucket by internal quality / selection score descending
        def get_score(cand: Dict[str, Any]) -> float:
            return float(
                cand.get("final_rank_score")
                or cand.get("selection_score")
                or cand.get("overall_score")
                or cand.get("quality_score")
                or 0.0
            )

        for k in buckets:
            buckets[k].sort(key=get_score, reverse=True)

        selected: List[Dict[str, Any]] = []
        selected_domains: Set[str] = set()

        # Proportional round-robin allocation
        # E.g. for budget 10: 2 Real, 2 Compound, 2 Semantic, 2 Strong Inv, 1 Mod Inv, 1 Prefix
        strategy_order = [
            "REAL_WORD", "COMPOUND", "SEMANTIC", "STRONG_INVENTED",
            "MODERATE_INVENTED", "PREFIX_SUFFIX", "OTHER"
        ]

        # First pass: 1 from each non-empty bucket
        for strat in strategy_order:
            if len(selected) >= budget:
                break
            if buckets[strat]:
                cand = buckets[strat].pop(0)
                d = cand.get("domain", "")
                if d and d not in selected_domains:
                    selected.append(cand)
                    selected_domains.add(d)

        # Second pass: fill remaining budget by top remaining candidates round-robin
        while len(selected) < budget:
            progress = False
            for strat in strategy_order:
                if len(selected) >= budget:
                    break
                if buckets[strat]:
                    cand = buckets[strat].pop(0)
                    d = cand.get("domain", "")
                    if d and d not in selected_domains:
                        selected.append(cand)
                        selected_domains.add(d)
                        progress = True
            if not progress:
                break

        return selected
