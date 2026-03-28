import yfinance as yf
import pandas as pd
import time
from threading import Lock


_CACHE_TTL_SECONDS = 300
_cache_lock = Lock()
_cache = {}


def _cache_get(key):
    now = time.time()
    with _cache_lock:
        item = _cache.get(key)
        if not item:
            return None
        if now - item['ts'] > _CACHE_TTL_SECONDS:
            _cache.pop(key, None)
            return None
        return item['value']


def _cache_set(key, value):
    with _cache_lock:
        _cache[key] = {'ts': time.time(), 'value': value}


def _to_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_info_dict(ticker: str) -> dict:
    cache_key = ('info', ticker.upper())
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        t = yf.Ticker(ticker)
        info = t.info if hasattr(t, 'info') else {}
    except Exception as exc:
        raise ValueError(f"Failed to fetch metadata for {ticker}: {exc}")

    payload = info if isinstance(info, dict) else {}
    _cache_set(cache_key, payload)
    return payload

def get_prices(ticker: str, period: str = "1y") -> pd.Series:
    cache_key = ('prices', ticker.upper(), period)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached.copy()

    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=period)
    except Exception as exc:
        raise ValueError(f"Failed to fetch price history for {ticker}: {exc}")

    if hist is None or hist.empty:
        raise ValueError(f"No price history for {ticker}")

    prices = hist['Close'].dropna()
    if prices.empty:
        raise ValueError(f"No close-price data for {ticker}")

    _cache_set(cache_key, prices)
    return prices.copy()

def get_sector(ticker: str) -> str:
    info = _get_info_dict(ticker)
    sector = info.get('sector') if isinstance(info, dict) else None
    return sector or 'Unknown'


def get_fundamentals(ticker: str) -> dict:
    cache_key = ('fundamentals', ticker.upper())
    cached = _cache_get(cache_key)
    if cached is not None:
        return dict(cached)

    info = _get_info_dict(ticker)

    payload = {
        'sector': info.get('sector') or 'Unknown',
        'industry': info.get('industry') or 'Unknown',
        'market_cap': _to_float(info.get('marketCap')),
        'forward_pe': _to_float(info.get('forwardPE')),
        'trailing_pe': _to_float(info.get('trailingPE')),
        'dividend_yield': _to_float(info.get('dividendYield')),
        'beta_fundamental': _to_float(info.get('beta')),
        'current_price': _to_float(info.get('currentPrice')),
        'target_mean_price': _to_float(info.get('targetMeanPrice')),
        'recommendation_key': info.get('recommendationKey'),
        'earnings_quarterly_growth': _to_float(info.get('earningsQuarterlyGrowth')),
        'return_on_equity': _to_float(info.get('returnOnEquity')),
        'debt_to_equity': _to_float(info.get('debtToEquity')),
        'fifty_two_week_high': _to_float(info.get('fiftyTwoWeekHigh')),
        'fifty_two_week_low': _to_float(info.get('fiftyTwoWeekLow')),
        'average_volume': _to_float(info.get('averageVolume')),
    }
    _cache_set(cache_key, payload)
    return payload
