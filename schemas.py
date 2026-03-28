from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class PortfolioItem(BaseModel):
    ticker: str
    weight: float


class ComplianceRules(BaseModel):
    single_asset_max: Optional[float] = None
    sector_max: Optional[float] = None
    min_assets: Optional[int] = None
    max_assets: Optional[int] = None
    min_weight: Optional[float] = None
    min_sectors: Optional[int] = None
    weight_sum_tolerance: Optional[float] = None


class AnalysisConfig(BaseModel):
    benchmark: str = 'SPY'
    risk_profile: Literal['conservative', 'moderate', 'aggressive'] = 'moderate'
    mode: Literal['advanced', 'simple'] = 'advanced'
    stress_test: bool = True
    compliance_rules: ComplianceRules = Field(default_factory=ComplianceRules)


class PortfolioRequest(BaseModel):
    portfolio: List[PortfolioItem]
    analysis_config: AnalysisConfig = Field(default_factory=AnalysisConfig)

class RiskMetrics(BaseModel):
    volatility: float
    sharpe: float
    var_95: float
    beta: Optional[float]

class ComplianceResult(BaseModel):
    ok: bool
    issues: List[str]
    violations: List[dict] = Field(default_factory=list)

class AnalysisResult(BaseModel):
    portfolio: List[PortfolioItem]
    risk: dict
    compliance: ComplianceResult
    insights: Optional[dict]
