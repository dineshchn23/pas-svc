"""Enhanced finance chat agent with guardrails, routing, context, and simulation."""

import json
import logging
from typing import Dict, List, Tuple, Optional

from gemini_client import generate_insights
from chat_guardrails import FinanceGuardrails
from chat_router import IntentRouter
from chat_context import FinanceContextBuilder
from chat_simulation import WhatIfSimulator


logger = logging.getLogger('chat_agent')


class ChatAgent:
    """Comprehensive chat agent: guardrails → routing → context → prompt → parse → response."""

    def __init__(self):
        self.guardrails = FinanceGuardrails()
        self.router = IntentRouter()
        self.context_builder = FinanceContextBuilder()
        self.simulator = WhatIfSimulator()

    def respond(
        self,
        message: str,
        latest_result: Dict,
        mode: str = 'advanced',
        history: List[Dict] = None,
        session_state: Dict = None,
    ) -> Dict:
        """Main chat response pipeline."""
        history = history or []
        session_state = session_state or {}

        # Resolve short follow-ups (e.g., "show recent news") using prior session context.
        recovered_intent, recovered_entities = self._recover_follow_up_intent(message, session_state)

        # Pipeline step 1: Guardrails check
        if not FinanceGuardrails.is_finance_in_scope(message) and not recovered_intent:
            return FinanceGuardrails.get_refusal_response()

        # Pipeline step 2: Intent routing
        intent, entities = self.router.route(message)

        # Handle out-of-scope after routing
        if intent == 'out_of_scope':
            if recovered_intent:
                intent = recovered_intent
                entities = recovered_entities
            else:
                return FinanceGuardrails.get_refusal_response()

        if recovered_intent and intent in ('finance_general', 'out_of_scope'):
            # Prefer recovered ticker-aware intent for short action-chip follow-ups.
            intent = recovered_intent
            entities = recovered_entities

        # Keep any router-extracted entities (such as explicit tickers in current message).
        if recovered_entities:
            merged_tickers = list(dict.fromkeys((entities.get('tickers', []) or []) + (recovered_entities.get('tickers', []) or [])))
            if merged_tickers:
                entities['tickers'] = merged_tickers
            merged_sectors = list(dict.fromkeys((entities.get('sectors', []) or []) + (recovered_entities.get('sectors', []) or [])))
            if merged_sectors:
                entities['sectors'] = merged_sectors

        # Handle out-of-scope after routing
        if intent == 'out_of_scope':
            return FinanceGuardrails.get_refusal_response()

        # Pipeline step 3: Build context based on intent
        context, citations = self._build_context_for_intent(intent, entities, latest_result)

        # Pipeline step 4: What-if simulation if needed
        whatif_result = None
        if intent == 'portfolio_what_if':
            whatif_result = self.simulator.parse_and_simulate(message, latest_result)

        # Pipeline step 5: Build Gemini prompt
        prompt = self._build_prompt(
            message=message,
            intent=intent,
            entities=entities,
            context=context,
            mode=mode,
            history=history,
            whatif_result=whatif_result,
            session_state=session_state,
        )

        # Pipeline step 6: Call Gemini
        raw = generate_insights(prompt, max_output_tokens=700, temperature=0.15)

        # Pipeline step 7: Parse response with retry
        parsed = self._parse_json_robust(raw)
        if parsed and parsed.get('answer', '').strip():
            answer = str(parsed.get('answer')).strip()
            response = {
                'answer': answer,
                'confidence': self._normalize_confidence(parsed.get('confidence')),
                'citations': self._normalize_list(parsed.get('citations')),
                'follow_ups': self._normalize_list(parsed.get('follow_ups'))[:3],
                'source': 'gemini',
                'intent': intent,
                'entities': entities,
                'action_suggestions': self._get_action_suggestions(intent, entities),
                'context_used': citations,
            }
            return response

        # Pipeline step 8: Intent-aware fallback
        fallback = self._fallback_answer_contextual(intent, entities, message, latest_result, mode, whatif_result)
        fallback['source'] = 'deterministic_fallback'
        fallback['intent'] = intent
        fallback['entities'] = entities
        fallback['action_suggestions'] = self._get_action_suggestions(intent, entities)
        fallback['context_used'] = citations
        return fallback

    def _recover_follow_up_intent(self, message: str, session_state: Dict) -> Tuple[Optional[str], Dict]:
        """Recover ticker-focused follow-up intent from session context."""
        if not message or not session_state:
            return None, {}

        lower = message.lower().strip()
        last_tickers = session_state.get('last_tickers', []) or []
        if not isinstance(last_tickers, list):
            last_tickers = []

        # If the user gave an explicit ticker in this message, let router handle it.
        if IntentRouter.TICKER_PATTERN.search(message):
            return None, {}

        ticker_followup_signals = [
            'news', 'headline', 'analyze deeper', 'deeper', 'compare',
            'benchmark', 'fit with my portfolio', 'this stock', 'this ticker',
            'that stock', 'that ticker',
        ]
        if any(signal in lower for signal in ticker_followup_signals) and last_tickers:
            return 'ticker_question', {'tickers': last_tickers, 'intent_type': 'ticker_follow_up'}

        portfolio_followup_signals = [
            'show sector breakdown', 'suggest rebalancing', 'highest risk',
            'restore original', 'full impact analysis',
        ]
        if any(signal in lower for signal in portfolio_followup_signals):
            return 'portfolio_question', {}

        return None, {}

    def _build_context_for_intent(self, intent: str, entities: Dict, latest_result: Dict) -> Tuple[Dict, List[str]]:
        """Build appropriate context based on intent."""
        if intent == 'portfolio_question':
            return self.context_builder.build_portfolio_context(latest_result)

        elif intent == 'ticker_question':
            tickers = entities.get('tickers', [])
            company_query = entities.get('company_query')
            if company_query and entities.get('intent_type') == 'company_securities_lookup':
                lookup_context, lookup_citations = self.context_builder.build_company_lookup_context(company_query)
                if tickers:
                    ticker_context, ticker_citations = self.context_builder.build_ticker_context(tickers)
                    lookup_context['tickers'] = ticker_context.get('tickers', {})
                    return lookup_context, lookup_citations + ticker_citations
                return lookup_context, lookup_citations
            if tickers:
                context, citations = self.context_builder.build_ticker_context(tickers)
                # If also comparing with portfolio, add portfolio context
                if entities.get('intent_type') == 'compare_portfolio':
                    portfolio_context, portfolio_cites = self.context_builder.build_portfolio_context(latest_result)
                    context['portfolio'] = portfolio_context
                    citations.extend(portfolio_cites)
                return context, citations
            return {}, []

        elif intent == 'portfolio_comparison':
            # Combine portfolio and ticker context
            tickers = entities.get('tickers', [])
            return self.context_builder.build_combined_context(latest_result, tickers=tickers)

        elif intent == 'portfolio_what_if':
            # Portfolio context for what-if
            return self.context_builder.build_portfolio_context(latest_result)

        elif intent == 'finance_general':
            # Minimal context for general finance questions
            portfolio_context, portfolio_cites = self.context_builder.build_portfolio_context(latest_result)
            return {'portfolio': portfolio_context}, portfolio_cites

        return {}, []

    def _build_prompt(
        self,
        message: str,
        intent: str,
        entities: Dict,
        context: Dict,
        mode: str,
        history: List[Dict],
        whatif_result: Optional[Dict] = None,
        session_state: Dict = None,
    ) -> str:
        """Build rich Gemini prompt with all available context."""
        session_state = session_state or {}

        # Format history
        history_lines = []
        for item in history[-8:]:
            role = str(item.get('role') or 'user')
            content = str(item.get('content') or '')[:800]
            if content:
                history_lines.append(f"- {role}: {content}")

        # Style guidance
        style = (
            'Use short plain-English sentences and practical guidance. Explain concepts simply.'
            if mode == 'simple'
            else 'Use precise language with concise finance terminology. Cite specific metrics when available.'
        )

        history_block = history_lines if history_lines else ['- none']

        # Build main prompt sections
        sections = [
            'You are an AI finance assistant specialized in portfolio analysis and investment questions.',
            'Important constraints:',
            '- Provide educational analysis only, not guaranteed returns or certain outcomes.',
            '- Do not claim certainty; include uncertainty where relevant.',
            '- Ground your answer in the provided analysis context.',
            '- If context is missing, say what data you would need.',
            f'- {style}',
            '',
            'Return ONLY strict JSON with keys:',
            'answer, confidence, citations, follow_ups',
            'confidence must be one of: high, medium, low',
            'citations must reference context paths such as portfolio.sector_allocation or ticker.AAPL',
            'follow_ups should be 2-3 short useful next questions.',
            '',
        ]

        # Add intent-specific guidance
        if intent == 'portfolio_what_if':
            sections.extend([
                'The user is asking about a hypothetical portfolio change.',
                'Provide analysis of the estimated impact.',
                'Note that full re-analysis may provide different results.',
                '',
            ])
        elif intent == 'ticker_question':
            sections.append('The user is asking about a specific ticker/company.\n')
        elif intent == 'portfolio_question':
            sections.append('The user is asking about their own portfolio.\n')

        # Add conversation history
        sections.extend([
            'Conversation history:',
            *history_block,
            '',
        ])

        # Add context JSON
        sections.extend([
            'Analysis context JSON:',
            json.dumps(context, ensure_ascii=True, default=str),
            '',
        ])

        # Add what-if details if applicable
        if whatif_result:
            sections.extend([
                'What-if simulation result:',
                json.dumps(whatif_result.get('impact', {}), ensure_ascii=True, default=str),
                '',
            ])

        # Add user question
        sections.extend([
            f'User intent detected: {intent}',
            f'Extracted entities: {json.dumps(entities, ensure_ascii=True)}',
            '',
            f'User question: {message}',
        ])

        return '\n'.join(sections)

    def _parse_json_robust(self, text: str) -> Optional[Dict]:
        """Robustly parse JSON from Gemini output, handling fenced/malformed responses."""
        if not text or not isinstance(text, str):
            return None

        candidate = text.strip()

        # Try direct parsing
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

        # Remove code fences
        candidate = candidate.replace('```json', '').replace('```', '').strip()

        # Try parsing again after fence removal
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

        # Extract JSON between braces
        start = candidate.find('{')
        end = candidate.rfind('}')
        if start >= 0 and end > start:
            try:
                obj = json.loads(candidate[start:end + 1])
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass

        logger.warning(f'Failed to parse Gemini JSON response. Raw: {text[:200]}...')
        return None

    def _get_action_suggestions(self, intent: str, entities: Dict) -> List[str]:
        """Generate contextual action suggestions based on intent."""
        if intent == 'portfolio_question':
            return [
                'Show sector breakdown',
                'What causes my highest risk?',
                'Compare with benchmark',
                'Suggest rebalancing',
            ]
        elif intent == 'ticker_question':
            tickers = entities.get('tickers', [])
            if tickers:
                return [
                    f'Compare {tickers[0]} with benchmark',
                    f'How does {tickers[0]} fit with my portfolio?',
                    'Show recent news',
                    'Analyze deeper',
                ]
            return ['Analyze another ticker', 'Compare tickers']
        elif intent == 'portfolio_what_if':
            return [
                'Show full impact analysis',
                'What if I do more?',
                'Check compliance impact',
                'Restore original',
            ]
        elif intent == 'finance_general':
            return [
                'Apply to my portfolio',
                'Show an example',
                'Compare with alternatives',
                'Ask a follow-up',
            ]
        return ['Ask another question', 'Explain simpler']

    def _fallback_answer_contextual(
        self,
        intent: str,
        entities: Dict,
        message: str,
        latest_result: Dict,
        mode: str,
        whatif_result: Optional[Dict] = None,
    ) -> Dict:
        """Generate intent-aware fallback response."""
        
        if intent == 'portfolio_question':
            return self._fallback_portfolio_question(latest_result, mode)
        elif intent == 'ticker_question':
            return self._fallback_ticker_question(entities, latest_result)
        elif intent == 'portfolio_what_if':
            return self._fallback_whatif_question(whatif_result, latest_result, message)
        elif intent == 'portfolio_comparison':
            return self._fallback_comparison_question(entities, latest_result)
        elif intent == 'finance_general':
            return self._fallback_general_question(message)
        else:
            return self._fallback_generic(message, latest_result, mode)

    def _fallback_portfolio_question(self, latest_result: Dict, mode: str) -> Dict:
        """Fallback for portfolio questions."""
        if not latest_result:
            return {
                'answer': (
                    'I need portfolio analysis data to answer this. '
                    'Run portfolio analysis first, then ask about diversification, sector allocation, or risk.'
                ),
                'confidence': 'low',
                'citations': [],
                'follow_ups': [
                    'Run analysis and ask how my portfolio is allocated',
                    'What sectors am I exposed to?',
                    'How diversified is my portfolio?',
                ],
            }

        risk = ((latest_result or {}).get('risk') or {}).get('portfolio', {}) or {}
        compliance = (latest_result or {}).get('compliance', {}) or {}
        portfolio = (latest_result or {}).get('portfolio', []) or []

        # Count sectors
        sector_count = len(set(holding.get('ticker', '') for holding in portfolio))

        answer_parts = [
            f'Your portfolio has {len(portfolio)} holdings'
            f' across {sector_count} different assets.'
        ]

        if risk.get('volatility'):
            answer_parts.append(f'Volatility: {float(risk["volatility"]) * 100:.1f}%.')

        if len(portfolio) >= 10:
            answer_parts.append('Your portfolio appears well-diversified with adequate holdings.')
        elif len(portfolio) >= 5:
            answer_parts.append('Your portfolio has moderate diversification; consider adding more uncorrelated assets.')
        else:
            answer_parts.append('Your portfolio is concentrated; consider adding more diverse holdings.')

        if not compliance.get('ok', True):
            violations = compliance.get('violations', [])
            answer_parts.append(f'⚠️ {len(violations)} compliance issue(s) detected.')

        answer = ' '.join(answer_parts)

        return {
            'answer': answer if answer else 'Your portfolio analysis is available. Ask specific questions about sectors, risk, or diversification.',
            'confidence': 'medium',
            'citations': ['portfolio', 'risk.portfolio.volatility', 'compliance.ok'],
            'follow_ups': [
                'What\'s my top holding?',
                'How much is in tech?',
                'Can I reduce risk?',
            ],
        }

    def _fallback_ticker_question(self, entities: Dict, latest_result: Dict) -> Dict:
        """Fallback for ticker questions."""
        tickers = entities.get('tickers', [])
        
        if not tickers:
            return {
                'answer': 'Please specify which ticker you\'d like to learn about (e.g., AAPL, MSFT, XLV).',
                'confidence': 'medium',
                'citations': [],
                'follow_ups': [
                    'Tell me about AAPL',
                    'How does MSFT compare to my portfolio?',
                    'What sector is XLV?',
                ],
            }

        ticker = tickers[0]
        answer = f'{ticker} is a financial ticker. I can provide analysis including sector, valuation, and portfolio fit.'

        portfolio = latest_result.get('portfolio', []) if latest_result else []
        portfolio_in_ticker = any(h.get('ticker') == ticker for h in portfolio)
        if portfolio_in_ticker:
            answer += f' {ticker} is in your current portfolio.'
        else:
            answer += f' {ticker} is not in your current portfolio.'

        return {
            'answer': answer,
            'confidence': 'medium',
            'citations': [f'ticker:{ticker}'],
            'follow_ups': [
                f'How is {ticker} performing?',
                f'Does {ticker} fit my portfolio?',
                'Compare with another ticker',
            ],
        }

    def _fallback_whatif_question(self, whatif_result: Optional[Dict], latest_result: Dict, message: str) -> Dict:
        """Fallback for what-if questions."""
        if not whatif_result:
            return {
                'answer': (
                    'I can simulate portfolio changes like "reduce AAPL to 10%," "add XLV," or "replace XOM with V." '
                    'Please rephrase your what-if question with specific ticker and action.'
                ),
                'confidence': 'low',
                'citations': [],
                'follow_ups': [
                    'What if I reduce my largest holding by 50%?',
                    'What if I add more tech?',
                    'Show impact of equal weighting',
                ],
            }

        impact = whatif_result.get('impact', {})
        current = impact.get('current', {})
        hypothetical = impact.get('hypothetical', {})
        delta = impact.get('delta', {})

        parts = [
            f'Simulated change: {whatif_result.get("action", "modify")} {", ".join(whatif_result.get("tickers", []))}.'
        ]

        if delta.get('holdings'):
            parts.append(f'Holdings: {current.get("holdings_count")} → {hypothetical.get("holdings_count")}')

        if delta.get('concentration') is not None:
            conc_delta = delta['concentration']
            direction = 'more' if conc_delta > 0 else 'less'
            parts.append(f'Portfolio becomes {direction} concentrated.')

        parts.append('Use /analyze to compute full impact with re-analysis.')

        return {
            'answer': ' '.join(parts),
            'confidence': 'medium',
            'citations': [],
            'follow_ups': [
                'Run full reanalysis',
                'Try a different change',
                'Show current portfolio',
            ],
        }

    def _fallback_comparison_question(self, entities: Dict, latest_result: Dict) -> Dict:
        """Fallback for portfolio/ticker comparison."""
        tickers = entities.get('tickers', [])
        
        answer = 'I can help compare portfolio allocations with specific tickers or sectors. '
        
        if len(tickers) >= 2:
            answer += f'Comparing {tickers[0]} vs {tickers[1]}. For detailed metrics, I can analyze sector, valuation, and risk factors.'
        else:
            answer += 'Please specify which tickers or sectors to compare.'

        return {
            'answer': answer,
            'confidence': 'medium',
            'citations': [],
            'follow_ups': [
                'Compare correlations',
                'Which is higher risk?',
                'Show performance over time',
            ],
        }

    def _fallback_general_question(self, message: str) -> Dict:
        """Fallback for general finance questions."""
        return {
            'answer': (
                'This is a general finance question. I can provide educational context, '
                'but for personalized advice specific to your portfolio, ask about your holdings, allocation, or risk metrics.'
            ),
            'confidence': 'medium',
            'citations': [],
            'follow_ups': [
                'How does this apply to my portfolio?',
                'Show an example with my holdings',
                'What should I do?',
            ],
        }

    def _fallback_generic(self, message: str, latest_result: Dict, mode: str) -> Dict:
        """Generic fallback."""
        risk = ((latest_result or {}).get('risk') or {}).get('portfolio', {}) or {}
        compliance = (latest_result or {}).get('compliance', {}) or {}

        answer = (
            'I can help with portfolio analysis questions. '
            'Ask about diversification, sector allocation, risk, compliance, or rebalancing.'
        )

        if risk.get('volatility'):
            answer += f' Your current volatility is {float(risk["volatility"]) * 100:.1f}%.'

        return {
            'answer': answer,
            'confidence': 'low',
            'citations': [],
            'follow_ups': [
                'How is my portfolio allocated?',
                'Is it diversified?',
                'What are my main risks?',
            ],
        }

    def _normalize_confidence(self, value) -> str:
        value = str(value or '').lower().strip()
        if value in {'high', 'medium', 'low'}:
            return value
        return 'medium'

    def _normalize_list(self, value) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if value is None:
            return []
        text = str(value).strip()
        return [text] if text else []

