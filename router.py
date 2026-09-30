import os
import time
import json
import httpx
import asyncio
from typing import List, Dict, Any, Optional
import uuid
import logging
import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ModelRouter")

# =========================================================================
# XKIRO FREE MODEL POOL CATALOG & ALIAS RESOLUTION
# =========================================================================

XKIRO_MODEL_ALIASES: Dict[str, str] = {
    # DeepSeek family
    "deepseek-v4.1-flash:free": "deepseek/deepseek-v4.1-flash:free",
    "deepseek-v4.1-flash": "deepseek/deepseek-v4.1-flash:free",
    "deepseek-v4-pro": "deepseek/deepseek-v4-pro",
    "deepseek-v4-flash": "deepseek/deepseek-v4-flash",
    "deepseek-v3.2": "deepseek/deepseek-v3.2",
    "deepseek-v3.1": "deepseek/deepseek-v3.1",
    # Mistral family
    "mistral-large-2512": "mistralai/mistral-large-2512",
    "mistral-medium-3.5": "mistralai/mistral-medium-3.5",
    "mistral-small-2603": "mistralai/mistral-small-2603",
    "codestral-2508": "mistralai/codestral-2508",
    "devstral-2": "mistralai/devstral-medium",
    "devstral-medium": "mistralai/devstral-medium",
    "ministral-3-14b": "mistralai/ministral-14b",
    "ministral-14b": "mistralai/ministral-14b",
    "ministral-3-8b": "mistralai/ministral-8b",
    "ministral-8b": "mistralai/ministral-8b",
    "ministral-3-3b": "mistralai/ministral-3b",
    "ministral-3b": "mistralai/ministral-3b",
    # MiniMax family
    "minimax-m3:free": "minimax/minimax-m3:free",
    "minimax-m3": "minimax/minimax-m3:free",
    "minimax-m2.7:free": "minimax/minimax-m2.7:free",
    "minimax-m2.7": "minimax/minimax-m2.7:free",
    "minimax-m2.7-highspeed:free": "minimax/minimax-m2.7-highspeed:free",
    "minimax-m2.7-highspeed": "minimax/minimax-m2.7-highspeed:free",
    "minimax-m2.5:free": "minimax/minimax-m2.5:free",
    "minimax-m2.5": "minimax/minimax-m2.5:free",
    "minimax-m2.5-highspeed:free": "minimax/minimax-m2.5-highspeed:free",
    "minimax-m2.5-highspeed": "minimax/minimax-m2.5-highspeed:free",
    "minimax-m2.1:free": "minimax/minimax-m2.1:free",
    "minimax-m2.1": "minimax/minimax-m2.1:free",
    "minimax-m2.1-highspeed:free": "minimax/minimax-m2.1-highspeed:free",
    "minimax-m2.1-highspeed": "minimax/minimax-m2.1-highspeed:free",
    "minimax-m2:free": "minimax/minimax-m2:free",
    "minimax-m2": "minimax/minimax-m2:free",
    # MiMo family
    "mimo-v2.6-flash:free": "xiaomi/mimo-v2.6-flash:free",
    "mimo-v2.6-flash": "xiaomi/mimo-v2.6-flash:free",
    # Qwen family
    "qwen3.8-omni-flash:free": "qwen/qwen3.8-omni-flash:free",
    "qwen3.8-omni-flash": "qwen/qwen3.8-omni-flash:free",
    "qwen3.8-max:free": "qwen/qwen3.8-max:free",
    "qwen3.8-max": "qwen/qwen3.8-max:free",
    "qwen3.7-max:free": "qwen/qwen3.7-max:free",
    "qwen3.7-max": "qwen/qwen3.7-max:free",
    "qwen3.7-plus:free": "qwen/qwen3.7-plus:free",
    "qwen3.7-plus": "qwen/qwen3.7-plus:free",
    "qwen3.7-flash:free": "qwen/qwen3.7-flash:free",
    "qwen3.7-flash": "qwen/qwen3.7-flash:free",
    "qwen3.6-plus:free": "qwen/qwen3.6-plus:free",
    "qwen3.6-plus": "qwen/qwen3.6-plus:free",
    "qwen3.6-max-preview:free": "qwen/qwen3.6-max-preview:free",
    "qwen3.6-max-preview": "qwen/qwen3.6-max-preview:free",
    "qwen3.6-27b:free": "qwen/qwen3.6-27b:free",
    "qwen3.6-27b": "qwen/qwen3.6-27b:free",
    "qwen3.5-plus:free": "qwen/qwen3.5-plus:free",
    "qwen3.5-plus": "qwen/qwen3.5-plus:free",
    "qwen3.5-omni-plus:free": "qwen/qwen3.5-omni-plus:free",
    "qwen3.5-omni-plus": "qwen/qwen3.5-omni-plus:free",
    "qwen3.6-35b-a3b:free": "qwen/qwen3.6-35b-a3b:free",
    "qwen3.6-35b-a3b": "qwen/qwen3.6-35b-a3b:free",
    "qwen3.5-flash:free": "qwen/qwen3.5-flash:free",
    "qwen3.5-flash": "qwen/qwen3.5-flash:free",
    "qwen3.5-397b-a17b:free": "qwen/qwen3.5-397b-a17b:free",
    "qwen3.5-397b-a17b": "qwen/qwen3.5-397b-a17b:free",
    "qwen3.5-omni-flash:free": "qwen/qwen3.5-omni-flash:free",
    "qwen3.5-omni-flash": "qwen/qwen3.5-omni-flash:free",
    "qwen3-max:free": "qwen/qwen3-max:free",
    "qwen3-max": "qwen/qwen3-max:free",
    "qwen-plus-2025-07-28:free": "qwen/qwen-plus-2025-07-28:free",
    "qwen3-coder-plus:free": "qwen/qwen3-coder-plus:free",
    "qwen3-coder-plus": "qwen/qwen3-coder-plus:free",
    "qwen3-vl-plus:free": "qwen/qwen3-vl-plus:free",
    "qwen3-vl-plus": "qwen/qwen3-vl-plus:free",
    "qwen3-omni-flash:free": "qwen/qwen3-omni-flash:free",
    "qwen3-omni-flash": "qwen/qwen3-omni-flash:free",
    # Cohere family
    "command-a-plus": "cohere/command-a-plus",
    "command-a-reasoning": "cohere/command-a-reasoning",
    "command-a": "cohere/command-a",
    "command-a-translate": "cohere/command-a-translate",
    "command-a-vision": "cohere/command-a-vision",
    "north-mini-code": "cohere/north-mini-code",
    "north-small-translate": "cohere/north-small-translate",
    "command-r-plus-08-2024": "cohere/command-r-plus-08-2024",
    "command-r-08-2024": "cohere/command-r-08-2024",
    "command-r7b-12-2024": "cohere/command-r7b-12-2024",
    "aya-expanse-32b": "cohere/aya-expanse-32b",
    "aya-vision-32b": "cohere/aya-vision-32b",
    "tiny-aya-global": "cohere/tiny-aya-global",
    "tiny-aya-earth": "cohere/tiny-aya-earth",
    "tiny-aya-fire": "cohere/tiny-aya-fire",
    "tiny-aya-water": "cohere/tiny-aya-water",
    # Other pool models
    "dots3-note-preview": "dots-studio/dots-3-note-preview:free",
    "dots-3-note-preview:free": "dots-studio/dots-3-note-preview:free",
    "lfm2.5-2.6b": "liquid/lfm-2.5-2.6b:free",
    "lfm-2.5-2.6b:free": "liquid/lfm-2.5-2.6b:free",
    "muse-spark-1.3": "meta/muse-spark-1.3-contributor:free",
    "muse-spark-1.3-contributor:free": "meta/muse-spark-1.3-contributor:free",
    "sensenova-6.8-flash-lite": "sensenova/sensenova-6.8-flash-lite",
    "sensenova-6.7-flash-lite": "sensenova/sensenova-6.7-flash-lite",
    "sensenova-u1.5-lite": "sensenova/sensenova-u1.5-lite",
}

def resolve_xkiro_model_id(model_ref: str) -> str:
    """Normalize model identifier to canonical XKIRO provider model string."""
    clean = model_ref.strip()
    if clean in XKIRO_MODEL_ALIASES:
        return XKIRO_MODEL_ALIASES[clean]
    lower = clean.lower()
    if lower in XKIRO_MODEL_ALIASES:
        return XKIRO_MODEL_ALIASES[lower]
    return clean

# Deterministic 3-step per-model fallback chains (model A -> fallback A1 -> fallback A2)
XKIRO_MODEL_FALLBACKS: Dict[str, List[str]] = {
    # DeepSeek family
    "deepseek/deepseek-v4.1-flash:free": ["deepseek/deepseek-v4-flash", "deepseek/deepseek-v3.2"],
    "deepseek/deepseek-v4-pro": ["deepseek/deepseek-v4.1-flash:free", "deepseek/deepseek-v3.2"],
    "deepseek/deepseek-v4-flash": ["deepseek/deepseek-v4.1-flash:free", "deepseek/deepseek-v3.1"],
    "deepseek/deepseek-v3.2": ["deepseek/deepseek-v3.1", "deepseek/deepseek-v4.1-flash:free"],
    "deepseek/deepseek-v3.1": ["deepseek/deepseek-v3.2", "deepseek/deepseek-v4-flash"],
    # Mistral family
    "mistralai/mistral-large-2512": ["mistralai/mistral-medium-3.5", "mistralai/mistral-small-2603"],
    "mistralai/mistral-medium-3.5": ["mistralai/mistral-small-2603", "mistralai/ministral-14b"],
    "mistralai/mistral-small-2603": ["mistralai/ministral-14b", "mistralai/ministral-8b"],
    "mistralai/codestral-2508": ["mistralai/devstral-medium", "mistralai/mistral-small-2603"],
    "mistralai/devstral-medium": ["mistralai/codestral-2508", "mistralai/ministral-14b"],
    "mistralai/ministral-14b": ["mistralai/ministral-8b", "mistralai/ministral-3b"],
    "mistralai/ministral-8b": ["mistralai/ministral-14b", "mistralai/ministral-3b"],
    "mistralai/ministral-3b": ["mistralai/ministral-8b", "mistralai/ministral-14b"],
    # MiniMax family
    "minimax/minimax-m3:free": ["minimax/minimax-m2.7:free", "minimax/minimax-m2.5:free"],
    "minimax/minimax-m2.7:free": ["minimax/minimax-m2.7-highspeed:free", "minimax/minimax-m2.5:free"],
    "minimax/minimax-m2.7-highspeed:free": ["minimax/minimax-m2.5-highspeed:free", "minimax/minimax-m2.1:free"],
    "minimax/minimax-m2.5:free": ["minimax/minimax-m2.5-highspeed:free", "minimax/minimax-m2.1:free"],
    "minimax/minimax-m2.5-highspeed:free": ["minimax/minimax-m2.1-highspeed:free", "minimax/minimax-m2:free"],
    "minimax/minimax-m2.1:free": ["minimax/minimax-m2.1-highspeed:free", "minimax/minimax-m2:free"],
    "minimax/minimax-m2.1-highspeed:free": ["minimax/minimax-m2:free", "minimax/minimax-m2.5:free"],
    "minimax/minimax-m2:free": ["minimax/minimax-m2.1:free", "minimax/minimax-m2.5:free"],
    # MiMo family
    "xiaomi/mimo-v2.6-flash:free": ["qwen/qwen3.8-omni-flash:free", "deepseek/deepseek-v4.1-flash:free"],
    # Qwen family
    "qwen/qwen3.8-max:free": ["qwen/qwen3.7-max:free", "qwen/qwen3.6-plus:free"],
    "qwen/qwen3.7-max:free": ["qwen/qwen3.7-plus:free", "qwen/qwen3.6-plus:free"],
    "qwen/qwen3.8-omni-flash:free": ["qwen/qwen3.7-flash:free", "qwen/qwen3.5-omni-flash:free"],
    "qwen/qwen3.7-plus:free": ["qwen/qwen3.6-plus:free", "qwen/qwen3.5-plus:free"],
    "qwen/qwen3.7-flash:free": ["qwen/qwen3.5-flash:free", "qwen/qwen3.8-omni-flash:free"],
    "qwen/qwen3.6-plus:free": ["qwen/qwen3.6-27b:free", "qwen/qwen3.5-plus:free"],
    "qwen/qwen3.6-max-preview:free": ["qwen/qwen3.7-max:free", "qwen/qwen3.6-plus:free"],
    "qwen/qwen3.6-27b:free": ["qwen/qwen3.5-plus:free", "qwen/qwen3.6-plus:free"],
    "qwen/qwen3.5-plus:free": ["qwen/qwen3.5-397b-a17b:free", "qwen/qwen3.6-plus:free"],
    "qwen/qwen3.5-omni-plus:free": ["qwen/qwen3.5-omni-flash:free", "qwen/qwen3.8-omni-flash:free"],
    "qwen/qwen3.6-35b-a3b:free": ["qwen/qwen3.5-397b-a17b:free", "qwen/qwen3.6-plus:free"],
    "qwen/qwen3.5-flash:free": ["qwen/qwen3.7-flash:free", "qwen/qwen3.5-omni-flash:free"],
    "qwen/qwen3.5-397b-a17b:free": ["qwen/qwen3.5-plus:free", "qwen/qwen3.6-35b-a3b:free"],
    "qwen/qwen3.5-omni-flash:free": ["qwen/qwen3.8-omni-flash:free", "qwen/qwen3.7-flash:free"],
    "qwen/qwen3-max:free": ["qwen/qwen3.8-max:free", "qwen/qwen3.7-max:free"],
    "qwen/qwen-plus-2025-07-28:free": ["qwen/qwen3.6-plus:free", "qwen/qwen3.5-plus:free"],
    "qwen/qwen3-coder-plus:free": ["qwen/qwen3.6-plus:free", "mistralai/codestral-2508"],
    "qwen/qwen3-vl-plus:free": ["qwen/qwen3.8-omni-flash:free", "cohere/aya-vision-32b"],
    "qwen/qwen3-omni-flash:free": ["qwen/qwen3.8-omni-flash:free", "qwen/qwen3.5-omni-flash:free"],
    # Cohere family
    "cohere/command-a-reasoning": ["cohere/command-a-plus", "cohere/command-a"],
    "cohere/command-a-plus": ["cohere/command-a", "cohere/command-r-plus-08-2024"],
    "cohere/command-a": ["cohere/command-a-plus", "cohere/command-r-08-2024"],
    "cohere/command-a-translate": ["cohere/north-small-translate", "cohere/aya-expanse-32b"],
    "cohere/command-a-vision": ["cohere/aya-vision-32b", "qwen/qwen3-vl-plus:free"],
    "cohere/north-mini-code": ["mistralai/codestral-2508", "qwen/qwen3-coder-plus:free"],
    "cohere/north-small-translate": ["cohere/command-a-translate", "cohere/aya-expanse-32b"],
    "cohere/command-r-plus-08-2024": ["cohere/command-r-08-2024", "cohere/command-r7b-12-2024"],
    "cohere/command-r-08-2024": ["cohere/command-r7b-12-2024", "cohere/command-a"],
    "cohere/command-r7b-12-2024": ["cohere/command-r-08-2024", "cohere/command-a"],
    "cohere/aya-expanse-32b": ["cohere/tiny-aya-global", "cohere/command-a-translate"],
    "cohere/aya-vision-32b": ["cohere/command-a-vision", "qwen/qwen3-vl-plus:free"],
    "cohere/tiny-aya-global": ["cohere/tiny-aya-earth", "cohere/tiny-aya-water"],
    "cohere/tiny-aya-earth": ["cohere/tiny-aya-fire", "cohere/tiny-aya-global"],
    "cohere/tiny-aya-fire": ["cohere/tiny-aya-water", "cohere/tiny-aya-earth"],
    "cohere/tiny-aya-water": ["cohere/tiny-aya-global", "cohere/tiny-aya-fire"],
    # Other pool models
    "dots-studio/dots-3-note-preview:free": ["qwen/qwen3.7-max:free", "mistralai/mistral-large-2512"],
    "liquid/lfm-2.5-2.6b:free": ["qwen/qwen3.7-flash:free", "deepseek/deepseek-v4.1-flash:free"],
    "meta/muse-spark-1.3-contributor:free": ["minimax/minimax-m3:free", "qwen/qwen3.8-max:free"],
    "sensenova/sensenova-6.8-flash-lite": ["sensenova/sensenova-6.7-flash-lite", "qwen/qwen3.7-flash:free"],
    "sensenova/sensenova-6.7-flash-lite": ["sensenova/sensenova-u1.5-lite", "qwen/qwen3.7-flash:free"],
    "sensenova/sensenova-u1.5-lite": ["sensenova/sensenova-6.7-flash-lite", "qwen/qwen3.5-flash:free"],
}

def get_model_fallback_chain(model_ref: str) -> List[str]:
    """Returns 2 distinct fallback model IDs for the given model ID.
    Enforces per-model fallback: model A -> fallback A1 -> fallback A2.
    """
    model_id = resolve_xkiro_model_id(model_ref)
    if model_id in XKIRO_MODEL_FALLBACKS:
        return list(XKIRO_MODEL_FALLBACKS[model_id])
    lower = model_id.lower()
    if lower in XKIRO_MODEL_FALLBACKS:
        return list(XKIRO_MODEL_FALLBACKS[lower])
    # Default family-based fallbacks
    prefix = model_id.split("/")[0] if "/" in model_id else ""
    family_matches = [
        m["id"] for m in XKIRO_MODEL_POOL
        if (prefix and m["id"].startswith(f"{prefix}/")) and m["id"] != model_id
    ]
    if len(family_matches) >= 2:
        return family_matches[:2]
    elif len(family_matches) == 1:
        return [family_matches[0], "qwen/qwen3.7-max:free"]
    return ["qwen/qwen3.7-max:free", "mistralai/mistral-large-2512"]


# Structured metadata for all registered models in the XKIRO pool
XKIRO_MODEL_POOL: List[Dict[str, Any]] = [
    # --- DeepSeek ---
    {
        "id": "deepseek/deepseek-v4.1-flash:free",
        "name": "DeepSeek V4.1 Flash",
        "family": "DeepSeek",
        "role": "Red Team / Fast Review",
        "primary_for": ["red_team"],
        "fallback_for": ["linguistic_judge", "fast_screen"],
        "focus": "reasoning",
        "is_free": True
    },
    {
        "id": "deepseek/deepseek-v4-pro",
        "name": "DeepSeek V4 Pro",
        "family": "DeepSeek",
        "role": "Generation / Commercial / Arbiter",
        "primary_for": ["consensus_arbiter"],
        "fallback_for": ["domain_generation", "brand_judge", "commercial_judge"],
        "focus": "reasoning",
        "is_free": True
    },
    {
        "id": "deepseek/deepseek-v4-flash",
        "name": "DeepSeek V4 Flash",
        "family": "DeepSeek",
        "role": "General Reasoning (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "reasoning",
        "is_free": True
    },
    {
        "id": "deepseek/deepseek-v3.2",
        "name": "DeepSeek V3.2",
        "family": "DeepSeek",
        "role": "General Reasoning (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "reasoning",
        "is_free": True
    },
    {
        "id": "deepseek/deepseek-v3.1",
        "name": "DeepSeek V3.1",
        "family": "DeepSeek",
        "role": "General Reasoning (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "reasoning",
        "is_free": True
    },
    # --- Mistral ---
    {
        "id": "mistralai/mistral-large-2512",
        "name": "Mistral Large 2512",
        "family": "Mistral",
        "role": "Linguistic / Brand / Fallback",
        "primary_for": ["linguistic_judge"],
        "fallback_for": ["domain_generation", "brand_judge", "commercial_judge", "consensus_arbiter", "multilingual"],
        "focus": "linguistic",
        "is_free": True
    },
    {
        "id": "mistralai/mistral-medium-3.5",
        "name": "Mistral Medium 3.5",
        "family": "Mistral",
        "role": "Red Team / Analysis Fallback",
        "primary_for": [],
        "fallback_for": ["red_team"],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "mistralai/mistral-small-2603",
        "name": "Mistral Small 2603",
        "family": "Mistral",
        "role": "Fast Screen / Fallback",
        "primary_for": [],
        "fallback_for": ["fast_screen"],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "mistralai/codestral-2508",
        "name": "Codestral 2508",
        "family": "Mistral",
        "role": "Code / Architecture (Non-Judge)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "code",
        "is_free": True
    },
    {
        "id": "mistralai/devstral-medium",
        "name": "Devstral 2",
        "family": "Mistral",
        "role": "Code / Automation (Non-Judge)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "code",
        "is_free": True
    },
    {
        "id": "mistralai/ministral-14b",
        "name": "Ministral 3 14B",
        "family": "Mistral",
        "role": "Fast Screen / Fallback",
        "primary_for": [],
        "fallback_for": ["fast_screen"],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "mistralai/ministral-8b",
        "name": "Ministral 3 8B",
        "family": "Mistral",
        "role": "Lightweight Reasoning (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "mistralai/ministral-3b",
        "name": "Ministral 3 3B",
        "family": "Mistral",
        "role": "Ultra-Fast Edge (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    # --- MiniMax ---
    {
        "id": "minimax/minimax-m3:free",
        "name": "MiniMax M3",
        "family": "MiniMax",
        "role": "Generation / Brand / Commercial Fallback",
        "primary_for": [],
        "fallback_for": ["domain_generation", "brand_judge", "commercial_judge"],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "minimax/minimax-m2.7:free",
        "name": "MiniMax M2.7",
        "family": "MiniMax",
        "role": "General Pool",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "minimax/minimax-m2.7-highspeed:free",
        "name": "MiniMax M2.7 HighSpeed",
        "family": "MiniMax",
        "role": "Fast Screen / Fallback",
        "primary_for": [],
        "fallback_for": ["fast_screen"],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "minimax/minimax-m2.5:free",
        "name": "MiniMax M2.5",
        "family": "MiniMax",
        "role": "General Pool",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "minimax/minimax-m2.5-highspeed:free",
        "name": "MiniMax M2.5 HighSpeed",
        "family": "MiniMax",
        "role": "Fast Screen Pool",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "minimax/minimax-m2.1:free",
        "name": "MiniMax M2.1",
        "family": "MiniMax",
        "role": "General Pool",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "minimax/minimax-m2.1-highspeed:free",
        "name": "MiniMax M2.1 HighSpeed",
        "family": "MiniMax",
        "role": "Fast Screen Pool",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "minimax/minimax-m2:free",
        "name": "MiniMax M2",
        "family": "MiniMax",
        "role": "General Pool",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    # --- MiMo ---
    {
        "id": "xiaomi/mimo-v2.6-flash:free",
        "name": "MiMo V2.6 Flash",
        "family": "MiMo",
        "role": "General Pool",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    # --- Qwen ---
    {
        "id": "qwen/qwen3.8-max:free",
        "name": "Qwen 3.8 Max",
        "family": "Qwen",
        "role": "Brand / Generation / Arbiter",
        "primary_for": ["domain_generation", "brand_judge"],
        "fallback_for": ["consensus_arbiter"],
        "focus": "reasoning",
        "is_free": True
    },
    {
        "id": "qwen/qwen3.7-max:free",
        "name": "Qwen 3.7 Max",
        "family": "Qwen",
        "role": "Linguistic / Red Team Fallback",
        "primary_for": [],
        "fallback_for": ["linguistic_judge", "red_team"],
        "focus": "reasoning",
        "is_free": True
    },
    {
        "id": "qwen/qwen3.8-omni-flash:free",
        "name": "Qwen 3.8 Omni Flash",
        "family": "Qwen",
        "role": "Fast Screen Primary",
        "primary_for": ["fast_screen"],
        "fallback_for": [],
        "focus": "multimodal",
        "is_free": True
    },
    {
        "id": "qwen/qwen3.7-plus:free",
        "name": "Qwen 3.7 Plus",
        "family": "Qwen",
        "role": "High-Capacity General (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "qwen/qwen3.7-flash:free",
        "name": "Qwen 3.7 Flash",
        "family": "Qwen",
        "role": "Fast Inference (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "qwen/qwen3.6-plus:free",
        "name": "Qwen 3.6 Plus",
        "family": "Qwen",
        "role": "Red Team Fallback",
        "primary_for": [],
        "fallback_for": ["red_team"],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "qwen/qwen3.6-max-preview:free",
        "name": "Qwen 3.6 Max Preview",
        "family": "Qwen",
        "role": "Reasoning Preview (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "reasoning",
        "is_free": True
    },
    {
        "id": "qwen/qwen3.6-27b:free",
        "name": "Qwen 3.6 27B",
        "family": "Qwen",
        "role": "Mid-Scale Reasoning (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "reasoning",
        "is_free": True
    },
    {
        "id": "qwen/qwen3.5-plus:free",
        "name": "Qwen 3.5 Plus",
        "family": "Qwen",
        "role": "General Pool",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "qwen/qwen3.5-omni-plus:free",
        "name": "Qwen 3.5 Omni Plus",
        "family": "Qwen",
        "role": "Multimodal Pool",
        "primary_for": [],
        "fallback_for": [],
        "focus": "multimodal",
        "is_free": True
    },
    {
        "id": "qwen/qwen3.6-35b-a3b:free",
        "name": "Qwen 3.6 35B A3B",
        "family": "Qwen",
        "role": "MoE Architecture Pool",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "qwen/qwen3.5-flash:free",
        "name": "Qwen 3.5 Flash",
        "family": "Qwen",
        "role": "Fast Inference (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "qwen/qwen3.5-397b-a17b:free",
        "name": "Qwen 3.5 397B A17B",
        "family": "Qwen",
        "role": "Ultra-Scale MoE (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "qwen/qwen3.5-omni-flash:free",
        "name": "Qwen 3.5 Omni Flash",
        "family": "Qwen",
        "role": "Multimodal Fast (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "multimodal",
        "is_free": True
    },
    {
        "id": "qwen/qwen3-max:free",
        "name": "Qwen 3 Max",
        "family": "Qwen",
        "role": "Legacy Flagship (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "reasoning",
        "is_free": True
    },
    {
        "id": "qwen/qwen-plus-2025-07-28:free",
        "name": "Qwen Plus (Snapshot)",
        "family": "Qwen",
        "role": "Snapshot Baseline (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "qwen/qwen3-coder-plus:free",
        "name": "Qwen 3 Coder Plus",
        "family": "Qwen",
        "role": "Code / Specialized (Non-Judge)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "code",
        "is_free": True
    },
    {
        "id": "qwen/qwen3-vl-plus:free",
        "name": "Qwen 3 VL Plus",
        "family": "Qwen",
        "role": "Vision / Multimodal (Non-Judge)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "multimodal",
        "is_free": True
    },
    {
        "id": "qwen/qwen3-omni-flash:free",
        "name": "Qwen 3 Omni Flash",
        "family": "Qwen",
        "role": "Multimodal Fast (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "multimodal",
        "is_free": True
    },
    # --- Cohere ---
    {
        "id": "cohere/command-a-reasoning",
        "name": "Command A Reasoning",
        "family": "Cohere",
        "role": "Commercial / Final Review",
        "primary_for": ["commercial_judge"],
        "fallback_for": ["consensus_arbiter"],
        "focus": "reasoning",
        "is_free": True
    },
    {
        "id": "cohere/command-a-plus",
        "name": "Command A Plus",
        "family": "Cohere",
        "role": "Linguistic Fallback",
        "primary_for": [],
        "fallback_for": ["linguistic_judge"],
        "focus": "linguistic",
        "is_free": True
    },
    {
        "id": "cohere/command-a",
        "name": "Command A",
        "family": "Cohere",
        "role": "General Pool",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "cohere/command-a-translate",
        "name": "Command A Translate",
        "family": "Cohere",
        "role": "Multilingual Specialist",
        "primary_for": ["multilingual"],
        "fallback_for": [],
        "focus": "translation",
        "is_free": True
    },
    {
        "id": "cohere/command-a-vision",
        "name": "Command A Vision",
        "family": "Cohere",
        "role": "Multimodal (Non-Judge)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "multimodal",
        "is_free": True
    },
    {
        "id": "cohere/north-mini-code",
        "name": "North Mini Code",
        "family": "Cohere",
        "role": "Code (Non-Judge)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "code",
        "is_free": True
    },
    {
        "id": "cohere/north-small-translate",
        "name": "North Small Translate",
        "family": "Cohere",
        "role": "Multilingual Fallback",
        "primary_for": [],
        "fallback_for": ["multilingual"],
        "focus": "translation",
        "is_free": True
    },
    {
        "id": "cohere/command-r-plus-08-2024",
        "name": "Command R+ (08-2024)",
        "family": "Cohere",
        "role": "General Enterprise (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "reasoning",
        "is_free": True
    },
    {
        "id": "cohere/command-r-08-2024",
        "name": "Command R (08-2024)",
        "family": "Cohere",
        "role": "General (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "cohere/command-r7b-12-2024",
        "name": "Command R 7B",
        "family": "Cohere",
        "role": "Compact Reasoning (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "cohere/aya-expanse-32b",
        "name": "Aya Expanse 32B",
        "family": "Cohere",
        "role": "Multilingual Specialist",
        "primary_for": [],
        "fallback_for": ["multilingual"],
        "focus": "translation",
        "is_free": True
    },
    {
        "id": "cohere/aya-vision-32b",
        "name": "Aya Vision 32B",
        "family": "Cohere",
        "role": "Multimodal (Non-Judge)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "multimodal",
        "is_free": True
    },
    {
        "id": "cohere/tiny-aya-global",
        "name": "Tiny Aya Global",
        "family": "Cohere",
        "role": "Global Multilingual Edge (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "translation",
        "is_free": True
    },
    {
        "id": "cohere/tiny-aya-earth",
        "name": "Tiny Aya Earth",
        "family": "Cohere",
        "role": "Multilingual Edge (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "translation",
        "is_free": True
    },
    {
        "id": "cohere/tiny-aya-fire",
        "name": "Tiny Aya Fire",
        "family": "Cohere",
        "role": "Multilingual Edge (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "translation",
        "is_free": True
    },
    {
        "id": "cohere/tiny-aya-water",
        "name": "Tiny Aya Water",
        "family": "Cohere",
        "role": "Multilingual Edge (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "translation",
        "is_free": True
    },
    # --- Other Pool Models ---
    {
        "id": "dots-studio/dots-3-note-preview:free",
        "name": "Dots3 Note Preview",
        "family": "Other",
        "role": "General Pool",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "liquid/lfm-2.5-2.6b:free",
        "name": "LFM 2.5 2.6B",
        "family": "Other",
        "role": "Liquid Neural Edge (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "meta/muse-spark-1.3-contributor:free",
        "name": "Muse Spark 1.3",
        "family": "Other",
        "role": "Creative Ideation (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "sensenova/sensenova-6.8-flash-lite",
        "name": "SenseNova 6.8 Flash Lite",
        "family": "Other",
        "role": "General Fast (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "sensenova/sensenova-6.7-flash-lite",
        "name": "SenseNova 6.7 Flash Lite",
        "family": "Other",
        "role": "General Fast (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
    {
        "id": "sensenova/sensenova-u1.5-lite",
        "name": "SenseNova U1.5 Lite",
        "family": "Other",
        "role": "Compact Edge (Pool)",
        "primary_for": [],
        "fallback_for": [],
        "focus": "general",
        "is_free": True
    },
]


# =========================================================================
# MODEL INTELLIGENCE & TELEMETRY LAYER
# =========================================================================

class ModelIntelligenceLayer:
    def __init__(self):
        self.stats = {}
        
    def record_usage(
        self,
        provider: str,
        model: str,
        latency: float,
        success: bool,
        error_msg: str = None,
        mark_unavailable: bool = False
    ):
        key = f"{provider}:{model}"
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if key not in self.stats:
            self.stats[key] = {
                "success_count": 0,
                "fail_count": 0,
                "consecutive_failures": 0,
                "total_latency": 0.0,
                "avg_latency": 0.0,
                "last_latency": 0.0,
                "reliability": 100.0,
                "status": "ONLINE" if success else "UNAVAILABLE",
                "cooldown_until": 0,
                "last_error": None,
                "last_success": None
            }
        
        stat = self.stats[key]
        stat["last_latency"] = round(latency, 3)
        if success:
            stat["success_count"] += 1
            stat["consecutive_failures"] = 0
            stat["total_latency"] += latency
            stat["status"] = "ONLINE"
            stat["cooldown_until"] = 0
            stat["last_success"] = now_ts
            stat["last_error"] = None
        else:
            stat["fail_count"] += 1
            stat["consecutive_failures"] += 1
            stat["last_error"] = error_msg
            
            # Rate limit specific
            if "429" in str(error_msg or ""):
                stat["status"] = "RATE_LIMITED"
                stat["cooldown_until"] = time.time() + 60
            elif "timeout" in str(error_msg or "").lower() or "timed out" in str(error_msg or "").lower():
                stat["status"] = "TIMEOUT"
                stat["cooldown_until"] = time.time() + 60
            elif mark_unavailable or "403" in str(error_msg or "") or "404" in str(error_msg or ""):
                stat["status"] = "ERROR"
                stat["cooldown_until"] = time.time() + int(os.getenv("PROVIDER_COOLDOWN_SECONDS", "3600"))
                logger.warning(f"[CIRCUIT-BREAKER] {key} marked ERROR: {error_msg}")
            elif stat["consecutive_failures"] >= 2:
                stat["status"] = "DEGRADED" if stat["success_count"] > 0 else "ERROR"
                stat["cooldown_until"] = time.time() + int(os.getenv("PROVIDER_COOLDOWN_SECONDS", "1800"))
                logger.warning(f"[CIRCUIT-BREAKER] {key} marked {stat['status']} until {stat['cooldown_until']}")
            else:
                stat["status"] = "ERROR"
            
        total_calls = stat["success_count"] + stat["fail_count"]
        stat["reliability"] = (stat["success_count"] / total_calls) * 100 if total_calls > 0 else 0.0
        if stat["success_count"] > 0:
            stat["avg_latency"] = stat["total_latency"] / stat["success_count"]

    def is_model_available(self, provider: str, model: str) -> bool:
        key = f"{provider}:{model}"
        if key not in self.stats:
            return True
        stat = self.stats[key]
        if stat["status"] in ["UNAVAILABLE", "ERROR", "RATE LIMITED", "RATE_LIMITED", "TIMEOUT", "temporarily_unavailable"]:
            if time.time() > stat.get("cooldown_until", 0):
                return True # Half-open probe allowed
            return False
        return True

    def get_model_score(self, provider: str, model: str) -> float:
        key = f"{provider}:{model}"
        if key not in self.stats:
            return 100.0 
        stat = self.stats[key]
        if not self.is_model_available(provider, model):
            return -100.0 # Push to back of fallback queue
            
        reliability = stat.get("reliability", 100.0)
        avg_latency = stat.get("avg_latency", 1.0)
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
                "last_latency": round(stat.get("last_latency", 0.0), 3),
                "last_error": stat["last_error"],
                "last_success": stat.get("last_success"),
                "cooldown_until": stat["cooldown_until"] if stat["cooldown_until"] > time.time() else None
            }
            if stat["status"] in ["UNAVAILABLE", "temporarily_unavailable"] and providers[provider]["status"] == "healthy":
                providers[provider]["status"] = "degraded"
        return providers


# =========================================================================
# MODEL ROUTER
# =========================================================================

class ModelRouter:
    def __init__(self):
        self.intelligence = ModelIntelligenceLayer()
        self.providers = {
            "xkiro": {
                "base_url": "https://api.xkiro.com/v1",
                "api_key": os.getenv("XKIRO_API_KEY")
            },
            "nvidia": {
                "base_url": "https://integrate.api.nvidia.com/v1",
                "api_key": os.getenv("NVIDIA_API_KEY")
            },
            "openrouter": {
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": os.getenv("OPENROUTER_API_KEY")
            }
        }
        
        self.semaphores = {
            "xkiro": asyncio.Semaphore(int(os.getenv("XKIRO_CONCURRENCY", "5"))),
            "nvidia": asyncio.Semaphore(int(os.getenv("NVIDIA_CONCURRENCY", "5"))),
            "openrouter": asyncio.Semaphore(int(os.getenv("OPENROUTER_CONCURRENCY", "5"))),
        }
        
        # Capability-Based Routing Chains (Section 2)
        # Primary Model -> Fallback #1 -> Fallback #2 -> Fallback #3
        self.task_profiles = {
            # GENERATION
            "domain_generation": [
                {"provider": "xkiro", "model": "qwen/qwen3.8-max:free"},
                {"provider": "xkiro", "model": "deepseek/deepseek-v4-pro"},
                {"provider": "xkiro", "model": "minimax/minimax-m3:free"},
                {"provider": "xkiro", "model": "mistralai/mistral-large-2512"},
                {"provider": "nvidia", "model": "deepseek-ai/deepseek-v4.1-flash"}
            ],
            "naming_generator": [
                {"provider": "xkiro", "model": "qwen/qwen3.8-max:free"},
                {"provider": "xkiro", "model": "deepseek/deepseek-v4-pro"},
                {"provider": "xkiro", "model": "minimax/minimax-m3:free"},
                {"provider": "xkiro", "model": "mistralai/mistral-large-2512"},
                {"provider": "nvidia", "model": "deepseek-ai/deepseek-v4.1-flash"}
            ],
            "trend_research": [
                {"provider": "xkiro", "model": "qwen/qwen3.8-max:free"},
                {"provider": "xkiro", "model": "mistralai/mistral-large-2512"},
                {"provider": "nvidia", "model": "nvidia/nemotron-3-super-120b-a12b"}
            ],
            # LINGUISTIC / PRONUNCIATION (Full Pool Coverage)
            "linguistic_judge": [
                {"provider": "xkiro", "model": "mistralai/mistral-large-2512"},
                {"provider": "xkiro", "model": "qwen/qwen3.7-max:free"},
                {"provider": "xkiro", "model": "deepseek/deepseek-v4.1-flash:free"},
                {"provider": "xkiro", "model": "cohere/command-a-plus"},
                {"provider": "xkiro", "model": "mistralai/mistral-medium-3.5"},
                {"provider": "xkiro", "model": "mistralai/mistral-small-2603"},
                {"provider": "xkiro", "model": "mistralai/ministral-14b"},
                {"provider": "xkiro", "model": "mistralai/ministral-8b"},
                {"provider": "xkiro", "model": "mistralai/ministral-3b"},
                {"provider": "xkiro", "model": "cohere/command-a-translate"},
                {"provider": "xkiro", "model": "cohere/north-small-translate"},
                {"provider": "xkiro", "model": "cohere/aya-expanse-32b"},
                {"provider": "xkiro", "model": "cohere/tiny-aya-global"},
                {"provider": "xkiro", "model": "cohere/tiny-aya-earth"},
                {"provider": "xkiro", "model": "cohere/tiny-aya-fire"},
                {"provider": "xkiro", "model": "cohere/tiny-aya-water"},
            ],
            "quality_evaluator": [
                {"provider": "xkiro", "model": "mistralai/mistral-large-2512"},
                {"provider": "xkiro", "model": "qwen/qwen3.7-max:free"},
                {"provider": "xkiro", "model": "deepseek/deepseek-v4.1-flash:free"},
                {"provider": "xkiro", "model": "cohere/command-a-plus"}
            ],
            # BRAND EVALUATION (Full Pool Coverage)
            "brand_judge": [
                {"provider": "xkiro", "model": "qwen/qwen3.8-max:free"},
                {"provider": "xkiro", "model": "minimax/minimax-m3:free"},
                {"provider": "xkiro", "model": "deepseek/deepseek-v4-pro"},
                {"provider": "xkiro", "model": "mistralai/mistral-large-2512"},
                {"provider": "xkiro", "model": "minimax/minimax-m2.7:free"},
                {"provider": "xkiro", "model": "minimax/minimax-m2.7-highspeed:free"},
                {"provider": "xkiro", "model": "minimax/minimax-m2.5:free"},
                {"provider": "xkiro", "model": "minimax/minimax-m2.5-highspeed:free"},
                {"provider": "xkiro", "model": "minimax/minimax-m2.1:free"},
                {"provider": "xkiro", "model": "minimax/minimax-m2.1-highspeed:free"},
                {"provider": "xkiro", "model": "minimax/minimax-m2:free"},
                {"provider": "xkiro", "model": "qwen/qwen3.7-plus:free"},
                {"provider": "xkiro", "model": "qwen/qwen3.7-flash:free"},
                {"provider": "xkiro", "model": "qwen/qwen3.6-plus:free"},
                {"provider": "xkiro", "model": "qwen/qwen3.6-max-preview:free"},
                {"provider": "xkiro", "model": "qwen/qwen3.6-27b:free"},
                {"provider": "xkiro", "model": "qwen/qwen3.5-plus:free"},
            ],
            "brandability": [
                {"provider": "xkiro", "model": "qwen/qwen3.8-max:free"},
                {"provider": "xkiro", "model": "minimax/minimax-m3:free"},
                {"provider": "xkiro", "model": "deepseek/deepseek-v4-pro"},
                {"provider": "xkiro", "model": "mistralai/mistral-large-2512"}
            ],
            # COMMERCIAL / BUYER (Full Pool Coverage)
            "commercial_judge": [
                {"provider": "xkiro", "model": "cohere/command-a-reasoning"},
                {"provider": "xkiro", "model": "deepseek/deepseek-v4-pro"},
                {"provider": "xkiro", "model": "mistralai/mistral-large-2512"},
                {"provider": "xkiro", "model": "minimax/minimax-m3:free"},
                {"provider": "xkiro", "model": "cohere/command-a"},
                {"provider": "xkiro", "model": "cohere/command-r-plus-08-2024"},
                {"provider": "xkiro", "model": "cohere/command-r-08-2024"},
                {"provider": "xkiro", "model": "cohere/command-r7b-12-2024"},
                {"provider": "xkiro", "model": "deepseek/deepseek-v3.2"},
                {"provider": "xkiro", "model": "deepseek/deepseek-v3.1"},
                {"provider": "xkiro", "model": "qwen/qwen3.6-35b-a3b:free"},
                {"provider": "xkiro", "model": "qwen/qwen3.5-397b-a17b:free"},
                {"provider": "xkiro", "model": "qwen/qwen3-max:free"},
                {"provider": "xkiro", "model": "qwen/qwen-plus-2025-07-28:free"},
                {"provider": "xkiro", "model": "qwen/qwen3-coder-plus:free"},
            ],
            "commercial_evaluator": [
                {"provider": "xkiro", "model": "cohere/command-a-reasoning"},
                {"provider": "xkiro", "model": "deepseek/deepseek-v4-pro"},
                {"provider": "xkiro", "model": "mistralai/mistral-large-2512"},
                {"provider": "xkiro", "model": "minimax/minimax-m3:free"}
            ],
            # RED TEAM (Full Pool Coverage)
            "red_team": [
                {"provider": "xkiro", "model": "deepseek/deepseek-v4.1-flash:free"},
                {"provider": "xkiro", "model": "qwen/qwen3.7-max:free"},
                {"provider": "xkiro", "model": "mistralai/mistral-medium-3.5"},
                {"provider": "xkiro", "model": "qwen/qwen3.6-plus:free"},
                {"provider": "xkiro", "model": "deepseek/deepseek-v4-flash"},
                {"provider": "xkiro", "model": "qwen/qwen3.8-omni-flash:free"},
                {"provider": "xkiro", "model": "qwen/qwen3.5-omni-plus:free"},
                {"provider": "xkiro", "model": "qwen/qwen3.5-flash:free"},
                {"provider": "xkiro", "model": "qwen/qwen3.5-omni-flash:free"},
                {"provider": "xkiro", "model": "qwen/qwen3-omni-flash:free"},
                {"provider": "xkiro", "model": "qwen/qwen3-vl-plus:free"},
                {"provider": "xkiro", "model": "xiaomi/mimo-v2.6-flash:free"},
                {"provider": "xkiro", "model": "mistralai/codestral-2508"},
                {"provider": "xkiro", "model": "mistralai/devstral-medium"},
                {"provider": "xkiro", "model": "cohere/north-mini-code"},
                {"provider": "xkiro", "model": "cohere/aya-vision-32b"},
                {"provider": "xkiro", "model": "cohere/command-a-vision"},
            ],
            # FINAL ARBITRATION
            "consensus_arbiter": [
                {"provider": "xkiro", "model": "deepseek/deepseek-v4-pro"},
                {"provider": "xkiro", "model": "qwen/qwen3.8-max:free"},
                {"provider": "xkiro", "model": "cohere/command-a-reasoning"},
                {"provider": "xkiro", "model": "mistralai/mistral-large-2512"}
            ],
            "final_judge": [
                {"provider": "xkiro", "model": "deepseek/deepseek-v4-pro"},
                {"provider": "xkiro", "model": "qwen/qwen3.8-max:free"},
                {"provider": "xkiro", "model": "cohere/command-a-reasoning"},
                {"provider": "xkiro", "model": "mistralai/mistral-large-2512"}
            ],
            # FAST SCREEN / FALLBACK
            "fast_screen": [
                {"provider": "xkiro", "model": "qwen/qwen3.8-omni-flash:free"},
                {"provider": "xkiro", "model": "deepseek/deepseek-v4.1-flash:free"},
                {"provider": "xkiro", "model": "minimax/minimax-m2.7-highspeed:free"},
                {"provider": "xkiro", "model": "mistralai/mistral-small-2603"},
                {"provider": "xkiro", "model": "mistralai/ministral-14b"}
            ],
            # MULTILINGUAL
            "multilingual": [
                {"provider": "xkiro", "model": "cohere/command-a-translate"},
                {"provider": "xkiro", "model": "cohere/aya-expanse-32b"},
                {"provider": "xkiro", "model": "cohere/north-small-translate"},
                {"provider": "xkiro", "model": "mistralai/mistral-large-2512"}
            ]
        }
        self.client = httpx.AsyncClient(timeout=30.0)

    async def _make_request(
        self,
        provider: str,
        model: str,
        prompt: str,
        temperature: float,
        max_tokens: int,
        req_id: str,
        attempt: int
    ) -> str:
        # Resolve aliases if needed
        model = resolve_xkiro_model_id(model) if provider == "xkiro" else model

        if not self.intelligence.is_model_available(provider, model):
            raise Exception(f"Model {model} on {provider} is temporarily unavailable (circuit breaker open).")
            
        prov_info = self.providers.get(provider)
        if not prov_info or not prov_info["api_key"] or str(prov_info["api_key"]).startswith("ضع"):
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
                
                logger.info(f"[AI-REQ] id={req_id} provider={provider} model={model} attempt={attempt} status={response.status_code} latency={latency:.2f}s")
                self.intelligence.record_usage(provider, model, latency, success=True)
                return content
            except httpx.HTTPStatusError as e:
                latency = time.time() - start_time
                status_code = e.response.status_code
                err_text = e.response.text[:120] if hasattr(e.response, "text") else str(e)
                err_str = f"HTTP {status_code}: {err_text}"
                
                # If 403 (unauthorized/paying customers only) or 404 (model not found), mark model permanently unavailable in current pool
                mark_unavailable = status_code in [403, 404]
                self.intelligence.record_usage(provider, model, latency, success=False, error_msg=err_str, mark_unavailable=mark_unavailable)
                logger.error(f"[AI-REQ-FAIL] id={req_id} provider={provider} model={model} attempt={attempt} status={status_code} latency={latency:.2f}s err={err_text}")
                
                if status_code in [429, 500, 502, 503, 504]:
                    await asyncio.sleep(min(2 ** attempt, 8))
                raise e
            except Exception as e:
                latency = time.time() - start_time
                err_str = str(e)
                self.intelligence.record_usage(provider, model, latency, success=False, error_msg=err_str)
                logger.error(f"[AI-REQ-FAIL] id={req_id} provider={provider} model={model} attempt={attempt} err={err_str}")
                raise e

    async def execute_profile(
        self,
        provider: str,
        model: str,
        prompt: str,
        temperature: float = 0.5,
        max_tokens: int = 1024,
        max_retries: int = 1
    ) -> dict:
        """Execute one explicitly selected router profile without re-ranking it.
        Used by independent expert roles so one judge cannot silently switch to a
        different model family based on another role's result.
        """
        canonical_model = resolve_xkiro_model_id(model) if provider == "xkiro" else model
        req_id = str(uuid.uuid4())[:8]
        errors = []
        for attempt in range(max(1, max_retries)):
            started = time.time()
            try:
                content = await self._make_request(provider, canonical_model, prompt, temperature, max_tokens, req_id, attempt)
                return {
                    "content": content,
                    "provider": provider,
                    "model": canonical_model,
                    "latency_ms": round((time.time() - started) * 1000.0, 2),
                    "fallback_used": False,
                }
            except Exception as exc:
                errors.append(f"{provider}/{canonical_model}: {str(exc)}")
                if "unavailable" in str(exc).lower() or "403" in str(exc):
                    break # Skip retries if permanently unavailable
        raise Exception(f"Explicit model profile failed: {errors}")

    async def execute_task(
        self,
        task: str,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        max_retries: int = 2
    ) -> str:
        profiles = self.task_profiles.get(task)
        if not profiles:
            raise ValueError(f"Unknown task profile: {task}")
            
        req_id = str(uuid.uuid4())[:8]
        errors = []
        fallback_used = False
        
        for idx, profile in enumerate(profiles):
            provider = profile["provider"]
            model = resolve_xkiro_model_id(profile["model"]) if provider == "xkiro" else profile["model"]
            
            if not self.intelligence.is_model_available(provider, model):
                continue
                
            if idx > 0:
                fallback_used = True
                
            for attempt in range(max_retries):
                try:
                    content = await self._make_request(provider, model, prompt, temperature, max_tokens, req_id, attempt)
                    return content
                except Exception as e:
                    errors.append(f"{provider}/{model}: {str(e)}")
                    if "unavailable" in str(e).lower() or "403" in str(e):
                        break # Immediately go to next fallback
            
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

    async def execute_task_json(
        self,
        task: str,
        prompt: str,
        temperature: float = 0.5,
        max_tokens: int = 1024,
        max_retries: int = 2
    ) -> dict:
        profiles = self.task_profiles.get(task)
        if not profiles:
            raise ValueError(f"Unknown task profile: {task}")
            
        req_id = str(uuid.uuid4())[:8]
        errors = []
        
        for profile in profiles:
            provider = profile["provider"]
            model = resolve_xkiro_model_id(profile["model"]) if provider == "xkiro" else profile["model"]
            
            if not self.intelligence.is_model_available(provider, model):
                continue
            
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
                    if "unavailable" in str(e).lower() or "403" in str(e):
                        break 
                
        raise Exception(f"All models for task '{task}' failed. Errors: {errors}")

    async def test_model(self, provider: str, model: str) -> Dict[str, Any]:
        """Performs a real lightweight connectivity probe on a single model.
        Never displays ONLINE unless verified with a real 200 OK request.
        """
        canonical_model = resolve_xkiro_model_id(model) if provider == "xkiro" else model
        started = time.time()
        req_id = f"test_{str(uuid.uuid4())[:6]}"
        prov_info = self.providers.get(provider)
        
        if not prov_info or not prov_info.get("api_key") or str(prov_info.get("api_key")).startswith("ضع"):
            return {
                "provider": provider,
                "model": canonical_model,
                "status": "NOT CONFIGURED",
                "latency_ms": None,
                "last_error": "Missing or placeholder API key",
                "last_success": None,
                "tested_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            
        try:
            # Minimal prompt to check alive status with zero hallucination & minimal token usage
            content = await self._make_request(
                provider=provider,
                model=canonical_model,
                prompt="ping",
                temperature=0.0,
                max_tokens=5,
                req_id=req_id,
                attempt=0
            )
            latency_ms = round((time.time() - started) * 1000.0, 2)
            stat = self.intelligence.stats.get(f"{provider}:{canonical_model}", {})
            return {
                "provider": provider,
                "model": canonical_model,
                "status": "ONLINE",
                "latency_ms": latency_ms,
                "last_error": None,
                "last_success": stat.get("last_success") or datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "tested_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
        except httpx.TimeoutException:
            latency_ms = round((time.time() - started) * 1000.0, 2)
            self.intelligence.record_usage(provider, canonical_model, latency_ms / 1000.0, success=False, error_msg="Request timed out")
            return {
                "provider": provider,
                "model": canonical_model,
                "status": "TIMEOUT",
                "latency_ms": latency_ms,
                "last_error": "Request timed out",
                "last_success": self.intelligence.stats.get(f"{provider}:{canonical_model}", {}).get("last_success"),
                "tested_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
        except httpx.HTTPStatusError as e:
            latency_ms = round((time.time() - started) * 1000.0, 2)
            code = e.response.status_code
            status = "RATE_LIMITED" if code == 429 else "ERROR"
            err = f"HTTP {code}: {e.response.text[:120]}"
            self.intelligence.record_usage(provider, canonical_model, latency_ms / 1000.0, success=False, error_msg=err, mark_unavailable=code in [403, 404])
            return {
                "provider": provider,
                "model": canonical_model,
                "status": status,
                "latency_ms": latency_ms,
                "last_error": err,
                "last_success": self.intelligence.stats.get(f"{provider}:{canonical_model}", {}).get("last_success"),
                "tested_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
        except Exception as e:
            latency_ms = round((time.time() - started) * 1000.0, 2)
            err = str(e)[:180]
            status = "TIMEOUT" if "timed out" in err.lower() else "ERROR"
            self.intelligence.record_usage(provider, canonical_model, latency_ms / 1000.0, success=False, error_msg=err)
            return {
                "provider": provider,
                "model": canonical_model,
                "status": status,
                "latency_ms": latency_ms,
                "last_error": err,
                "last_success": self.intelligence.stats.get(f"{provider}:{canonical_model}", {}).get("last_success"),
                "tested_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }

    async def check_configured_models_health(self) -> Dict[str, Any]:
        """Runs minimal health probes across active primary capability models.
        Avoids creating massive traffic across all 57 models simultaneously.
        """
        # Collect distinct primary models from each active capability
        primary_targets = [
            ("xkiro", "qwen/qwen3.8-max:free", "Generation & Brand Primary"),
            ("xkiro", "mistralai/mistral-large-2512", "Linguistic Primary"),
            ("xkiro", "cohere/command-a-reasoning", "Commercial Primary"),
            ("xkiro", "deepseek/deepseek-v4.1-flash:free", "Red Team Primary"),
            ("xkiro", "deepseek/deepseek-v4-pro", "Consensus Arbiter Primary"),
        ]
        
        results = {}
        for prov, mod, role_desc in primary_targets:
            res = await self.test_model(prov, mod)
            res["role_desc"] = role_desc
            results[f"{prov}:{mod}"] = res
            
        return results

    def get_model_pool_health(self) -> List[Dict[str, Any]]:
        """Returns catalog of all XKIRO pool models with live truthful statuses."""
        xkiro_key = self.providers.get("xkiro", {}).get("api_key")
        has_key = bool(xkiro_key and not str(xkiro_key).startswith("ضع"))
        
        output = []
        for item in XKIRO_MODEL_POOL:
            m_id = item["id"]
            stat = self.intelligence.stats.get(f"xkiro:{m_id}")
            
            if not has_key:
                status = "NOT_CONFIGURED"
            elif stat:
                raw_st = stat.get("status", "STANDBY")
                if raw_st in ["RATE LIMITED", "RATE_LIMITED"]:
                    status = "RATE_LIMITED"
                elif raw_st in ["UNAVAILABLE", "ERROR"]:
                    status = "ERROR"
                elif raw_st in ["TIMEOUT", "DEGRADED", "ONLINE"]:
                    status = raw_st
                else:
                    status = raw_st
            else:
                # Configured key exists, but model has not had a live request yet
                status = "STANDBY"
                
            entry = {
                **item,
                "provider": "xkiro",
                "status": status,
                "latency_ms": round(stat.get("avg_latency", 0.0) * 1000.0, 1) if stat and stat.get("avg_latency") else None,
                "last_latency_ms": round(stat.get("last_latency", 0.0) * 1000.0, 1) if stat and stat.get("last_latency") else None,
                "success_count": stat.get("success_count", 0) if stat else 0,
                "fail_count": stat.get("fail_count", 0) if stat else 0,
                "last_success": stat.get("last_success") if stat else None,
                "last_error": stat.get("last_error") if stat else None,
                "reliability": round(stat.get("reliability", 100.0), 1) if stat else 100.0,
            }
            output.append(entry)
            
        return output

    def get_capability_routing_summary(self) -> Dict[str, Any]:
        """Returns the configured capability chains and current live fallback state."""
        summary = {}
        for capability, chain in self.task_profiles.items():
            primary = chain[0] if chain else None
            fallbacks = chain[1:] if len(chain) > 1 else []
            summary[capability] = {
                "primary": primary,
                "fallbacks": fallbacks,
                "chain_length": len(chain),
                "active_model": next((p for p in chain if self.intelligence.is_model_available(p["provider"], p["model"])), primary)
            }
        return summary
