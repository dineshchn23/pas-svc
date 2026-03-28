import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

import market_service
from gemini_client import generate_insights


BENCHMARK_NAMES = {
    'SPY': 'S&P 500 ETF',
    '^NSEI': 'NIFTY 50 Index',
}


def _safe_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _series_to_points(series: pd.Series, tail: Optional[int] = 252) -> List[Dict]:
    if series is None or series.empty:
        return []
    payload = series.dropna()
    if tail is not None and len(payload) > tail:
        payload = payload.tail(tail)
    return [
        {'date': idx.strftime('%Y-%m-%d'), 'value': float(val)}
        for idx, val in payload.items()
    ]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _market_cap_bucket(market_cap: Optional[float]) -> str:
    if market_cap is None:
        return 'unknown'
    if market_cap >= 2e11:
        return 'mega_cap'
    if market_cap >= 1e10:
        return 'large_cap'
    if market_cap >= 2e9:
        return 'mid_cap'
    return 'small_cap'


class RebalancingEngine:
    """Simple heuristic rebalancing to reduce concentration and improve risk mix."""

    def suggest(self, portfolio: List[Dict], risk: Dict, compliance: Dict) -> Dict:
        if not portfolio:
            return {
                'current_weights': {},
                'suggested_weights': {},
                'deltas': {},
                'rationale': ['No holdings were provided.'],
            }

        tickers = [item['ticker'] for item in portfolio]
        current = {item['ticker']: float(item['weight']) for item in portfolio}
        suggested = dict(current)

        rules = compliance.get('applied_rules') or {}
        max_weight = _safe_float(rules.get('single_asset_max'), 0.4)
        if max_weight is None or max_weight <= 0:
            max_weight = 0.4

        vol_map = {}
        sharpe_map = {}
        for ticker in tickers:
            asset = risk.get('assets', {}).get(ticker, {})
            vol = _safe_float(asset.get('volatility'))
            asset_return = _safe_float(asset.get('mean_annual_return'))
            vol_map[ticker] = vol if vol and vol > 0 else 0.25
            sharpe_map[ticker] = (asset_return or 0.0) / max(vol_map[ticker], 1e-6)

        excess = 0.0
        rationale = []
        for ticker in tickers:
            if suggested[ticker] > max_weight:
                overflow = suggested[ticker] - max_weight
                suggested[ticker] = max_weight
                excess += overflow
                rationale.append(
                    f"Reduced {ticker} to {max_weight * 100:.1f}% to lower concentration risk."
                )

        if excess > 1e-9:
            for _ in range(5):
                eligible = [t for t in tickers if suggested[t] < max_weight - 1e-9]
                if not eligible:
                    break
                scores = {
                    t: max((1.0 / max(vol_map[t], 1e-6)) * max(sharpe_map[t] + 1.5, 0.1), 0.1)
                    for t in eligible
                }
                total_score = sum(scores.values())
                moved = 0.0
                for ticker in eligible:
                    capacity = max_weight - suggested[ticker]
                    add = min(capacity, excess * (scores[ticker] / total_score))
                    suggested[ticker] += add
                    moved += add
                excess -= moved
                if moved <= 1e-9:
                    break

        total = sum(suggested.values())
        if total > 0:
            for ticker in tickers:
                suggested[ticker] /= total

        deltas = {ticker: suggested[ticker] - current[ticker] for ticker in tickers}
        cov_dict = risk.get('covariance_matrix') or {}
        old_vol = self._portfolio_volatility_from_cov(current, tickers, cov_dict)
        new_vol = self._portfolio_volatility_from_cov(suggested, tickers, cov_dict)

        if not rationale:
            rationale.append('Current allocation is already within the selected concentration thresholds.')
        rationale.append('Redistribution favors lower-volatility names with stronger risk-adjusted return profiles.')

        return {
            'current_weights': current,
            'suggested_weights': suggested,
            'deltas': deltas,
            'estimated_volatility_before': old_vol,
            'estimated_volatility_after': new_vol,
            'estimated_volatility_delta': (
                (new_vol - old_vol) if old_vol is not None and new_vol is not None else None
            ),
            'rationale': rationale,
        }

    def _portfolio_volatility_from_cov(self, weights: Dict, tickers: List[str], cov_dict: Dict) -> Optional[float]:
        if not cov_dict:
            return None
        try:
            w = np.array([weights[t] for t in tickers], dtype=float)
            cov = np.array([[float(cov_dict[a][b]) for b in tickers] for a in tickers], dtype=float)
            var = float(np.dot(w.T, np.dot(cov, w)))
            return float(np.sqrt(max(var, 0.0)))
        except Exception:
            return None


class SupervisorAgent:
    def __init__(self, risk_agent, compliance_agent, reporting_agent, aggregator, rebalancing_engine=None):
        self.risk_agent = risk_agent
        self.compliance_agent = compliance_agent
        self.reporting_agent = reporting_agent
        self.aggregator = aggregator
        self.rebalancing_engine = rebalancing_engine or RebalancingEngine()

    def run(self, portfolio: List[Dict], analysis_config: Optional[Dict] = None):
        return self.run_with_callback(portfolio, lambda event, data: None, analysis_config)

    def run_with_callback(self, portfolio: List[Dict], emit, analysis_config: Optional[Dict] = None):
        config = analysis_config or {}
        tasks = ['risk', 'compliance', 'rebalancing', 'reporting']
        results = {}
        timings = {}
        total_start = time.perf_counter()

        emit('started', {'tasks': tasks})
        emit('agent_running', {'agent': 'risk'})
        emit('agent_running', {'agent': 'compliance'})

        with ThreadPoolExecutor(max_workers=2) as executor:
            risk_start = time.perf_counter()
            risk_future = executor.submit(self.risk_agent.analyze, portfolio, config)
            compliance_start = time.perf_counter()
            compliance_future = executor.submit(self.compliance_agent.check, portfolio, config)

            try:
                risk = risk_future.result()
                results['risk'] = risk
                t = round(time.perf_counter() - risk_start, 4)
                timings['risk_seconds'] = t
                emit('agent_done', {'agent': 'risk', 'result': risk, 'duration': t})
            except Exception as exc:
                timings['risk_seconds'] = round(time.perf_counter() - risk_start, 4)
                results['risk_error'] = str(exc) + '\n' + traceback.format_exc()
                emit('agent_error', {'agent': 'risk', 'error': str(exc)})

            try:
                compliance = compliance_future.result()
                results['compliance'] = compliance
                t = round(time.perf_counter() - compliance_start, 4)
                timings['compliance_seconds'] = t
                emit('agent_done', {'agent': 'compliance', 'result': compliance, 'duration': t})
            except Exception as exc:
                timings['compliance_seconds'] = round(time.perf_counter() - compliance_start, 4)
                results['compliance_error'] = str(exc) + '\n' + traceback.format_exc()
                emit('agent_error', {'agent': 'compliance', 'error': str(exc)})

            emit('agent_running', {'agent': 'rebalancing'})
            rebalancing_start = time.perf_counter()
            try:
                rebalancing = self.rebalancing_engine.suggest(
                    portfolio,
                    results.get('risk', {}),
                    results.get('compliance', {}),
                )
                results['rebalancing'] = rebalancing
                t = round(time.perf_counter() - rebalancing_start, 4)
                timings['rebalancing_seconds'] = t
                emit('agent_done', {'agent': 'rebalancing', 'result': rebalancing, 'duration': t})
            except Exception as exc:
                timings['rebalancing_seconds'] = round(time.perf_counter() - rebalancing_start, 4)
                results['rebalancing_error'] = str(exc) + '\n' + traceback.format_exc()
                emit('agent_error', {'agent': 'rebalancing', 'error': str(exc)})

            emit('agent_running', {'agent': 'reporting'})
            reporting_start = time.perf_counter()
            try:
                report = self.reporting_agent.generate(portfolio, results, config)
                results['report'] = report
                t = round(time.perf_counter() - reporting_start, 4)
                timings['reporting_seconds'] = t
                emit('agent_done', {'agent': 'reporting', 'result': report, 'duration': t})
            except Exception as exc:
                timings['reporting_seconds'] = round(time.perf_counter() - reporting_start, 4)
                results['report_error'] = str(exc) + '\n' + traceback.format_exc()
                emit('agent_error', {'agent': 'reporting', 'error': str(exc)})

        aggregation = self.aggregator.aggregate(portfolio, results)
        results['aggregation'] = aggregation
        timings['total_seconds'] = round(time.perf_counter() - total_start, 4)
        results['timings'] = timings
        emit('aggregated', {'aggregation': aggregation, 'timings': timings})
        return tasks, results


class RiskAgent:
    def __init__(self, benchmark='SPY'):
        self.default_benchmark = benchmark

    def analyze(self, portfolio: List[Dict], analysis_config: Optional[Dict] = None):
        config = analysis_config or {}
        benchmark_symbol = self._normalize_benchmark(str(config.get('benchmark') or self.default_benchmark))
        stress_test = bool(config.get('stress_test', True))
        rf = 0.01

        assets = {}
        daily_returns = {}
        fundamentals_rollup = []
        for item in portfolio:
            ticker = item['ticker']
            prices = market_service.get_prices(ticker)
            returns = prices.pct_change().dropna()
            daily_returns[ticker] = returns
            fundamentals = market_service.get_fundamentals(ticker)
            size_bucket = _market_cap_bucket(fundamentals.get('market_cap'))
            dividend_yield = _safe_float(fundamentals.get('dividend_yield')) or 0.0
            assets[ticker] = {
                'volatility': float(returns.std() * (252 ** 0.5)),
                'mean_annual_return': float(returns.mean() * 252),
                'cumulative_return': float(((1 + returns).cumprod() - 1).iloc[-1]) if not returns.empty else None,
                'fundamentals': {
                    **fundamentals,
                    'size_bucket': size_bucket,
                    'income_profile': 'income_oriented' if dividend_yield >= 0.02 else 'low_income',
                },
            }
            fundamentals_rollup.append((float(item['weight']), fundamentals, size_bucket))

        tickers = [item['ticker'] for item in portfolio]
        weights = np.array([float(item['weight']) for item in portfolio], dtype=float)
        returns_matrix = pd.concat([daily_returns[t] for t in tickers], axis=1, join='inner')
        returns_matrix.columns = tickers

        portfolio_daily = returns_matrix.dot(weights)
        portfolio_cumulative = (1 + portfolio_daily).cumprod() - 1
        portfolio_total_return = float(portfolio_cumulative.iloc[-1]) if not portfolio_cumulative.empty else None
        portfolio_vol = float(portfolio_daily.std() * (252 ** 0.5))
        portfolio_return_ann = float(portfolio_daily.mean() * 252)
        sharpe = (portfolio_return_ann - rf) / portfolio_vol if portfolio_vol > 0 else 0.0
        var_95 = float(-np.percentile(portfolio_daily, 5) * (252 ** 0.5))

        rolling_vol_30 = portfolio_daily.rolling(30).std() * (252 ** 0.5)
        rolling_vol_90 = portfolio_daily.rolling(90).std() * (252 ** 0.5)
        rolling_return_30 = (1 + portfolio_daily).rolling(30).apply(np.prod, raw=True) - 1
        rolling_return_90 = (1 + portfolio_daily).rolling(90).apply(np.prod, raw=True) - 1
        rolling_sharpe_30 = self._rolling_sharpe(portfolio_daily, 30, rf)
        rolling_sharpe_90 = self._rolling_sharpe(portfolio_daily, 90, rf)

        portfolio_growth = 1 + portfolio_cumulative
        running_peak = portfolio_growth.cummax()
        drawdown_series = portfolio_growth / running_peak - 1
        max_drawdown = float(drawdown_series.min()) if not drawdown_series.empty else None

        covariance = returns_matrix.cov() * 252
        correlation_df = returns_matrix.corr().fillna(0.0)
        correlation_payload = self._build_correlation_payload(correlation_df)
        risk_contribution = self._risk_contribution(tickers, weights, covariance)

        benchmark_payload = self._build_benchmark_payload(portfolio_daily, benchmark_symbol, rf)
        beta = benchmark_payload.get('beta')
        alpha = benchmark_payload.get('alpha')
        relative_performance = benchmark_payload.get('relative_performance_series', [])

        stress = None
        if stress_test:
            beta_for_shock = beta if beta is not None else 1.0
            shock = -0.20
            stress = {
                'name': 'market_shock_-20pct',
                'shock_assumption': shock,
                'estimated_portfolio_impact': float(beta_for_shock * shock),
            }

        portfolio_characteristics = self._derive_portfolio_characteristics(portfolio, fundamentals_rollup)
        fundamentals_summary = self._build_portfolio_fundamentals(portfolio, assets)
        return_distribution = {
            'mean_daily_return': float(portfolio_daily.mean()),
            'median_daily_return': float(portfolio_daily.median()),
            'std_daily_return': float(portfolio_daily.std()),
            'best_day': float(portfolio_daily.max()),
            'worst_day': float(portfolio_daily.min()),
            'positive_day_ratio': float((portfolio_daily > 0).mean()),
            'skewness': float(portfolio_daily.skew()),
            'kurtosis': float(portfolio_daily.kurt()),
        }

        return {
            'assets': assets,
            'portfolio': {
                'volatility': portfolio_vol,
                'sharpe': sharpe,
                'var_95': var_95,
                'beta': beta,
                'alpha': alpha,
                'max_drawdown': max_drawdown,
                'cumulative_return': portfolio_total_return,
                'rolling_volatility_latest': {
                    '30d': float(rolling_vol_30.dropna().iloc[-1]) if not rolling_vol_30.dropna().empty else None,
                    '90d': float(rolling_vol_90.dropna().iloc[-1]) if not rolling_vol_90.dropna().empty else None,
                },
                'rolling_return_latest': {
                    '30d': float(rolling_return_30.dropna().iloc[-1]) if not rolling_return_30.dropna().empty else None,
                    '90d': float(rolling_return_90.dropna().iloc[-1]) if not rolling_return_90.dropna().empty else None,
                },
                'rolling_sharpe_latest': {
                    '30d': float(rolling_sharpe_30.dropna().iloc[-1]) if not rolling_sharpe_30.dropna().empty else None,
                    '90d': float(rolling_sharpe_90.dropna().iloc[-1]) if not rolling_sharpe_90.dropna().empty else None,
                },
                'return_distribution_summary': return_distribution,
                'fundamentals': fundamentals_summary,
                'characteristics': portfolio_characteristics,
            },
            'benchmark': benchmark_payload,
            'performance': {
                'cumulative_returns': {
                    'portfolio': _series_to_points(portfolio_cumulative, tail=504),
                    'benchmark': benchmark_payload.get('cumulative_returns', []),
                },
                'rolling_returns': {
                    '30d': _series_to_points(rolling_return_30, tail=252),
                    '90d': _series_to_points(rolling_return_90, tail=252),
                },
                'rolling_sharpe': {
                    '30d': _series_to_points(rolling_sharpe_30, tail=252),
                    '90d': _series_to_points(rolling_sharpe_90, tail=252),
                },
                'relative_performance': relative_performance,
                'benchmark': benchmark_payload,
                'series': {
                    'portfolio_cumulative': _series_to_points(portfolio_cumulative, tail=504),
                    'benchmark_cumulative': benchmark_payload.get('cumulative_returns', []),
                    'rolling_return_30d': _series_to_points(rolling_return_30, tail=252),
                    'rolling_return_90d': _series_to_points(rolling_return_90, tail=252),
                },
            },
            'risk_insights': {
                'correlation_matrix': correlation_payload,
                'risk_contribution': risk_contribution,
                'series': {
                    'drawdown': _series_to_points(drawdown_series, tail=504),
                    'rolling_vol_30d': _series_to_points(rolling_vol_30, tail=252),
                    'rolling_vol_90d': _series_to_points(rolling_vol_90, tail=252),
                    'rolling_sharpe_30d': _series_to_points(rolling_sharpe_30, tail=252),
                    'rolling_sharpe_90d': _series_to_points(rolling_sharpe_90, tail=252),
                },
                'drawdown_summary': {
                    'max_drawdown': max_drawdown,
                    'latest_drawdown': float(drawdown_series.iloc[-1]) if not drawdown_series.empty else None,
                },
                'concentration': {
                    'largest_holding': self._largest_holding(portfolio),
                    'largest_sector': self._largest_sector(portfolio_characteristics.get('sector_weights', {})),
                },
                'stress_test': stress,
            },
            'correlation_matrix': correlation_payload,
            'covariance_matrix': covariance.round(8).to_dict(),
            'risk_contribution': risk_contribution,
        }

    def _normalize_benchmark(self, benchmark: str) -> str:
        benchmark = benchmark.strip().upper() if benchmark else self.default_benchmark
        if benchmark in {'NIFTY', 'NSEI'}:
            return '^NSEI'
        if benchmark not in {'SPY', '^NSEI'}:
            return self.default_benchmark
        return benchmark

    def _build_benchmark_payload(self, portfolio_daily: pd.Series, benchmark_symbol: str, rf: float) -> Dict:
        payload = {
            'name': BENCHMARK_NAMES.get(benchmark_symbol, benchmark_symbol),
            'symbol': benchmark_symbol,
            'returns': [],
            'cumulative_returns': [],
            'cumulative_return': None,
            'alpha': None,
            'beta': None,
            'relative_performance': None,
            'relative_performance_series': [],
        }
        try:
            benchmark_prices = market_service.get_prices(benchmark_symbol)
            benchmark_daily = benchmark_prices.pct_change().dropna()
        except Exception:
            return payload

        aligned = pd.concat([portfolio_daily, benchmark_daily], axis=1, join='inner').dropna()
        if aligned.empty:
            return payload
        aligned.columns = ['portfolio', 'benchmark']

        benchmark_cumulative = (1 + aligned['benchmark']).cumprod() - 1
        portfolio_cumulative = (1 + aligned['portfolio']).cumprod() - 1
        relative_performance = portfolio_cumulative - benchmark_cumulative
        covariance = aligned['portfolio'].cov(aligned['benchmark'])
        benchmark_var = aligned['benchmark'].var()
        beta = float(covariance / benchmark_var) if benchmark_var > 0 else None
        portfolio_total = float(portfolio_cumulative.iloc[-1])
        benchmark_total = float(benchmark_cumulative.iloc[-1])
        alpha = portfolio_total - benchmark_total

        payload.update({
            'returns': _series_to_points(aligned['benchmark'], tail=504),
            'cumulative_returns': _series_to_points(benchmark_cumulative, tail=504),
            'cumulative_return': benchmark_total,
            'portfolio_cumulative_return': portfolio_total,
            'alpha': alpha,
            'alpha_annualized': float((aligned['portfolio'].mean() * 252 - rf) - (aligned['benchmark'].mean() * 252 - rf)),
            'beta': beta,
            'relative_performance': float(relative_performance.iloc[-1]),
            'relative_performance_series': _series_to_points(relative_performance, tail=504),
        })
        return payload

    def _build_correlation_payload(self, correlation_df: pd.DataFrame) -> Dict:
        labels = list(correlation_df.columns)
        values = correlation_df.round(4).values.tolist()
        strong_pairs = []
        weak_pairs = []
        for i, left in enumerate(labels):
            for j in range(i + 1, len(labels)):
                right = labels[j]
                value = float(correlation_df.iloc[i, j])
                item = {'left': left, 'right': right, 'value': value}
                if value > 0.8:
                    strong_pairs.append(item)
                if abs(value) < 0.3:
                    weak_pairs.append(item)
        return {
            'labels': labels,
            'values': values,
            'strong_pairs': strong_pairs,
            'weak_pairs': weak_pairs,
        }

    def _risk_contribution(self, tickers: List[str], weights: np.ndarray, covariance: pd.DataFrame) -> List[Dict]:
        if covariance is None or covariance.empty:
            return []
        cov = covariance.values
        port_var = float(np.dot(weights.T, np.dot(cov, weights)))
        if port_var <= 0:
            return []
        sigma_w = np.dot(cov, weights)
        contributions_var = weights * sigma_w
        total = float(np.sum(contributions_var))
        if total <= 0:
            return []
        payload = []
        for idx, ticker in enumerate(tickers):
            pct = float(contributions_var[idx] / total)
            payload.append({
                'ticker': ticker,
                'contribution_percent': pct,
                'contribution_pct': pct,
            })
        payload.sort(key=lambda item: item['contribution_percent'], reverse=True)
        return payload

    def _rolling_sharpe(self, returns: pd.Series, window: int, rf_annual: float) -> pd.Series:
        rf_daily = rf_annual / 252.0
        rolling_mean = returns.rolling(window).mean() - rf_daily
        rolling_std = returns.rolling(window).std()
        ratio = rolling_mean / rolling_std.replace(0, np.nan)
        return ratio * np.sqrt(252)

    def _build_portfolio_fundamentals(self, portfolio: List[Dict], assets: Dict) -> Dict:
        def weighted_avg(field: str):
            num = 0.0
            den = 0.0
            for item in portfolio:
                val = assets.get(item['ticker'], {}).get('fundamentals', {}).get(field)
                if val is None:
                    continue
                num += float(item['weight']) * float(val)
                den += float(item['weight'])
            return None if den <= 0 else num / den

        analyst_upside = 0.0
        analyst_den = 0.0
        for item in portfolio:
            fundamentals = assets.get(item['ticker'], {}).get('fundamentals', {})
            price = _safe_float(fundamentals.get('current_price'))
            target = _safe_float(fundamentals.get('target_mean_price'))
            if price and target and price > 0:
                analyst_upside += float(item['weight']) * ((target - price) / price)
                analyst_den += float(item['weight'])

        market_cap_total = sum(
            assets.get(item['ticker'], {}).get('fundamentals', {}).get('market_cap') or 0.0
            for item in portfolio
        )
        return {
            'forward_pe_weighted': weighted_avg('forward_pe'),
            'trailing_pe_weighted': weighted_avg('trailing_pe'),
            'dividend_yield_weighted': weighted_avg('dividend_yield'),
            'beta_fundamental_weighted': weighted_avg('beta_fundamental'),
            'analyst_upside_weighted': None if analyst_den <= 0 else analyst_upside / analyst_den,
            'total_market_cap': market_cap_total if market_cap_total > 0 else None,
            'coverage': {
                'tickers_with_market_cap': sum(
                    1
                    for item in portfolio
                    if assets.get(item['ticker'], {}).get('fundamentals', {}).get('market_cap') is not None
                ),
                'total_tickers': len(portfolio),
            },
        }

    def _derive_portfolio_characteristics(self, portfolio: List[Dict], fundamentals_rollup: List):
        sector_weights = {}
        size_weights = {}
        dividend_weight = 0.0
        growth_weight = 0.0
        for weight, fundamentals, size_bucket in fundamentals_rollup:
            sector = fundamentals.get('sector') or 'Unknown'
            sector_weights[sector] = sector_weights.get(sector, 0.0) + weight
            size_weights[size_bucket] = size_weights.get(size_bucket, 0.0) + weight
            if (_safe_float(fundamentals.get('dividend_yield')) or 0.0) >= 0.02:
                dividend_weight += weight
            if (_safe_float(fundamentals.get('forward_pe')) or 0.0) >= 25:
                growth_weight += weight

        style_flags = []
        if size_weights.get('mega_cap', 0.0) + size_weights.get('large_cap', 0.0) >= 0.7:
            style_flags.append('large_cap_dominated')
        if growth_weight >= 0.5:
            style_flags.append('growth_heavy')
        if dividend_weight < 0.25:
            style_flags.append('low_income_exposure')

        return {
            'sector_weights': sector_weights,
            'size_weights': size_weights,
            'style_flags': style_flags,
        }

    def _largest_holding(self, portfolio: List[Dict]) -> Optional[Dict]:
        if not portfolio:
            return None
        item = max(portfolio, key=lambda row: row['weight'])
        return {'ticker': item['ticker'], 'weight': float(item['weight'])}

    def _largest_sector(self, sector_weights: Dict) -> Optional[Dict]:
        if not sector_weights:
            return None
        sector, weight = max(sector_weights.items(), key=lambda item: item[1])
        return {'sector': sector, 'weight': float(weight)}


class ComplianceAgent:
    PROFILE_RULES = {
        'conservative': {
            'single_asset_max': 0.25,
            'sector_max': 0.40,
            'min_assets': 5,
            'max_assets': 15,
            'min_weight': 0.03,
            'min_sectors': 3,
            'weight_sum_tolerance': 0.01,
        },
        'moderate': {
            'single_asset_max': 0.40,
            'sector_max': 0.60,
            'min_assets': 4,
            'max_assets': 20,
            'min_weight': 0.02,
            'min_sectors': 2,
            'weight_sum_tolerance': 0.02,
        },
        'aggressive': {
            'single_asset_max': 0.50,
            'sector_max': 0.75,
            'min_assets': 3,
            'max_assets': 25,
            'min_weight': 0.01,
            'min_sectors': 1,
            'weight_sum_tolerance': 0.03,
        },
    }

    def check(self, portfolio: List[Dict], analysis_config: Optional[Dict] = None):
        config = analysis_config or {}
        risk_profile = str(config.get('risk_profile') or 'moderate').lower()
        profile_rules = dict(self.PROFILE_RULES.get(risk_profile, self.PROFILE_RULES['moderate']))
        for key, value in (config.get('compliance_rules') or {}).items():
            if value is not None and key in profile_rules:
                profile_rules[key] = value

        issues = []
        violations = []
        total_weight = sum(item['weight'] for item in portfolio)
        if abs(total_weight - 1.0) > profile_rules['weight_sum_tolerance']:
            self._add_violation(violations, issues, 'weight_sum', 'high', (
                f"Portfolio weights sum to {total_weight * 100:.1f}% and must stay within "
                f"{profile_rules['weight_sum_tolerance'] * 100:.0f}% of 100%."
            ))

        if len(portfolio) < profile_rules['min_assets']:
            self._add_violation(violations, issues, 'min_assets', 'medium', (
                f"Portfolio holds {len(portfolio)} assets, below the minimum of {profile_rules['min_assets']}."
            ))
        if len(portfolio) > profile_rules['max_assets']:
            self._add_violation(violations, issues, 'max_assets', 'medium', (
                f"Portfolio holds {len(portfolio)} assets, above the maximum of {profile_rules['max_assets']}."
            ))

        for item in portfolio:
            if item['weight'] > profile_rules['single_asset_max'] + 1e-9:
                self._add_violation(violations, issues, 'single_asset_max', 'high', (
                    f"{item['ticker']} is {item['weight'] * 100:.1f}% of the portfolio, above the limit of {profile_rules['single_asset_max'] * 100:.0f}%."
                ))
            if 0 < item['weight'] < profile_rules['min_weight'] - 1e-9:
                self._add_violation(violations, issues, 'min_weight', 'low', (
                    f"{item['ticker']} is only {item['weight'] * 100:.1f}%, below the minimum position size of {profile_rules['min_weight'] * 100:.0f}%."
                ))

        sectors = {}
        for item in portfolio:
            sector = market_service.get_sector(item['ticker']) or 'Unknown'
            sectors[sector] = sectors.get(sector, 0.0) + item['weight']

        for sector, weight in sectors.items():
            if weight > profile_rules['sector_max'] + 1e-9:
                self._add_violation(violations, issues, 'sector_max', 'high', (
                    f"Sector {sector} is {weight * 100:.1f}% of the portfolio, above the allowed {profile_rules['sector_max'] * 100:.0f}%."
                ))

        if len(sectors) < profile_rules['min_sectors']:
            self._add_violation(violations, issues, 'min_sectors', 'medium', (
                f"Portfolio spans {len(sectors)} sectors, below the minimum diversification requirement of {profile_rules['min_sectors']}."
            ))

        return {
            'ok': not violations,
            'issues': issues,
            'violations': violations,
            'sectors': sectors,
            'risk_profile': risk_profile,
            'applied_rules': profile_rules,
        }

    def _add_violation(self, violations: List[Dict], issues: List[str], rule: str, severity: str, message: str):
        issues.append(message)
        violations.append({'rule': rule, 'message': message, 'severity': severity})


class ReportingAgent:
    def generate(self, portfolio: List[Dict], results: Dict, analysis_config: Optional[Dict] = None):
        config = analysis_config or {}
        mode = str(config.get('mode') or 'advanced')
        fallback = self._build_fallback(portfolio, results)

        prompt = self._build_prompt(portfolio, results)
        insight = generate_insights(prompt)
        if not insight or insight.startswith('[Gemini API error]') or len(insight.strip()) < 120:
            fallback['source'] = 'deterministic_fallback'
            fallback['mode'] = mode
            return fallback

        parsed = self._parse_structured_report(insight)
        if not parsed:
            fallback['source'] = 'deterministic_fallback'
            fallback['mode'] = mode
            return fallback

        merged = self._normalize_report(parsed, fallback)
        merged['source'] = 'gemini'
        merged['mode'] = mode
        return merged

    def _build_prompt(self, portfolio: List[Dict], results: Dict) -> str:
        risk = results.get('risk', {})
        port = risk.get('portfolio', {})
        benchmark = risk.get('benchmark', {})
        compliance = results.get('compliance', {})
        rebalancing = results.get('rebalancing', {})
        characteristics = port.get('characteristics', {})
        contributions = risk.get('risk_contribution', [])[:3]
        compliance_lines = [
            f"- Violation: {v.get('severity')} / {v.get('rule')} / {v.get('message')}"
            for v in compliance.get('violations', [])
        ] or ['- Violation: none']
        rebalancing_lines = [
            f"- {ticker}: {(weight * 100):.1f}%"
            for ticker, weight in (rebalancing.get('suggested_weights') or {}).items()
        ] or ['- No suggestion']

        return '\n'.join([
            'You are the reporting agent for a portfolio intelligence platform.',
            'Return ONLY strict JSON with keys: summary, simple_summary, key_insights, simple_insights, risks, opportunities, recommendations, explanations.',
            'explanations must contain keys volatility, sharpe, var, alpha, concentration. Each key must be an object with advanced and simple strings.',
            'Make all statements data-driven, specific, and actionable. Do not use generic filler.',
            '',
            'Portfolio:',
            *[f"- {item['ticker']}: {item['weight'] * 100:.1f}%" for item in portfolio],
            '',
            'Core metrics:',
            f"- Cumulative return: {self._fmt_pct(port.get('cumulative_return'))}",
            f"- Volatility: {self._fmt_pct(port.get('volatility'))}",
            f"- Sharpe: {self._fmt_num(port.get('sharpe'))}",
            f"- VaR 95: {self._fmt_pct(port.get('var_95'))}",
            f"- Max drawdown: {self._fmt_pct(port.get('max_drawdown'))}",
            f"- Alpha: {self._fmt_pct(port.get('alpha'))}",
            f"- Benchmark: {benchmark.get('name')} ({benchmark.get('symbol')}) cumulative return {self._fmt_pct(benchmark.get('cumulative_return'))}",
            '',
            'Portfolio characteristics:',
            f"- Style flags: {', '.join(characteristics.get('style_flags', [])) or 'none'}",
            *[f"- Top risk contributor: {item['ticker']} at {self._fmt_pct(item.get('contribution_percent'))}" for item in contributions],
            '',
            'Compliance:',
            f"- Passed: {'yes' if compliance.get('ok') else 'no'}",
            *compliance_lines,
            '',
            'Rebalancing:',
            *rebalancing_lines,
        ])

    def _build_fallback(self, portfolio: List[Dict], results: Dict) -> Dict:
        risk = results.get('risk', {})
        port = risk.get('portfolio', {})
        benchmark = risk.get('benchmark', {})
        compliance = results.get('compliance', {})
        rebalancing = results.get('rebalancing', {})
        characteristics = port.get('characteristics', {})
        largest_holding = risk.get('risk_insights', {}).get('concentration', {}).get('largest_holding')
        largest_sector = risk.get('risk_insights', {}).get('concentration', {}).get('largest_sector')

        high_var = (port.get('var_95') or 0) > 0.20
        low_sharpe = (port.get('sharpe') or 0) < 0.8
        concentration = (largest_holding or {}).get('weight', 0) > 0.30 or (largest_sector or {}).get('weight', 0) > 0.55

        key_insights = []
        if benchmark.get('alpha') is not None:
            key_insights.append(
                f"Portfolio {'outperformed' if benchmark['alpha'] >= 0 else 'lagged'} the benchmark by {self._fmt_pct(benchmark['alpha'])}."
            )
        if characteristics.get('style_flags'):
            key_insights.append(
                f"Portfolio profile is {', '.join(flag.replace('_', ' ') for flag in characteristics['style_flags'])}."
            )
        if largest_holding:
            key_insights.append(
                f"Largest holding is {largest_holding['ticker']} at {self._fmt_pct(largest_holding['weight'])}."
            )

        risks = []
        if high_var:
            risks.append(f"Worst expected annualized loss at 95% confidence is {self._fmt_pct(port.get('var_95'))}, which is elevated.")
        if low_sharpe:
            risks.append(f"Sharpe ratio is {self._fmt_num(port.get('sharpe'))}, indicating weak return per unit of risk.")
        if concentration and largest_sector:
            risks.append(f"Sector concentration is led by {largest_sector['sector']} at {self._fmt_pct(largest_sector['weight'])}.")
        if not risks:
            risks.append('Risk profile is balanced relative to the selected benchmark and policy limits.')

        opportunities = []
        if (port.get('fundamentals', {}).get('analyst_upside_weighted') or 0) > 0.10:
            opportunities.append('Analyst targets imply upside potential if the current growth thesis holds.')
        if 'low_income_exposure' in characteristics.get('style_flags', []):
            opportunities.append('Income exposure is low, so adding yield-oriented names could diversify the return profile.')
        if benchmark.get('alpha') is not None and benchmark['alpha'] < 0:
            opportunities.append('Relative underperformance leaves room to tighten benchmark tracking or rotate away from laggards.')
        if not opportunities:
            opportunities.append('Current mix already balances growth and diversification reasonably well.')

        recommendations = list(rebalancing.get('rationale', []))[:2]
        if compliance.get('violations'):
            recommendations.append('Address the highest-severity compliance violation before approving the allocation.')
        else:
            recommendations.append('Review benchmark-relative drift weekly and rebalance only if concentration worsens.')
        recommendations = recommendations[:4]

        summary = (
            f"The portfolio returned {self._fmt_pct(port.get('cumulative_return'))} with volatility at {self._fmt_pct(port.get('volatility'))}, "
            f"Sharpe at {self._fmt_num(port.get('sharpe'))}, and alpha versus {benchmark.get('symbol') or 'benchmark'} at {self._fmt_pct(benchmark.get('alpha'))}."
        )
        simple_summary = (
            f"Your portfolio {'beat' if (benchmark.get('alpha') or 0) >= 0 else 'trailed'} the market by {self._fmt_pct(benchmark.get('alpha'))} and had "
            f"{'high' if high_var else 'manageable'} price swings."
        )

        explanations = {
            'volatility': {
                'advanced': f"Annualized volatility is {self._fmt_pct(port.get('volatility'))}, which measures the typical size of portfolio price moves.",
                'simple': f"Price swings are about {self._fmt_pct(port.get('volatility'))}; bigger numbers mean a bumpier ride.",
            },
            'sharpe': {
                'advanced': f"Sharpe ratio is {self._fmt_num(port.get('sharpe'))}, summarizing return earned per unit of total risk.",
                'simple': f"Risk vs reward is {self._fmt_num(port.get('sharpe'))}; higher means you were paid more for the risk you took.",
            },
            'var': {
                'advanced': f"Historical 95% VaR is {self._fmt_pct(port.get('var_95'))}, the modeled annualized loss threshold in a stressed but plausible scenario.",
                'simple': f"Worst expected loss is about {self._fmt_pct(port.get('var_95'))} in a bad market stretch.",
            },
            'alpha': {
                'advanced': f"Alpha versus {benchmark.get('symbol') or 'benchmark'} is {self._fmt_pct(benchmark.get('alpha'))}, representing excess return over the benchmark path.",
                'simple': f"Beating the market is {self._fmt_pct(benchmark.get('alpha'))}; positive means you finished ahead of the benchmark.",
            },
            'concentration': {
                'advanced': (
                    f"Largest holding is {(largest_holding or {}).get('ticker', 'n/a')} at {self._fmt_pct((largest_holding or {}).get('weight'))}; "
                    f"largest sector is {(largest_sector or {}).get('sector', 'n/a')} at {self._fmt_pct((largest_sector or {}).get('weight'))}."
                ),
                'simple': 'A lot of your result depends on a few names or sectors when concentration gets too high.',
            },
            'high_var': 'VaR is high, so downside scenarios deserve tighter position sizing.' if high_var else 'VaR is within a moderate range for this mix.',
            'low_sharpe': 'Sharpe is low, so returns have not justified the risk taken.' if low_sharpe else 'Sharpe is healthy for the risk taken.',
            'concentration_flag': 'Concentration is elevated and should be monitored.' if concentration else 'Concentration is not the main risk driver right now.',
        }

        return {
            'summary': summary,
            'simple_summary': simple_summary,
            'key_insights': key_insights,
            'simple_insights': [
                insight.replace('Portfolio', 'Your portfolio').replace('benchmark', 'market')
                for insight in key_insights
            ] or [simple_summary],
            'risks': risks,
            'opportunities': opportunities,
            'recommendations': recommendations,
            'explanations': explanations,
            'compliance_issues': [v['message'] for v in compliance.get('violations', [])],
        }

    def _parse_structured_report(self, text: str) -> Optional[Dict]:
        candidate = (text or '').strip()
        if not candidate:
            return None
        try:
            obj = json.loads(candidate)
            return obj if isinstance(obj, dict) else None
        except Exception:
            pass
        start = candidate.find('{')
        end = candidate.rfind('}')
        if start >= 0 and end > start:
            try:
                obj = json.loads(candidate[start:end + 1])
                return obj if isinstance(obj, dict) else None
            except Exception:
                return None
        return None

    def _normalize_report(self, parsed: Dict, fallback: Dict) -> Dict:
        explanations = parsed.get('explanations') if isinstance(parsed.get('explanations'), dict) else {}
        merged_explanations = dict(fallback.get('explanations', {}))
        for key, value in explanations.items():
            merged_explanations[key] = value
        return {
            'summary': parsed.get('summary') or fallback.get('summary'),
            'simple_summary': parsed.get('simple_summary') or fallback.get('simple_summary'),
            'key_insights': parsed.get('key_insights') or fallback.get('key_insights', []),
            'simple_insights': parsed.get('simple_insights') or fallback.get('simple_insights', []),
            'risks': parsed.get('risks') or fallback.get('risks', []),
            'opportunities': parsed.get('opportunities') or fallback.get('opportunities', []),
            'recommendations': parsed.get('recommendations') or fallback.get('recommendations', []),
            'explanations': merged_explanations,
            'compliance_issues': parsed.get('compliance_issues') or fallback.get('compliance_issues', []),
        }

    def _fmt_pct(self, value):
        return 'n/a' if value is None else f"{value * 100:.1f}%"

    def _fmt_num(self, value):
        return 'n/a' if value is None else f"{value:.2f}"


class Aggregator:
    def aggregate(self, portfolio: List[Dict], results: Dict):
        risk = results.get('risk') or {}
        compliance = results.get('compliance') or {}
        rebalancing = results.get('rebalancing') or {}
        report = results.get('report') or {}
        performance = risk.get('performance') or {}
        risk_insights = risk.get('risk_insights') or {}
        benchmark = risk.get('benchmark') or performance.get('benchmark') or {}

        return {
            'portfolio': portfolio,
            'risk': risk,
            'benchmark': benchmark,
            'performance': performance,
            'risk_insights': risk_insights,
            'correlation_matrix': risk.get('correlation_matrix') or risk_insights.get('correlation_matrix'),
            'risk_contribution': risk.get('risk_contribution') or risk_insights.get('risk_contribution', []),
            'compliance': compliance,
            'rebalancing': rebalancing,
            'report': report,
            'insights': report,
            'meta': {
                'schema_version': '3.0',
                'generated_at_unix': int(time.time()),
            },
        }
