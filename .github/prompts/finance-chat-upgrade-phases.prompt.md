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

## Phase 1

Goal: Finance-only domain gate and safer chat boundary

Prompt:

Implement phase 1 of the finance chat upgrade in this repo.

Objective:
Make chat finance-only. The chat must answer only portfolio, investing, finance, benchmark, sector, risk, valuation, diversification, rebalancing, ETF, index, and ticker-related questions. It must refuse unrelated prompts like coding help, jokes, general trivia, politics, health, or personal topics.

Requirements:
- Add a backend guardrail layer before Gemini is called.
- Keep the existing chat endpoint working.
- Refuse out-of-scope prompts with a short helpful response that redirects users to supported finance topics.
- Do not rely only on prompt wording. Implement deterministic backend checks.
- Preserve current response shape unless a small backward-compatible extension is necessary.
- Keep changes minimal and consistent with the existing style.

Suggested implementation:
- Add a finance-domain classifier or guardrail helper.
- Integrate it into the current chat flow in [chat_agent.py](../../chat_agent.py) or [main.py](../../main.py).
- Reuse current chat response fields where possible.
- Add at least a few obvious allow and deny heuristics.

Acceptance criteria:
- Finance questions still work.
- Non-finance questions are refused before Gemini is used.
- Existing UI does not break.
- Update [README.md](../../README.md) with the supported chat scope.

Also:
- Add tests if there is an existing test pattern; otherwise add minimal validation coverage in a pragmatic way.
- Summarize exactly what changed and any remaining limitations.

## Phase 2

Goal: Intent routing for portfolio, ticker, and what-if requests

Prompt:

Implement phase 2 of the finance chat upgrade in this repo.

Objective:
Add a deterministic intent router for chat so the system can distinguish between:
- portfolio_question
- ticker_question
- portfolio_what_if
- finance_general
- out_of_scope

Requirements:
- Build routing before final answer generation.
- Extract useful entities from the user message:
  - ticker symbols
  - sectors
  - compare intent
  - explain intent
  - what-if or rebalance intent
- Keep the system conservative: if unsure, prefer finance_general over overfitting.
- Integrate cleanly with the current chat flow in [chat_agent.py](../../chat_agent.py).

Implementation notes:
- Start with deterministic heuristics and regex-style extraction.
- Do not overengineer with a full NLP stack.
- Return structured routing output that later phases can reuse.

Acceptance criteria:
- “Is my portfolio diversified?” routes to portfolio_question.
- “Tell me about NVDA” routes to ticker_question.
- “What if I reduce AAPL to 10%?” routes to portfolio_what_if.
- “Explain Sharpe ratio” routes to finance_general or portfolio_question depending on context.
- Out-of-scope prompts still refuse cleanly.

Also:
- Keep the code modular so later phases can plug in context builders.
- Document the routing categories briefly in [README.md](../../README.md).

## Phase 3

Goal: Finance context builder with real portfolio and sector context

Prompt:

Implement phase 3 of the finance chat upgrade in this repo.

Objective:
Improve chat context so diversification, sector, risk, and portfolio-fit questions can be answered properly.

Requirements:
- Build a structured finance context layer used by chat.
- For portfolio questions, include:
  - sector weights
  - concentration data
  - top risk contributors
  - benchmark summary
  - portfolio characteristics
  - compliance status and violations
- Reuse data already produced by analysis in [agents.py](../../agents.py).
- Do not duplicate heavy analytics if the latest result already contains the needed fields.

Important:
The current chat context is too thin for diversification questions. Fix that by pulling in the right fields from the latest analysis result.

Acceptance criteria:
- A question like “is my portfolio diversified?” can be answered using actual sector/concentration context.
- A question like “what sector am I overweight in?” can be answered from latest analysis.
- The chat response should cite the relevant structured context fields when possible.

Also:
- Keep the context builder modular for later ticker mode.
- Update any docs if the internal architecture meaningfully changes.

## Phase 4

Goal: Harden Gemini response handling and parsing

Prompt:

Implement phase 4 of the finance chat upgrade in this repo.

Objective:
Make Gemini response handling robust so chat does not frequently fall back due to malformed model output.

Requirements:
- Improve parsing in [chat_agent.py](../../chat_agent.py).
- Handle:
  - fenced JSON
  - extra leading or trailing prose
  - partial JSON extraction when valid
- If parsing fails, retry once with a repair-style prompt or a tighter formatting prompt.
- Keep fallback behavior as a final safety net.
- Add internal logging or diagnostics for parse failures without exposing noisy internals to the UI.

Important:
Do not break the current response contract. Keep the returned answer clean.

Acceptance criteria:
- Fenced JSON parses successfully.
- Typical Gemini formatting drift no longer causes immediate fallback.
- Fallback frequency should drop.
- The code remains readable and not overly complex.

Also:
- Keep generation settings in [gemini_client.py](../../gemini_client.py) configurable if needed.
- Summarize the new fallback path and retry behavior.

## Phase 5

Goal: Ticker research mode for any finance ticker

Prompt:

Implement phase 5 of the finance chat upgrade in this repo.

Objective:
Allow chat to answer questions about any finance ticker, even if it is not in the current portfolio.

Requirements:
- Add ticker research support using [market_service.py](../../market_service.py).
- For ticker questions, build a compact context including:
  - sector
  - market cap
  - valuation fields if available
  - dividend yield
  - beta or similar risk indicators if available
  - recent performance snapshot if practical
- Support simple compare questions like:
  - “AAPL vs MSFT”
  - “How does XOM fit with my portfolio?”
- If the user asks about portfolio fit, combine ticker context with latest portfolio context.

Constraints:
- Stay within the existing data sources.
- Do not invent unsupported fundamentals.
- Be explicit when data is missing.

Acceptance criteria:
- “Tell me about NVDA” returns a finance-grounded answer.
- “Compare JPM and MSFT” returns a useful comparison.
- “How would XLV fit with my portfolio?” references current portfolio context.

Also:
- Keep the code extensible for later what-if simulation.
- Update [README.md](../../README.md) to mention any-ticker chat support.

## Phase 6

Goal: Question-aware fallback instead of generic fallback

Prompt:

Implement phase 6 of the finance chat upgrade in this repo.

Objective:
Replace the current generic fallback answer with intent-aware fallback behavior.

Requirements:
- Keep fallback deterministic and grounded.
- For diversification questions, fallback should use sector weights and concentration.
- For risk questions, fallback should use volatility, VaR, drawdown, and top contributors.
- For compliance questions, fallback should use rule status and violations.
- For ticker questions, fallback should use deterministic market/fundamental data when available.
- Follow-up suggestions must match the user’s topic.

Important:
The fallback should no longer return the same generic summary for different user questions.

Acceptance criteria:
- “Is it diversified?” fallback discusses diversification.
- “Why is my risk high?” fallback discusses actual risk drivers.
- “Is this compliant?” fallback discusses compliance.
- “Tell me about TSLA” fallback uses ticker data if Gemini fails.

Also:
- Keep responses concise and practical.
- Preserve the current chat endpoint contract.

## Phase 7

Goal: Interactive UI with action chips and richer chat state

Prompt:

Implement phase 7 of the finance chat upgrade in this repo.

Objective:
Upgrade the chat UI from basic Q&A into an interactive finance assistant.

Requirements:
- Enhance the chat panel in [ui/index.html](../../ui/index.html), [ui/app.js](../../ui/app.js), and [ui/styles.css](../../ui/styles.css).
- Add clickable follow-up actions after answers.
- Add quick actions such as:
  - Explain simply
  - Show diversification view
  - Compare with benchmark
  - Suggest lower-risk alternatives
  - Compare tickers
- Make out-of-scope refusals render clearly and still offer supported finance prompts.
- Preserve the current visual style of the app.

Acceptance criteria:
- Chat feels interactive rather than static.
- Users can continue with one-click follow-up actions.
- The UI stays responsive and readable on desktop and mobile.
- Existing analysis UI still works.

Also:
- Keep the changes visually consistent with the current design language.
- Avoid unnecessary rework of unrelated frontend areas.

## Phase 8

Goal: Extend API response shape for richer chat interactions

Prompt:

Implement phase 8 of the finance chat upgrade in this repo.

Objective:
Extend the chat API so the frontend can render richer interactive behavior.

Requirements:
- Extend the chat response in [schemas.py](../../schemas.py) and [main.py](../../main.py) with backward-compatible fields such as:
  - intent
  - entities
  - action_suggestions
  - context_used
- Keep existing fields intact so current UI behavior still works if the new fields are ignored.
- Populate the new fields from the router and context builder.

Acceptance criteria:
- The chat response includes structured intent and suggestions.
- Existing frontend behavior remains compatible.
- New UI actions can be driven by response data rather than hardcoded chips alone.

Also:
- Keep the schema changes minimal and explicit.
- Document the new response fields in [README.md](../../README.md).

## Phase 9

Goal: Structured session memory for follow-up questions

Prompt:

Implement phase 9 of the finance chat upgrade in this repo.

Objective:
Improve conversational continuity so short follow-up questions resolve correctly.

Requirements:
- Extend session memory in [memory.py](../../memory.py) to keep lightweight structured chat state, not just raw message history.
- Track useful context such as:
  - last intent
  - last ticker
  - last compared tickers
  - last discussed topic
- Use this state in chat so follow-ups like:
  - “what about healthcare?”
  - “compare it with my portfolio”
  - “make that simpler”
can resolve correctly.

Acceptance criteria:
- Follow-up finance prompts use prior context within the session.
- Session memory remains bounded and simple.
- The feature still works without long history payloads from the client.

Also:
- Do not add a database; keep it in memory for now.
- Preserve current session_id behavior.

## Phase 10

Goal: Portfolio what-if simulation

Prompt:

Implement phase 10 of the finance chat upgrade in this repo.

Objective:
Allow users to ask simple what-if portfolio questions and receive grounded answers.

Requirements:
- Support requests like:
  - “What if I reduce AAPL to 10%?”
  - “What if I add XLV?”
  - “What if I replace XOM with V?”
- Parse the requested change.
- Create a temporary hypothetical portfolio.
- Reuse existing analysis capabilities where practical.
- Return a concise summary of impact on:
  - volatility
  - concentration
  - compliance
  - diversification

Constraints:
- Keep the first version simple and robust.
- Do not attempt full natural-language optimization of arbitrary portfolio rewrites.

Acceptance criteria:
- At least a few common what-if patterns work reliably.
- The resulting answer clearly compares current vs hypothetical state.
- Errors are handled clearly when the request cannot be parsed.

Also:
- Keep the code modular so later simulation improvements are easy.

## Phase 11

Goal: Tests, diagnostics, and documentation cleanup

Prompt:

Implement phase 11 of the finance chat upgrade in this repo.

Objective:
Stabilize the feature with tests, diagnostics, and documentation.

Requirements:
- Add tests for:
  - finance guardrails
  - intent routing
  - parsing robustness
  - fallback behavior
  - ticker questions
  - out-of-scope refusal
- Add pragmatic diagnostics for:
  - Gemini parse failures
  - fallback reason
  - routing result
- Update [README.md](../../README.md) and [ARCHITECTURE_ONE_PAGER.md](../../ARCHITECTURE_ONE_PAGER.md) to reflect the final finance chat design.

Acceptance criteria:
- Core finance chat paths are covered.
- Docs match the implemented system.
- Diagnostics make future chat debugging easier.
