# AI Portfolio Analysis System

This project is a FastAPI-based portfolio analysis service with a single-page demo UI. It combines market data, policy checks, and Gemini-generated commentary behind a lightweight multi-agent orchestration layer.

The current implementation is optimized for a demo flow:

- structured portfolio input in the browser
- parallel risk and compliance execution
- reporting after analysis context is available
- live status streaming to the UI via server-sent events

## What It Does

Given a portfolio of tickers and weights, the service:

1. pulls recent market data for each asset
2. computes portfolio and per-asset risk metrics
3. checks the portfolio against basic compliance rules
4. generates AI commentary using Gemini
5. aggregates the outputs into a single result payload
6. optionally streams stage-by-stage progress to the UI

## Architecture

The app has four main layers.

### 1. API and UI Layer

Implemented in [main.py](main.py).

- serves the FastAPI API
- serves the static demo UI from `ui/`
- exposes a standard analysis endpoint and a streaming analysis endpoint
- exposes a Gemini diagnostic endpoint
- stores the latest result in an in-memory store for quick retrieval

### 2. Orchestration Layer

Implemented primarily in [agents.py](agents.py), with an adapter in [langgraph_orchestrator.py](langgraph_orchestrator.py).

- `SupervisorAgent` coordinates execution across the other agents
- Risk and Compliance run in parallel using `ThreadPoolExecutor`
- Reporting runs after both complete so it can use full analysis context
- Aggregator merges outputs into a single response shape
- `langgraph_orchestrator.py` currently acts as a compatibility wrapper and falls back to the supervisor flow if LangGraph is unavailable or incompatible

### 3. Analysis Agents

Implemented in [agents.py](agents.py).

- `RiskAgent`: computes per-asset and portfolio metrics including annualized volatility, Sharpe ratio, historical 95% VaR, beta versus SPY, and weighted fundamentals (forward P/E, dividend yield, analyst upside, total market cap, coverage)
- `ComplianceAgent`: checks minimum asset count, max single-asset concentration, and max sector concentration
- `ReportingAgent`: builds a structured prompt from analysis results (including enriched fundamentals) and requests a concise investment note from Gemini; if Gemini fails or returns weak output, it falls back to a deterministic summary
- `Aggregator`: normalizes the final output into a single object consumed by the UI and `/results`

### 4. Integration and Storage Layer

- [market_service.py](market_service.py): wraps `yfinance` to fetch prices, sector metadata, and per-ticker fundamentals
- [gemini_client.py](gemini_client.py): wraps `google-genai`, normalizes environment variables, lists available models, and performs model fallback when possible
- [memory.py](memory.py): simple thread-safe in-memory store for the latest analysis result

## Logic Flow

### Non-streaming flow

`POST /analyze`

1. FastAPI validates the request using `PortfolioRequest`
2. The portfolio is converted to plain dictionaries
3. `langgraph_orchestrator.orchestrate(...)` is called
4. The orchestrator delegates to `SupervisorAgent.run(...)`
5. Risk and Compliance execute in parallel
6. Reporting runs after both are available
7. Aggregation is performed
8. The result is stored in memory and returned to the client

### Streaming flow

`POST /analyze/stream`

1. FastAPI validates the request
2. An `asyncio.Queue` is created for cross-thread event delivery
3. The supervisor runs in a worker thread
4. Each stage emits events such as `started`, `agent_running`, `agent_done`, `agent_error`, and `aggregated`
5. FastAPI exposes those events as `text/event-stream`
6. The browser consumes the stream and updates the pipeline diagram, activity log, and result cards in real time

### Execution order

The effective runtime sequence is:

```text
Portfolio Input
    |
    v
Supervisor
    |
    +--> Risk Agent -----------+
    |                          |
    +--> Compliance Agent -----+--> Reporting Agent --> Aggregator
```

Risk and Compliance run concurrently. Reporting waits for both outputs so the Gemini prompt can include both market and policy context.

## Business Logic Summary

### Risk logic

- Downloads 1 year of price history per ticker
- Computes daily returns per asset
- Calculates per-asset annualized volatility and annualized mean return
- Fetches per-asset fundamentals (sector, industry, valuation, yield, market cap, analyst target, and quality/leverage fields)
- Builds weighted portfolio returns
- Calculates portfolio annualized volatility
- Calculates Sharpe ratio using a fixed 1% annual risk-free rate assumption
- Calculates annualized historical 95% VaR from the portfolio return distribution
- Estimates beta versus SPY when benchmark data is available
- Computes weighted portfolio fundamentals and coverage diagnostics for the UI and report context

### Compliance logic

Current policy rules in code:

| Parameter | Default | Rule |
|---|---|---|
| `min_assets` | `4` | Minimum number of holdings |
| `max_assets` | `20` | Maximum number of holdings |
| `single_asset_max` | `40%` | No single asset above this weight |
| `min_weight` | `2%` | No position below this weight |
| `sector_max` | `60%` | No sector above this combined weight |
| `min_sectors` | `2` | Minimum number of distinct sectors |
| `weight_sum_tolerance` | `±2%` | Portfolio weights must sum to ~100% |

All parameters are set in `ComplianceAgent.__init__()` and can be adjusted there.

### Reporting logic

- Builds a structured summary from holdings, risk metrics, fundamentals snapshot, and compliance findings
- Requests a short markdown-formatted investment note from Gemini
- Uses a deterministic fallback summary if Gemini is unavailable or the response is too weak

## Third-Party Integrations

### Google Gemini via `google-genai`

Used in [gemini_client.py](gemini_client.py).

- primary purpose: generate the AI Insights narrative
- model name is configurable via `GEMINI_MODEL`
- API key is read from `GEMINI_API_KEY`
- supports model-name normalization for common copy/paste mistakes
- supports fallback across preferred models when the requested model is unavailable
- exposes diagnostics through `GET /debug/gemini`

### Yahoo Finance via `yfinance`

Used in [market_service.py](market_service.py).

- fetches historical close prices
- fetches sector metadata per ticker
- fetches enriched ticker fundamentals (valuation, yield, analyst, quality/leverage, liquidity fields)
- acts as the source for both risk calculations and compliance sector rollups

### LangGraph

Included as a dependency, but the current implementation uses it as an optional compatibility layer rather than a fully modeled graph.

- if available, the adapter can attach lightweight flow metadata
- if unavailable or incompatible, execution falls back to `SupervisorAgent`
- current system behavior does not depend on LangGraph to function

## Project Structure

```text
main.py                  FastAPI app, routes, SSE streaming, static UI serving
agents.py                Supervisor + Risk/Compliance/Reporting/Aggregator agents
gemini_client.py         Gemini SDK wrapper, env normalization, model fallback
market_service.py        Market data, sector, and fundamentals lookups via yfinance
langgraph_orchestrator.py Optional LangGraph adapter with safe fallback
memory.py                Thread-safe in-memory result store
schemas.py               Pydantic request/response models
ui/                      Single-page demo UI (includes fundamentals snapshot tiles)
requirements.txt         Python dependencies
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

## Environment Variables

Create a `.env` file inside `pas-svc/`:

```dotenv
GEMINI_API_KEY=your_google_api_key_here
GEMINI_MODEL=gemini-2.0-flash
```

Notes:

- `GEMINI_MODEL` is optional; the code defaults to `gemini-2.0-flash`
- copied values such as `GEMINI_MODEL=gemini-1.5-flash` are normalized in code
- copied values such as `GEMINI_API_KEY=AIza...` are also normalized in code

For Vercel deployment, add the same variable names in the Vercel Environment Variables UI and paste only the raw value into each field.

Example:

- correct value for `GEMINI_API_KEY`: `AIza...`
- incorrect value for `GEMINI_API_KEY`: `GEMINI_API_KEY=AIza...`

Obtain a key from https://aistudio.google.com/app/apikey and ensure the Generative Language API is enabled for the related Google project.

## Run Locally

From inside `pas-svc`:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Open the UI at:

```text
http://localhost:8000/
```

## API Endpoints

- `GET /` - serves the demo UI
- `POST /analyze` - runs portfolio analysis and returns the full result object
- `POST /analyze/stream` - streams stage-by-stage analysis events for the UI
- `GET /results` - returns the last in-memory analysis result
- `GET /debug/gemini` - performs a Gemini connectivity diagnostic

## Known Constraints

- the in-memory result store is process-local and not durable
- `yfinance` responses may vary in latency or completeness across tickers
- the current LangGraph integration is a fallback adapter, not a full graph-native workflow
- Gemini access depends on a valid, non-restricted API key and enabled project APIs
