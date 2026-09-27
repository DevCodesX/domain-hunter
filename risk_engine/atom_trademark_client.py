"""
Atom Trademark Search Client
Integrates with Atom's trademark search API as an additional IP signal
alongside USPTO and curated known_brands databases.

Uses ATOM_TRADEMARK_API_KEY and ATOM_TRADEMARK_API_URL.
Note: Kept distinct from ATOM_API_KEY (used for marketplace/premium domain checks in Stage 6)
because trademark API access may use a separate token or product plan.
"""

import os
import re
import asyncio
import logging
import httpx
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from risk_engine.models import RiskLevel

logger = logging.getLogger("AtomTrademarkClient")

class AtomTrademarkResult(BaseModel):
    status: str = "NOT_CHECKED"  # "HIT" | "NO_HIT" | "NOT_CHECKED" | "ERROR"
    risk_level: Optional[RiskLevel] = None  # LOW | MEDIUM | HIGH | CRITICAL | None
    raw_matches: List[Dict[str, Any]] = Field(default_factory=list)
    reason: str = ""

class AtomTrademarkClient:
    """
    Dedicated client for Atom trademark search API.
    Enforces concurrency limits, in-memory caching, and graceful degradation.
    """
    _warned_missing_key: bool = False

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
        timeout: float = 5.0,
        concurrency: int = 4
    ):
        # Read ATOM_TRADEMARK_API_KEY explicitly (distinct from ATOM_API_KEY marketplace key)
        self.api_key = api_key if api_key is not None else os.getenv("ATOM_TRADEMARK_API_KEY", "")
        self.base_url = base_url or os.getenv("ATOM_TRADEMARK_API_URL", "https://www.atom.com/api/marketplace/trademark-search")
        self._external_client = client
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(concurrency)
        self._cache: Dict[str, AtomTrademarkResult] = {}

    def _normalize(self, candidate: str) -> str:
        """Normalizes candidate: strip .com, lowercase, alphanumeric only."""
        cand = candidate.lower().strip()
        if cand.endswith(".com"):
            cand = cand[:-4]
        return re.sub(r'[^a-z0-9]', '', cand)

    def clear_cache(self) -> None:
        """Clears the in-memory candidate cache."""
        self._cache.clear()

    async def search_trademark(self, candidate: str) -> AtomTrademarkResult:
        """
        Searches trademark database via Atom API for candidate name.
        Returns AtomTrademarkResult with status HIT, NO_HIT, NOT_CHECKED, or ERROR.
        Never raises unhandled network exceptions; degrades gracefully.
        """
        if not candidate:
            return AtomTrademarkResult(
                status="NOT_CHECKED",
                risk_level=None,
                raw_matches=[],
                reason="Atom: NOT_CHECKED (empty candidate)"
            )

        norm = self._normalize(candidate)
        if norm in self._cache:
            return self._cache[norm]

        clean_key = self.api_key.strip()
        # If API key is missing or placeholder, degrade immediately without any network call
        if not clean_key or clean_key in ["your_atom_trademark_key", "your_atom_token_here", "PLACEHOLDER"] or clean_key.startswith("ضع"):
            if not AtomTrademarkClient._warned_missing_key:
                logger.warning("ATOM_TRADEMARK_API_KEY is not configured; Atom trademark screening will be NOT_CHECKED.")
                AtomTrademarkClient._warned_missing_key = True

            result = AtomTrademarkResult(
                status="NOT_CHECKED",
                risk_level=None,
                raw_matches=[],
                reason="Atom: NOT_CHECKED (no API key configured)"
            )
            self._cache[norm] = result
            return result

        # Network request with async concurrency control
        async with self.semaphore:
            client = self._external_client
            should_close = False
            if client is None:
                client = httpx.AsyncClient(timeout=self.timeout)
                should_close = True

            try:
                headers = {
                    "Authorization": f"Bearer {clean_key}",
                    "User-Agent": "DomainHunter/2.0 (Legitimate Trademark Screening)",
                    "Accept": "application/json"
                }
                params = {"keyword": norm}
                response = await client.get(self.base_url, headers=headers, params=params, timeout=self.timeout)

                if response.status_code == 200:
                    try:
                        data = response.json()
                    except Exception:
                        logger.warning(f"Atom trademark response for '{norm}' was malformed JSON")
                        res = AtomTrademarkResult(
                            status="ERROR",
                            risk_level=None,
                            raw_matches=[],
                            reason="Atom: ERROR (malformed JSON response)"
                        )
                        self._cache[norm] = res
                        return res

                    # Support standard payload collections: matches, trademarks, results, data, items
                    raw_matches = (
                        data.get("matches") or
                        data.get("trademarks") or
                        data.get("results") or
                        data.get("data") or
                        data.get("items") or
                        []
                    )
                    if not isinstance(raw_matches, list):
                        raw_matches = [raw_matches] if raw_matches else []

                    is_hit = bool(data.get("hit", False)) or (len(raw_matches) > 0)

                    if is_hit:
                        # Check for exact collision or high similarity
                        exact_hit = any(
                            isinstance(m, dict) and (
                                m.get("exact_match") is True or
                                str(m.get("mark", "")).lower().replace(" ", "") == norm or
                                float(m.get("similarity", 0)) >= 0.95
                            )
                            for m in raw_matches
                        )
                        hit_risk = RiskLevel.CRITICAL if exact_hit else RiskLevel.HIGH
                        res = AtomTrademarkResult(
                            status="HIT",
                            risk_level=hit_risk,
                            raw_matches=raw_matches,
                            reason=f"Atom trademark collision: {len(raw_matches)} conflicting mark(s) found"
                        )
                    else:
                        res = AtomTrademarkResult(
                            status="NO_HIT",
                            risk_level=RiskLevel.LOW,
                            raw_matches=[],
                            reason="Atom: NO_HIT (no conflicting marks found)"
                        )
                    self._cache[norm] = res
                    return res

                elif response.status_code in (401, 403):
                    logger.warning(f"Atom trademark API authentication failed: HTTP {response.status_code}")
                    res = AtomTrademarkResult(
                        status="ERROR",
                        risk_level=None,
                        raw_matches=[],
                        reason=f"Atom API error: HTTP {response.status_code} authentication failure"
                    )
                    self._cache[norm] = res
                    return res
                else:
                    logger.warning(f"Atom trademark API returned HTTP {response.status_code} for '{norm}'")
                    res = AtomTrademarkResult(
                        status="ERROR",
                        risk_level=None,
                        raw_matches=[],
                        reason=f"Atom API error: HTTP {response.status_code}"
                    )
                    self._cache[norm] = res
                    return res

            except httpx.TimeoutException as e:
                logger.warning(f"Atom trademark API timed out for '{norm}': {e}")
                res = AtomTrademarkResult(
                    status="ERROR",
                    risk_level=None,
                    raw_matches=[],
                    reason=f"Atom API timeout for '{norm}'"
                )
                self._cache[norm] = res
                return res
            except Exception as e:
                logger.warning(f"Atom trademark API error for '{norm}': {e}")
                res = AtomTrademarkResult(
                    status="ERROR",
                    risk_level=None,
                    raw_matches=[],
                    reason=f"Atom API error: {str(e)}"
                )
                self._cache[norm] = res
                return res
            finally:
                if should_close:
                    await client.aclose()
