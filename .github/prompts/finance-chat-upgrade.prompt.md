---
mode: agent
description: "Use when implementing the complete Finance Chat feature for pas-svc. Build the entire feature in one shot with all capabilities integrated."
---

# Finance Chat Feature Implementation

Implement a comprehensive finance-only chat system that handles portfolio Q&A, ticker research, what-if simulation, and interactive follow-ups.

## Core Files to Use

[chat_agent.py](../../chat_agent.py), [main.py](../../main.py), [schemas.py](../../schemas.py), [memory.py](../../memory.py), [market_service.py](../../market_service.py), [agents.py](../../agents.py), [ui/app.js](../../ui/app.js), [ui/index.html](../../ui/index.html), [ui/styles.css](../../ui/styles.css), [README.md](../../README.md), [ARCHITECTURE_ONE_PAGER.md](../../ARCHITECTURE_ONE_PAGER.md).

## Implementation Rules

- Implement all capabilities as one cohesive system.
- Keep the existing `/chat` endpoint working; extend contracts as needed.
- Validate all edited files before finishing.
- Update docs to reflect the final architecture.
- Provide a complete summary of what was built and tested.

## Complete Feature Specification

### Feature Goal

Make chat a highly interactive, finance-only assistant that answers:
- Portfolio Q&A (diversification, sector weights, risk, compliance)
- Ticker research for any finance ticker
- Portfolio what-if simulations
- Finance education and explanations
- And refuses all non-finance topics with helpful redirection

### Core Capabilities

**1. Finance-Only Domain Gate**
- Refuse unrelated prompts like coding help, jokes, trivia, politics, health, personal topics
- Implement backend guardrails before Gemini is called
- Reply with short helpful message redirecting to supported topics
- Use deterministic backend checks, not prompt-only

**2. Intent Routing & Entity Extraction**
Detect and classify user intent as one of:
- `portfolio_question`: "Is my portfolio diversified?" "What sectors am I exposed to?"
- `ticker_question`: "Tell me about NVDA" "How does JPM compare to MSFT?"
- `portfolio_what_if`: "What if I reduce AAPL to 10%?" "What if I add XLV?"
- `portfolio_comparison`: "How does my portfolio fit with XLV?" "Compare AAPL vs my allocation"
- `finance_general`: "Explain Sharpe ratio" "What is diversification?"
- `out_of_scope`: Non-finance topics

Extract useful entities:
- Ticker symbols (AAPL, MSFT, XLV, XOM, etc.)
- Sectors (healthcare, tech, financial, energy, etc.)
- Compare intent, explain intent, what-if intent

**3. Rich Finance Context Builder**
For portfolio questions, assemble context from latest analysis result:
- Sector weights and allocations
- Concentration data (top 10 holdings, Herfindahl index)
- Top risk contributors
- Volatility, VaR, max drawdown
- Benchmark comparison
- Compliance status and violations
- Portfolio characteristics (dividend yield, tax-loss harvesting opportunity, etc.)

For ticker questions, fetch from market_service:
- Sector and industry
- Market cap
- P/E, P/B, dividend yield if available
- Beta or volatility
- Recent performance snapshot
- Valuation vs benchmark

**4. Robust Gemini Response Handling**
- Handle fenced JSON (```json ... ```)
- Strip leading/trailing prose
- Partial JSON extraction
- Retry once with repair prompt if parsing fails
- Keep deterministic fallback as final safety net
- Log parse failures internally

**5. Question-Aware Fallback**
Replace generic fallback with intent-specific responses:
- Diversification question: Use sector weights, concentration
- Risk question: Use volatility, VaR, drawdown, top contributors
- Compliance question: Use rule status and violations  
- Ticker question: Use market data if available
- Include follow-up suggestions matching the topic

**6. API Schema Extension**
Extend chat response with backward-compatible fields:
```
{
  "answer": "...",
  "confidence": 0.9,
  "citations": [...],
  "follow_ups": [...],
  "source": "gemini|fallback",
  "session_id": "...",
  "intent": "portfolio_question|ticker_question|...",
  "entities": {"tickers": ["AAPL"], "sectors": ["tech"]},
  "action_suggestions": ["Explain simply", "Show sector breakdown", "Compare with XLY"],
  "context_used": ["sector_weights", "concentration", "risk_drivers"]
}
```

**7. Session Memory Enhancement**
Store lightweight structured session state:
- `last_intent`: Previous question type
- `last_ticker`: Last researched ticker
- `last_compared_tickers`: Tickers compared
- `last_discussed_topic`: Topic from last answer
- `portfolio_context_snapshot`: Quick ref to latest sector/risk state

Enable follow-ups like:
- "What about healthcare?" (uses last_discussed_topic context)
- "Compare it with my portfolio" (uses last_ticker + portfolio context)
- "Make that simpler" (retains last_intent and entities)

**8. Interactive UI**
- Add clickable action chips after chat responses
- Quick actions: "Explain simply", "Show diversification", "Compare with benchmark", "Suggest alternatives", "Compare tickers"
- Render out-of-scope refusals clearly with finance topic suggestions
- Preserve current visual style
- Keep responsive on desktop and mobile

**9. Portfolio What-If Simulation**
Support requests like:
- "What if I reduce AAPL to 10%?"
- "What if I add XLV to the portfolio?"
- "What if I replace XOM with V?"

For each what-if:
- Parse the requested change
- Create temporary hypothetical portfolio
- Reuse analysis engine to compute impact
- Compare current vs hypothetical on: volatility, concentration, compliance, diversification
- Return concise summary with clear before/after metrics

**10. Guardrails & Error Handling**
- Finance-only check happens first in request pipeline
- Out-of-scope is detected early and refused deterministically
- Parsing failures are caught and logged, fallback used
- What-if parse errors are handled clearly
- Missing data is explicit ("data not available")
- Session memory remains bounded (max recent messages, max state keys)

### Acceptance Criteria

**Finance Domain Gate**
- ✅ Finance questions still work
- ✅ Non-finance questions refused before Gemini
- ✅ UI doesn't break
- ✅ [README.md](../../README.md) documents supported scope

**Intent & Routing**
- ✅ "Is my portfolio diversified?" → portfolio_question
- ✅ "Tell me about NVDA" → ticker_question
- ✅ "What if I reduce AAPL to 10%?" → portfolio_what_if
- ✅ "Explain Sharpe ratio" → finance_general
- ✅ Out-of-scope prompts refuse cleanly

**Context & Answers**
- ✅ Diversification questions answered with sector/concentration context
- ✅ Risk questions answered with volatility/VaR/drawdown context
- ✅ Ticker research works for any ticker
- ✅ Portfolio fit questions combine ticker + portfolio context
- ✅ Fallback is intent-aware, not generic

**Parsing & Robustness**
- ✅ Fenced JSON parses successfully
- ✅ Gemini formatting drift doesn't cause immediate fallback
- ✅ Parse failures logged but don't break chat
- ✅ Fallback frequency reduced significantly

**API & UI**
- ✅ Chat response includes intent, entities, action_suggestions, context_used
- ✅ Existing frontend compatible (new fields ignored if not used)
- ✅ Action chips render and are clickable
- ✅ Follow-ups driven by response data and context
- ✅ Responsive on desktop and mobile

**Session & Follow-Ups**
- ✅ Follow-up questions resolve using prior context
- ✅ Session memory is bounded and simple
- ✅ Works without long history payloads from client

**What-If Simulation**
- ✅ Common what-if patterns parse and simulate
- ✅ Results compare current vs hypothetical clearly
- ✅ Parse errors handled gracefully
- ✅ Reuses existing analysis engine

**Testing & Documentation**
- ✅ Tests cover: guardrails, routing, parsing, fallback, ticker mode, what-if, refusal
- ✅ Diagnostics logged for: Gemini parse failures, fallback reason, routing result
- ✅ [README.md](../../README.md) and [ARCHITECTURE_ONE_PAGER.md](../../ARCHITECTURE_ONE_PAGER.md) updated with final design

### Implementation Notes

- Built as one integrated system, not phases
- All components work together: guardrails → routing → context → prompt → parse → fallback / response
- Session memory is bounded in-memory, no database
- What-if uses existing analysis; no new heavy analytics
- UI enhancements are visual only, no new endpoints
- Backward compatible: existing UI still works with old response shape
- Modular design: each component (guardrails, router, context, fallback) can be tested independently

### Delivery Checklist

- [ ] Finance guardrails implemented and tested
- [ ] Intent router working for all 6+ intents
- [ ] Context builders populate sector, risk, ticker, portfolio data
- [ ] Gemini parsing handles fenced/malformed JSON
- [ ] Question-aware fallback replaces generic fallback
- [ ] Session memory tracks intent/ticker/topic/context
- [ ] API response shape extended with intent/entities/actions/context
- [ ] UI action chips render and work
- [ ] What-if simulation parses and computes
- [ ] All acceptance criteria passing
- [ ] Docs updated
- [ ] Tests and diagnostics in place

### Summary

Implement a complete, integrated finance chat system that answers portfolio and ticker questions, simulates what-if scenarios, provides interactive follow-ups, and gracefully refuses non-finance topics. Use all capabilities working together as one system.
