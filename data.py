import yfinance as yf
import pandas as pd

# These are the 11 S&P 500 sector ETFs — one ETF represents each sector
SECTOR_ETFS = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Communication Services": "XLC",
}


def fetch_sector_prices(period="6mo"):
    """Download historical price data for all sector ETFs."""
    tickers = list(SECTOR_ETFS.values())
    raw = yf.download(tickers, period=period, auto_adjust=True, progress=False)

    # Pull out just the closing prices
    prices = raw["Close"]
    return prices


def fetch_benchmark_prices(period="6mo"):
    """Download S&P 500 (SPY) as the benchmark to compare sectors against."""
    raw = yf.download("SPY", period=period, auto_adjust=True, progress=False)
    return raw["Close"]


def get_etf_holdings(ticker: str):
    """Fetch top holdings for an ETF. Returns a DataFrame or None if unavailable."""
    try:
        t = yf.Ticker(ticker)
        holdings = t.funds_data.top_holdings
        if holdings is not None and not holdings.empty:
            return holdings
    except Exception:
        return None
    return None
