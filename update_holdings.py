"""
Run this script locally (not on the cloud) to refresh holdings_data.json.
After running, commit and push the updated file to GitHub.

    python update_holdings.py
"""
import json
import time
import pandas as pd
import os

TICKERS = [
    "XLK","XLF","XLV","XLE","XLI","XLC","XLY","XLP","XLU","XLRE","XLB",
    "VGT","VNQ","VHT",
    "SOXX","SMH","DRAM","IGV","CIBR","SKYY","BOTZ","FDN","AIQ","DTCR",
    "XBI","IBB","IHI","IHF","PJP","ARKG",
    "KRE","KBE","IAI","FINX","BIZD",
    "XOP","OIH","ICLN","AMLP","TAN","URA",
    "ITA","IYT","JETS","ITB","PAVE",
    "GDX","MOO","SLX","LIT","COPX","REMX",
    "XRT","PEJ","AWAY","IBUY","BETZ",
    "PHO",
]

OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "holdings_data.json")


def fetch_holdings_live(ticker):
    """Fetch live from Yahoo Finance using yfinance's authenticated session."""
    from yfinance.data import YfData
    yfdata = YfData()
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
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


holdings_db = {}
failed = []

for i, ticker in enumerate(TICKERS):
    try:
        result = fetch_holdings_live(ticker)
        if result is not None and not result.empty:
            holdings_db[ticker] = {
                "symbols": list(result.index),
                "names":   list(result["Name"]),
                "weights": list(result["Holding Percent"]),
            }
            top = result.index[0]
            pct = round(result["Holding Percent"].iloc[0] * 100, 1)
            print(f"OK   {ticker:6s} ({i+1}/{len(TICKERS)}) — {top} {pct}%")
        else:
            failed.append(ticker)
            print(f"FAIL {ticker:6s} — no data returned")
    except Exception as e:
        failed.append(ticker)
        print(f"FAIL {ticker:6s} — {e}")
    time.sleep(0.5)

with open(OUTPUT_FILE, "w") as f:
    json.dump(holdings_db, f, indent=2)

print(f"\nSaved {len(holdings_db)} ETFs to holdings_data.json")
if failed:
    print(f"Failed: {failed}")
