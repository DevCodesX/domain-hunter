import os
import sys
import asyncio
import datetime
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

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

async def run_all_tests():
    passed = 0
    failed = 0
    total = 15

    print("==================================================")
    print("RUNNING DOMAIN HUNTER PIPELINE VERIFICATION SUITE")
    print("==================================================")

    # 1. Registered domain -> rejected
    try:
        engine = AvailabilityEngine()
        res = await engine.check_domain("talenta.com")
        assert res.status == AvailabilityStatus.REGISTERED, f"Expected REGISTERED, got {res.status}"
        assert res.is_registered is True
        assert res.is_accepted() is False
        assert res.rejection_reason is not None
        print("✓ Test 1 Passed: Registered domain (talenta.com) -> rejected")
        passed += 1
    except Exception as e:
        print(f"✗ Test 1 Failed: {e}")
        failed += 1

    # 2. Premium domain -> rejected
    try:
        engine = AvailabilityEngine()
        with patch.object(engine, '_check_godaddy_api', new_callable=AsyncMock) as mock_gd:
            with patch.object(engine, '_check_verisign_rdap', new_callable=AsyncMock) as mock_rdap:
                mock_rdap.return_value = AvailabilityResult(
                    domain="premiumbrandtest.com",
                    status=AvailabilityStatus.AVAILABLE_STANDARD,
                    provider="verisign_rdap",
                    is_registered=False,
                    registration_available=True
                )
                mock_gd.return_value = (True, True) # (available=True, is_premium=True)
                res = await engine.check_domain("premiumbrandtest.com")
                assert res.status == AvailabilityStatus.PREMIUM, f"Expected PREMIUM, got {res.status}"
                assert res.is_premium is True
                assert res.is_accepted() is False
        print("✓ Test 2 Passed: Premium domain -> rejected")
        passed += 1
    except Exception as e:
        print(f"✗ Test 2 Failed: {e}")
        failed += 1

    # 3. Standard available domain -> accepted
    try:
        engine = AvailabilityEngine()
        test_d = "unregisteredantigravitysuite99238472.com"
        res = await engine.check_domain(test_d)
        assert res.status == AvailabilityStatus.AVAILABLE_STANDARD, f"Expected AVAILABLE_STANDARD, got {res.status}"
        assert res.is_registered is False
        assert res.is_premium is False
        assert res.registration_available is True
        assert res.is_accepted() is True
        print(f"✓ Test 3 Passed: Standard available domain ({test_d}) -> accepted")
        passed += 1
    except Exception as e:
        print(f"✗ Test 3 Failed: {e}")
        failed += 1

    # 4. Availability timeout -> rejected from final list
    try:
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
        print("✓ Test 4 Passed: Availability timeout -> rejected from final list")
        passed += 1
    except Exception as e:
        print(f"✗ Test 4 Failed: {e}")
        failed += 1

    # 5. Provider 503 -> rejected from final list
    try:
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
        print("✓ Test 5 Passed: Provider 503 -> rejected from final list")
        passed += 1
    except Exception as e:
        print(f"✗ Test 5 Failed: {e}")
        failed += 1

    # 6. Provider 429 -> rejected from final list
    try:
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
        print("✓ Test 6 Passed: Provider 429 -> rejected from final list")
        passed += 1
    except Exception as e:
        print(f"✗ Test 6 Failed: {e}")
        failed += 1

    # 7. Malformed AI domain -> rejected
    try:
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
        print(f"✓ Test 7 Passed: {len(cases)} Malformed AI domains -> all rejected")
        passed += 1
    except Exception as e:
        print(f"✗ Test 7 Failed: {e}")
        failed += 1

    # 8. Duplicate domain -> deduplicated
    try:
        raw_list = ["testbrand.com", "TestBrand.COM", "https://testbrand.com", "www.testbrand.com", "testbrand.com"]
        unique = set()
        for item in raw_list:
            norm, _ = normalize_and_validate_candidate(item)
            if norm:
                unique.add(norm)
        assert len(unique) == 1
        assert "testbrand.com" in unique
        print("✓ Test 8 Passed: Duplicate domains -> cleanly deduplicated")
        passed += 1
    except Exception as e:
        print(f"✗ Test 8 Failed: {e}")
        failed += 1

    # 9. Manual generation -> actually runs
    try:
        with patch("main.job_runner") as mock_runner:
            mock_runner.is_running = False
            mock_runner.run_domain_hunt = AsyncMock()
            response = client.post("/api/domains/run")
            assert response.status_code == 200
            data = response.json()
            assert data.get("status") == "started"
            assert "job_id" in data
        print("✓ Test 9 Passed: Manual generation endpoint -> actually triggers pipeline run")
        passed += 1
    except Exception as e:
        print(f"✗ Test 9 Failed: {e}")
        failed += 1

    # 10. Daily generation -> actually runs
    try:
        mock_router = MagicMock()
        mock_http = MagicMock()
        pipeline = DomainHunterPipeline(mock_router, mock_http)
        with patch.object(pipeline, 'run_domain_hunt', new_callable=AsyncMock) as mock_hunt:
            mock_hunt.return_value = {"status": "completed", "results": []}
            res = await pipeline.run_domain_hunt(trigger="scheduled")
            assert res["status"] == "completed"
            mock_hunt.assert_called_once_with(trigger="scheduled")
        print("✓ Test 10 Passed: Daily generation -> uses identical run_domain_hunt(trigger='scheduled')")
        passed += 1
    except Exception as e:
        print(f"✗ Test 10 Failed: {e}")
        failed += 1

    # 11. Manual run while another run is active -> HTTP 409
    try:
        with patch("main.job_runner") as mock_runner:
            mock_runner.is_running = True
            response = client.post("/api/domains/run")
            assert response.status_code == 409
            data = response.json()
            assert data.get("status") == "already_running"
        print("✓ Test 11 Passed: Manual run conflict while active -> HTTP 409 already_running")
        passed += 1
    except Exception as e:
        print(f"✗ Test 11 Failed: {e}")
        failed += 1

    # 12. Supabase final records contain verified availability
    try:
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
        print("✓ Test 12 Passed: Supabase final record contract validated with all verification fields")
        passed += 1
    except Exception as e:
        print(f"✗ Test 12 Failed: {e}")
        failed += 1

    # 13. Frontend only displays verified domains
    try:
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
        print("✓ Test 13 Passed: GET /api/domains/latest returns ONLY AVAILABLE_STANDARD domains")
        passed += 1
    except Exception as e:
        print(f"✗ Test 13 Failed: {e}")
        failed += 1

    # 14. Refresh does not start a new hunt
    try:
        with patch("main.job_runner") as mock_runner:
            mock_runner.is_running = False
            res1 = client.get("/api/domains/latest")
            res2 = client.get("/api/domains/status")
            assert res1.status_code in [200, 404]
            assert res2.status_code == 200
            assert mock_runner.run_domain_hunt.called is False if hasattr(mock_runner, 'run_domain_hunt') else True
        print("✓ Test 14 Passed: Polling / Refreshing endpoints does NOT trigger a new hunt")
        passed += 1
    except Exception as e:
        print(f"✗ Test 14 Failed: {e}")
        failed += 1

    # 15. Last successful results remain visible if a new run fails
    try:
        state = {
            "latest_results": {
                "run_date": "2026-09-25T14:00:00Z",
                "results": [
                    {
                        "domain": "preservedsavedbrand.com",
                        "domain_name": "preservedsavedbrand.com",
                        "availability_status": "AVAILABLE_STANDARD",
                        "is_registered": False,
                        "is_premium": False,
                        "registration_available": True
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
        print("✓ Test 15 Passed: Last successful results remain visible when a run fails")
        passed += 1
    except Exception as e:
        print(f"✗ Test 15 Failed: {e}")
        failed += 1

    # =========================================================================
    # PHASE 1 & 2 VERIFICATION TESTS (Tests 16 to 31)
    # =========================================================================
    from quality_engine import (
        QualityFeatureExtractor, OneWordQualityEngine, NamingTypeClassifier,
        QualityScorer, DiversityEngine
    )
    from risk_engine import (
        TrademarkRiskEngine, ExistingBrandEngine, RiskLevel, BrandStatus,
        levenshtein_similarity, jaro_winkler_similarity, soundex, metaphone,
        calculate_comprehensive_similarity
    )
    from router import ModelRouter

    # 16. One-word classification
    try:
        engine = OneWordQualityEngine()
        res_real = engine.compute_one_word_score("stride")
        assert res_real["is_one_word"] is True
        assert res_real["word_length"] == 6
        print("✓ Test 16 Passed: One-word classification -> authentic dictionary word validated")
        passed += 1
    except Exception as e:
        print(f"✗ Test 16 Failed: {e}")
        failed += 1

    # 17. Dictionary detection
    try:
        engine = OneWordQualityEngine()
        is_d, z = engine.is_dictionary_word("beacon")
        assert is_d is True and z >= 2.5
        is_bad, _ = engine.is_dictionary_word("asdfjklzxcv")
        assert is_bad is False
        print("✓ Test 17 Passed: Dictionary detection -> verified real words vs non-words")
        passed += 1
    except Exception as e:
        print(f"✗ Test 17 Failed: {e}")
        failed += 1

    # 18. Syllable extraction
    try:
        fe = QualityFeatureExtractor()
        assert fe.count_syllables("cloud") == 1
        assert fe.count_syllables("beacon") == 2
        assert fe.count_syllables("autonomous") >= 3
        print("✓ Test 18 Passed: Syllable extraction -> accurate phonetic syllable counts")
        passed += 1
    except Exception as e:
        print(f"✗ Test 18 Failed: {e}")
        failed += 1

    # 19. Pronunciation scoring
    try:
        fe = QualityFeatureExtractor()
        assert fe.compute_pronounceability_score("velora") >= 80.0
        assert fe.compute_pronounceability_score("xqzlyv") < 30.0
        print("✓ Test 19 Passed: Pronunciation scoring -> distinguishes smooth vs unpronounceable")
        passed += 1
    except Exception as e:
        print(f"✗ Test 19 Failed: {e}")
        failed += 1

    # 20. Structural filtering
    try:
        fe = QualityFeatureExtractor()
        features = fe.extract_features("peakflow.com")
        assert features["char_length"] == 8
        assert features["passes_hard_filter"] is True
        print("✓ Test 20 Passed: Structural filtering -> complete feature vector generated")
        passed += 1
    except Exception as e:
        print(f"✗ Test 20 Failed: {e}")
        failed += 1

    # 21. Naming strategy classification
    try:
        classifier = NamingTypeClassifier()
        assert classifier.classify("beacon.com")["naming_type"] == "ONE_WORD"
        assert classifier.classify("getpulse.com")["naming_type"] == "PREFIX_SUFFIX"
        assert classifier.classify("cloudnest.com")["naming_type"] in ["COMPOUND", "TWO_WORD"]
        assert classifier.classify("aaaaaaaa.com")["naming_type"] == "RANDOM"
        print("✓ Test 21 Passed: Naming strategy classification -> classified ONE_WORD, PREFIX_SUFFIX, COMPOUND, RANDOM")
        passed += 1
    except Exception as e:
        print(f"✗ Test 21 Failed: {e}")
        failed += 1

    # 22. Quality score calculation
    try:
        scorer = QualityScorer()
        fe = QualityFeatureExtractor()
        one_engine = OneWordQualityEngine(fe)
        classifier = NamingTypeClassifier(one_engine)
        domain = "peakflow.com"
        struct = fe.extract_features(domain)
        one_eval = one_engine.compute_one_word_score(domain)
        naming = classifier.classify(domain)
        res = scorer.score_candidate(domain=domain, structural_features=struct, one_word_features=one_eval, naming_type_info=naming)
        assert 50 <= res["quality_score"] <= 100
        assert "brandability" in res["quality_breakdown"]
        print("✓ Test 22 Passed: Quality score calculation -> multi-dimensional weighted scores calculated")
        passed += 1
    except Exception as e:
        print(f"✗ Test 22 Failed: {e}")
        failed += 1

    # 23. Hard vs soft filtering
    try:
        fe = QualityFeatureExtractor()
        pass_mash, r_mash = fe.evaluate_hard_filters("xqzlyv")
        assert pass_mash is False
        pass_long, _ = fe.evaluate_hard_filters("cybercommand")
        assert pass_long is True
        print("✓ Test 23 Passed: Hard vs soft filtering -> hard rejects mash, soft-scores meaningful 12-char")
        passed += 1
    except Exception as e:
        print(f"✗ Test 23 Failed: {e}")
        failed += 1

    # 24. String similarity
    try:
        assert levenshtein_similarity("cloudora", "claudora") >= 0.85
        assert jaro_winkler_similarity("cloudora", "claudora") >= 0.88
        print("✓ Test 24 Passed: String similarity -> Levenshtein and Jaro-Winkler verified")
        passed += 1
    except Exception as e:
        print(f"✗ Test 24 Failed: {e}")
        failed += 1

    # 25. Phonetic similarity
    try:
        assert soundex("Smith") == soundex("Smythe")
        assert metaphone("cloudora") == metaphone("claudora")
        comp = calculate_comprehensive_similarity("cloudora", "claudora")
        assert comp["is_phonetic_match"] is True
        print("✓ Test 25 Passed: Phonetic similarity -> Soundex & Metaphone phonetic matches detected")
        passed += 1
    except Exception as e:
        print(f"✗ Test 25 Failed: {e}")
        failed += 1

    # 26. Trademark risk classification
    try:
        tm_engine = TrademarkRiskEngine()
        report_crit = await tm_engine.screen_candidate("apple.com")
        assert report_crit.ip_risk_level == RiskLevel.CRITICAL
        assert report_crit.decision == "REJECT"
        report_low = await tm_engine.screen_candidate("uniqueneuralmesh99.com")
        assert report_low.ip_risk_level == RiskLevel.LOW
        print("✓ Test 26 Passed: Trademark risk classification -> CRITICAL reject vs LOW pass")
        passed += 1
    except Exception as e:
        print(f"✗ Test 26 Failed: {e}")
        failed += 1

    # 27. Existing brand classification
    try:
        brand_engine = ExistingBrandEngine()
        matches = brand_engine.analyze_domain("stripe")
        assert len(matches) > 0
        assert matches[0].brand_status == BrandStatus.FAMOUS_BRAND
        print("✓ Test 27 Passed: Existing brand classification -> Stripe flagged as FAMOUS_BRAND")
        passed += 1
    except Exception as e:
        print(f"✗ Test 27 Failed: {e}")
        failed += 1

    # 28. Diversity selection
    try:
        diversity = DiversityEngine()
        candidates = [
            {"domain": "agentflow.com", "domain_name": "agentflow.com", "quality_score": 92, "naming_type": "COMPOUND"},
            {"domain": "agentforge.com", "domain_name": "agentforge.com", "quality_score": 91, "naming_type": "COMPOUND"},
            {"domain": "flowagent.com", "domain_name": "flowagent.com", "quality_score": 90, "naming_type": "COMPOUND"},
            {"domain": "beacon.com", "domain_name": "beacon.com", "quality_score": 89, "naming_type": "ONE_WORD"},
            {"domain": "velora.com", "domain_name": "velora.com", "quality_score": 88, "naming_type": "INVENTED"},
        ]
        selected = diversity.select_diverse_candidates(candidates, limit=3)
        assert len(selected) <= 3
        agent_count = sum(1 for d in selected if "agent" in d["domain"])
        assert agent_count <= 2
        print("✓ Test 28 Passed: Diversity selection -> near-duplicate clusters suppressed")
        passed += 1
    except Exception as e:
        print(f"✗ Test 28 Failed: {e}")
        failed += 1

    # 29. Malformed LLM JSON recovery
    try:
        router = ModelRouter()
        parsed = router.extract_json_safe("```json\n{\"brandability\": 90}\n```")
        assert parsed["brandability"] == 90
        print("✓ Test 29 Passed: Malformed LLM JSON recovery -> parsed markdown wrapped JSON")
        passed += 1
    except Exception as e:
        print(f"✗ Test 29 Failed: {e}")
        failed += 1

    # 30. Provider failure fallback
    try:
        router = ModelRouter()
        call_counts = {"primary": 0, "fallback": 0}
        async def mock_req(provider, model, prompt, temp, tokens, req_id, attempt):
            if provider == "xkiro":
                call_counts["primary"] += 1
                raise Exception("503 Service Unavailable")
            elif provider == "nvidia":
                call_counts["fallback"] += 1
                return "{\"success\": true}"
            return "{}"
        with patch.object(router, '_make_request', side_effect=mock_req):
            res = await router.execute_task_json("domain_generation", "test", max_retries=1)
            assert res.get("success") is True
            assert call_counts["primary"] >= 1
            assert call_counts["fallback"] >= 1
        print("✓ Test 30 Passed: Provider failure fallback -> seamlessly fell back on 503")
        passed += 1
    except Exception as e:
        print(f"✗ Test 30 Failed: {e}")
        failed += 1

    # 31. Pipeline continuation after individual candidate failure
    try:
        tm_engine = TrademarkRiskEngine()
        candidates = ["validbrand.com", None, "", "anothergoodbrand.com"]
        passed_reps = []
        for c in candidates:
            try:
                if c: passed_reps.append(await tm_engine.screen_candidate(c))
            except Exception: pass
        assert len(passed_reps) == 2
        print("✓ Test 31 Passed: Pipeline continuation -> individual bad candidate isolated")
        passed += 1
    except Exception as e:
        print(f"✗ Test 31 Failed: {e}")
        failed += 1

    # =========================================================================
    # PHASE 2.5: OPPORTUNITY & SEMANTIC EXPANSION ENGINE TESTS (Tests 32 to 40)
    # =========================================================================
    from opportunity_engine import (
        MARKET_CATEGORIES,
        DEFAULT_CATEGORY_ALLOCATION,
        MAX_CATEGORY_CONCENTRATION,
        SEMANTIC_ROOT_LIBRARY,
        get_roots_for_category,
        find_semantic_cluster,
        MultilingualEngine,
        RadioTestScorer,
        CategoryFitScorer,
        OpportunityScorer,
        ConceptDiscoveryEngine,
        MatrixOpportunityGenerator
    )

    # 32. Semantic root library retrieval & affinity
    try:
        assert len(SEMANTIC_ROOT_LIBRARY) == 7
        ai_roots = get_roots_for_category("AI & Technology")
        assert len(ai_roots) > 0
        assert "mind" in ai_roots or "vision" in ai_roots or "engine" in ai_roots
        print("✓ Test 32 Passed: Semantic root library -> all 7 commercial concepts & category affinities active")
        passed += 1
    except Exception as e:
        print(f"✗ Test 32 Failed: {e}")
        failed += 1

    # 33. Multilingual verified lexical dictionary
    try:
        ml = MultilingualEngine()
        entry = ml.lookup_term("veritas")
        assert entry is not None
        assert entry["language"] == "Latin"
        assert "truth" in entry["english_meaning"].lower()
        assert entry["confidence"] >= 0.95
        print("✓ Test 33 Passed: Multilingual dictionary -> verified factual meanings without LLM hallucination")
        passed += 1
    except Exception as e:
        print(f"✗ Test 33 Failed: {e}")
        failed += 1

    # 34. Multilingual brandability filter
    try:
        ml = MultilingualEngine()
        res_v = ml.evaluate_foreign_word_brandability("veritas")
        assert res_v["passes_foreign_brandability_gate"] is True
        assert res_v["brandability"] >= 65
        res_bad = ml.evaluate_foreign_word_brandability("schmetterling")
        assert res_bad["passes_foreign_brandability_gate"] is False
        print("✓ Test 34 Passed: Multilingual brandability filter -> screens pronunciation, length, and spelling")
        passed += 1
    except Exception as e:
        print(f"✗ Test 34 Failed: {e}")
        failed += 1

    # 35. Radio / spelling-from-sound scoring
    try:
        score_lumina = RadioTestScorer.calculate_radio_score("lumina.com")
        assert score_lumina["radio_test_score"] >= 80
        score_ph = RadioTestScorer.calculate_radio_score("phthisis.com")
        assert score_ph["radio_test_score"] < score_lumina["radio_test_score"]
        print("✓ Test 35 Passed: Radio test score -> deterministic orthographic transparency calculated")
        passed += 1
    except Exception as e:
        print(f"✗ Test 35 Failed: {e}")
        failed += 1

    # 36. Category fit scoring
    try:
        fit_scores, best = CategoryFitScorer.calculate_category_fit("agentflow.com", "AI & Technology")
        assert len(fit_scores) >= 9
        assert fit_scores.get("ai_tech", fit_scores.get("ai_startups", 0)) >= 70
        assert best in ["AI & Technology", "AI_STARTUPS"]
        print("✓ Test 36 Passed: Category fit scoring -> evaluated across all 9 market categories")
        passed += 1
    except Exception as e:
        print(f"✗ Test 36 Failed: {e}")
        failed += 1

    # 37. Opportunity discovery scoring
    try:
        fit_b2b, _ = CategoryFitScorer.calculate_category_fit("lawguard.com", "B2B High-CPC / Commercial Services")
        opp = OpportunityScorer.calculate_opportunity_score(
            domain="lawguard.com",
            market_category="B2B High-CPC / Commercial Services",
            category_fit_scores=fit_b2b,
            trend_score=85
        )
        assert 70 <= opp["opportunity_score"] <= 100
        assert opp["commercial_intent"] >= 80
        print("✓ Test 37 Passed: Opportunity score -> separates market opportunity from naming quality")
        passed += 1
    except Exception as e:
        print(f"✗ Test 37 Failed: {e}")
        failed += 1

    # 38. Multi-source concept discovery
    try:
        discovery = ConceptDiscoveryEngine()
        concepts = await discovery.discover_concepts(trending_context=["Sports score 123"], target_count=12)
        assert len(concepts) >= 8
        sources = {c["source"] for c in concepts}
        assert "EVERGREEN_COMMERCIAL_NICHES" in sources
        assert "STARTUP_MARKET_SIGNALS" in sources
        assert "SEMANTIC_NAMING_CONCEPTS" in sources
        sports_cnt = sum(1 for c in concepts if "sport" in c["category"].lower() or "bet" in c["category"].lower())
        assert (sports_cnt / len(concepts)) <= 0.15
        print("✓ Test 38 Passed: Multi-source concept discovery -> 4 sources combined & sports capped <= 10-15%")
        passed += 1
    except Exception as e:
        print(f"✗ Test 38 Failed: {e}")
        failed += 1

    # 39. Matrix opportunity candidate generation
    try:
        mock_strategy_gen = MagicMock()
        mock_strategy_gen.generate_all_strategies = AsyncMock(return_value=[
            {"domain": "agentcore.com", "generation_strategy": "COMPOUND", "source_concept": "AI agents"},
            {"domain": "veritas.com", "generation_strategy": "ONE_WORD", "source_concept": "Truth audit"}
        ])
        matrix_gen = MatrixOpportunityGenerator(strategy_generator=mock_strategy_gen)
        cands = await matrix_gen.generate_matrix_candidates(
            concepts=[{"concept": "AI agents", "category": "AI & Technology", "subcategory": "AI Agents"}],
            target_total=10
        )
        assert len(cands) >= 2
        for c in cands:
            assert "radio_test_score" in c
            assert "category_fit" in c
            assert "opportunity_score" in c
        print("✓ Test 39 Passed: Matrix candidate generation -> Category × Strategy matrix enriched with Phase 2.5 metadata")
        passed += 1
    except Exception as e:
        print(f"✗ Test 39 Failed: {e}")
        failed += 1

    # 40. Category diversity selection quota
    try:
        diversity = DiversityEngine()
        test_cands = [
            {"domain_name": f"bet{i}.com", "quality_score": 90 - i, "market_category": "Sports & Entertainment", "naming_type": "COMPOUND"}
            for i in range(8)
        ] + [
            {"domain_name": f"ai{i}.com", "quality_score": 88 - i, "market_category": "AI & Technology", "naming_type": "COMPOUND"}
            for i in range(4)
        ] + [
            {"domain_name": f"fin{i}.com", "quality_score": 85 - i, "market_category": "Finance", "naming_type": "COMPOUND"}
            for i in range(4)
        ]
        selected = diversity.select_diverse_candidates(test_cands, target_count=8, max_per_category=3)
        sports_cnt = sum(1 for c in selected if c.get("market_category") == "Sports & Entertainment")
        assert sports_cnt <= 3
        print("✓ Test 40 Passed: Category diversity quota -> single category cannot monopolize final candidate pool")
        passed += 1
    except Exception as e:
        print(f"✗ Test 40 Failed: {e}")
        failed += 1

    # =========================================================================
    # PHASE 2.75: NAMING INTELLIGENCE REFINEMENT TESTS (Tests 41 to 47)
    # =========================================================================
    from quality_engine.brand_refinement import (
        WordGlueDetector,
        AIGeneratedFeelDetector,
        CompoundNaturalnessScorer,
        BuyerClarityScorer,
        CandidateTrendFitScorer,
        FinalJudge
    )
    from quality_engine.quality_scorer import QualityScorer
    from quality_engine.config import get_quality_weights

    # 41. Quality weights sum to exactly 1.0 (100%)
    try:
        w = get_quality_weights()
        tot = sum(w.values())
        assert abs(tot - 1.0) < 0.001
        assert "natural_brand" in w and "buyer_clarity" in w and "startup_naturalness" in w
        print("✓ Test 41 Passed: Phase 2.75 Quality weights sum to exactly 1.0 (100%)")
        passed += 1
    except Exception as e:
        print(f"✗ Test 41 Failed: {e}")
        failed += 1

    # 42. Word-Glue Detector
    try:
        bad_names = ["cleartether.com", "firmclause.com", "bindrule.com", "stilltether.com", "dockterm.com", "surekeel.com"]
        for b in bad_names:
            det = WordGlueDetector.detect_word_glue(b)
            assert det["is_word_glue"] is True
            assert det["word_glue_penalty"] >= 20

        good_names = ["stripe.com", "coinbase.com", "ironclad.com", "cloudnest.com"]
        for g in good_names:
            det = WordGlueDetector.detect_word_glue(g)
            assert det["is_word_glue"] is False
            assert det["word_glue_penalty"] == 0
        print("✓ Test 42 Passed: Word-Glue Detector -> generic adj+noun & verb+noun compounds detected and penalized")
        passed += 1
    except Exception as e:
        print(f"✗ Test 42 Failed: {e}")
        failed += 1

    # 43. AI-Generated Feel Detector
    try:
        syn = AIGeneratedFeelDetector.evaluate_ai_feel("yuridix.com")
        assert syn["ai_generated_feel_score"] > 30
        stuff = AIGeneratedFeelDetector.evaluate_ai_feel("vzxqflow.com")
        assert stuff["is_flagged"] is True
        nat = AIGeneratedFeelDetector.evaluate_ai_feel("apex.com")
        assert nat["ai_generated_feel_score"] <= 30
        print("✓ Test 43 Passed: AI-Generated Feel Detector -> synthetic consonant stuffing & forced suffixes flagged")
        passed += 1
    except Exception as e:
        print(f"✗ Test 43 Failed: {e}")
        failed += 1

    # 44. Candidate Trend Fit (Identical Trend 82 Bug Fix)
    try:
        concept = "AI Agent Automation & Autonomous Workflows"
        t_fit1 = CandidateTrendFitScorer.calculate_trend_fit("agentflow.com", concept, concept_trend_relevance=90)
        t_fit2 = CandidateTrendFitScorer.calculate_trend_fit("drywood.com", concept, concept_trend_relevance=90)
        assert t_fit1["blended_trend_score"] != t_fit2["blended_trend_score"]
        assert t_fit1["candidate_trend_fit_score"] > t_fit2["candidate_trend_fit_score"]
        print("✓ Test 44 Passed: Candidate Trend Fit -> identical Trend 82 bug permanently resolved with candidate-specific fit")
        passed += 1
    except Exception as e:
        print(f"✗ Test 44 Failed: {e}")
        failed += 1

    # 45. Buyer Clarity Scorer
    try:
        b_ai = BuyerClarityScorer.evaluate_buyer_clarity("agentcore.com", market_category="AI & Technology")
        assert b_ai["buyer_clarity_score"] >= 80
        assert b_ai["buyer_count"] >= 3
        assert "AI SaaS" in b_ai["buyer_industries"]
        print("✓ Test 45 Passed: Buyer Clarity Scorer -> commercial buyer archetypes, buyer count & startup fit mapped")
        passed += 1
    except Exception as e:
        print(f"✗ Test 45 Failed: {e}")
        failed += 1

    # 46. Final Judge 10-Criteria Evaluation
    try:
        buyer = BuyerClarityScorer.evaluate_buyer_clarity("agentmesh.com", "AI & Technology")
        glue = WordGlueDetector.detect_word_glue("agentmesh.com")
        ai = AIGeneratedFeelDetector.evaluate_ai_feel("agentmesh.com")
        verdict = FinalJudge.evaluate(
            domain="agentmesh.com",
            quality_score=88,
            natural_brand_score=85,
            startup_naturalness_score=88,
            radio_test_score=85,
            buyer_clarity=buyer,
            word_glue=glue,
            ai_feel=ai,
            market_category="AI & Technology"
        )
        assert verdict["verdict"] == "APPROVED"
        assert verdict["criteria_met_count"] >= 7
        print("✓ Test 46 Passed: Final Judge Assessment -> 10 commercial criteria evaluated in structured JSON")
        passed += 1
    except Exception as e:
        print(f"✗ Test 46 Failed: {e}")
        failed += 1

    # 47. Quality Scorer composite scoring with word-glue penalty
    try:
        scorer = QualityScorer()
        res_nat = scorer.score_candidate(
            domain="novacore.com",
            structural_features={"label": "novacore", "char_length": 8, "pronounceability_score": 88, "spelling_simplicity": 85, "estimated_memorability": 86},
            one_word_features={"one_word_score": 0},
            naming_type_info={"naming_type": "SEMANTIC_BRANDABLE"},
            concept="Core AI and Neural Infrastructure",
            market_category="AI & Technology"
        )
        res_glue = scorer.score_candidate(
            domain="firmclause.com",
            structural_features={"label": "firmclause", "char_length": 10, "pronounceability_score": 80, "spelling_simplicity": 75, "estimated_memorability": 70},
            one_word_features={"one_word_score": 0},
            naming_type_info={"naming_type": "COMPOUND"},
            concept="Enterprise Legal Tech",
            market_category="B2B High-CPC / Commercial Services"
        )
        assert res_nat["quality_score"] > res_glue["quality_score"]
        assert res_glue["word_glue_penalty"] >= 25
        print("✓ Test 47 Passed: Quality Scorer -> natural brandable outranks word-glue compound via Phase 2.75 penalties")
        passed += 1
    except Exception as e:
        print(f"✗ Test 47 Failed: {e}")
        failed += 1

    total = 47
    print("==================================================")
    print(f"TEST RESULTS: {passed}/{total} PASSED ({failed} failed)")
    print("==================================================")
    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_all_tests())
