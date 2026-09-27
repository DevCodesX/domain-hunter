"""
Domain Hunter - Risk Engine Data Models & Enums
Defines risk levels, brand statuses, match details, and risk reports.
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import datetime

class RiskLevel(str, Enum):
    NOT_CHECKED = "NOT_CHECKED"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class BrandStatus(str, Enum):
    NO_SIGNIFICANT_USE = "NO_SIGNIFICANT_USE"
    MINOR_USE = "MINOR_USE"
    ACTIVE_BUSINESS = "ACTIVE_BUSINESS"
    ESTABLISHED_BRAND = "ESTABLISHED_BRAND"
    FAMOUS_BRAND = "FAMOUS_BRAND"

class MatchType(str, Enum):
    EXACT = "EXACT"
    PHONETIC = "PHONETIC"
    SIMILAR_STRING = "SIMILAR_STRING"
    TOKEN_OVERLAP = "TOKEN_OVERLAP"
    PREFIX_SUFFIX_VARIANT = "PREFIX_SUFFIX_VARIANT"

class TrademarkMatch(BaseModel):
    trademark_name: str
    source: str
    match_type: MatchType
    similarity_score: float # 0.0 to 1.0
    status: str = "REGISTERED"
    category_overlap: bool = False
    evidence: str = ""

class ExistingBrandMatch(BaseModel):
    brand_name: str
    brand_status: BrandStatus
    confidence: float # 0.0 to 1.0
    source: str = "curated_brand_intelligence"
    evidence: str = ""

class IPRiskReport(BaseModel):
    domain: str
    ip_risk_level: RiskLevel = RiskLevel.NOT_CHECKED
    ip_check_status: str = "NOT_CHECKED" # "CHECKED", "NOT_CHECKED", "FAILED"
    ip_risk_score: int = 0 # 0 (no risk) to 100 (critical risk)
    exact_match_count: int = 0
    similar_match_count: int = 0
    brand_match_count: int = 0
    provider: str = "USPTO / Curated Brand Engine"
    disclaimer: str = "IP/trademark screening is a risk signal, not legal advice or legal clearance."
    trademark_matches: List[Dict[str, Any]] = Field(default_factory=list)
    brand_matches: List[Dict[str, Any]] = Field(default_factory=list)
    negative_associations: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    decision: str = "PASS" # PASS, REVIEW, REJECT
    reasons: List[str] = Field(default_factory=list)
    contributing_sources: List[str] = Field(default_factory=list)
    sources: Dict[str, Any] = Field(default_factory=dict)
    checked_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    def is_eligible(self) -> bool:
        """CRITICAL risk is strictly ineligible (REJECT). HIGH requires human review. LOW, MEDIUM, NOT_CHECKED are eligible."""
        return self.ip_risk_level != RiskLevel.CRITICAL
