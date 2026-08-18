import yfinance as yf
import pandas as pd
import json
import os

# Pre-fetched holdings stored locally so the app never has to call Yahoo Finance
# for this data at runtime. Update by running: python update_holdings.py
_HOLDINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "holdings_data.json")
_holdings_cache = None

def _load_holdings_db():
    global _holdings_cache
    if _holdings_cache is None:
        if os.path.exists(_HOLDINGS_FILE):
            with open(_HOLDINGS_FILE) as f:
                _holdings_cache = json.load(f)
        else:
            _holdings_cache = {}
    return _holdings_cache

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
    """
    Load top holdings for an ETF from the local holdings_data.json file.
    Data was pre-fetched from Yahoo Finance and committed to the repo.
    Run update_holdings.py to refresh the data.
    Returns a DataFrame with columns [Name, Holding Percent], or None if not found.
    """
    get_etf_holdings.last_error = None
    db = _load_holdings_db()
    entry = db.get(ticker)
    if not entry:
        return None
    try:
        df = pd.DataFrame({
            "Name":            entry["names"],
            "Holding Percent": entry["weights"],
        }, index=entry["symbols"])
        df.index.name = "Symbol"
        return df if not df.empty else None
    except Exception as e:
        get_etf_holdings.last_error = str(e)
        return None


get_etf_holdings.last_error = None
