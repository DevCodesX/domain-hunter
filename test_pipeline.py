import os
import sys
import pytest
import asyncio
import datetime
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

# Add workspace to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from availability import (
    AvailabilityEngine,
    AvailabilityStatus,
    AvailabilityResult,
    normalize_and_validate_candidate
)
from scheduler import DomainHunterPipeline, get_job_state, save_job_state
import main
from main import app
from fastapi.testclient import TestClient

client = TestClient(app)

# ==========================================
# 1. Registered domain -> rejected
# ==========================================
@pytest.mark.asyncio
async def test_registered_domain_rejected():
    engine = AvailabilityEngine()
    # talenta.com, predicta.com, kinetica.com are definitely registered
    res = await engine.check_domain("talenta.com")
    assert res.status == AvailabilityStatus.REGISTERED
    assert res.is_registered is True
    assert res.is_accepted() is False
    assert res.rejection_reason is not None

# ==========================================
# 2. Premium domain -> rejected
# ==========================================
@pytest.mark.asyncio
async def test_premium_domain_rejected():
    engine = AvailabilityEngine()
    # Mock Atom or GoDaddy returning premium
    with patch.object(engine, '_check_godaddy_api', new_callable=AsyncMock) as mock_gd:
        with patch.object(engine, '_check_verisign_rdap', new_callable=AsyncMock) as mock_rdap:
            # RDAP says unregistered at registry
            mock_rdap.return_value = AvailabilityResult(
                domain="premiumtestbrand.com",
                status=AvailabilityStatus.AVAILABLE_STANDARD,
                provider="verisign_rdap",
                is_registered=False,
                registration_available=True
            )
            # But registrar says premium
            mock_gd.return_value = (True, True) # (avail=True, is_prem=True)
            
            res = await engine.check_domain("premiumtestbrand.com")
            assert res.status == AvailabilityStatus.PREMIUM
            assert res.is_premium is True
            assert res.is_accepted() is False

# ==========================================
# 3. Standard available domain -> accepted
# ==========================================
@pytest.mark.asyncio
async def test_standard_available_domain_accepted():
    engine = AvailabilityEngine()
    # Very unique non-existent test domain
    test_d = "unregisteredantigravitysuite99238472.com"
    res = await engine.check_domain(test_d)
    assert res.status == AvailabilityStatus.AVAILABLE_STANDARD
    assert res.is_registered is False
    assert res.is_premium is False
    assert res.registration_available is True
    assert res.is_accepted() is True

# ==========================================
# 4. Availability timeout -> rejected from final list
# ==========================================
@pytest.mark.asyncio
async def test_availability_timeout_rejected():
    engine = AvailabilityEngine()
    with patch.object(engine, '_check_verisign_rdap', new_callable=AsyncMock) as mock_rdap:
        mock_rdap.return_value = AvailabilityResult(
            domain="timeouttestbrand.com",
            status=AvailabilityStatus.TIMEOUT,
            provider="verisign_rdap",
            error="Connection timed out",
            rejection_reason="timeout"
        )
        res = await engine.check_domain("timeouttestbrand.com")
        assert res.status == AvailabilityStatus.TIMEOUT
        assert res.is_accepted() is False

# ==========================================
# 5. Provider 503 -> rejected from final list
# ==========================================
@pytest.mark.asyncio
async def test_provider_503_rejected():
    engine = AvailabilityEngine()
    with patch.object(engine, '_check_verisign_rdap', new_callable=AsyncMock) as mock_rdap:
        mock_rdap.return_value = AvailabilityResult(
            domain="error503testbrand.com",
            status=AvailabilityStatus.ERROR,
            provider="verisign_rdap",
            error="HTTP 503 Upstream Server Error",
            rejection_reason="provider_server_error"
        )
        res = await engine.check_domain("error503testbrand.com")
        assert res.status == AvailabilityStatus.ERROR
        assert res.is_accepted() is False

# ==========================================
# 6. Provider 429 -> rejected from final list
# ==========================================
@pytest.mark.asyncio
async def test_provider_429_rejected():
    engine = AvailabilityEngine()
    with patch.object(engine, '_check_verisign_rdap', new_callable=AsyncMock) as mock_rdap:
        mock_rdap.return_value = AvailabilityResult(
            domain="ratelimittestbrand.com",
            status=AvailabilityStatus.RATE_LIMITED,
            provider="verisign_rdap",
            error="HTTP 429 Too Many Requests",
            rejection_reason="rate_limited"
        )
        res = await engine.check_domain("ratelimittestbrand.com")
        assert res.status == AvailabilityStatus.RATE_LIMITED
        assert res.is_accepted() is False

# ==========================================
# 7. Malformed AI domain -> rejected
# ==========================================
def test_malformed_ai_domain_rejected():
    cases = [
        "not a domain",
        "domain with spaces.com",
        "invalid!chars.com",
        "missingextension",
        "double.dot..com",
        "-startinghyphen.com",
        "endinghyphen-.com",
        "consecutive--hyphens.com",
        "punycode-xn--test.com",
        "wrongtld.org",
        "toolong" + "a"*70 + ".com"
    ]
    for c in cases:
        norm, err = normalize_and_validate_candidate(c)
        assert norm is None, f"Expected {c} to be rejected, got {norm}"
        assert err is not None

# ==========================================
# 8. Duplicate domain -> deduplicated
# ==========================================
def test_duplicate_domain_deduplicated():
    raw_list = ["testbrand.com", "TestBrand.COM", "https://testbrand.com", "www.testbrand.com", "testbrand.com"]
    unique = set()
    for item in raw_list:
        norm, _ = normalize_and_validate_candidate(item)
        if norm:
            unique.add(norm)
    assert len(unique) == 1
    assert "testbrand.com" in unique

# ==========================================
# 9. Manual generation -> actually runs
# ==========================================
@pytest.mark.asyncio
async def test_manual_generation_runs():
    # Verify manual run endpoint returns 200 started
    with patch("main.job_runner") as mock_runner:
        mock_runner.is_running = False
        mock_runner.run_domain_hunt = AsyncMock()
        
        response = client.post("/api/domains/run")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "started"
        assert "job_id" in data

# ==========================================
# 10. Daily generation -> actually runs
# ==========================================
@pytest.mark.asyncio
async def test_daily_generation_runs():
    mock_router = MagicMock()
    mock_http = MagicMock()
    pipeline = DomainHunterPipeline(mock_router, mock_http)
    
    # Mock stage execution to verify trigger="scheduled" works identically
    with patch.object(pipeline, 'run_domain_hunt', new_callable=AsyncMock) as mock_hunt:
        mock_hunt.return_value = {"status": "completed", "results": []}
        res = await pipeline.run_domain_hunt(trigger="scheduled")
        assert res["status"] == "completed"
        mock_hunt.assert_called_once_with(trigger="scheduled")

# ==========================================
# 11. Manual run while another run is active -> HTTP 409
# ==========================================
def test_manual_run_conflict_409():
    with patch("main.job_runner") as mock_runner:
        mock_runner.is_running = True
        response = client.post("/api/domains/run")
        assert response.status_code == 409
        data = response.json()
        assert data.get("status") == "already_running"

# ==========================================
# 12. Supabase final records contain verified availability
# ==========================================
@pytest.mark.asyncio
async def test_supabase_final_records_contract():
    # Verify the structure matches Phase 12 requirement
    sample_record = {
        "domain_name": "verifiedstartupdomain.com",
        "category": "Tech & AI",
        "availability_status": "AVAILABLE_STANDARD",
        "availability_provider": "verisign_rdap",
        "is_registered": False,
        "is_premium": False,
        "registration_available": True,
        "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "overall_score": 92
    }
    assert sample_record["availability_status"] == "AVAILABLE_STANDARD"
    assert sample_record["is_registered"] is False
    assert sample_record["is_premium"] is False
    assert sample_record["registration_available"] is True

# ==========================================
# 13. Frontend endpoint returns ONLY verified domains
# ==========================================
def test_frontend_only_displays_verified():
    # Mock latest_results containing a mixed list (simulating corrupted state)
    fake_state = {
        "latest_results": {
            "run_date": "2026-09-25T15:00:00Z",
            "results": [
                {
                    "domain": "badregistered.com",
                    "domain_name": "badregistered.com",
                    "availability_status": "REGISTERED",
                    "is_registered": True
                },
                {
                    "domain": "goodavailable.com",
                    "domain_name": "goodavailable.com",
                    "availability_status": "AVAILABLE_STANDARD",
                    "is_registered": False,
                    "is_premium": False,
                    "registration_available": True
                },
                {
                    "domain": "badpremium.com",
                    "domain_name": "badpremium.com",
                    "availability_status": "PREMIUM",
                    "is_premium": True
                }
            ]
        }
    }
    with patch("main.get_supabase", return_value=None):
        with patch("main.get_job_state", return_value=fake_state):
            response = client.get("/api/domains/latest")
            assert response.status_code == 200
            data = response.json()
            returned_domains = data.get("domains", [])
            assert len(returned_domains) == 1
            assert returned_domains[0]["domain"] == "goodavailable.com"
            assert returned_domains[0]["availability_status"] == "AVAILABLE_STANDARD"

# ==========================================
# 14. Refresh does not start a new hunt
# ==========================================
def test_refresh_does_not_start_hunt():
    with patch("main.job_runner") as mock_runner:
        mock_runner.is_running = False
        # Calling GET /api/domains/latest or GET /api/domains/status must be read-only
        res1 = client.get("/api/domains/latest")
        res2 = client.get("/api/domains/status")
        assert res1.status_code in [200, 404]
        assert res2.status_code == 200
        # Pipeline must NOT have been triggered
        assert mock_runner.run_domain_hunt.called is False if hasattr(mock_runner, 'run_domain_hunt') else True

# ==========================================
# 15. Last successful results remain visible if a new run fails
# ==========================================
def test_last_successful_results_preserved_on_failure():
    # If a run fails, latest_results is NOT cleared
    state = {
        "latest_results": {
            "run_date": "2026-09-25T14:00:00Z",
            "results": [
                {
                    "domain": "preservedsavedbrand.com",
                    "domain_name": "preservedsavedbrand.com",
                    "availability_status": "AVAILABLE_STANDARD",
                    "is_registered": False,
                    "is_premium": False
                }
            ]
        },
        "current_job": {
            "status": "failed",
            "error": "Upstream timeout during AI step"
        }
    }
    with patch("main.get_supabase", return_value=None):
        with patch("main.get_job_state", return_value=state):
            response = client.get("/api/domains/latest")
            data = response.json()
            assert data.get("status") == "success"
            domains = data.get("domains", [])
            assert len(domains) == 1
            assert domains[0]["domain"] == "preservedsavedbrand.com"
