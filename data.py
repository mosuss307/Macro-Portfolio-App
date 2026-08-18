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
    """
    Fetch top holdings for an ETF via Yahoo Finance quoteSummary API.
    Uses yfinance's own get_raw_json() which handles Chrome TLS impersonation,
    crumb auth, retries, and cookie strategy — identical to how yfinance fetches
    price data, so it works on Streamlit Cloud just as price data does.
    Returns a DataFrame with columns [Name, Holding Percent] where Holding Percent
    is a raw float (e.g. 0.1859 = 18.59%), or None if unavailable.
    """
    try:
        from yfinance.data import YfData

        yfdata = YfData()
        url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
        # get_raw_json handles crumb injection, retries, and cookie strategy automatically
        data = yfdata.get_raw_json(url, params={"modules": "topHoldings"})

        result = data.get("quoteSummary", {}).get("result") or []
        if not result:
            return None

        raw_holdings = result[0].get("topHoldings", {}).get("holdings", [])
        if not raw_holdings:
            return None

        rows = []
        for h in raw_holdings:
            name = h.get("holdingName", "")
            pct  = h.get("holdingPercent", {})
            pct_raw = pct.get("raw", 0) if isinstance(pct, dict) else float(pct)
            rows.append({"Name": name, "Holding Percent": pct_raw})

        df = pd.DataFrame(rows, index=[h.get("symbol", "") for h in raw_holdings])
        df.index.name = "Symbol"
        return df if not df.empty else None

    except Exception as e:
        # Store error so the UI can display it for debugging
        get_etf_holdings.last_error = str(e)
        return None


get_etf_holdings.last_error = None
