from typing import List, Optional
from pydantic import BaseModel

class PortfolioItem(BaseModel):
    ticker: str
    weight: float

class PortfolioRequest(BaseModel):
    portfolio: List[PortfolioItem]

class RiskMetrics(BaseModel):
    volatility: float
    sharpe: float
    var_95: float
    beta: Optional[float]

class ComplianceResult(BaseModel):
    ok: bool
    issues: List[str]

class AnalysisResult(BaseModel):
    portfolio: List[PortfolioItem]
    risk: dict
    compliance: ComplianceResult
    insights: Optional[str]
