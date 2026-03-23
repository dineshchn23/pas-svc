import numpy as np
import pandas as pd
from typing import List, Dict
import traceback
from concurrent.futures import ThreadPoolExecutor
import time

import market_service
from gemini_client import generate_insights

class SupervisorAgent:
    def __init__(self, risk_agent, compliance_agent, reporting_agent, aggregator):
        self.risk_agent = risk_agent
        self.compliance_agent = compliance_agent
        self.reporting_agent = reporting_agent
        self.aggregator = aggregator

    def run(self, portfolio: List[Dict]):
        """Run all agents sequentially (no streaming). Delegates to run_with_callback."""
        return self.run_with_callback(portfolio, lambda event, data: None)

    def run_with_callback(self, portfolio: List[Dict], emit):
        """Run all agents and call emit(event, data) at each stage.

        Risk + Compliance run in parallel; Reporting runs after Risk completes;
        Aggregator runs last. emit is called from the executor thread — callers
        must use thread-safe dispatch (e.g. asyncio loop.call_soon_threadsafe).
        """
        tasks = ['risk', 'compliance', 'reporting']
        results = {}
        timings = {}
        total_start = time.perf_counter()

        emit('started', {'tasks': tasks})
        emit('agent_running', {'agent': 'risk'})
        emit('agent_running', {'agent': 'compliance'})

        with ThreadPoolExecutor(max_workers=2) as executor:
            risk_start = time.perf_counter()
            risk_future = executor.submit(self.risk_agent.analyze, portfolio)
            compliance_start = time.perf_counter()
            compliance_future = executor.submit(self.compliance_agent.check, portfolio)

            # Risk must finish before reporting (reporting reads risk output)
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

            emit('agent_running', {'agent': 'reporting'})
            reporting_start = time.perf_counter()
            try:
                report = self.reporting_agent.generate(portfolio, results)
                results['report'] = report
                t = round(time.perf_counter() - reporting_start, 4)
                timings['reporting_seconds'] = t
                emit('agent_done', {'agent': 'reporting', 'result': report, 'duration': t})
            except Exception as e:
                timings['reporting_seconds'] = round(time.perf_counter() - reporting_start, 4)
                results['report_error'] = str(e) + '\n' + traceback.format_exc()
                emit('agent_error', {'agent': 'reporting', 'error': str(e)})

            # Collect compliance (likely already done, ran in parallel with risk)
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

        aggregation = self.aggregator.aggregate(portfolio, results)
        results['aggregation'] = aggregation
        timings['total_seconds'] = round(time.perf_counter() - total_start, 4)
        results['timings'] = timings

        emit('aggregated', {'aggregation': aggregation, 'timings': timings})
        return tasks, results

class RiskAgent:
    def __init__(self, benchmark='SPY'):
        self.benchmark = benchmark

    def analyze(self, portfolio: List[Dict]):
        # downloads prices, computes volatility, sharpe, var, beta
        assets = {}
        daily_returns = {}
        for item in portfolio:
            ticker = item['ticker']
            prices = market_service.get_prices(ticker)
            ret = prices.pct_change().dropna()
            daily_returns[ticker] = ret
            assets[ticker] = {
                'volatility': float(ret.std() * (252 ** 0.5)),
                'mean_annual_return': float(ret.mean() * 252)
            }

        # portfolio returns
        weights = np.array([item['weight'] for item in portfolio])
        tickers = [item['ticker'] for item in portfolio]
        rets_matrix = pd.concat([daily_returns[t] for t in tickers], axis=1, join='inner')
        rets_matrix.columns = tickers
        port_daily = rets_matrix.dot(weights)
        vol = float(port_daily.std() * (252 ** 0.5))
        mean_ann = float(port_daily.mean() * 252)
        # Sharpe (assume rf = 1% annual)
        rf = 0.01
        sharpe = (mean_ann - rf) / vol if vol > 0 else 0.0
        # VaR 95% historical
        var_95 = float(-np.percentile(port_daily, 5) * (252 ** 0.5))
        # Beta vs benchmark
        try:
            bench_prices = market_service.get_prices(self.benchmark)
            bench_ret = bench_prices.pct_change().dropna()
            joined = pd.concat([port_daily, bench_ret], axis=1, join='inner')
            joined.columns = ['portfolio', 'bench']
            cov = joined['portfolio'].cov(joined['bench'])
            var_bench = joined['bench'].var()
            beta = float(cov / var_bench) if var_bench > 0 else None
        except Exception:
            beta = None

        result = {
            'assets': assets,
            'portfolio': {
                'volatility': vol,
                'sharpe': sharpe,
                'var_95': var_95,
                'beta': beta
            }
        }
        return result

class ComplianceAgent:
    def __init__(self, single_asset_max=0.4, sector_max=0.6, min_assets=4):
        self.single_asset_max = single_asset_max
        self.sector_max = sector_max
        self.min_assets = min_assets

    def check(self, portfolio: List[Dict]):
        issues = []
        if len(portfolio) < self.min_assets:
            issues.append(f"Minimum assets requirement not met ({len(portfolio)} < {self.min_assets})")

        # single asset
        for item in portfolio:
            if item['weight'] > self.single_asset_max + 1e-9:
                issues.append(f"Asset {item['ticker']} weight {item['weight']} exceeds max {self.single_asset_max}")

        # sector aggregation
        sector_map = {}
        for item in portfolio:
            sector = market_service.get_sector(item['ticker']) or 'Unknown'
            sector_map.setdefault(sector, 0.0)
            sector_map[sector] += item['weight']

        for sector, total in sector_map.items():
            if total > self.sector_max + 1e-9:
                issues.append(f"Sector {sector} weight {total} exceeds max {self.sector_max}")

        return {
            'ok': len(issues) == 0,
            'issues': issues,
            'sectors': sector_map
        }

class ReportingAgent:
    def __init__(self):
        pass

    def generate(self, portfolio: List[Dict], results: Dict):
        summary = []
        summary.append('Portfolio allocation:')
        for p in portfolio:
            summary.append(f"- {p['ticker']}: {p['weight']*100:.1f}%")
        # include high-level risk
        port = results.get('risk', {}).get('portfolio', {})
        summary.append('\nRisk metrics:')
        summary.append(f"- Volatility: {port.get('volatility')}")
        summary.append(f"- Sharpe: {port.get('sharpe')}")
        summary.append(f"- VaR 95: {port.get('var_95')}")

        prompt = '\n'.join(summary)
        insight = generate_insights(prompt)
        return insight

class Aggregator:
    def aggregate(self, portfolio: List[Dict], results: Dict):
        return {
            'portfolio': portfolio,
            'risk': results.get('risk'),
            'compliance': results.get('compliance'),
            'insights': results.get('report')
        }
