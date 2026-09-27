"""
Base Trademark Provider Interface
Abstract class for trademark search providers.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
from risk_engine.models import TrademarkMatch

class TrademarkProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the trademark provider."""
        pass

    @abstractmethod
    async def search(self, term: str) -> List[TrademarkMatch]:
        """
        Searches trademark database for matching or conflicting marks.
        Returns a list of TrademarkMatch objects.
        Must handle exceptions gracefully and return empty list on network/upstream error.
        """
        pass
