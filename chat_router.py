"""Intent routing and entity extraction for chat."""

import re
from typing import Dict, List, Tuple, Optional


class IntentRouter:
    """Deterministic intent classifier and entity extractor."""

    # Ticker pattern
    TICKER_PATTERN = re.compile(r'\b([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\b')

    # Company name aliases to ticker symbols.
    COMPANY_TO_TICKER = {
        'apple': 'AAPL',
        'microsoft': 'MSFT',
        'google': 'GOOGL',
        'alphabet': 'GOOGL',
        'amazon': 'AMZN',
        'nvidia': 'NVDA',
        'meta': 'META',
        'tesla': 'TSLA',
        'netflix': 'NFLX',
        'amd': 'AMD',
        'intel': 'INTC',
        'uber': 'UBER',
        'airbnb': 'ABNB',
        'salesforce': 'CRM',
        'oracle': 'ORCL',
        'adobe': 'ADBE',
        'palantir': 'PLTR',
        'tata motors': 'TMCV.NS',
        'tata consultancy services': 'TCS.NS',
        'tcs': 'TCS.NS',
        'tata steel': 'TATASTEEL.NS',
        'tata power': 'TATAPOWER.NS',
        'infosys': 'INFY.NS',
        'reliance': 'RELIANCE.NS',
        'hdfc bank': 'HDFCBANK.NS',
    }

    # Common sectors
    SECTORS = {
        'technology', 'tech', 'software', 'hardware',
        'healthcare', 'health', 'pharma', 'biotech', 'medical',
        'finance', 'banking', 'financial services', 'insurance',
        'energy', 'oil', 'gas', 'renewable',
        'consumer', 'retail', 'discretionary', 'staples',
        'industrial', 'manufacturing', 'defense',
        'utilities', 'telecom', 'communications',
        'materials', 'mining', 'agriculture',
        'real estate', 'reit'
    }

    # Intent keywords and patterns
    PORTFOLIO_INTENT_KEYWORDS = [
        'portfolio', 'diversif', 'allocat', 'weight', 'holding',
        'overweight', 'underweight', 'sector', 'concentration',
        'exposure', 'balanced', 'rebalanc', 'my stock', 'my fund'
    ]

    TICKER_INTENT_KEYWORDS = [
        'tell me', 'about', 'stock', 'ticker', 'price', 'performance',
        'earnings', 'news', 'compare', 'versus', 'vs', 'correlation'
    ]

    WHATIF_INTENT_KEYWORDS = [
        'what if', 'suppose', 'imagine', 'hypothetical', 'reduce', 'increase',
        'add', 'remove', 'replace', 'swap', 'change', 'sell', 'buy'
    ]

    COMPARE_INTENT_KEYWORDS = [
        'compare', 'versus', 'vs', 'difference', 'similarity', 'better', 'worse',
        'fit', 'fit with', 'against', 'relative to'
    ]

    EXPLAIN_INTENT_KEYWORDS = [
        'explain', 'what is', 'define', 'mean', 'meaning', 'understand',
        'simple', 'easier', 'clear', 'teach', 'describe'
    ]

    @staticmethod
    def route(message: str) -> Tuple[str, Dict]:
        """
        Classify message intent and extract entities.
        
        Returns:
            (intent, entities_dict) where intent is one of:
            - portfolio_question
            - ticker_question
            - portfolio_what_if
            - portfolio_comparison
            - out_of_scope
            
            entities_dict contains: tickers, sectors, comparison_type, etc.
        """
        if not message or not isinstance(message, str):
            return 'out_of_scope', {}

        lower = message.lower()
        entities = {}

        # Extract company/group lookup phrase, e.g. "securities belong to tata".
        company_lookup_pattern = re.compile(r'(?:belong to|for|under)\s+([a-zA-Z][a-zA-Z\s]{1,40})')
        company_match = company_lookup_pattern.search(lower)
        if company_match:
            company_query = company_match.group(1).strip(' ?,.')
            if company_query:
                entities['company_query'] = company_query

        # Extract tickers
        tickers = [t.upper() for t in IntentRouter.TICKER_PATTERN.findall(message)]

        # Extract lowercase ticker tokens and company names.
        token_pattern = re.compile(r'\b[a-zA-Z]{1,10}\b')
        tokens = set(token_pattern.findall(lower))
        for company, ticker in IntentRouter.COMPANY_TO_TICKER.items():
            if company in lower:
                tickers.append(ticker)

        # If user asks at group level, include all known mapped tickers containing that group name.
        company_query = entities.get('company_query')
        if company_query:
            for company, ticker in IntentRouter.COMPANY_TO_TICKER.items():
                if company_query in company:
                    tickers.append(ticker)
        known_tickers = set(IntentRouter.COMPANY_TO_TICKER.values())
        for token in tokens:
            upper_token = token.upper()
            if upper_token in known_tickers:
                tickers.append(upper_token)

        if tickers:
            entities['tickers'] = list(set(tickers))  # unique tickers

        # Extract sectors
        sectors = [s for s in IntentRouter.SECTORS if s in lower]
        if sectors:
            entities['sectors'] = list(set(sectors))

        # Detect what-if (high confidence)
        if any(kw in lower for kw in IntentRouter.WHATIF_INTENT_KEYWORDS):
            entities['intent_type'] = 'what_if'
            return 'portfolio_what_if', entities

        # Detect comparison (high confidence)
        if any(kw in lower for kw in IntentRouter.COMPARE_INTENT_KEYWORDS):
            # If comparing tickers, ticker_question
            if len(entities.get('tickers', [])) >= 2:
                entities['intent_type'] = 'compare_tickers'
                return 'ticker_question', entities
            # If comparing portfolio, portfolio_comparison
            if any(w in lower for w in ['my', 'our', 'portfolio', 'holdings']):
                entities['intent_type'] = 'compare_portfolio'
                return 'portfolio_comparison', entities
            # Default to ticker
            entities['intent_type'] = 'compare'
            return 'ticker_question', entities

        # Detect explain (lower confidence, often paired with other intents)
        is_explain = any(kw in lower for kw in IntentRouter.EXPLAIN_INTENT_KEYWORDS)
        entities['explain_requested'] = is_explain
        if is_explain:
            # If explaining a ticker, ticker_question
            if any(kw in lower for kw in ['stock', 'ticker', 'company', 'about']):
                if entities.get('tickers'):
                    return 'ticker_question', entities
            # If explaining a portfolio/finance concept, treat as portfolio_question
            if any(w in lower for w in ['sharpe', 'volatility', 'beta', 'alpha', 'correlation', 'concentration', 'diversification', 'var']):
                return 'portfolio_question', entities

        # Detect portfolio_question (about user's own portfolio)
        if any(kw in lower for kw in IntentRouter.PORTFOLIO_INTENT_KEYWORDS):
            if any(w in lower for w in ['my', 'our', 'i have', 'portfolio', 'holdings']):
                return 'portfolio_question', entities

        # Detect ticker_question (about a specific ticker)
        if any(kw in lower for kw in IntentRouter.TICKER_INTENT_KEYWORDS):
            if entities.get('tickers'):
                return 'ticker_question', entities
            # If asking about a company without ticker symbol
            if any(w in lower for w in ['company', 'stock', 'etf', 'fund']):
                # Extract potential company names (proper nouns, but hard to detect)
                # For now, default to ticker_question if no other signal
                return 'ticker_question', entities
            # Finance-news question without an explicit ticker.
            if any(w in lower for w in ['news', 'headline', 'market']):
                return 'portfolio_question', entities

        # Plain-language company/ticker question without explicit finance terms.
        if entities.get('tickers'):
            return 'ticker_question', entities

        # Security lookup by company/group, even without explicit ticker.
        if entities.get('company_query') and any(w in lower for w in ['security', 'securities', 'stock', 'stocks', 'listed', 'belong']):
            entities['intent_type'] = 'company_securities_lookup'
            return 'ticker_question', entities

        # Detect portfolio_question by context
        if any(w in lower for w in ['portfolio', 'allocation', 'diversif', 'allocat', 'concentration']):
            return 'portfolio_question', entities

        # Default: if tickers or sectors were extracted, treat as ticker or portfolio question
        if entities.get('tickers'):
            return 'ticker_question', entities

        if entities.get('sectors'):
            return 'portfolio_question', entities

        # Default if we extracted something but unclear
        if entities:
            return 'portfolio_question', entities

        return 'out_of_scope', {}

    @staticmethod
    def extract_what_if_details(message: str) -> Optional[Dict]:
        """Parse what-if request to extract change details."""
        lower = message.lower()
        details = {}

        # Pattern: "what if I <action> <ticker> to <percentage>?"
        # e.g., "reduce AAPL to 10%", "add XLV", "replace XOM with V"

        # Extract action
        if 'reduce' in lower:
            details['action'] = 'reduce'
        elif 'increase' in lower:
            details['action'] = 'increase'
        elif 'add' in lower:
            details['action'] = 'add'
        elif 'remove' in lower:
            details['action'] = 'remove'
        elif 'replace' in lower or 'swap' in lower:
            details['action'] = 'replace'
        elif 'change' in lower:
            details['action'] = 'change'
        else:
            details['action'] = 'modify'

        # Extract tickers in order
        tickers = IntentRouter.TICKER_PATTERN.findall(message)
        if tickers:
            details['tickers'] = tickers

        # Extract percentage values
        pct_pattern = re.compile(r'(\d+\.?\d*)%')
        percentages = pct_pattern.findall(message)
        if percentages:
            details['percentages'] = [float(p) for p in percentages]

        return details if details else None
