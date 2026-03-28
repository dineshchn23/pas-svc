import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

import market_service
from gemini_client import generate_insights


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
        for ticker in tickers:
            vol = _safe_float(risk.get('assets', {}).get(ticker, {}).get('volatility'))
            vol_map[ticker] = vol if vol and vol > 0 else 0.25

        excess = 0.0
        rationale = []
        for ticker in tickers:
            if suggested[ticker] > max_weight:
                overflow = suggested[ticker] - max_weight
                suggested[ticker] = max_weight
                excess += overflow
                rationale.append(
                    f"Reduced {ticker} to {max_weight * 100:.1f}% cap to limit concentration risk."
                )

        if excess > 1e-9:
            for _ in range(5):
                eligible = [t for t in tickers if suggested[t] < max_weight - 1e-9]
                if not eligible:
                    break
                inv_vol = {t: 1.0 / max(vol_map[t], 1e-6) for t in eligible}
                total_score = sum(inv_vol.values())
                if total_score <= 0:
                    break

                moved = 0.0
                for ticker in eligible:
                    capacity = max_weight - suggested[ticker]
                    proposed = excess * (inv_vol[ticker] / total_score)
                    add = min(capacity, proposed)
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
            rationale.append('Current allocation is already within concentration thresholds.')
        rationale.append('Redistribution favors lower-volatility assets to support risk-adjusted returns.')

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
        """Run all agents sequentially (no streaming). Delegates to run_with_callback."""
        return self.run_with_callback(portfolio, lambda event, data: None, analysis_config)

    def run_with_callback(self, portfolio: List[Dict], emit, analysis_config: Optional[Dict] = None):
        """Run all agents and call emit(event, data) at each stage.

        Risk + Compliance run in parallel; Rebalancing + Reporting run after both
        complete so they can use full analysis context; Aggregator runs last.
        emit is called from the executor thread - callers must use thread-safe dispatch
        (e.g. asyncio loop.call_soon_threadsafe).
        """
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
            except Exception as e:
                timings['risk_seconds'] = round(time.perf_counter() - risk_start, 4)
                results['risk_error'] = str(e) + '\n' + traceback.format_exc()
                emit('agent_error', {'agent': 'risk', 'error': str(e)})

            try:
                compliance = compliance_future.result()
                results['compliance'] = compliance
                t = round(time.perf_counter() - compliance_start, 4)
                timings['compliance_seconds'] = t
                emit('agent_done', {'agent': 'compliance', 'result': compliance, 'duration': t})
            except Exception as e:
                timings['compliance_seconds'] = round(time.perf_counter() - compliance_start, 4)
                results['compliance_error'] = str(e) + '\n' + traceback.format_exc()
                emit('agent_error', {'agent': 'compliance', 'error': str(e)})

            emit('agent_running', {'agent': 'rebalancing'})
            rebalancing_start = time.perf_counter()
            try:
                suggestions = self.rebalancing_engine.suggest(
                    portfolio,
                    results.get('risk', {}),
                    results.get('compliance', {}),
                )
                results['rebalancing'] = suggestions
                t = round(time.perf_counter() - rebalancing_start, 4)
                timings['rebalancing_seconds'] = t
                emit('agent_done', {'agent': 'rebalancing', 'result': suggestions, 'duration': t})
            except Exception as e:
                timings['rebalancing_seconds'] = round(time.perf_counter() - rebalancing_start, 4)
                results['rebalancing_error'] = str(e) + '\n' + traceback.format_exc()
                emit('agent_error', {'agent': 'rebalancing', 'error': str(e)})

            emit('agent_running', {'agent': 'reporting'})
            reporting_start = time.perf_counter()
            try:
                report = self.reporting_agent.generate(portfolio, results, config)
                results['report'] = report
                t = round(time.perf_counter() - reporting_start, 4)
                timings['reporting_seconds'] = t
                emit('agent_done', {'agent': 'reporting', 'result': report, 'duration': t})
            except Exception as e:
                timings['reporting_seconds'] = round(time.perf_counter() - reporting_start, 4)
                results['report_error'] = str(e) + '\n' + traceback.format_exc()
                emit('agent_error', {'agent': 'reporting', 'error': str(e)})

        aggregation = self.aggregator.aggregate(portfolio, results)
        results['aggregation'] = aggregation
        timings['total_seconds'] = round(time.perf_counter() - total_start, 4)
        results['timings'] = timings

        emit('aggregated', {'aggregation': aggregation, 'timings': timings})
        return tasks, results


class RiskAgent:
    def __init__(self, benchmark='SPY'):
        self.default_benchmark = benchmark

    def _weighted_average(self, portfolio: List[Dict], assets: Dict, field: str):
        numerator = 0.0
        denominator = 0.0
        for item in portfolio:
            ticker = item['ticker']
            weight = float(item['weight'])
            value = assets.get(ticker, {}).get('fundamentals', {}).get(field)
            if value is None:
                continue
            numerator += weight * float(value)
            denominator += weight
        if denominator <= 0:
            return None
        return numerator / denominator

    def _weighted_analyst_upside(self, portfolio: List[Dict], assets: Dict):
        numerator = 0.0
        denominator = 0.0
        for item in portfolio:
            ticker = item['ticker']
            weight = float(item['weight'])
            f = assets.get(ticker, {}).get('fundamentals', {})
            price = f.get('current_price')
            target = f.get('target_mean_price')
            if price is None or target is None or price <= 0:
                continue
            upside = (target - price) / price
            numerator += weight * float(upside)
            denominator += weight
        if denominator <= 0:
            return None
        return numerator / denominator

    def _risk_contribution(self, tickers: List[str], weights: np.ndarray, covariance: pd.DataFrame) -> List[Dict]:
        if covariance is None or covariance.empty:
            return []
        cov = covariance.values
        port_var = float(np.dot(weights.T, np.dot(cov, weights)))
        if port_var <= 0:
            return []
        sigma_w = np.dot(cov, weights)
        contributions_var = weights * sigma_w
        port_vol = float(np.sqrt(port_var))

        payload = []
        for idx, ticker in enumerate(tickers):
            pct = float(contributions_var[idx] / port_var)
            payload.append({
                'ticker': ticker,
                'contribution_pct': pct,
                'contribution_vol': float((contributions_var[idx] / port_var) * port_vol),
            })
        payload.sort(key=lambda x: x['contribution_pct'], reverse=True)
        return payload

    def analyze(self, portfolio: List[Dict], analysis_config: Optional[Dict] = None):
        config = analysis_config or {}
        benchmark = str(config.get('benchmark') or self.default_benchmark)
        stress_test = bool(config.get('stress_test', True))

        assets = {}
        daily_returns = {}
        for item in portfolio:
            ticker = item['ticker']
            prices = market_service.get_prices(ticker)
            ret = prices.pct_change().dropna()
            daily_returns[ticker] = ret
            fundamentals = market_service.get_fundamentals(ticker)
            assets[ticker] = {
                'volatility': float(ret.std() * (252 ** 0.5)),
                'mean_annual_return': float(ret.mean() * 252),
                'fundamentals': fundamentals,
            }

        weights = np.array([item['weight'] for item in portfolio], dtype=float)
        tickers = [item['ticker'] for item in portfolio]
        rets_matrix = pd.concat([daily_returns[t] for t in tickers], axis=1, join='inner')
        rets_matrix.columns = tickers

        port_daily = rets_matrix.dot(weights)
        vol = float(port_daily.std() * (252 ** 0.5))
        mean_ann = float(port_daily.mean() * 252)

        rf = 0.01
        sharpe = (mean_ann - rf) / vol if vol > 0 else 0.0
        var_95 = float(-np.percentile(port_daily, 5) * (252 ** 0.5))

        bench_ret = None
        try:
            bench_prices = market_service.get_prices(benchmark)
            bench_ret = bench_prices.pct_change().dropna()
            joined = pd.concat([port_daily, bench_ret], axis=1, join='inner').dropna()
            joined.columns = ['portfolio', 'bench']
            cov = joined['portfolio'].cov(joined['bench'])
            var_bench = joined['bench'].var()
            beta = float(cov / var_bench) if var_bench > 0 else None
        except Exception:
            beta = None

        covariance = rets_matrix.cov() * 252
        correlation = rets_matrix.corr().fillna(0.0)
        risk_contribution = self._risk_contribution(tickers, weights, covariance)

        cumulative_portfolio = (1 + port_daily).cumprod() - 1
        peak = (1 + cumulative_portfolio).cummax()
        drawdown_series = (1 + cumulative_portfolio) / peak - 1
        max_drawdown = float(drawdown_series.min()) if not drawdown_series.empty else None

        rolling_vol_30 = port_daily.rolling(30).std() * (252 ** 0.5)
        rolling_vol_90 = port_daily.rolling(90).std() * (252 ** 0.5)
        rolling_return_30 = (1 + port_daily).rolling(30).apply(np.prod, raw=True) - 1
        rolling_return_90 = (1 + port_daily).rolling(90).apply(np.prod, raw=True) - 1

        cumulative_benchmark = pd.Series(dtype=float)
        benchmark_payload = {'ticker': benchmark, 'cumulative_return': None, 'alpha': None}
        if bench_ret is not None and not bench_ret.empty:
            aligned = pd.concat([port_daily, bench_ret], axis=1, join='inner').dropna()
            aligned.columns = ['portfolio', 'benchmark']
            if not aligned.empty:
                cumulative_benchmark = (1 + aligned['benchmark']).cumprod() - 1
                bench_ann = float(aligned['benchmark'].mean() * 252)
                alpha = None
                if beta is not None:
                    alpha = float((aligned['portfolio'].mean() * 252 - rf) - beta * (bench_ann - rf))
                benchmark_payload = {
                    'ticker': benchmark,
                    'cumulative_return': float(cumulative_benchmark.iloc[-1]),
                    'alpha': alpha,
                }

        stress = None
        if stress_test:
            market_shock = -0.20
            beta_for_shock = beta if beta is not None else 1.0
            stress = {
                'name': 'market_shock_-20pct',
                'shock_assumption': market_shock,
                'estimated_portfolio_impact': float(beta_for_shock * market_shock),
            }

        total_market_cap = sum(
            assets.get(item['ticker'], {}).get('fundamentals', {}).get('market_cap') or 0.0
            for item in portfolio
        )
        covered_fundamentals_count = sum(
            1
            for item in portfolio
            if assets.get(item['ticker'], {}).get('fundamentals', {}).get('market_cap') is not None
        )

        portfolio_fundamentals = {
            'forward_pe_weighted': self._weighted_average(portfolio, assets, 'forward_pe'),
            'trailing_pe_weighted': self._weighted_average(portfolio, assets, 'trailing_pe'),
            'dividend_yield_weighted': self._weighted_average(portfolio, assets, 'dividend_yield'),
            'beta_fundamental_weighted': self._weighted_average(portfolio, assets, 'beta_fundamental'),
            'analyst_upside_weighted': self._weighted_analyst_upside(portfolio, assets),
            'total_market_cap': float(total_market_cap) if total_market_cap > 0 else None,
            'coverage': {
                'tickers_with_market_cap': covered_fundamentals_count,
                'total_tickers': len(portfolio),
            },
        }

        return {
            'assets': assets,
            'portfolio': {
                'volatility': vol,
                'sharpe': sharpe,
                'var_95': var_95,
                'beta': beta,
                'max_drawdown': max_drawdown,
                'cumulative_return': float(cumulative_portfolio.iloc[-1]) if not cumulative_portfolio.empty else None,
                'rolling_volatility_latest': {
                    '30d': float(rolling_vol_30.dropna().iloc[-1]) if not rolling_vol_30.dropna().empty else None,
                    '90d': float(rolling_vol_90.dropna().iloc[-1]) if not rolling_vol_90.dropna().empty else None,
                },
                'rolling_return_latest': {
                    '30d': float(rolling_return_30.dropna().iloc[-1]) if not rolling_return_30.dropna().empty else None,
                    '90d': float(rolling_return_90.dropna().iloc[-1]) if not rolling_return_90.dropna().empty else None,
                },
                'alpha': benchmark_payload.get('alpha'),
                'fundamentals': portfolio_fundamentals,
            },
            'performance': {
                'benchmark': benchmark_payload,
                'series': {
                    'portfolio_cumulative': _series_to_points(cumulative_portfolio, tail=504),
                    'benchmark_cumulative': _series_to_points(cumulative_benchmark, tail=504),
                    'rolling_return_30d': _series_to_points(rolling_return_30, tail=252),
                    'rolling_return_90d': _series_to_points(rolling_return_90, tail=252),
                },
            },
            'risk_insights': {
                'correlation_matrix': correlation.round(4).to_dict(),
                'covariance_matrix': covariance.round(8).to_dict(),
                'risk_contribution': risk_contribution,
                'series': {
                    'drawdown': _series_to_points(drawdown_series, tail=504),
                    'rolling_vol_30d': _series_to_points(rolling_vol_30, tail=252),
                    'rolling_vol_90d': _series_to_points(rolling_vol_90, tail=252),
                },
                'stress_test': stress,
            },
            'correlation_matrix': correlation.round(4).to_dict(),
            'covariance_matrix': covariance.round(8).to_dict(),
            'risk_contribution': risk_contribution,
        }


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

        custom_rules = config.get('compliance_rules') or {}
        for key, value in custom_rules.items():
            if value is not None and key in profile_rules:
                profile_rules[key] = value

        issues = []
        violations = []

        total_weight = sum(item['weight'] for item in portfolio)
        if abs(total_weight - 1.0) > profile_rules['weight_sum_tolerance']:
            message = (
                f"Portfolio weights sum to {total_weight * 100:.1f}% - must be within "
                f"{profile_rules['weight_sum_tolerance'] * 100:.0f}% of 100%"
            )
            issues.append(message)
            violations.append({'rule': 'weight_sum', 'severity': 'high', 'message': message})

        if len(portfolio) < profile_rules['min_assets']:
            message = f"Minimum assets requirement not met ({len(portfolio)} < {profile_rules['min_assets']})"
            issues.append(message)
            violations.append({'rule': 'min_assets', 'severity': 'medium', 'message': message})

        if len(portfolio) > profile_rules['max_assets']:
            message = f"Portfolio exceeds maximum holding count ({len(portfolio)} > {profile_rules['max_assets']})"
            issues.append(message)
            violations.append({'rule': 'max_assets', 'severity': 'medium', 'message': message})

        for item in portfolio:
            if item['weight'] > profile_rules['single_asset_max'] + 1e-9:
                message = (
                    f"{item['ticker']} weight {item['weight'] * 100:.1f}% exceeds "
                    f"single-asset max {profile_rules['single_asset_max'] * 100:.0f}%"
                )
                issues.append(message)
                violations.append({'rule': 'single_asset_max', 'severity': 'high', 'message': message})

        for item in portfolio:
            if 0 < item['weight'] < profile_rules['min_weight'] - 1e-9:
                message = (
                    f"{item['ticker']} weight {item['weight'] * 100:.1f}% is below "
                    f"minimum position size {profile_rules['min_weight'] * 100:.0f}%"
                )
                issues.append(message)
                violations.append({'rule': 'min_weight', 'severity': 'low', 'message': message})

        sector_map = {}
        for item in portfolio:
            sector = market_service.get_sector(item['ticker']) or 'Unknown'
            sector_map.setdefault(sector, 0.0)
            sector_map[sector] += item['weight']

        for sector, total in sector_map.items():
            if total > profile_rules['sector_max'] + 1e-9:
                message = (
                    f"Sector '{sector}' weight {total * 100:.1f}% exceeds "
                    f"sector max {profile_rules['sector_max'] * 100:.0f}%"
                )
                issues.append(message)
                violations.append({'rule': 'sector_max', 'severity': 'high', 'message': message})

        if len(sector_map) < profile_rules['min_sectors']:
            message = (
                f"Portfolio spans only {len(sector_map)} sector(s) - "
                f"minimum required is {profile_rules['min_sectors']}"
            )
            issues.append(message)
            violations.append({'rule': 'min_sectors', 'severity': 'medium', 'message': message})

        return {
            'ok': len(issues) == 0,
            'issues': issues,
            'violations': violations,
            'sectors': sector_map,
            'risk_profile': risk_profile,
            'applied_rules': profile_rules,
        }


class ReportingAgent:
    def _fmt_pct(self, value):
        return 'n/a' if value is None else f"{value * 100:.1f}%"

    def _fmt_num(self, value):
        return 'n/a' if value is None else f"{value:.2f}"

    def _build_fallback(self, portfolio: List[Dict], results: Dict):
        port = results.get('risk', {}).get('portfolio', {})
        compliance = results.get('compliance', {})
        issues = compliance.get('issues', [])
        sectors = compliance.get('sectors', {})
        top_holding = max(portfolio, key=lambda item: item['weight']) if portfolio else None
        top_sector = max(sectors.items(), key=lambda item: item[1]) if sectors else None

        summary = (
            f"Largest holding is {top_holding['ticker']} at {self._fmt_pct(top_holding['weight'])}; "
            f"portfolio volatility is {self._fmt_pct(port.get('volatility'))} and Sharpe is {self._fmt_num(port.get('sharpe'))}."
            if top_holding else
            'Portfolio composition was not available.'
        )

        risks = [
            f"Estimated 95% annualized VaR is {self._fmt_pct(port.get('var_95'))}.",
            f"Beta versus benchmark is {self._fmt_num(port.get('beta'))}.",
        ]
        opportunities = [
            f"Largest sector exposure is {top_sector[0]} at {self._fmt_pct(top_sector[1])}." if top_sector else 'Sector concentration data was not available.'
        ]
        recommendations = []
        if issues:
            recommendations.append('Rebalance concentration hotspots before policy sign-off.')
        else:
            recommendations.append('No compliance breaches detected under current rules.')
            recommendations.append('Monitor concentration drift and benchmark-relative drawdown weekly.')

        return {
            'summary': summary,
            'risks': risks,
            'opportunities': opportunities,
            'compliance_issues': issues,
            'recommendations': recommendations,
            'source': 'deterministic_fallback',
        }

    def _parse_structured_report(self, text: str) -> Optional[Dict]:
        if not text:
            return None
        candidate = text.strip()
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        start = candidate.find('{')
        end = candidate.rfind('}')
        if start >= 0 and end > start:
            try:
                obj = json.loads(candidate[start:end + 1])
                if isinstance(obj, dict):
                    return obj
            except Exception:
                return None
        return None

    def generate(self, portfolio: List[Dict], results: Dict, analysis_config: Optional[Dict] = None):
        port = results.get('risk', {}).get('portfolio', {})
        fundamentals = port.get('fundamentals', {})
        compliance = results.get('compliance', {})
        sectors = compliance.get('sectors', {})
        issues = compliance.get('issues', [])
        violations = compliance.get('violations', [])
        rebalancing = results.get('rebalancing', {})
        holdings = sorted(portfolio, key=lambda item: item['weight'], reverse=True)
        top_sectors = sorted(sectors.items(), key=lambda item: item[1], reverse=True)

        prompt = '\n'.join([
            'You are the reporting agent for an AI portfolio analysis dashboard.',
            'Return a strict JSON object only, with keys: summary, risks, opportunities, compliance_issues, recommendations.',
            'Requirements:',
            '- summary: a concise actionable paragraph for PM audience.',
            '- risks: array of 3 to 5 concrete portfolio risks grounded in provided metrics.',
            '- opportunities: array of 2 to 4 opportunities based on risk/valuation mix.',
            '- compliance_issues: array of concise issue strings (empty array if none).',
            '- recommendations: array of 3 to 6 specific next actions.',
            'Use only the data below. Do not invent numbers or performance claims.',
            '',
            'Portfolio Allocation:',
            *[f"- {item['ticker']}: {item['weight'] * 100:.1f}%" for item in holdings],
            '',
            'Risk Metrics:',
            f"- Volatility: {self._fmt_pct(port.get('volatility'))}",
            f"- Sharpe: {self._fmt_num(port.get('sharpe'))}",
            f"- VaR 95: {self._fmt_pct(port.get('var_95'))}",
            f"- Beta vs benchmark: {self._fmt_num(port.get('beta'))}",
            f"- Max Drawdown: {self._fmt_pct(port.get('max_drawdown'))}",
            f"- Alpha: {self._fmt_num(port.get('alpha'))}",
            f"- Forward PE (weighted): {self._fmt_num(fundamentals.get('forward_pe_weighted'))}",
            f"- Dividend Yield (weighted): {self._fmt_pct(fundamentals.get('dividend_yield_weighted'))}",
            f"- Analyst Upside (weighted): {self._fmt_pct(fundamentals.get('analyst_upside_weighted'))}",
            '',
            'Compliance Status:',
            f"- Passed: {'yes' if compliance.get('ok') else 'no'}",
            *([f"- Issue: {issue}" for issue in issues] if issues else ['- Issue: none']),
            *([f"- Violation: {v.get('rule')} [{v.get('severity')}]: {v.get('message')}" for v in violations] if violations else ['- Violation: none']),
            '',
            'Sector Exposure:',
            *([f"- {sector}: {weight * 100:.1f}%" for sector, weight in top_sectors] if top_sectors else ['- No sector data available']),
            '',
            'Rebalancing Suggestions:',
            *([f"- {k}: {(v * 100):.1f}%" for k, v in (rebalancing.get('suggested_weights') or {}).items()] if rebalancing else ['- No rebalancing data available']),
        ])

        insight = generate_insights(prompt)
        if not insight or insight.startswith('[Gemini API error]') or len(insight.strip()) < 120:
            return self._build_fallback(portfolio, results)

        parsed = self._parse_structured_report(insight)
        if not parsed:
            return self._build_fallback(portfolio, results)

        return {
            'summary': parsed.get('summary', ''),
            'risks': parsed.get('risks', []),
            'opportunities': parsed.get('opportunities', []),
            'compliance_issues': parsed.get('compliance_issues', issues),
            'recommendations': parsed.get('recommendations', []),
            'source': 'gemini',
        }


class Aggregator:
    def aggregate(self, portfolio: List[Dict], results: Dict):
        risk = results.get('risk') or {}
        risk_insights = risk.get('risk_insights') or {}
        performance = risk.get('performance') or {}
        compliance = results.get('compliance') or {}
        report = results.get('report') or {}
        rebalancing = results.get('rebalancing') or {}

        return {
            'portfolio': portfolio,
            'risk': risk,
            'performance': performance,
            'risk_insights': risk_insights,
            'compliance': compliance,
            'rebalancing': rebalancing,
            'report': report,
            'insights': report,
            'meta': {
                'schema_version': '2.0',
                'generated_at_unix': int(time.time()),
            },
        }
