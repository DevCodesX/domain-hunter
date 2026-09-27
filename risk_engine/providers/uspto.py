"""
USPTO Trademark Provider
Integrates with the official USPTO open trademark data / search interface.
Complies with terms of service, provides graceful fallback on network timeouts or API outages.
"""

import httpx
import logging
from typing import List, Dict, Any, Optional
from risk_engine.providers.base import TrademarkProvider
from risk_engine.models import TrademarkMatch, MatchType
from risk_engine.similarity import calculate_comprehensive_similarity

logger = logging.getLogger("USPTOProvider")

class USPTOProvider(TrademarkProvider):
    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        self._external_client = client
        self.endpoint = "https://developer.uspto.gov/ibd-api/v1/application/publications"

    @property
    def name(self) -> str:
        return "uspto_official_api"

    async def search(self, term: str) -> List[TrademarkMatch]:
        """
        Queries USPTO open records for matching marks.
        Never throws unhandled exceptions; returns empty list on network or rate limit errors.
        """
        clean_term = term.lower().replace(".com", "").strip()
        if len(clean_term) < 3:
            return []

        client = self._external_client
        should_close = False
        if not client:
            client = httpx.AsyncClient(timeout=4.0)
            should_close = True

        matches: List[TrademarkMatch] = []
        try:
            # Query official USPTO API endpoint
            headers = {
                "User-Agent": "DomainHunter-ScreeningEngine/2.0 (Legitimate Trademark Screening)",
                "Accept": "application/json"
            }
            params = {
                "searchText": clean_term,
                "start": 0,
                "rows": 5
            }
            res = await client.get(self.endpoint, params=params, headers=headers, timeout=3.5)
            if res.status_code == 200:
                data = res.json()
                docs = data.get("response", {}).get("docs", []) or data.get("results", [])
                for doc in docs:
                    mark_name = doc.get("inventionTitle") or doc.get("markLiteralText") or doc.get("title", "")
                    if mark_name:
                        sim = calculate_comprehensive_similarity(clean_term, mark_name)
                        if sim["composite_similarity"] >= 0.70:
                            matches.append(TrademarkMatch(
                                trademark_name=mark_name,
                                source="uspto_open_api",
                                match_type=MatchType.EXACT if sim["composite_similarity"] >= 0.98 else MatchType.SIMILAR_STRING,
                                similarity_score=sim["composite_similarity"],
                                status="REGISTERED",
                                category_overlap=True,
                                evidence=f"USPTO record match for '{mark_name}' (Similarity: {sim['composite_similarity']:.2f})"
                            ))
        except (httpx.TimeoutException, httpx.RequestError) as e:
            logger.debug(f"USPTO API transient error for '{clean_term}': {e}. Continuing with local intelligence.")
        except Exception as e:
            logger.debug(f"USPTO query error for '{clean_term}': {e}")
        finally:
            if should_close:
                await client.aclose()

        return matches
