"""
Production Hunt Verification Script
Executes a live Domain Hunt using DomainHunterPipeline in production mode.
Validates:
- Real Verisign RDAP is used
- No test_mock_registry appears anywhere
- Reports all metrics and provider distributions
"""

import os
import sys
import json
import asyncio
import logging
import httpx

# Ensure production mode
os.environ["APP_ENV"] = "production"
os.environ["ALLOW_MOCK_REGISTRY"] = "false"

# Configure logging to console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("LiveHuntAudit")

from router import ModelRouter
from availability import AvailabilityEngine, is_production_mode, REAL_REGISTRY_PROVIDERS, MOCK_REGISTRY_PROVIDERS
from scheduler import DomainHunterPipeline, get_job_state
from main import get_supabase

async def main():
    logger.info("=== Starting Production Domain Hunt ===")
    logger.info(f"is_production_mode: {is_production_mode()}")
    assert is_production_mode() is True, "Must be in production mode!"

    router = ModelRouter()
    http_client = httpx.AsyncClient(timeout=15.0)
    avail_engine = AvailabilityEngine(http_client)

    logger.info(f"Availability Engine Provider: {avail_engine.provider}")
    assert avail_engine.provider in REAL_REGISTRY_PROVIDERS, f"Engine provider {avail_engine.provider} not real!"

    pipeline = DomainHunterPipeline(router, http_client, avail_engine)

    try:
        run_res = await pipeline.run_domain_hunt(trigger="manual", geo="us")
        logger.info(f"Hunt Completed! Status: {run_res.get('status')}")

        scan_id = run_res.get("scan_id")
        stats = run_res.get("stats", {})
        results = run_res.get("results", [])

        print("\n" + "="*60)
        print("PRODUCTION DOMAIN HUNT SUMMARY REPORT")
        print("="*60)
        print(f"Scan ID: {scan_id}")
        print(f"Candidates Generated: {stats.get('total_generated', 0)}")
        print(f"Candidates Validated (Normalized): {stats.get('normalized_valid', 0)}")
        print(f"Availability Checked: {stats.get('availability_checked', 0)}")
        print(f"Registered (Rejected): {stats.get('availability_registered', 0)}")
        print(f"Available Standard: {stats.get('availability_standard', 0)}")
        print(f"Premium (Rejected): {stats.get('availability_premium', 0)}")
        print(f"Unknown / Failed: {stats.get('availability_unknown', 0)}")
        print(f"IP Screened: {stats.get('ip_screened', 0)}")
        print(f"IP Passed: {stats.get('ip_passed', 0)}")
        print(f"Final Opportunities: {len(results)}")
        print("="*60)

        # Provider distribution check across ALL final opportunities
        provider_counts = {}
        for r in results:
            prov = r.get("availability_provider")
            provider_counts[prov] = provider_counts.get(prov, 0) + 1

        print("FINAL OPPORTUNITIES PROVIDER DISTRIBUTION:")
        for prov, count in provider_counts.items():
            print(f"  {prov}: {count}")

        # Verification of hard invariants
        for r in results:
            d = r.get("domain")
            prov = r.get("availability_provider")
            status = r.get("availability_status")
            verified = r.get("availability_verified")
            prem = r.get("premium_status")
            is_reg = r.get("is_registered")

            assert prov != "test_mock_registry", f"FATAL: Mock provider on {d}!"
            assert prov in REAL_REGISTRY_PROVIDERS, f"FATAL: Non-real provider {prov} on {d}!"
            assert status == "AVAILABLE_STANDARD", f"FATAL: Non-available status {status} on {d}!"
            assert verified is True, f"FATAL: availability_verified is not True on {d}!"
            assert prem != "PREMIUM", f"FATAL: Premium domain {d} reached final results!"
            assert is_reg is False, f"FATAL: Registered domain {d} reached final results!"

        print("\nALL HARD SAFETY INVARIANTS SATISFIED!")
        print(f"Total verified available opportunities: {len(results)}")

        # Print top 15 domains with their details
        print("\nTOP VERIFIED OPPORTUNITIES:")
        for idx, r in enumerate(results[:15], 1):
            print(f"{idx}. {r.get('domain')} | Score: {r.get('overall_score')} | Provider: {r.get('availability_provider')} | Verified: {r.get('availability_verified')} | Status: {r.get('availability_status')}")

        # Save output json for reporting
        with open("live_hunt_results.json", "w", encoding="utf-8") as f:
            json.dump({
                "scan_id": scan_id,
                "stats": stats,
                "provider_counts": provider_counts,
                "results": results
            }, f, indent=2)

    finally:
        await http_client.aclose()
        await router.client.aclose()

if __name__ == "__main__":
    asyncio.run(main())
