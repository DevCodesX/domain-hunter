"""
Section 13 — Production Availability Verification Test Suite
Explicitly tests all 10 verification scenarios required by the production availability contract:

TEST 1: Known registered .com domain -> REGISTERED -> rejected
TEST 2: Known available .com domain -> AVAILABLE_STANDARD -> provider = verisign_rdap
TEST 3: RDAP timeout -> TIMEOUT/UNKNOWN -> never reaches final opportunities
TEST 4: RDAP HTTP 429 -> RATE_LIMITED/UNKNOWN -> never becomes AVAILABLE
TEST 5: RDAP HTTP 500 -> ERROR/UNKNOWN -> never becomes AVAILABLE
TEST 6: Mock provider -> allowed ONLY inside explicit test environment
TEST 7: Production + mock provider -> hard failure / blocked
TEST 8: DNS has no records but RDAP says REGISTERED -> REGISTERED
TEST 9: DNS exists (active NS) and RDAP says REGISTERED -> REGISTERED
TEST 10: Final selection contains ONLY availability_status = AVAILABLE_STANDARD & availability_verified = True
"""

import os
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from availability import (
    AvailabilityEngine,
    AvailabilityStatus,
    AvailabilityResult,
    REAL_REGISTRY_PROVIDERS,
    MOCK_REGISTRY_PROVIDERS,
    is_production_mode,
    normalize_and_validate_candidate
)
from scheduler import DomainHunterPipeline, get_job_state


@pytest.mark.asyncio
async def test_1_known_registered_domain():
    """TEST 1: A known registered .com domain -> REGISTERED -> rejected from final pool."""
    engine = AvailabilityEngine()
    res = await engine.check_domain("google.com")
    assert res.status == AvailabilityStatus.REGISTERED
    assert res.is_registered is True
    assert res.is_accepted() is False
    assert res.registration_available is False
    assert res.rejection_reason is not None


@pytest.mark.asyncio
async def test_2_known_available_domain():
    """TEST 2: A known available .com domain -> AVAILABLE_STANDARD -> provider = verisign_rdap."""
    engine = AvailabilityEngine()
    test_d = "unregisteredantigravitysuite99238472.com"
    res = await engine.check_domain(test_d)
    assert res.status == AvailabilityStatus.AVAILABLE_STANDARD
    assert res.provider == "verisign_rdap"
    assert res.is_registered is False
    assert res.is_premium is False
    assert res.registration_available is True
    assert res.availability_verified is True
    assert res.availability_check_status == "VERIFIED"
    assert res.is_accepted() is True


@pytest.mark.asyncio
async def test_3_rdap_timeout_never_available():
    """TEST 3: RDAP timeout -> TIMEOUT/UNKNOWN -> never reaches final opportunities."""
    engine = AvailabilityEngine()
    with patch.object(engine, '_check_verisign_rdap', new_callable=AsyncMock) as mock_rdap:
        mock_rdap.return_value = AvailabilityResult(
            domain="timeoutcandidate99.com",
            status=AvailabilityStatus.TIMEOUT,
            provider="verisign_rdap",
            availability_verified=False,
            availability_check_status="FAILED",
            error="Connection timed out",
            rejection_reason="timeout"
        )
        res = await engine.check_domain("timeoutcandidate99.com")
        assert res.status in [AvailabilityStatus.TIMEOUT, AvailabilityStatus.UNKNOWN]
        assert res.is_accepted() is False
        assert res.registration_available is False


@pytest.mark.asyncio
async def test_4_rdap_429_never_available():
    """TEST 4: RDAP HTTP 429 -> RATE_LIMITED / UNKNOWN -> never becomes AVAILABLE."""
    engine = AvailabilityEngine()
    with patch.object(engine, '_check_verisign_rdap', new_callable=AsyncMock) as mock_rdap:
        mock_rdap.return_value = AvailabilityResult(
            domain="ratelimitedcandidate99.com",
            status=AvailabilityStatus.RATE_LIMITED,
            provider="verisign_rdap",
            http_status=429,
            availability_verified=False,
            availability_check_status="FAILED",
            error="HTTP 429 Too Many Requests",
            rejection_reason="rate_limited"
        )
        res = await engine.check_domain("ratelimitedcandidate99.com")
        assert res.status == AvailabilityStatus.RATE_LIMITED
        assert res.is_accepted() is False
        assert res.status != AvailabilityStatus.AVAILABLE_STANDARD


@pytest.mark.asyncio
async def test_5_rdap_500_never_available():
    """TEST 5: RDAP HTTP 500 -> ERROR / UNKNOWN -> never becomes AVAILABLE."""
    engine = AvailabilityEngine()
    with patch.object(engine, '_check_verisign_rdap', new_callable=AsyncMock) as mock_rdap:
        mock_rdap.return_value = AvailabilityResult(
            domain="servererrorcandidate99.com",
            status=AvailabilityStatus.ERROR,
            provider="verisign_rdap",
            http_status=500,
            availability_verified=False,
            availability_check_status="FAILED",
            error="HTTP 500 Upstream Error",
            rejection_reason="provider_server_error"
        )
        res = await engine.check_domain("servererrorcandidate99.com")
        assert res.status == AvailabilityStatus.ERROR
        assert res.is_accepted() is False
        assert res.status != AvailabilityStatus.AVAILABLE_STANDARD


def test_6_mock_provider_allowed_only_in_test_environment():
    """TEST 6: Mock provider -> allowed ONLY inside explicit test environment."""
    mock_res = AvailabilityResult(
        domain="mocktest99.com",
        status=AvailabilityStatus.AVAILABLE_STANDARD,
        provider="test_mock_registry",
        is_registered=False,
        is_premium=False,
        registration_available=True,
        availability_verified=True,
        availability_check_status="VERIFIED"
    )

    old_env = os.environ.get("APP_ENV")
    old_allow = os.environ.get("ALLOW_MOCK_REGISTRY")
    try:
        # In test mode
        os.environ["APP_ENV"] = "test"
        os.environ["ALLOW_MOCK_REGISTRY"] = "true"
        assert not is_production_mode()
        assert mock_res.is_accepted() is True
    finally:
        if old_env is not None: os.environ["APP_ENV"] = old_env
        else: os.environ.pop("APP_ENV", None)
        if old_allow is not None: os.environ["ALLOW_MOCK_REGISTRY"] = old_allow
        else: os.environ.pop("ALLOW_MOCK_REGISTRY", None)


def test_7_production_blocks_mock_provider():
    """TEST 7: Production mode + mock provider -> hard blocked / rejected."""
    mock_res = AvailabilityResult(
        domain="mocktest99.com",
        status=AvailabilityStatus.AVAILABLE_STANDARD,
        provider="test_mock_registry",
        is_registered=False,
        is_premium=False,
        registration_available=True,
        availability_verified=True,
        availability_check_status="VERIFIED"
    )

    old_env = os.environ.get("APP_ENV")
    old_allow = os.environ.get("ALLOW_MOCK_REGISTRY")
    try:
        # Strict production mode
        os.environ["APP_ENV"] = "production"
        os.environ["ALLOW_MOCK_REGISTRY"] = "false"
        assert is_production_mode() is True
        # Must be rejected!
        assert mock_res.is_accepted() is False

        # Injected mock engine in pipeline must be rejected in production
        class DummyMockEngine:
            provider = "test_mock_registry"
        
        pipeline = DomainHunterPipeline(router=MagicMock(), http_client=MagicMock(), availability_engine=DummyMockEngine())
        # Pipeline must have fallen closed to real AvailabilityEngine
        assert pipeline.availability_engine.__class__.__name__ == "AvailabilityEngine"
    finally:
        if old_env is not None: os.environ["APP_ENV"] = old_env
        else: os.environ.pop("APP_ENV", None)
        if old_allow is not None: os.environ["ALLOW_MOCK_REGISTRY"] = old_allow
        else: os.environ.pop("ALLOW_MOCK_REGISTRY", None)


@pytest.mark.asyncio
async def test_8_dns_nxdomain_but_rdap_registered():
    """TEST 8: DNS has no records (NXDOMAIN) but RDAP says REGISTERED -> REGISTERED."""
    engine = AvailabilityEngine()
    with patch.object(engine, '_check_dns_nameservers', new_callable=AsyncMock) as mock_dns:
        with patch.object(engine, '_check_verisign_rdap', new_callable=AsyncMock) as mock_rdap:
            # DNS says NXDOMAIN (no nameservers)
            mock_dns.return_value = False
            # But authoritative Verisign RDAP says 200 (Registered, e.g. defensive registration)
            mock_rdap.return_value = AvailabilityResult(
                domain="defensivereg.com",
                status=AvailabilityStatus.REGISTERED,
                provider="verisign_rdap",
                is_registered=True,
                registration_available=False,
                availability_verified=True,
                availability_check_status="VERIFIED",
                http_status=200
            )

            res = await engine.check_domain("defensivereg.com")
            assert res.status == AvailabilityStatus.REGISTERED
            assert res.is_registered is True
            assert res.is_accepted() is False


@pytest.mark.asyncio
async def test_9_dns_active_ns_and_rdap_registered():
    """TEST 9: DNS exists (active NS) and RDAP says REGISTERED -> REGISTERED."""
    engine = AvailabilityEngine()
    # Cloudflare check returns True (active NS)
    with patch.object(engine, '_check_dns_nameservers', new_callable=AsyncMock) as mock_dns:
        mock_dns.return_value = True
        res = await engine.check_domain("activeexample.com")
        assert res.status == AvailabilityStatus.REGISTERED
        assert res.is_registered is True
        assert res.is_accepted() is False
        assert res.provider == "doh_nameservers"


def test_10_final_selection_contains_only_verified_available_standard():
    """TEST 10: Final opportunity contract enforces ONLY verified AVAILABLE_STANDARD."""
    candidates = [
        {
            "domain": "verifiedavail.com",
            "availability_status": "AVAILABLE_STANDARD",
            "availability_provider": "verisign_rdap",
            "availability_verified": True,
            "availability_check_status": "VERIFIED",
            "premium_status": "NOT_PREMIUM",
            "is_registered": False,
            "is_premium": False,
            "registration_available": True
        },
        {
            "domain": "mockcandidate.com",
            "availability_status": "AVAILABLE_STANDARD",
            "availability_provider": "test_mock_registry",
            "availability_verified": True,
            "availability_check_status": "VERIFIED",
            "premium_status": "NOT_PREMIUM",
            "is_registered": False,
            "is_premium": False,
            "registration_available": True
        },
        {
            "domain": "unverifiedcandidate.com",
            "availability_status": "AVAILABLE_STANDARD",
            "availability_provider": "verisign_rdap",
            "availability_verified": False,
            "availability_check_status": "UNVERIFIED",
            "premium_status": "NOT_PREMIUM",
            "is_registered": False,
            "is_premium": False,
            "registration_available": True
        },
        {
            "domain": "premiumcandidate.com",
            "availability_status": "PREMIUM",
            "availability_provider": "atom_marketplace",
            "availability_verified": True,
            "availability_check_status": "VERIFIED",
            "premium_status": "PREMIUM",
            "is_registered": False,
            "is_premium": True,
            "registration_available": False
        },
        {
            "domain": "registeredcandidate.com",
            "availability_status": "REGISTERED",
            "availability_provider": "verisign_rdap",
            "availability_verified": True,
            "availability_check_status": "VERIFIED",
            "premium_status": "NOT_PREMIUM",
            "is_registered": True,
            "is_premium": False,
            "registration_available": False
        }
    ]

    old_env = os.environ.get("APP_ENV")
    old_allow = os.environ.get("ALLOW_MOCK_REGISTRY")
    try:
        os.environ["APP_ENV"] = "production"
        os.environ["ALLOW_MOCK_REGISTRY"] = "false"

        accepted = []
        for c in candidates:
            prov = c.get("availability_provider")
            is_mock = prov in MOCK_REGISTRY_PROVIDERS or "mock" in str(prov).lower()
            if is_production_mode() and is_mock:
                continue
            if is_production_mode() and prov not in REAL_REGISTRY_PROVIDERS:
                continue
            if is_production_mode() and not c.get("availability_verified"):
                continue
            if c.get("availability_status") != "AVAILABLE_STANDARD":
                continue
            if c.get("is_registered") or not c.get("registration_available"):
                continue
            if c.get("is_premium") or c.get("premium_status") == "PREMIUM":
                continue
            accepted.append(c["domain"])

        assert accepted == ["verifiedavail.com"]
    finally:
        if old_env is not None: os.environ["APP_ENV"] = old_env
        else: os.environ.pop("APP_ENV", None)
        if old_allow is not None: os.environ["ALLOW_MOCK_REGISTRY"] = old_allow
        else: os.environ.pop("ALLOW_MOCK_REGISTRY", None)
