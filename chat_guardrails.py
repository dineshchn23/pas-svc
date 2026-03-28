"""Finance-only domain guardrails for chat."""

import json
import re
import threading
import time
from typing import Dict, Optional, Tuple

from gemini_client import generate_insights


class FinanceGuardrails:
    """AI-based finance domain gate."""

    # In-memory classification cache to avoid repeated model calls.
    CACHE_TTL_SECONDS = 900
    MAX_CACHE_SIZE = 1024
    _scope_cache: Dict[str, Tuple[bool, float]] = {}
    _cache_lock = threading.Lock()

    # Fast-path phrases from in-product chips.
    ACTION_PHRASES = {
        'show recent news',
        'analyze deeper',
        'compare with benchmark',
        'show sector breakdown',
        'suggest rebalancing',
        'show full impact analysis',
        'restore original',
    }

    # Lightweight heuristic terms for clear messages.
    FAST_IN_SCOPE_TERMS = {
        'portfolio', 'stock', 'ticker', 'etf', 'fund', 'bond', 'equity',
        'invest', 'allocation', 'diversif', 'rebalance', 'risk', 'return',
        'volatility', 'benchmark', 'sector', 'holding', 'market', 'news',
        'earnings', 'dividend', 'valuation', 'alpha', 'beta', 'sharpe', 'var',
    }
    FAST_OUT_SCOPE_TERMS = {
        'recipe', 'cook', 'movie', 'music', 'travel', 'hotel', 'flight',
        'weather', 'joke', 'riddle', 'python code', 'javascript code',
        'debug my code', 'kubernetes', 'docker', 'react app',
    }

    # Ticker symbol pattern: 1-5 uppercase letters, optionally followed by .direction
    TICKER_PATTERN = re.compile(r'\b([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\b')

    SCOPE_PROMPT_TEMPLATE = (
        'You are a domain classifier for a finance assistant.\n'
        'Decide if the message is in scope for finance/investing support.\n'
        'IN_SCOPE examples: portfolio analysis, stocks, ETFs, funds, rebalancing, market news, '\
        'tickers, company performance, macroeconomics related to investing, risk metrics.\n'
        'OUT_OF_SCOPE examples: coding help, recipes, entertainment, travel, medical, politics, '\
        'and unrelated chit-chat.\n'
        'Return EXACTLY one token: IN_SCOPE or OUT_OF_SCOPE.\n\n'
        'Message: {message}'
    )

    @staticmethod
    def is_finance_in_scope(message: str) -> bool:
        """Check if message is about finance using AI classification."""
        if not message or not isinstance(message, str):
            return False

        normalized = FinanceGuardrails._normalize_message(message)

        # Cache hit: return in O(1) without model call.
        cached = FinanceGuardrails._cache_get(normalized)
        if cached is not None:
            return cached

        # Fast allow for known UI action phrases.
        if normalized in FinanceGuardrails.ACTION_PHRASES:
            FinanceGuardrails._cache_set(normalized, True)
            return True

        # Fast in-scope for clear finance wording.
        if any(term in normalized for term in FinanceGuardrails.FAST_IN_SCOPE_TERMS):
            FinanceGuardrails._cache_set(normalized, True)
            return True

        # Fast out-of-scope for clearly unrelated wording.
        if any(term in normalized for term in FinanceGuardrails.FAST_OUT_SCOPE_TERMS):
            FinanceGuardrails._cache_set(normalized, False)
            return False

        # Ticker pattern is a strong finance signal.
        if FinanceGuardrails.TICKER_PATTERN.search(message):
            FinanceGuardrails._cache_set(normalized, True)
            return True

        prompt = FinanceGuardrails.SCOPE_PROMPT_TEMPLATE.format(message=message.strip())
        raw = generate_insights(prompt, max_output_tokens=16, temperature=0.0)
        parsed = FinanceGuardrails._parse_scope_output(raw)
        if parsed is not None:
            FinanceGuardrails._cache_set(normalized, parsed)
            return parsed

        # Fallback when classifier output is unavailable/malformed.
        # Prefer avoiding false negatives (blocking valid finance prompts).
        if any(term in normalized for term in FinanceGuardrails.FAST_OUT_SCOPE_TERMS):
            FinanceGuardrails._cache_set(normalized, False)
            return False
        FinanceGuardrails._cache_set(normalized, True)
        return True

    @staticmethod
    def _normalize_message(message: str) -> str:
        """Normalize free text to improve cache hit-rate."""
        return ' '.join(str(message).strip().lower().split())

    @staticmethod
    def _cache_get(key: str) -> Optional[bool]:
        """Read a cached decision if not expired."""
        now = time.time()
        with FinanceGuardrails._cache_lock:
            row = FinanceGuardrails._scope_cache.get(key)
            if not row:
                return None
            value, expiry = row
            if expiry < now:
                FinanceGuardrails._scope_cache.pop(key, None)
                return None
            return value

    @staticmethod
    def _cache_set(key: str, value: bool) -> None:
        """Store a cached decision with TTL and bounded size."""
        expiry = time.time() + FinanceGuardrails.CACHE_TTL_SECONDS
        with FinanceGuardrails._cache_lock:
            FinanceGuardrails._scope_cache[key] = (value, expiry)
            if len(FinanceGuardrails._scope_cache) > FinanceGuardrails.MAX_CACHE_SIZE:
                prune_count = max(1, FinanceGuardrails.MAX_CACHE_SIZE // 10)
                for old_key in list(FinanceGuardrails._scope_cache.keys())[:prune_count]:
                    FinanceGuardrails._scope_cache.pop(old_key, None)

    @staticmethod
    def _parse_scope_output(raw: str) -> bool | None:
        """Parse classifier output token IN_SCOPE or OUT_OF_SCOPE."""
        if not raw or not isinstance(raw, str):
            return None

        token = raw.strip().upper()
        if token == 'IN_SCOPE':
            return True
        if token == 'OUT_OF_SCOPE':
            return False

        # Tolerate extra text and fenced blocks.
        cleaned = token.replace('```', ' ').replace('JSON', ' ')
        if 'OUT_OF_SCOPE' in cleaned:
            return False
        if 'IN_SCOPE' in cleaned:
            return True

        # Backward-compatible parse if model still returns JSON.
        candidate = raw.strip().replace('```json', '').replace('```', '').strip()
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and isinstance(parsed.get('in_scope'), bool):
                return parsed['in_scope']
        except json.JSONDecodeError:
            return None

        return None

    @staticmethod
    def get_refusal_response() -> Dict:
        """Return a helpful refusal for out-of-scope questions."""
        return {
            'answer': (
                'I can only help with finance and portfolio questions. '
                'I can answer questions about stock portfolios, diversification, sector allocation, '
                'risk analysis, individual tickers, benchmarking, and portfolio optimization. '
                'Please ask about something related to investments or finance.'
            ),
            'confidence': 'high',
            'citations': [],
            'follow_ups': [
                'Is my portfolio diversified across sectors?',
                'Tell me about AAPL or another ticker.',
                'How should I rebalance my portfolio?',
                'What is my portfolio volatility and risk?',
            ],
            'source': 'guardrails',
            'intent': 'out_of_scope',
            'entities': {},
            'action_suggestions': [],
            'context_used': [],
        }


