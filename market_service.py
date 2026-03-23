import yfinance as yf
import pandas as pd

def get_prices(ticker: str, period: str = "1y") -> pd.Series:
    t = yf.Ticker(ticker)
    hist = t.history(period=period)
    if hist is None or hist.empty:
        raise ValueError(f"No price history for {ticker}")
    return hist['Close']

def get_sector(ticker: str) -> str:
    t = yf.Ticker(ticker)
    info = t.info if hasattr(t, 'info') else {}
    sector = info.get('sector') if isinstance(info, dict) else None
    return sector or 'Unknown'
