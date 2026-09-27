import os
import time
import json
import httpx
import asyncio
from typing import List, Dict, Any, Optional
import uuid
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ModelRouter")

class ModelIntelligenceLayer:
    def __init__(self):
        self.stats = {}
        
    def record_usage(self, provider: str, model: str, latency: float, success: bool, error_msg: str = None):
        key = f"{provider}:{model}"
        if key not in self.stats:
            self.stats[key] = {
                "success_count": 0,
                "fail_count": 0,
                "consecutive_failures": 0,
                "total_latency": 0.0,
                "avg_latency": 0.0,
                "reliability": 100.0,
                "status": "healthy",
                "cooldown_until": 0,
                "last_error": None
            }
        
        stat = self.stats[key]
        if success:
            stat["success_count"] += 1
            stat["consecutive_failures"] = 0
            stat["total_latency"] += latency
            stat["status"] = "healthy"
            stat["cooldown_until"] = 0
        else:
            stat["fail_count"] += 1
            stat["consecutive_failures"] += 1
            stat["last_error"] = error_msg
            
            if stat["consecutive_failures"] >= 3:
                stat["status"] = "temporarily_unavailable"
                stat["cooldown_until"] = time.time() + int(os.getenv("PROVIDER_COOLDOWN_SECONDS", "1800"))
                logger.warning(f"[CIRCUIT-BREAKER] {key} marked unavailable until {stat['cooldown_until']}")
            
        total_calls = stat["success_count"] + stat["fail_count"]
        stat["reliability"] = (stat["success_count"] / total_calls) * 100
        if stat["success_count"] > 0:
            stat["avg_latency"] = stat["total_latency"] / stat["success_count"]

    def is_model_available(self, provider: str, model: str) -> bool:
        key = f"{provider}:{model}"
        if key not in self.stats:
            return True
        stat = self.stats[key]
        if stat["status"] == "temporarily_unavailable":
            if time.time() > stat["cooldown_until"]:
                return True # Half-open
            return False
        return True

    def get_model_score(self, provider: str, model: str) -> float:
        key = f"{provider}:{model}"
        if key not in self.stats:
            return 100.0 
        stat = self.stats[key]
        if not self.is_model_available(provider, model):
            return -100.0 # Push to back of queue
            
        reliability = stat["reliability"]
        avg_latency = stat["avg_latency"]
        latency_score = max(0, 100 - (avg_latency * 5)) 
        return (reliability * 0.7) + (latency_score * 0.3)
        
    def get_providers_health(self):
        providers = {}
        for key, stat in self.stats.items():
            provider = key.split(":")[0]
            if provider not in providers:
                providers[provider] = {"status": "healthy", "models": {}}
            providers[provider]["models"][key] = {
                "status": stat["status"],
                "reliability": round(stat["reliability"], 2),
                "avg_latency": round(stat["avg_latency"], 2),
                "last_error": stat["last_error"],
                "cooldown_until": stat["cooldown_until"] if stat["cooldown_until"] > time.time() else None
            }
            if stat["status"] == "temporarily_unavailable" and providers[provider]["status"] == "healthy":
                providers[provider]["status"] = "degraded"
        return providers

class ModelRouter:
    def __init__(self):
        self.intelligence = ModelIntelligenceLayer()
        self.providers = {
            "nvidia": {
                "base_url": "https://integrate.api.nvidia.com/v1",
                "api_key": os.getenv("NVIDIA_API_KEY")
            },
            "xkiro": {
                "base_url": "https://api.xkiro.com/v1",
                "api_key": os.getenv("XKIRO_API_KEY")
            },
            "openrouter": {
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": os.getenv("OPENROUTER_API_KEY")
            }
        }
        
        self.semaphores = {
            "nvidia": asyncio.Semaphore(int(os.getenv("NVIDIA_CONCURRENCY", "5"))),
            "xkiro": asyncio.Semaphore(int(os.getenv("XKIRO_CONCURRENCY", "5"))),
            "openrouter": asyncio.Semaphore(int(os.getenv("OPENROUTER_CONCURRENCY", "5"))),
        }
        
        self.task_profiles = {
            "trend_research": [
                {"provider": "nvidia", "model": "nvidia/nemotron-3-super-120b-a12b"},
                {"provider": "xkiro", "model": "qwen/qwen3.8-max:free"}
            ],
            "domain_generation": [
                {"provider": "xkiro", "model": "qwen/qwen3.8-max:free"},
                {"provider": "nvidia", "model": "deepseek-ai/deepseek-v4.1-flash"}
            ],
            "naming_generator": [
                {"provider": "xkiro", "model": "qwen/qwen3.8-max:free"},
                {"provider": "nvidia", "model": "deepseek-ai/deepseek-v4.1-flash"}
            ],
            "brandability": [
                {"provider": "nvidia", "model": "glm-5.3-flash"},
                {"provider": "nvidia", "model": "deepseek-ai/deepseek-v4.1-flash"},
                {"provider": "xkiro", "model": "qwen/qwen3.8-max:free"}
            ],
            "quality_evaluator": [
                {"provider": "nvidia", "model": "glm-5.3-flash"},
                {"provider": "nvidia", "model": "deepseek-ai/deepseek-v4.1-flash"},
                {"provider": "xkiro", "model": "qwen/qwen3.8-max:free"}
            ],
            "commercial_evaluator": [
                {"provider": "nvidia", "model": "deepseek-ai/deepseek-v4.1-flash"},
                {"provider": "xkiro", "model": "qwen/qwen3.8-max:free"}
            ],
            "final_judge": [
                {"provider": "nvidia", "model": "deepseek-ai/deepseek-v4.1-flash"},
                {"provider": "xkiro", "model": "qwen/qwen3.8-max:free"}
            ]
        }
        self.client = httpx.AsyncClient(timeout=30.0)

    async def _make_request(self, provider: str, model: str, prompt: str, temperature: float, max_tokens: int, req_id: str, attempt: int) -> str:
        if not self.intelligence.is_model_available(provider, model):
            raise Exception(f"Model {model} on {provider} is temporarily unavailable (circuit breaker open).")
            
        prov_info = self.providers.get(provider)
        if not prov_info or not prov_info["api_key"] or prov_info["api_key"].startswith("ضع"):
            raise ValueError(f"Provider {provider} API Key missing or invalid")
            
        url = f"{prov_info['base_url']}/chat/completions"
        headers = {
            "Authorization": f"Bearer {prov_info['api_key']}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        semaphore = self.semaphores.get(provider, asyncio.Semaphore(1))
        async with semaphore:
            start_time = time.time()
            try:
                response = await self.client.post(url, headers=headers, json=payload)
                latency = time.time() - start_time
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                
                logger.info(f"[AI-REQ] id={req_id} task=inference provider={provider} model={model} attempt={attempt} status={response.status_code} latency={latency:.2f}s len={len(content)}")
                self.intelligence.record_usage(provider, model, latency, success=True)
                return content
            except httpx.HTTPStatusError as e:
                latency = time.time() - start_time
                err_str = str(e.response.status_code)
                self.intelligence.record_usage(provider, model, latency, success=False, error_msg=err_str)
                logger.error(f"[AI-REQ-FAIL] id={req_id} provider={provider} model={model} attempt={attempt} status={err_str} latency={latency:.2f}s")
                
                if e.response.status_code in [429, 500, 502, 503, 504]:
                    await asyncio.sleep(min(2 ** attempt, 15))
                raise e
            except Exception as e:
                latency = time.time() - start_time
                err_str = str(e)
                self.intelligence.record_usage(provider, model, latency, success=False, error_msg=err_str)
                logger.error(f"[AI-REQ-FAIL] id={req_id} provider={provider} model={model} attempt={attempt} err={err_str}")
                raise e

    async def execute_task(self, task: str, prompt: str, temperature: float = 0.7, max_tokens: int = 1024, max_retries: int = 2) -> str:
        profiles = self.task_profiles.get(task)
        if not profiles:
            raise ValueError(f"Unknown task profile: {task}")
            
        profiles = sorted(profiles, key=lambda p: self.intelligence.get_model_score(p["provider"], p["model"]), reverse=True)
        req_id = str(uuid.uuid4())[:8]
        errors = []
        
        for profile in profiles:
            provider = profile["provider"]
            model = profile["model"]
            
            for attempt in range(max_retries):
                try:
                    content = await self._make_request(provider, model, prompt, temperature, max_tokens, req_id, attempt)
                    return content
                except Exception as e:
                    errors.append(f"{provider}/{model}: {str(e)}")
                    if "temporarily unavailable" in str(e):
                        break # Go to next model
            
        raise Exception(f"All models for task '{task}' failed. Errors: {errors}")

    def extract_json_safe(self, text: str) -> dict:
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start:end+1]
            
        return json.loads(text)

    async def execute_task_json(self, task: str, prompt: str, temperature: float = 0.5, max_tokens: int = 1024, max_retries: int = 2) -> dict:
        profiles = self.task_profiles.get(task)
        if not profiles:
            raise ValueError(f"Unknown task profile: {task}")
            
        profiles = sorted(profiles, key=lambda p: self.intelligence.get_model_score(p["provider"], p["model"]), reverse=True)
        req_id = str(uuid.uuid4())[:8]
        errors = []
        
        for profile in profiles:
            provider = profile["provider"]
            model = profile["model"]
            
            for attempt in range(max_retries):
                try:
                    content = await self._make_request(provider, model, prompt, temperature, max_tokens, req_id, attempt)
                    try:
                        parsed_json = self.extract_json_safe(content)
                        return parsed_json
                    except json.JSONDecodeError as je:
                        logger.warning(f"[JSON-PARSE-ERR] id={req_id} provider={provider} model={model} attempt={attempt}. Content: {content[:150]}...")
                        if attempt == max_retries - 1:
                            errors.append(f"{provider}/{model} JSON error: {je}")
                            raise je 
                        await asyncio.sleep(1)
                except Exception as e:
                    errors.append(f"{provider}/{model}: {str(e)}")
                    if "temporarily unavailable" in str(e):
                        break 
                
        raise Exception(f"All models for task '{task}' failed. Errors: {errors}")
