import os
import re
import time
import asyncio
import datetime
import logging
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple
from pydantic import BaseModel, Field
import httpx

logger = logging.getLogger("AvailabilityEngine")

REAL_REGISTRY_PROVIDERS = {"verisign_rdap", "godaddy_api", "atom_marketplace", "doh_nameservers"}
MOCK_REGISTRY_PROVIDERS = {"test_mock_registry", "mock_registry", "fake_rdap"}

def is_production_mode() -> bool:
    env = os.getenv("APP_ENV", "production").lower()
    allow_mock = os.getenv("ALLOW_MOCK_REGISTRY", "false").lower() == "true"
    return env == "production" and not allow_mock

class AvailabilityStatus(str, Enum):
    AVAILABLE_STANDARD = "AVAILABLE_STANDARD"
    REGISTERED = "REGISTERED"
    PREMIUM = "PREMIUM"
    UNKNOWN = "UNKNOWN"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"

class AvailabilityResult(BaseModel):
    domain: str
    status: AvailabilityStatus
    provider: str
    checked_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    is_registered: bool = False
    is_premium: bool = False
    registration_available: bool = False
    availability_verified: bool = False
    availability_check_status: str = "UNVERIFIED" # "VERIFIED", "UNVERIFIED", "FAILED", "NOT_CHECKED"
    premium_status: str = "NOT_PREMIUM" # "NOT_PREMIUM", "PREMIUM", "UNKNOWN"
    premium_provider: Optional[str] = None
    http_status: Optional[int] = None
    elapsed_ms: Optional[float] = None
    retry_count: int = 0
    confidence: float = 1.0
    raw_response: Optional[Any] = None
    error: Optional[str] = None
    rejection_reason: Optional[str] = None

    def __init__(self, **data):
        super().__init__(**data)
        # Authoritative real provider auto-verification
        if self.provider in REAL_REGISTRY_PROVIDERS and self.status in [AvailabilityStatus.AVAILABLE_STANDARD, AvailabilityStatus.REGISTERED]:
            if not self.availability_verified and self.availability_check_status == "UNVERIFIED":
                self.availability_verified = True
                self.availability_check_status = "VERIFIED"
            # Auto-set registration_available for AVAILABLE_STANDARD from real providers
            if self.status == AvailabilityStatus.AVAILABLE_STANDARD and not self.is_registered:
                self.registration_available = True

    def is_accepted(self) -> bool:
        # Hard invariant: mock provider NEVER qualifies in production
        if is_production_mode() and self.provider in MOCK_REGISTRY_PROVIDERS:
            return False

        # In production mode, domain MUST be verified by a real authoritative provider
        if is_production_mode() and not self.availability_verified:
            return False

        return (
            self.status == AvailabilityStatus.AVAILABLE_STANDARD
            and self.availability_check_status == "VERIFIED"
            and not self.is_registered
            and not self.is_premium
            and self.premium_status != "PREMIUM"
            and self.registration_available is True
        )

def normalize_and_validate_candidate(candidate: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Phase 2: Normalize and validate domain candidates.
    - lowercase
    - remove protocol (http://, https://)
    - remove www.
    - remove whitespace
    - remove invalid characters
    - ensure valid .com syntax
    - reject malformed domains
    - reject domains containing spaces
    - reject Unicode/punycode
    """
    if not candidate or not isinstance(candidate, str):
        return None, "empty_candidate"

    clean = candidate.strip().lower()
    clean = re.sub(r"^https?://", "", clean)
    clean = re.sub(r"^www\.", "", clean)
    clean = clean.split("/")[0].split(":")[0].strip()

    # Reject if spaces inside
    if " " in clean or "\t" in clean or "\n" in clean:
        return None, "contains_whitespace"

    # Reject if punycode or unicode
    if clean.startswith("xn--") or any(ord(c) > 127 for c in clean):
        return None, "unicode_or_punycode_unsupported"

    # Reject if double extensions like .io.com, .ai.com, .com.com
    parts = clean.split(".")
    if len(parts) != 2 or parts[1] != "com":
        return None, "invalid_extension_not_com"

    label = parts[0]
    # Check label requirements
    if len(label) < 2 or len(label) > 63:
        return None, "label_length_invalid"

    if label.startswith("-") or label.endswith("-"):
        return None, "hyphen_at_boundary"

    if "--" in label:
        return None, "consecutive_hyphens"

    if not re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", label) and len(label) > 1:
        return None, "invalid_characters"

    if len(label) == 1 and not label.isalnum():
        return None, "invalid_single_character"

    return f"{label}.com", None

class AvailabilityEngine:
    provider: str = "verisign_rdap"

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None):
        self.provider = "verisign_rdap"
        self._external_client = http_client
        self.semaphore = asyncio.Semaphore(4) # Limit concurrency for registry safety
        self.cache: Dict[str, Tuple[AvailabilityResult, float]] = {}
        self.cache_ttl = 300 # 5 minutes cache

    def _get_client(self) -> httpx.AsyncClient:
        if self._external_client:
            return self._external_client
        return httpx.AsyncClient(timeout=10.0)

    async def _check_dns_nameservers(self, domain: str, client: httpx.AsyncClient) -> Optional[bool]:
        """
        Fast DNS NS lookup via Cloudflare DNS over HTTPS.
        Returns:
            True if domain has active nameservers (definitely registered)
            False if NXDOMAIN (status 3)
            None if indeterminate / timeout / error
        """
        try:
            url = f"https://cloudflare-dns.com/dns-query?name={domain}&type=NS"
            res = await client.get(url, headers={"accept": "application/dns-json"}, timeout=4.0)
            if res.status_code == 200:
                data = res.json()
                status = data.get("Status")
                answers = data.get("Answer", [])
                if status == 0 and len(answers) > 0:
                    return True # Has active nameservers -> definitely registered
                if status == 3: # NXDOMAIN
                    return False
        except Exception as e:
            logger.debug(f"DoH check for {domain} skipped: {e}")
        return None

    async def _check_atom_marketplace(self, domain: str, client: httpx.AsyncClient) -> Optional[bool]:
        """
        Atom marketplace check if configured.
        Returns:
            True if domain is listed on Atom (premium/aftermarket)
            False if not listed
            None if Atom check not configured or unavailable
        """
        atom_key = os.getenv("ATOM_API_KEY", "")
        if not atom_key or atom_key == "your_atom_token_here" or atom_key.startswith("ضع"):
            return None

        try:
            url = f"https://api.atom.com/v1/domains/search?query={domain}"
            headers = {"Authorization": f"Bearer {atom_key}", "User-Agent": "DomainHunter/2.0"}
            res = await client.get(url, headers=headers, timeout=5.0)
            if res.status_code == 200:
                data = res.json()
                listings = data.get("domains", []) or data.get("data", [])
                for item in listings:
                    if isinstance(item, dict) and item.get("name", "").lower() == domain:
                        return True
            elif res.status_code in [401, 403]:
                logger.warning(f"Atom API authentication failed: HTTP {res.status_code}")
                return None
        except Exception as e:
            logger.debug(f"Atom check for {domain} error: {e}")
        return None

    async def _check_godaddy_api(self, domain: str, client: httpx.AsyncClient) -> Optional[Tuple[bool, bool]]:
        """
        GoDaddy check if valid reseller credentials exist.
        Returns:
            (is_available, is_premium) if successful
            None if credentials missing, 401, 403, or failure
        """
        godaddy_key = os.getenv("GODADDY_API_KEY", "")
        godaddy_secret = os.getenv("GODADDY_API_SECRET", "")
        if not godaddy_key or not godaddy_secret or godaddy_key.startswith("ضع"):
            return None

        url = f"https://api.godaddy.com/v1/domains/available?domain={domain}&checkType=FAST"
        headers = {
            "Authorization": f"sso-key {godaddy_key}:{godaddy_secret}",
            "Content-Type": "application/json"
        }
        try:
            res = await client.get(url, headers=headers, timeout=6.0)
            if res.status_code == 200:
                data = res.json()
                avail = bool(data.get("available"))
                # GoDaddy flags premium domains or high prices
                is_prem = bool(data.get("premium", False)) or (data.get("price", 0) > 25000000) # price in micro-units
                return (avail, is_prem)
            elif res.status_code in [401, 403]:
                logger.debug(f"GoDaddy API not accessible (HTTP {res.status_code}), falling back to Verisign RDAP.")
                return None
        except Exception as e:
            logger.debug(f"GoDaddy API error for {domain}: {e}")
        return None

    def _log_rdap(self, res: AvailabilityResult):
        code_str = str(res.http_status) if res.http_status is not None else "N/A"
        lat_str = f"{res.elapsed_ms:.1f}ms" if res.elapsed_ms is not None else "N/A"
        logger.info(
            f"[RDAP] {res.domain} provider=verisign_rdap status={code_str} "
            f"availability={res.status.value} latency={lat_str} retries={res.retry_count}"
        )

    async def _check_verisign_rdap(self, domain: str, client: httpx.AsyncClient) -> AvailabilityResult:
        """
        Authoritative Registry Provider for .com: Verisign RDAP.
        Every single .com domain is officially registered at Verisign.
        - HTTP 200 -> REGISTERED (active registration record exists)
        - HTTP 404 -> AVAILABLE_STANDARD (no registry record exists -> available)
        - HTTP 429 -> RATE_LIMITED (unknown / retry)
        - HTTP 5xx / timeout -> ERROR / TIMEOUT (unknown / retry)
        """
        url = f"https://rdap.verisign.com/com/v1/domain/{domain}"
        headers = {
            "User-Agent": "DomainHunter/2.0 (Verisign RDAP Availability Engine)",
            "Accept": "application/rdap+json, application/json"
        }

        max_retries = 2
        for attempt in range(max_retries + 1):
            t_start = time.time()
            try:
                res = await client.get(url, headers=headers, timeout=8.0)
                elapsed_ms = (time.time() - t_start) * 1000.0

                if res.status_code == 200:
                    result = AvailabilityResult(
                        domain=domain,
                        status=AvailabilityStatus.REGISTERED,
                        provider="verisign_rdap",
                        is_registered=True,
                        is_premium=False,
                        registration_available=False,
                        availability_verified=True,
                        availability_check_status="VERIFIED",
                        premium_status="NOT_CHECKED",
                        http_status=200,
                        elapsed_ms=elapsed_ms,
                        retry_count=attempt,
                        confidence=1.0,
                        rejection_reason="domain_registered"
                    )
                    self._log_rdap(result)
                    return result
                elif res.status_code == 404:
                    result = AvailabilityResult(
                        domain=domain,
                        status=AvailabilityStatus.AVAILABLE_STANDARD,
                        provider="verisign_rdap",
                        is_registered=False,
                        is_premium=False,
                        registration_available=True,
                        availability_verified=True,
                        availability_check_status="VERIFIED",
                        premium_status="NOT_PREMIUM",
                        http_status=404,
                        elapsed_ms=elapsed_ms,
                        retry_count=attempt,
                        confidence=1.0
                    )
                    self._log_rdap(result)
                    return result
                elif res.status_code == 429:
                    if attempt < max_retries:
                        backoff = 1.5 * (attempt + 1)
                        logger.warning(f"RDAP rate limited for {domain}, backing off {backoff:.1f}s (attempt {attempt+1}/{max_retries})")
                        await asyncio.sleep(backoff)
                        continue
                    result = AvailabilityResult(
                        domain=domain,
                        status=AvailabilityStatus.RATE_LIMITED,
                        provider="verisign_rdap",
                        is_registered=False,
                        is_premium=False,
                        registration_available=False,
                        availability_verified=False,
                        availability_check_status="FAILED",
                        http_status=429,
                        elapsed_ms=elapsed_ms,
                        retry_count=attempt,
                        error="HTTP 429 Too Many Requests",
                        rejection_reason="rate_limited"
                    )
                    self._log_rdap(result)
                    return result
                elif res.status_code in [500, 502, 503, 504]:
                    if attempt < max_retries:
                        await asyncio.sleep(1.0 * (attempt + 1))
                        continue
                    result = AvailabilityResult(
                        domain=domain,
                        status=AvailabilityStatus.ERROR,
                        provider="verisign_rdap",
                        is_registered=False,
                        is_premium=False,
                        registration_available=False,
                        availability_verified=False,
                        availability_check_status="FAILED",
                        http_status=res.status_code,
                        elapsed_ms=elapsed_ms,
                        retry_count=attempt,
                        error=f"HTTP {res.status_code} Upstream Server Error",
                        rejection_reason="provider_server_error"
                    )
                    self._log_rdap(result)
                    return result
                else:
                    result = AvailabilityResult(
                        domain=domain,
                        status=AvailabilityStatus.ERROR,
                        provider="verisign_rdap",
                        is_registered=False,
                        is_premium=False,
                        registration_available=False,
                        availability_verified=False,
                        availability_check_status="FAILED",
                        http_status=res.status_code,
                        elapsed_ms=elapsed_ms,
                        retry_count=attempt,
                        error=f"HTTP {res.status_code}",
                        rejection_reason="upstream_error"
                    )
                    self._log_rdap(result)
                    return result
            except httpx.TimeoutException as e:
                elapsed_ms = (time.time() - t_start) * 1000.0
                if attempt < max_retries:
                    await asyncio.sleep(1.0)
                    continue
                result = AvailabilityResult(
                    domain=domain,
                    status=AvailabilityStatus.TIMEOUT,
                    provider="verisign_rdap",
                    is_registered=False,
                    is_premium=False,
                    registration_available=False,
                    availability_verified=False,
                    availability_check_status="FAILED",
                    elapsed_ms=elapsed_ms,
                    retry_count=attempt,
                    error=f"Timeout: {str(e)}",
                    rejection_reason="timeout"
                )
                self._log_rdap(result)
                return result
            except Exception as e:
                elapsed_ms = (time.time() - t_start) * 1000.0
                if attempt < max_retries:
                    await asyncio.sleep(1.0)
                    continue
                result = AvailabilityResult(
                    domain=domain,
                    status=AvailabilityStatus.ERROR,
                    provider="verisign_rdap",
                    is_registered=False,
                    is_premium=False,
                    registration_available=False,
                    availability_verified=False,
                    availability_check_status="FAILED",
                    elapsed_ms=elapsed_ms,
                    retry_count=attempt,
                    error=str(e),
                    rejection_reason="network_error"
                )
                self._log_rdap(result)
                return result

        result = AvailabilityResult(
            domain=domain,
            status=AvailabilityStatus.UNKNOWN,
            provider="verisign_rdap",
            is_registered=False,
            is_premium=False,
            registration_available=False,
            availability_verified=False,
            availability_check_status="FAILED",
            error="Retries exhausted",
            rejection_reason="retries_exhausted"
        )
        self._log_rdap(result)
        return result

    async def check_domain(self, domain: str) -> AvailabilityResult:
        """
        Phase 4: Hard Availability Gate
        Flow:
        1. Syntax & Normalization
        2. Cache check
        3. DNS Nameservers Pre-filter (if NS active -> registered)
        4. Primary Registry Verisign RDAP Check
        5. Atom / GoDaddy Marketplace & Premium check
        6. Structured logging
        """
        # 1. Normalize & Validate Syntax
        normalized, error_reason = normalize_and_validate_candidate(domain)
        if not normalized:
            res = AvailabilityResult(
                domain=domain,
                status=AvailabilityStatus.ERROR,
                provider="syntax_validator",
                availability_verified=False,
                availability_check_status="FAILED",
                rejection_reason=error_reason or "malformed_domain"
            )
            self._log_result(res)
            return res

        # 2. Check memory cache
        now = time.time()
        if normalized in self.cache:
            cached_res, timestamp = self.cache[normalized]
            if now - timestamp < self.cache_ttl:
                # Cache hit
                return cached_res

        client = self._get_client()

        async with self.semaphore:
            # 3. Fast DNS check (Supporting signal only - active NS = registered)
            has_ns = await self._check_dns_nameservers(normalized, client)
            if has_ns is True:
                # Active nameservers means domain is registered
                res = AvailabilityResult(
                    domain=normalized,
                    status=AvailabilityStatus.REGISTERED,
                    provider="doh_nameservers",
                    is_registered=True,
                    is_premium=False,
                    registration_available=False,
                    availability_verified=True,
                    availability_check_status="VERIFIED",
                    confidence=1.0,
                    rejection_reason="nameservers_active"
                )
                self.cache[normalized] = (res, now)
                self._log_result(res)
                return res

            # 4. Primary Registry RDAP Check (Authoritative)
            rdap_result = await self._check_verisign_rdap(normalized, client)
            await asyncio.sleep(0.06) # gentle registry throttle

            # If registered or error or timeout, reject immediately
            if rdap_result.status != AvailabilityStatus.AVAILABLE_STANDARD:
                self.cache[normalized] = (rdap_result, now)
                self._log_result(rdap_result)
                return rdap_result

            # 5. Domain is unregistered at registry level -> Check marketplace / premium
            # Check Atom if configured
            is_atom_premium = await self._check_atom_marketplace(normalized, client)
            if is_atom_premium is True:
                res = AvailabilityResult(
                    domain=normalized,
                    status=AvailabilityStatus.PREMIUM,
                    provider="atom_marketplace",
                    is_registered=False,
                    is_premium=True,
                    registration_available=False,
                    availability_verified=True,
                    availability_check_status="VERIFIED",
                    premium_status="PREMIUM",
                    premium_provider="atom_marketplace",
                    rejection_reason="atom_marketplace_premium"
                )
                self.cache[normalized] = (res, now)
                self._log_result(res)
                return res

            # Check GoDaddy if configured
            godaddy_check = await self._check_godaddy_api(normalized, client)
            if godaddy_check is not None:
                avail, is_prem = godaddy_check
                if not avail:
                    res = AvailabilityResult(
                        domain=normalized,
                        status=AvailabilityStatus.REGISTERED,
                        provider="godaddy_api",
                        is_registered=True,
                        registration_available=False,
                        availability_verified=True,
                        availability_check_status="VERIFIED",
                        rejection_reason="godaddy_marked_unavailable"
                    )
                    self.cache[normalized] = (res, now)
                    self._log_result(res)
                    return res
                if is_prem:
                    res = AvailabilityResult(
                        domain=normalized,
                        status=AvailabilityStatus.PREMIUM,
                        provider="godaddy_api",
                        is_registered=False,
                        is_premium=True,
                        registration_available=False,
                        availability_verified=True,
                        availability_check_status="VERIFIED",
                        premium_status="PREMIUM",
                        premium_provider="godaddy_api",
                        rejection_reason="godaddy_marked_premium"
                    )
                    self.cache[normalized] = (res, now)
                    self._log_result(res)
                    return res

            # Hard gate passed: Standard registration verified via Verisign RDAP
            final_res = AvailabilityResult(
                domain=normalized,
                status=AvailabilityStatus.AVAILABLE_STANDARD,
                provider="verisign_rdap",
                is_registered=False,
                is_premium=False,
                registration_available=True,
                availability_verified=True,
                availability_check_status="VERIFIED",
                premium_status="NOT_PREMIUM",
                premium_provider="verisign_rdap",
                http_status=404,
                elapsed_ms=rdap_result.elapsed_ms,
                confidence=1.0
            )
            self.cache[normalized] = (final_res, now)
            self._log_result(final_res)
            return final_res

    def _log_result(self, res: AvailabilityResult):
        """
        Phase 20 & Section 16: Structured & Diagnostic Logging
        """
        accepted = res.is_accepted()
        code_str = str(res.http_status) if res.http_status is not None else "N/A"
        lat_str = f"{res.elapsed_ms:.1f}ms" if res.elapsed_ms is not None else "N/A"
        logger.info(
            f"[AVAILABILITY] domain={res.domain} provider={res.provider} status={res.status.value} "
            f"http_status={code_str} latency={lat_str} retries={res.retry_count} "
            f"verified={res.availability_verified} is_registered={res.is_registered} "
            f"is_premium={res.is_premium} premium_status={res.premium_status} accepted={str(accepted).lower()} "
        )


    async def check_batch(
        self,
        domains: List[str],
        on_progress=None,
        max_available: Optional[int] = None
    ) -> Dict[str, AvailabilityResult]:
        """
        Checks a batch of domain candidates with progress reporting.
        Supports early stopping via max_available when sufficient standard available domains are found.
        """
        results: Dict[str, AvailabilityResult] = {}
        avail_count = 0
        for idx, d in enumerate(domains):
            res = await self.check_domain(d)
            results[d] = res
            if res.status == AvailabilityStatus.AVAILABLE_STANDARD and res.is_accepted():
                avail_count += 1
            if on_progress:
                try:
                    await on_progress(idx + 1, len(domains), res)
                except Exception as e:
                    logger.debug(f"Progress callback error: {e}")
            if max_available and avail_count >= max_available:
                logger.info(f"[AVAILABILITY] Reached target max_available={max_available} standard available domains. Concluding availability check.")
                break
        return results
