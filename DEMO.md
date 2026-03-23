# Portfolio Analysis System — Demo Presentation

## Overview

This document is a structured walkthrough for the live demo of the **AI Portfolio Analysis System (PAS)**. It covers the problem context, the system architecture, each agent's role, what to show in the UI, and talking points for questions.

---

## Slide 1 — Problem Statement

**The challenge:** Analysing a multi-asset portfolio requires three types of expertise working in parallel — market risk quantification, regulatory and policy compliance, and narrative reporting. Done manually, these steps happen sequentially and require different people or tools.

**The opportunity:** An AI-native orchestration layer can coordinate specialist agents concurrently and produce a complete, human-readable investment note in seconds — not hours.

---

## Slide 2 — What We Built

> A Phase 2 multi-agent orchestration platform that analyses a portfolio, surfaces risk and compliance signals, generates AI commentary, and streams every step live to a visual dashboard.

Key capabilities:

| Capability | Detail |
|---|---|
| Parallel agent execution | Risk and Compliance agents run at the same time |
| Context-aware AI reporting | Gemini receives both risk and compliance context before generating insights |
| Live event streaming | Browser receives stage-by-stage events via SSE as agents complete |
| Compliance rule engine | Flags concentration and sector limit breaches in real time |
| Deterministic fallback | AI Insights degrade gracefully if Gemini is unavailable |

---

## Slide 3 — Architecture

```
Browser (Portfolio Input)
        |
        v
  FastAPI (main.py)
        |
        v
LangGraph Orchestrator (adapter)
        |
        v
  Supervisor Agent
        |
        +------------------+
        |                  |
     Risk Agent      Compliance Agent         ← parallel
        |                  |
        +------------------+
               |
        Reporting Agent                       ← waits for both
        (Gemini via google-genai)
               |
           Aggregator
               |
        Result  +  SSE Events → Browser
```

**Runtime layers:**

1. **API / UI layer** — FastAPI serves the REST endpoints and the single-page UI from the same process on port 8000.
2. **Orchestration layer** — `SupervisorAgent` manages parallel execution via `ThreadPoolExecutor`. Events are pushed to an `asyncio.Queue` linked to the SSE stream.
3. **Agent layer** — four focused agents, each responsible for a single concern.
4. **Integration layer** — `yfinance` for market data, `google-genai` SDK for Gemini, in-memory thread-safe store for the latest result.

---

## Slide 4 — The Agents

### Risk Agent
- Downloads 1 year of daily price history per ticker from Yahoo Finance
- Computes annualized volatility and mean return per asset
- Constructs weighted portfolio daily returns
- Outputs: **Volatility**, **Sharpe Ratio**, **Historical 95% VaR**, **Beta vs SPY**

### Compliance Agent
- Checks seven policy rules simultaneously with Risk:
  - Weights must sum to **100% ± 2%** (weight integrity check)
  - Minimum **4** assets in the portfolio
  - Maximum **20** assets in the portfolio
  - No single asset above **40%** weight
  - No position below **2%** weight (blocks trivial allocations)
  - No single sector above **60%** weight
  - Minimum **2** distinct sectors (sector diversification)
- Outputs: pass/fail verdict, list of issues, sector breakdown

### Reporting Agent
- Waits for both Risk and Compliance to complete
- Builds a structured prompt containing: holdings, risk metrics, compliance verdict, and sector exposure
- Calls Gemini and requests a three-section investment note:
  - **Overall Take** — largest holding, volatility, Sharpe summary
  - **Risk Readout** — VaR, Beta, top sector concentration
  - **Compliance / Actions** — outcome, recommended next step
- Falls back to a deterministic summary if Gemini fails or returns weak output

### Aggregator
- Merges all agent outputs into a single normalized response
- Writes to the in-memory store so `/results` always returns the latest run

---

## Slide 5 — Third-Party Integrations

### Google Gemini (`google-genai` SDK)
- Used exclusively by the Reporting Agent for narrative generation
- Configurable model via `GEMINI_MODEL` env var
- Preferred model order: `gemini-2.0-flash` → `gemini-2.0-flash-lite` → `gemini-1.5-flash` → `gemini-1.5-pro`
- Runtime model discovery: lists available models and filters fallback candidates at call time
- Diagnostic endpoint: `GET /debug/gemini`

### Yahoo Finance (`yfinance`)
- Fetches 1 year of adjusted close prices for each ticker
- Fetches sector metadata for compliance sector rollups
- All market data is fetched fresh on every analysis run — no caching

### LangGraph
- Installed and available as a future-ready integration point
- Currently acts as a thin wrapper; if unavailable it transparently delegates to the Supervisor
- Intent: replace the `ThreadPoolExecutor` orchestration with a full graph-native workflow in Phase 3

---

## Slide 6 — Live Demo Walkthrough

> Run the server before the session: `uvicorn main:app --host 0.0.0.0 --port 8000`
> Open the browser to `http://localhost:8000/`

### Step 1 — Show the UI
- Point out the **Agent Pipeline** diagram in the centre — all nodes are in "Waiting" state
- Point out the **Activity Log** panel — empty, waiting for events
- Point out the **Portfolio Input** section — pre-loaded with a sample 4-asset portfolio

### Step 2 — Explain the portfolio
The sample portfolio is:
| Ticker | Weight | Sector |
|---|---|---|
| AAPL | 35% | Technology |
| MSFT | 25% | Technology |
| GOOGL | 20% | Technology |
| JNJ | 20% | Healthcare |

Technology exposure is 80% — above the 60% sector limit. This will trigger a compliance flag.

### Step 3 — Click "Run Analysis"
Walk through what is happening live:

- **Risk and Compliance nodes** both turn blue ("Running…") at the same time — *this is the parallel execution happening*
- Activity log entries appear with elapsed timestamps as each agent reacts
- **Risk node** turns green first — the result card populates with live Volatility / Sharpe / VaR / Beta tiles and the per-asset breakdown
- **Compliance node** turns green — the result card shows a **FAIL** badge and the sector bar chart highlighting the Technology breach
- **Reporting node** turns blue — Gemini is being called with full context
- **Reporting node** turns green — AI Insights card populates with the three-section investment note
- **Aggregator** turns green — all done
- **Timings panel** shows the parallel speedup: total time is significantly less than Risk + Compliance combined

### Step 4 — Walk through the AI Insights card
- Point out the three sections: **Overall Take**, **Risk Readout**, **Compliance / Actions**
- Highlight that the Gemini prompt explicitly provided holdings, risk metrics, compliance outcome, and sector exposure — the model had full context before writing
- Highlight the recommended action in the **Compliance / Actions** section

### Step 5 — Show the Timings panel
- The bar chart makes the parallel speedup visual: Risk and Compliance bars are similar in length, but the total is not their sum
- This is the core architecture proof point: concurrency is working

### Step 6 — Test Gemini button (optional)
- Click **Test Gemini** to show the diagnostic directly
- Response shows `connected: true`, the resolved model name, and the raw Gemini reply
- Useful to demonstrate dependency health checks

---

## Slide 7 — Design Decisions Worth Noting

**Why ThreadPoolExecutor rather than async agents?**
The `yfinance` and `google-genai` SDK calls are both synchronous. Running them in a thread pool avoids blocking the FastAPI event loop while still achieving real parallelism.

**Why SSE instead of WebSocket?**
The traffic is one-directional (server → browser). SSE is sufficient, simpler to implement, and compatible with standard `fetch` without a third-party library.

**Why does Reporting wait for Compliance as well as Risk?**
The Gemini prompt needs to describe whether compliance passed or failed to generate an actionable investment note. Running Reporting before Compliance would produce generic output without policy context.

**Why a deterministic fallback for AI Insights?**
For a demo environment, a connectivity failure or quota error should not leave the card blank. The fallback computes the same sections from raw data, ensuring the UI always has a meaningful response.

---

## Slide 8 — API Reference (Quick)

| Method | Path | What it does |
|---|---|---|
| `GET` | `/` | Serves the demo UI |
| `POST` | `/analyze` | Runs analysis, returns full result JSON |
| `POST` | `/analyze/stream` | Runs analysis, streams SSE events |
| `GET` | `/results` | Returns the last analysis result |
| `GET` | `/debug/gemini` | Gemini connectivity check |

---

## Slide 9 — Current Constraints

- Result store is in-memory — not durable across restarts
- Rate limits on the free Gemini tier may cause 429 errors on rapid successive calls; the fallback summary activates automatically
- `yfinance` latency varies by ticker and network conditions
- LangGraph is available as a dependency but not yet a full graph workflow

---

## Slide 10 — Phase 3 Roadmap (Talking Points)

- Replace `ThreadPoolExecutor` with a proper LangGraph state graph, enabling conditional branching and retries per node
- Add a persistent result store (PostgreSQL or Redis) for multi-session history
- Extend the Compliance Agent with configurable rule sets loaded from a policy file
- Add PDF report export from the Reporting Agent output
- Support multi-benchmark beta (vs sector ETFs, not just SPY)
- Add a real-time positions feed via a broker API integration point

---

*Prepared for the Phase 2 Multi-Agent Orchestration demo.*
