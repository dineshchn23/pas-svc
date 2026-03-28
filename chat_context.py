"""Rich finance context builder for chat."""

import json
from typing import Dict, List, Tuple, Optional
import market_service


class FinanceContextBuilder:
    """Build structured finance context for different intent types."""

    @staticmethod
    def build_portfolio_context(latest_result: Dict) -> Tuple[Dict, List[str]]:
        """Build rich context for portfolio questions."""
        if not latest_result or not isinstance(latest_result, dict):
            return {}, []

        risk = latest_result.get('risk', {}) or {}
        portfolio = risk.get('portfolio', {}) or {}
        benchmark = latest_result.get('benchmark', {}) or risk.get('benchmark', {}) or {}
        compliance = latest_result.get('compliance', {}) or {}
        rebalancing = latest_result.get('rebalancing', {}) or {}
        report = latest_result.get('report', {}) or latest_result.get('insights', {}) or {}
        risk_contrib = latest_result.get('risk_contribution', []) or []

        # Extract sector allocation if available
        portfolio_list = latest_result.get('portfolio', []) or []
        sector_weights = FinanceContextBuilder._estimate_sector_weights(portfolio_list)
        top_holdings = sorted(
            portfolio_list,
            key=lambda x: float(x.get('weight', 0)),
            reverse=True
        )[:5] if portfolio_list else []

        context = {
            'portfolio': portfolio_list,
            'sector_allocation': sector_weights,
            'top_holdings': top_holdings,
            'risk': {
                'portfolio': {
                    'volatility': portfolio.get('volatility'),
                    'sharpe': portfolio.get('sharpe'),
                    'var_95': portfolio.get('var_95'),
                    'max_drawdown': portfolio.get('max_drawdown'),
                    'cumulative_return': portfolio.get('cumulative_return'),
                    'alpha': portfolio.get('alpha'),
                },
                'risk_contribution': risk_contrib[:5] if risk_contrib else [],
            },
            'benchmark': {
                'symbol': benchmark.get('symbol'),
                'name': benchmark.get('name'),
                'alpha': benchmark.get('alpha'),
                'cumulative_return': benchmark.get('cumulative_return'),
            },
            'compliance': {
                'ok': compliance.get('ok'),
                'violations': compliance.get('violations', []),
                'risk_profile': compliance.get('risk_profile'),
            },
            'rebalancing': {
                'suggested_weights': rebalancing.get('suggested_weights', {}),
                'rationale': rebalancing.get('rationale', []),
                'estimated_volatility_delta': rebalancing.get('estimated_volatility_delta'),
            },
            'report': {
                'summary': report.get('summary'),
                'key_insights': report.get('key_insights', []),
                'risks': report.get('risks', []),
                'opportunities': report.get('opportunities', []),
                'recommendations': report.get('recommendations', []),
            },
        }

        citations = [
            'sector_allocation',
            'risk.portfolio.volatility',
            'risk.portfolio.sharpe',
            'risk.portfolio.var_95',
            'risk.portfolio.max_drawdown',
            'risk.portfolio.cumulative_return',
            'benchmark.alpha',
            'compliance.ok',
            'compliance.violations',
            'rebalancing.suggested_weights',
            'rebalancing.rationale',
            'report.summary',
            'report.key_insights',
            'top_holdings',
        ]

        return context, citations

    @staticmethod
    def build_ticker_context(tickers: List[str]) -> Tuple[Dict, List[str]]:
        """Build context for ticker questions."""
        if not tickers:
            return {}, []

        context = {'tickers': {}}
        citations = []

        for ticker in tickers[:3]:  # Limit to 3 tickers for performance
            try:
                resolved_ticker = market_service.resolve_symbol(ticker)
                sector = market_service.get_sector(resolved_ticker)
                # Try to get more info if available
                info_context = {
                    'ticker': ticker,
                    'resolved_ticker': resolved_ticker,
                    'sector': sector,
                }

                # Fundamentals provide richer context than price-only responses.
                try:
                    fundamentals = market_service.get_fundamentals(resolved_ticker)
                    info_context['fundamentals'] = {
                        'industry': fundamentals.get('industry'),
                        'market_cap': fundamentals.get('market_cap'),
                        'forward_pe': fundamentals.get('forward_pe'),
                        'trailing_pe': fundamentals.get('trailing_pe'),
                        'beta_fundamental': fundamentals.get('beta_fundamental'),
                        'recommendation_key': fundamentals.get('recommendation_key'),
                    }
                except Exception:
                    pass
                
                # Try to extract price and fundamental data
                try:
                    prices = market_service.get_prices(resolved_ticker, period='1y')
                    if prices is not None and len(prices) > 0:
                        info_context['current_price'] = float(prices.iloc[-1]) if len(prices) > 0 else None
                        info_context['year_high'] = float(prices.max()) if len(prices) > 0 else None
                        info_context['year_low'] = float(prices.min()) if len(prices) > 0 else None
                        info_context['yoy_return'] = (
                            (float(prices.iloc[-1]) - float(prices.iloc[0])) / float(prices.iloc[0])
                            if len(prices) > 1 else None
                        )
                except Exception:
                    pass  # Price data optional

                # Add recent headlines for "news" style questions.
                try:
                    recent_news = market_service.get_recent_news(resolved_ticker, limit=5)
                    if recent_news:
                        info_context['recent_news'] = recent_news
                except Exception:
                    pass

                context['tickers'][ticker] = info_context
                citations.append(f'ticker:{resolved_ticker}')
            except Exception:
                context['tickers'][ticker] = {'ticker': ticker, 'error': 'data_unavailable'}

        return context, citations

    @staticmethod
    def build_company_lookup_context(company_query: str, limit: int = 8) -> Tuple[Dict, List[str]]:
        """Build context for queries like 'what securities belong to <company/group>?'."""
        if not company_query:
            return {}, []

        results = market_service.search_symbols(company_query, limit=limit)
        context = {
            'company_lookup': {
                'query': company_query,
                'matches': results,
            }
        }
        citations = [
            'company_lookup.query',
            'company_lookup.matches',
        ]
        return context, citations

    @staticmethod
    def build_combined_context(
        latest_result: Dict,
        tickers: List[str] = None,
        sectors: List[str] = None
    ) -> Tuple[Dict, List[str]]:
        """Build combined context for portfolio + ticker questions."""
        portfolio_context, portfolio_citations = FinanceContextBuilder.build_portfolio_context(latest_result)
        
        combined_context = {'portfolio': portfolio_context}
        combined_citations = portfolio_citations

        if tickers:
            ticker_context, ticker_citations = FinanceContextBuilder.build_ticker_context(tickers)
            combined_context['ticker'] = ticker_context
            combined_citations.extend(ticker_citations)

        return combined_context, combined_citations

    @staticmethod
    def _estimate_sector_weights(portfolio_list: List[Dict]) -> Dict[str, float]:
        """Estimate sector weights from portfolio holdings."""
        if not portfolio_list:
            return {}

        sector_weights = {}
        for holding in portfolio_list:
            ticker = holding.get('ticker', '').upper()
            weight = float(holding.get('weight', 0))
            
            try:
                sector = market_service.get_sector(ticker)
                sector_weights[sector] = sector_weights.get(sector, 0) + weight
            except Exception:
                sector_weights['Unknown'] = sector_weights.get('Unknown', 0) + weight

        # Normalize to percentages
        total = sum(sector_weights.values())
        if total > 0:
            sector_weights = {k: (v / total) * 100 for k, v in sector_weights.items()}

        return sector_weights

    @staticmethod
    def get_context_summary(context: Dict, intent: str) -> str:
        """Generate a brief text summary of assembled context."""
        if intent == 'portfolio_question':
            portfolio = context.get('portfolio', {})
            risk = portfolio.get('risk', {})
            portfolio_risk = risk.get('portfolio', {})
            sector_alloc = portfolio.get('sector_allocation', {})
            
            summary_parts = []
            if portfolio_risk.get('volatility'):
                summary_parts.append(f"Volatility: {portfolio_risk['volatility']:.2%}")
            if portfolio_risk.get('sharpe'):
                summary_parts.append(f"Sharpe: {portfolio_risk['sharpe']:.2f}")
            if sector_alloc:
                top_sector = max(sector_alloc.items(), key=lambda x: x[1])
                summary_parts.append(f"Top sector: {top_sector[0]} ({top_sector[1]:.1f}%)")
            
            return ' | '.join(summary_parts)

        elif intent == 'ticker_question':
            tickers_data = context.get('ticker', {}).get('tickers', {})
            if tickers_data:
                first_ticker = next(iter(tickers_data.values()))
                parts = [f"Ticker: {first_ticker.get('ticker')}"]
                if first_ticker.get('sector'):
                    parts.append(f"Sector: {first_ticker['sector']}")
                if first_ticker.get('current_price'):
                    parts.append(f"Price: ${first_ticker['current_price']:.2f}")
                return ' | '.join(parts)

        return ''
