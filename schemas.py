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


class ChatMessage(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: Optional[str] = Field(default=None, max_length=128)
    mode: Literal['advanced', 'simple'] = 'advanced'
    use_latest_analysis: bool = True
    history: List[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    confidence: Literal['high', 'medium', 'low']
    source: Literal['gemini', 'deterministic_fallback', 'guardrails']
    intent: Optional[str] = Field(default=None, description="Detected intent: portfolio_question, ticker_question, portfolio_what_if, portfolio_comparison, compliance_check, risk_analysis")
    entities: dict = Field(default_factory=dict, description="Extracted entities: tickers, sectors, etc.")
    action_suggestions: List[str] = Field(default_factory=list, description="Portfolio-focused follow-up actions (e.g., Compliance Check, Risk Analysis)")
    context_used: List[str] = Field(default_factory=list, description="Context fields used to generate answer")
