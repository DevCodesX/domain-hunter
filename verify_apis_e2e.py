"""
End-to-End API Verification Script
Tests all existing and new API endpoints against FastAPI app.
"""

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_endpoints():
    print("Testing API Endpoints...")
    
    # 1. Health
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    print("✓ GET /api/health passed")

    # 2. Settings (includes Phase 1 & 2 configs)
    r = client.get("/api/settings")
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert "quality_engine" in data
    assert "risk_engine" in data
    assert data["quality_engine"]["weights"]["brandability"] == 0.18
    print("✓ GET /api/settings passed with Phase 1 & 2 configs")

    # 3. Quality Config
    r = client.get("/api/quality/config")
    assert r.status_code == 200
    q_data = r.json()
    assert q_data["success"] is True
    assert "weights" in q_data
    assert "strategy_targets" in q_data
    print("✓ GET /api/quality/config passed")

    # 4. Quality Stats
    r = client.get("/api/quality/stats")
    assert r.status_code == 200
    assert r.json()["success"] is True
    print("✓ GET /api/quality/stats passed")

    # 5. Domains Latest
    r = client.get("/api/domains/latest")
    assert r.status_code == 200
    print("✓ GET /api/domains/latest passed")

    # 6. Domains Status
    r = client.get("/api/domains/status")
    assert r.status_code == 200
    print("✓ GET /api/domains/status passed")

    # 7. Domains Research
    r = client.get("/api/domains/research")
    assert r.status_code == 200
    print("✓ GET /api/domains/research passed")

    # 8. Domains Generate
    r = client.get("/api/domains/generate")
    assert r.status_code == 200
    print("✓ GET /api/domains/generate passed")

    # 9. Detail endpoints (quality, risk, explanation)
    # Using an example domain from job_state.json or mock
    r_q = client.get("/api/domains/wagerbyte.com/quality")
    assert r_q.status_code in [200, 404]
    print(f"✓ GET /api/domains/wagerbyte.com/quality returned HTTP {r_q.status_code}")

    r_r = client.get("/api/domains/wagerbyte.com/risk")
    assert r_r.status_code in [200, 404]
    print(f"✓ GET /api/domains/wagerbyte.com/risk returned HTTP {r_r.status_code}")

    r_e = client.get("/api/domains/wagerbyte.com/explanation")
    assert r_e.status_code in [200, 404]
    print(f"✓ GET /api/domains/wagerbyte.com/explanation returned HTTP {r_e.status_code}")

    print("\nALL API ENDPOINTS TESTED SUCCESSFULLY!")

if __name__ == "__main__":
    test_endpoints()
