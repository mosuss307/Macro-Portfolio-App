import pandas as pd


def calculate_momentum(prices, lookback_days=63):
    """
    Calculate momentum for each sector: how much has it returned
    over the last `lookback_days` trading days (default ~3 months)?
    A positive number means the sector went up.
    """
    # Compare the most recent price to the price N days ago
    recent_return = (prices.iloc[-1] - prices.iloc[-lookback_days]) / prices.iloc[-lookback_days]
    return recent_return * 100  # convert to percentage


def rank_sectors(momentum_series, sector_etfs):
    """
    Take the momentum numbers and build a ranked table from strongest to weakest.
    Returns a DataFrame with sector names, ETF tickers, and momentum %.
    """
    rows = []
    for sector_name, etf_ticker in sector_etfs.items():
        if etf_ticker in momentum_series.index:
            rows.append({
                "Sector": sector_name,
                "ETF": etf_ticker,
                "3-Month Return (%)": round(momentum_series[etf_ticker], 2),
            })

    result = pd.DataFrame(rows)
    result = result.sort_values("3-Month Return (%)", ascending=False).reset_index(drop=True)
    return result
