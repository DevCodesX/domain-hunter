"""
Classifier adapters for Phase 3/4 test compatibility.
Provides NamingType enum and re-exports NamingTypeClassifier with
an enum-returning classify() interface.
"""

from enum import Enum
from typing import Dict, Any, Optional
from quality_engine.naming_classifier import NamingTypeClassifier as _BaseNamingTypeClassifier


class NamingType(str, Enum):
    """Standard naming type classifications."""
    ONE_WORD = "ONE_WORD"
    REAL_WORD = "REAL_WORD"
    FOREIGN_WORD = "FOREIGN_WORD"
    COMPOUND = "COMPOUND"
    INVENTED = "INVENTED"
    PREFIX_SUFFIX = "PREFIX_SUFFIX"
    HYBRID = "HYBRID"
    SEMANTIC_BRAND = "SEMANTIC_BRANDABLE"
    SEMANTIC_BRANDABLE = "SEMANTIC_BRANDABLE"
    RANDOM = "RANDOM"
    OTHER = "OTHER"


class NamingTypeClassifier(_BaseNamingTypeClassifier):
    """
    Extended NamingTypeClassifier that returns NamingType enum values
    when classify() is called, instead of a dict.
    """

    def classify(self, domain_or_label: str) -> NamingType:
        """
        Classifies a domain and returns a NamingType enum value.
        Delegates to the base classifier and extracts the naming_type string.
        """
        result = super().classify(domain_or_label)
        if isinstance(result, dict):
            nt_str = result.get("naming_type", "INVENTED")
        else:
            nt_str = str(result)

        # Map to enum
        try:
            return NamingType(nt_str)
        except ValueError:
            # Try common mappings
            mapping = {
                "REAL_WORD": NamingType.ONE_WORD,
                "COINED": NamingType.INVENTED,
                "SEMANTIC_BRANDABLE": NamingType.SEMANTIC_BRAND,
            }
            return mapping.get(nt_str, NamingType.INVENTED)
