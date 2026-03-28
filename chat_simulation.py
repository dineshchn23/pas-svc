"""Portfolio what-if simulation for chat."""

import copy
from typing import Dict, List, Optional
from chat_router import IntentRouter


class WhatIfSimulator:
    """Simulate portfolio changes and compute impact."""

    @staticmethod
    def parse_and_simulate(message: str, latest_result: Dict) -> Optional[Dict]:
        """Parse what-if request and simulate impact."""
        if not latest_result or not latest_result.get('portfolio'):
            return None

        whatif_details = IntentRouter.extract_what_if_details(message)
        if not whatif_details:
            return None

        current_portfolio = latest_result.get('portfolio', [])
        action = whatif_details.get('action', 'modify')
        tickers = whatif_details.get('tickers', [])
        percentages = whatif_details.get('percentages', [])

        # Create hypothetical portfolio
        hypothetical = copy.deepcopy(current_portfolio)

        try:
            if action == 'reduce' and tickers and percentages:
                # Reduce a holding to a specific weight
                ticker = tickers[0]
                new_weight = percentages[0] / 100.0
                WhatIfSimulator._adjust_holding(hypothetical, ticker, new_weight)

            elif action == 'increase' and tickers and percentages:
                # Increase a holding
                ticker = tickers[0]
                increase_amount = percentages[0] / 100.0
                current_weight = next((h['weight'] for h in hypothetical if h['ticker'] == ticker), 0)
                new_weight = current_weight + increase_amount
                WhatIfSimulator._adjust_holding(hypothetical, ticker, new_weight)

            elif action == 'add' and tickers:
                # Add a new holding
                ticker = tickers[0]
                weight = percentages[0] / 100.0 if percentages else 0.05
                hypothetical.append({'ticker': ticker, 'weight': weight})
                # Rebalance remaining
                WhatIfSimulator._renormalize_weights(hypothetical)

            elif action == 'remove' and tickers:
                # Remove a holding
                ticker = tickers[0]
                hypothetical = [h for h in hypothetical if h['ticker'] != ticker]
                WhatIfSimulator._renormalize_weights(hypothetical)

            elif action == 'replace' and len(tickers) >= 2:
                # Replace one ticker with another
                old_ticker = tickers[0]
                new_ticker = tickers[1]
                old_weight = next((h['weight'] for h in hypothetical if h['ticker'] == old_ticker), 0)
                hypothetical = [h for h in hypothetical if h['ticker'] != old_ticker]
                hypothetical.append({'ticker': new_ticker, 'weight': old_weight})

            else:
                # Can't parse this what-if
                return None

        except Exception:
            return None

        # Compute simple metrics on hypothetical
        return {
            'action': action,
            'tickers': tickers,
            'current_portfolio': current_portfolio,
            'hypothetical_portfolio': hypothetical,
            'impact': WhatIfSimulator._estimate_impact(
                latest_result,
                current_portfolio,
                hypothetical
            ),
        }

    @staticmethod
    def _adjust_holding(portfolio: List[Dict], ticker: str, new_weight: float) -> None:
        """Adjust a single holding to a new weight and rebalance rest."""
        new_weight = max(0, min(new_weight, 1.0))  # Clamp to [0, 1]
        
        # Find and update the holding
        for holding in portfolio:
            if holding['ticker'] == ticker:
                holding['weight'] = new_weight
                break
        else:
            # Ticker not found, add it
            portfolio.append({'ticker': ticker, 'weight': new_weight})

        # Rebalance remaining weights
        WhatIfSimulator._renormalize_weights(portfolio)

    @staticmethod
    def _renormalize_weights(portfolio: List[Dict]) -> None:
        """Renormalize weights to sum to 1.0."""
        total = sum(h.get('weight', 0) for h in portfolio)
        if total > 0:
            for holding in portfolio:
                holding['weight'] = holding.get('weight', 0) / total
        else:
            # All weights are 0, equal weight
            if portfolio:
                eq_weight = 1.0 / len(portfolio)
                for holding in portfolio:
                    holding['weight'] = eq_weight

    @staticmethod
    def _estimate_impact(
        latest_result: Dict,
        current_portfolio: List[Dict],
        hypothetical_portfolio: List[Dict]
    ) -> Dict:
        """Estimate impact of change on key metrics."""
        # Simple heuristics for what-if impact (without re-running full analysis)
        
        impact = {
            'current': {},
            'hypothetical': {},
            'delta': {},
        }

        # Extract current metrics
        risk = latest_result.get('risk', {}) or {}
        portfolio_risk = risk.get('portfolio', {}) or {}
        
        impact['current']['volatility'] = portfolio_risk.get('volatility')
        impact['current']['sharpe'] = portfolio_risk.get('sharpe')
        impact['current']['concentration'] = WhatIfSimulator._estimate_concentration(current_portfolio)
        impact['current']['holdings_count'] = len(current_portfolio)

        # Estimate hypothetical metrics
        impact['hypothetical']['concentration'] = WhatIfSimulator._estimate_concentration(hypothetical_portfolio)
        impact['hypothetical']['holdings_count'] = len(hypothetical_portfolio)

        # Estimate deltas (simplified)
        # Concentration change
        if impact['current']['concentration'] is not None:
            conc_delta = impact['hypothetical']['concentration'] - impact['current']['concentration']
            impact['delta']['concentration'] = conc_delta

        # Holdings change
        impact['delta']['holdings'] = impact['hypothetical']['holdings_count'] - impact['current']['holdings_count']

        # Note: Full volatility/Sharpe re-computation would require re-running analysis
        # For now, we note that these require full analysis
        impact['hypothetical']['volatility'] = None
        impact['hypothetical']['sharpe'] = None
        impact['notes'] = [
            'Concentration and holdings count estimated immediately.',
            'Volatility and Sharpe require full analysis recomputation.',
            'Use /analyze to get full impact metrics.',
        ]

        return impact

    @staticmethod
    def _estimate_concentration(portfolio: List[Dict]) -> Optional[float]:
        """Estimate Herfindahl index (concentration metric)."""
        if not portfolio:
            return None

        # Herfindahl = sum(weight^2), ranges [1/n, 1]
        # Higher = more concentrated
        hhi = sum((float(h.get('weight', 0)) ** 2) for h in portfolio)
        return hhi
