import yfinance as yf
import pandas as pd
import time
import re
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


def resolve_symbol(query_or_symbol: str) -> str:
    """Resolve a user query or stale symbol to an active Yahoo symbol."""
    raw = (query_or_symbol or '').strip()
    if not raw:
        raise ValueError('Empty symbol/query')

    cache_key = ('resolve', raw.lower())
    cached = _cache_get(cache_key)
    if cached:
        return str(cached)

    # If input already looks like a symbol, trust it first.
    if re.fullmatch(r'[A-Za-z]{1,10}(?:\.[A-Za-z]{1,4})?', raw):
        symbol = raw.upper()
        try:
            get_prices(symbol, period='3mo')
            _cache_set(cache_key, symbol)
            return symbol
        except Exception:
            pass

    # Use Yahoo search to discover active symbols.
    try:
        search = yf.Search(raw, max_results=10)
        quotes = getattr(search, 'quotes', None) or []
    except Exception:
        quotes = []

    preferred = []
    fallback = []
    for item in quotes:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get('symbol') or '').strip().upper()
        quote_type = str(item.get('quoteType') or '').upper()
        exchange = str(item.get('exchange') or '').upper()
        if not symbol:
            continue
        if quote_type and quote_type not in {'EQUITY', 'ETF'}:
            continue
        if exchange in {'NMS', 'NYQ', 'NSI', 'BSE', 'NSE', 'NASDAQ', 'NYSE'}:
            preferred.append(symbol)
        else:
            fallback.append(symbol)

    candidates = preferred + fallback
    for symbol in candidates:
        try:
            get_prices(symbol, period='3mo')
            _cache_set(cache_key, symbol)
            return symbol
        except Exception:
            continue

    # Last resort: return normalized input so caller can still attempt fetches.
    if re.fullmatch(r'[A-Za-z]{1,10}(?:\.[A-Za-z]{1,4})?', raw):
        symbol = raw.upper()
        _cache_set(cache_key, symbol)
        return symbol

    raise ValueError(f'Unable to resolve symbol for query: {query_or_symbol}')


def search_symbols(query: str, limit: int = 8) -> list[dict]:
    """Search tradable symbols for a company/group query."""
    text = (query or '').strip()
    if not text:
        return []

    cache_key = ('search_symbols', text.lower(), int(limit))
    cached = _cache_get(cache_key)
    if cached is not None:
        return [dict(item) for item in cached]

    try:
        search = yf.Search(text, max_results=max(1, int(limit) * 2))
        quotes = getattr(search, 'quotes', None) or []
    except Exception:
        quotes = []

    results = []
    for item in quotes:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get('symbol') or '').strip().upper()
        quote_type = str(item.get('quoteType') or '').upper()
        if not symbol:
            continue
        if quote_type and quote_type not in {'EQUITY', 'ETF'}:
            continue
        results.append({
            'symbol': symbol,
            'name': item.get('shortname') or item.get('longname'),
            'exchange': item.get('exchange'),
            'quote_type': quote_type or None,
        })
        if len(results) >= int(limit):
            break

    _cache_set(cache_key, results)
    return [dict(item) for item in results]


def get_recent_news(ticker: str, limit: int = 5) -> list[dict]:
    """Fetch lightweight recent news metadata for a ticker."""
    cache_key = ('news', ticker.upper(), int(limit))
    cached = _cache_get(cache_key)
    if cached is not None:
        return [dict(item) for item in cached]

    try:
        t = yf.Ticker(ticker)
        raw_news = getattr(t, 'news', None) or []
    except Exception:
        raw_news = []

    cleaned = []
    for item in raw_news[: max(0, int(limit))]:
        if not isinstance(item, dict):
            continue
        cleaned.append({
            'title': item.get('title'),
            'publisher': item.get('publisher'),
            'link': item.get('link'),
            'provider_publish_time': item.get('providerPublishTime'),
            'type': item.get('type'),
        })

    _cache_set(cache_key, cleaned)
    return [dict(item) for item in cleaned]
