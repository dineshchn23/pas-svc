# PAS — Demo Summary (Concise)

## How the system works
- Browser posts a portfolio to FastAPI (/analyze or /analyze/stream).
- Supervisor starts Risk and Compliance agents in parallel (ThreadPoolExecutor).
- Risk: fetches 1yr prices via yfinance, computes per-asset and portfolio metrics (volatility, Sharpe, 95% VaR, Beta vs SPY).
- Compliance: evaluates policy rules (weights sum, min/max assets, per-asset/sector limits, sector diversification).
- Reporting: waits for Risk + Compliance, builds a structured prompt and calls Gemini via google-genai to generate a 3-part investment note.
- Aggregator merges outputs, stores the latest result in-memory, and streams SSE events to the browser.

## Gemini prompt (template)
You are an investment research assistant. Using the provided context, produce a concise three-section investment note (Overall Take; Risk Readout; Compliance / Actions).

Context:
- Holdings: [TICKER weight% ...]
- Portfolio metrics: volatility=X%, Sharpe=Y, 95% VaR=Z%
- Benchmark: SPY, Beta=B
- Weighted fundamentals: {PE, yield, market_cap}
- Compliance: PASS/FAIL + issues

Constraints: max 250 words, actionable tone, include all three sections. If any section is missing or model fails, return an error signal so the deterministic fallback can run.

## API reference (quick)
- GET / — demo UI
- POST /analyze — run analysis synchronously, returns final JSON
- POST /analyze/stream — run analysis and stream SSE events (agent.start/progress/complete, aggregator.complete)
- GET /results — last analysis result
- GET /debug/gemini — Gemini connectivity & resolved model

## Request example
POST /analyze
Content-Type: application/json

{
  "holdings": [
    {"ticker":"AAPL","weight":35.0},
    {"ticker":"MSFT","weight":25.0},
    {"ticker":"GOOGL","weight":20.0},
    {"ticker":"JNJ","weight":20.0}
  ],
  "benchmark": "SPY",
  "as_of_date": "2026-07-01"
}

## Response example (truncated)
{
  "run_id": "run_20260728_0001",
  "status": "complete",
  "agents": {
    "risk": {"status":"success","metrics":{"volatility":0.18,"sharpe":0.85,"var_95":-0.062,"beta":1.05}},
    "compliance": {"status":"fail","issues":["Technology 80% > 60%"]},
    "reporting": {"status":"success","model":"gemini-2.0-flash"}
  },
  "report": {
    "overall_take": "...",
    "risk_readout": "...",
    "compliance_actions": "Reduce Technology exposure below 60%."
  }
}
