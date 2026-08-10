"""
Sub-Sector Rotation Engine — entry/exit classification for the sector-rotation
book. Unit of decision is the ~40 sub-sector universe below (Sector -> Sub-sector
-> tickers). Every signal is relative-strength / price based — no OBV or volume,
since ETF volume reflects the wrapper, not the underlying holdings, and the
rotation decision should be driven by the same signal family whether a
sub-sector is ETF-wrapped or a curated stock basket.

Classification tiers per sub-sector:
  CONFIRMED LONG / CONFIRMED SHORT       — RS, MA, and return direction all agree
  STARTER LONG (leadership)              — RS trending up before price confirms,
                                            and beating its own parent sector
  STARTER LONG (broad-rotation)          — same early signal, but riding the
                                            parent sector rather than leading it
  EARLY WEAKNESS SHORT (lagging sector)  — mirror of starter long, RS breaking
                                            down before price confirms
  EARLY WEAKNESS SHORT (broad decline)   — same, but sector-wide, not isolated
  NEUTRAL / NO SETUP                     — nothing actionable either direction

Also reports universe breadth (% of sub-sectors RS-positive vs SPY) as regime
context, and the "resilient" / "vulnerable" flag for each sub-sector, cross-
sectionally ranked on volatility-normalized RS drawdown so the flag adapts to
whatever "normal" looks like in the current market rather than a fixed cutoff.
"""

import pandas as pd
import numpy as np

# ─────────────────────────────────────────────────────────────
# UNIVERSE: Sector -> Sub-sector -> tickers (ETF or individual stocks)
# ─────────────────────────────────────────────────────────────
UNIVERSE = {
    "Technology": {
        "Semiconductors - Broad":       ["SMH", "SOXX"],
        "Semiconductors - DRAM/Memory": ["MU", "WDC"],
        "Semiconductors - Fabless":     ["NVDA", "AMD", "QCOM", "AVGO"],
        "Semiconductors - Equipment":   ["AMAT", "LRCX", "KLAC"],
        "Enterprise Software":          ["IGV", "NOW", "MDB", "CRM", "WDAY"],
        "Cybersecurity":                ["CIBR", "CRWD", "PANW", "ZS"],
        "Cloud / SaaS":                 ["WCLD", "SNOW", "DDOG", "NET"],
        "Internet / Mega-Cap Tech":     ["QQQ", "META", "GOOGL", "AMZN"],
    },
    "Healthcare": {
        "Biotech":              ["IBB", "XBI", "MRNA", "REGN", "VRTX"],
        "Large-Cap Pharma":     ["IHE", "LLY", "JNJ", "PFE", "ABBV"],
        "Medical Devices":      ["IHI", "MDT", "ISRG", "SYK"],
        "Healthcare Services":  ["IHF", "UNH", "CVS"],
    },
    "Financials": {
        "Large Banks":     ["XLF", "JPM", "BAC", "GS", "MS"],
        "Regional Banks":  ["KRE", "KBE"],
        "Insurance":       ["KIE", "MET", "PRU"],
        "Fintech":         ["IPAY", "SQ", "PYPL", "V", "MA"],
    },
    "Energy": {
        "Oil & Gas E&P":          ["XOP", "CVX", "XOM", "COP"],
        "Oil Services":           ["OIH", "SLB", "HAL"],
        "Midstream / Pipelines":  ["AMLP", "ET", "EPD"],
        "Clean Energy":           ["ICLN", "ENPH", "FSLR"],
    },
    "Consumer Discretionary": {
        "Retail":            ["XRT", "AMZN", "TGT", "WMT"],
        "Homebuilders":      ["XHB", "ITB", "LEN", "DHI"],
        "Autos / EV":        ["GM", "F", "TSLA", "TM"],
        "Travel & Leisure":  ["JETS", "MAR", "HLT", "RCL"],
    },
    "Industrials": {
        "Defense & Aerospace":  ["ITA", "LMT", "RTX", "NOC"],
        "Transportation":      ["IYT", "UPS", "FDX", "DAL"],
        "Infrastructure":      ["PAVE", "CAT", "DE", "VMC"],
    },
    "Materials": {
        "Metals & Mining":  ["XME", "FCX", "NEM", "AA"],
        "Gold Miners":      ["GDX", "GDXJ", "NEM", "AEM"],
        "Steel":            ["SLX", "NUE", "STLD"],
        "Chemicals":        ["LIN", "APD", "DD"],
    },
    "Communication Services": {
        "Internet / Social Media":  ["META", "GOOGL", "SNAP"],
        "Telecom":                  ["IYZ", "T", "VZ"],
        "Media & Entertainment":    ["DIS", "NFLX", "WBD"],
    },
    "Consumer Staples": {
        "Food & Beverage":            ["PBJ", "KO", "PEP", "MDLZ"],
        "Household & Personal Care":  ["PG", "CL", "KMB"],
        "Wholesale / Discount":       ["COST", "WMT", "BJ"],
    },
    "Real Estate": {
        "Data Center REITs":   ["EQIX", "DLR", "AMT"],
        "Industrial REITs":    ["PLD", "STAG"],
        "Residential REITs":   ["REZ", "AVB", "EQR"],
        "Retail REITs":        ["SPG", "O"],
    },
    "Utilities": {
        "Electric Utilities":  ["IDU", "NEE", "SO", "DUK"],
        "Clean Power":         ["ICLN", "NEE", "ENPH"],
    },
}

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
RS_HIGH_LOW_WINDOW    = 126   # lookback for RS new-high / new-low
PRICE_HIGH_LOW_WINDOW = 126   # lookback for "has price already broken out"
NEAR_HIGH_PCT         = 0.98  # within 2% of rolling high/low counts as "at" it
DD_WINDOW             = 60    # trailing days for RS drawdown/resilience check
VOL_LOOKBACK          = 90    # trailing days used to measure each ticker's own normal RS volatility
RESILIENT_QUANTILE    = 0.75  # top quartile of vol-normalized drawdown (shallowest) = resilient
VULNERABLE_QUANTILE   = 0.25  # bottom quartile of vol-normalized drawdown (deepest) = vulnerable
CONFIRMED_SCORE       = 6     # out of 7, gate for confirmed long/short
EARLY_FRACTION        = 0.30  # min fraction of a group's tickers showing the early signal
MIN_HISTORY_DAYS      = 70    # minimum aligned trading days required to score a ticker


def sector_of_subsector_map():
    return {sub: sector for sector, subs in UNIVERSE.items() for sub in subs}


def subsector_tickers_map():
    return {sub: tickers for subs in UNIVERSE.values() for sub, tickers in subs.items()}


def all_universe_tickers():
    """Every unique ticker across the universe, sorted. Caller should add 'SPY' before downloading."""
    tickers = set()
    for subs in UNIVERSE.values():
        for t in subs.values():
            tickers.update(t)
    return sorted(tickers)


def _ema(s, span):
    return s.ewm(span=span, adjust=False).mean()


def compute_ticker_signals(ticker, close_all, spy):
    """RS/price-only signals for one ticker. No OBV or volume anywhere."""
    if ticker not in close_all.columns:
        return None
    c = close_all[ticker].dropna()
    aligned = pd.DataFrame({"c": c}).join(spy.rename("spy"), how="inner").dropna()
    if len(aligned) < MIN_HISTORY_DAYS:
        return None
    c = aligned["c"]
    s = aligned["spy"]
    rs = c / s

    e21  = _ema(rs, 21)
    e63  = _ema(rs, 63)
    e126 = _ema(rs, 126) if len(rs) >= 126 else None

    rs_trend_mid_up  = bool(e21.iloc[-1] > e63.iloc[-1])
    rs_trend_long_up = bool(e63.iloc[-1] > e126.iloc[-1]) if e126 is not None else rs_trend_mid_up
    rs_mom = float(e21.iloc[-1] / e63.iloc[-1] - 1) * 100  # smoothed RS momentum, used for ranking/leadership-in-sector

    rwin    = min(RS_HIGH_LOW_WINDOW, len(rs))
    rs_high = rs.rolling(rwin).max().iloc[-1]
    rs_low  = rs.rolling(rwin).min().iloc[-1]
    rs_new_high = bool(rs.iloc[-1] >= NEAR_HIGH_PCT * rs_high)
    rs_new_low  = bool(rs.iloc[-1] <= (2 - NEAR_HIGH_PCT) * rs_low)

    pwin   = min(PRICE_HIGH_LOW_WINDOW, len(c))
    p_high = c.rolling(pwin).max().iloc[-1]
    p_low  = c.rolling(pwin).min().iloc[-1]
    price_at_high = bool(c.iloc[-1] >= NEAR_HIGH_PCT * p_high)
    price_at_low  = bool(c.iloc[-1] <= (2 - NEAR_HIGH_PCT) * p_low)

    # Leadership showing up in relative terms before the absolute breakout (or breakdown)
    early_leadership = bool(rs_new_high and not price_at_high)
    early_weakness    = bool(rs_new_low  and not price_at_low)

    ma50  = c.rolling(50).mean().iloc[-1]
    ma200 = c.rolling(200).mean().iloc[-1] if len(c) >= 200 else None
    above_50  = bool(c.iloc[-1] > ma50)
    above_200 = bool(c.iloc[-1] > ma200) if ma200 is not None else True  # insufficient history -> don't penalize

    ret1m = float((c.iloc[-1] / c.iloc[-21]  - 1) * 100) if len(c) >= 21  else 0.0
    ret3m = float((c.iloc[-1] / c.iloc[-63]  - 1) * 100) if len(c) >= 63  else 0.0
    ret6m = float((c.iloc[-1] / c.iloc[-126] - 1) * 100) if len(c) >= 126 else 0.0

    # Relative drawdown, normalized by this ticker's OWN recent RS volatility (a
    # z-score of the pullback) so a volatile sub-sector isn't unfairly flagged
    # "vulnerable" next to a naturally calm one, or vice versa.
    ddw = rs.iloc[-DD_WINDOW:] if len(rs) >= DD_WINDOW else rs
    rs_dd_60 = float((ddw / ddw.cummax() - 1).min() * 100)
    rs_daily_ret = rs.pct_change().dropna()
    vwin = rs_daily_ret.iloc[-VOL_LOOKBACK:] if len(rs_daily_ret) >= VOL_LOOKBACK else rs_daily_ret
    daily_vol = float(vwin.std()) if len(vwin) >= 20 else None
    expected_wiggle_pct = daily_vol * np.sqrt(DD_WINDOW) * 100 if daily_vol else None
    rs_dd_60_norm = (rs_dd_60 / expected_wiggle_pct) if expected_wiggle_pct and expected_wiggle_pct > 0 else 0.0

    return dict(
        ticker=ticker, price=round(float(c.iloc[-1]), 2),
        rs_trend_mid_up=rs_trend_mid_up, rs_trend_long_up=rs_trend_long_up, rs_mom=rs_mom,
        rs_new_high=rs_new_high, rs_new_low=rs_new_low,
        early_leadership=early_leadership, early_weakness=early_weakness,
        above_50=above_50, above_200=above_200,
        ret1m=round(ret1m, 1), ret3m=round(ret3m, 1), ret6m=round(ret6m, 1),
        rs_dd_60=round(rs_dd_60, 1), rs_dd_60_norm=round(rs_dd_60_norm, 2),
    )


def _pct(vals):
    return round(100 * sum(vals) / len(vals), 0) if vals else 0.0


def run_rotation_scan(close_all, spy):
    """
    Full pipeline: score every ticker in the universe, aggregate to sub-sector,
    compute second-order RS vs parent sector, rank resilience cross-sectionally,
    and classify each sub-sector.

    Returns (subsector_agg, breadth_pct, n_groups):
      subsector_agg — dict keyed by sub-sector name -> aggregated signal dict
                       (includes "classification")
      breadth_pct   — % of sub-sectors currently RS-positive vs SPY
      n_groups      — number of sub-sectors successfully scored
    """
    sector_of = sector_of_subsector_map()
    sub_tickers = subsector_tickers_map()

    ticker_signals = {}
    for t in all_universe_tickers():
        r = compute_ticker_signals(t, close_all, spy)
        if r:
            ticker_signals[t] = r

    subsector_agg = {}
    for sub, tickers in sub_tickers.items():
        rows = [ticker_signals[t] for t in tickers if t in ticker_signals]
        if not rows:
            continue
        subsector_agg[sub] = dict(
            sector=sector_of[sub],
            n=len(rows),
            tickers=[r["ticker"] for r in rows],
            pct_rs_trend_mid_up=_pct([r["rs_trend_mid_up"] for r in rows]),
            pct_rs_trend_long_up=_pct([r["rs_trend_long_up"] for r in rows]),
            avg_rs_mom=round(float(np.mean([r["rs_mom"] for r in rows])), 2),
            pct_early_leadership=_pct([r["early_leadership"] for r in rows]),
            pct_early_weakness=_pct([r["early_weakness"] for r in rows]),
            pct_above_50=_pct([r["above_50"] for r in rows]),
            pct_above_200=_pct([r["above_200"] for r in rows]),
            avg_ret1m=round(float(np.mean([r["ret1m"] for r in rows])), 1),
            avg_ret3m=round(float(np.mean([r["ret3m"] for r in rows])), 1),
            avg_ret6m=round(float(np.mean([r["ret6m"] for r in rows])), 1),
            avg_rs_dd_norm=round(float(np.mean([r["rs_dd_60_norm"] for r in rows])), 2),
            # Leaders: positive RS momentum AND above 50d MA AND positive 3M return
            # rs_mom > 0 alone is misleading — a stock in freefall can still have positive
            # RS momentum if it's falling less fast than SPY.
            leaders=", ".join(sorted(
                [r["ticker"] for r in rows
                 if r["rs_mom"] > 0 and r["above_50"] and r["ret3m"] > 0],
                key=lambda tk: -next(r["rs_mom"] for r in rows if r["ticker"] == tk)
            )[:4]),
            # Laggards: negative RS momentum AND below 50d MA AND negative 3M return
            laggards=", ".join(sorted(
                [r["ticker"] for r in rows
                 if r["rs_mom"] < 0 and not r["above_50"] and r["ret3m"] < 0],
                key=lambda tk: next(r["rs_mom"] for r in rows if r["ticker"] == tk)
            )[:3]),
        )

    # Resilient / vulnerable: cross-sectional rank on vol-normalized drawdown,
    # not a fixed cutoff -- adapts to whatever "normal" looks like right now.
    if subsector_agg:
        dd_norm_values = np.array([a["avg_rs_dd_norm"] for a in subsector_agg.values()])
        resilient_cut  = float(np.quantile(dd_norm_values, RESILIENT_QUANTILE))
        vulnerable_cut = float(np.quantile(dd_norm_values, VULNERABLE_QUANTILE))
        for a in subsector_agg.values():
            a["resilient"]  = bool(a["avg_rs_dd_norm"] >= resilient_cut)
            a["vulnerable"] = bool(a["avg_rs_dd_norm"] <= vulnerable_cut)

    # Second-order RS: sub-sector momentum vs its own parent sector's average
    sector_avg_mom = {}
    for sector in UNIVERSE:
        subs_in_sector = [s for s, a in subsector_agg.items() if a["sector"] == sector]
        if subs_in_sector:
            sector_avg_mom[sector] = float(np.mean([subsector_agg[s]["avg_rs_mom"] for s in subs_in_sector]))
    for sub, a in subsector_agg.items():
        a["sector_avg_mom"] = round(sector_avg_mom.get(a["sector"], 0.0), 2)
        a["leading_within_sector"] = bool(a["avg_rs_mom"] > a["sector_avg_mom"])

    # Breadth overlay
    n_groups = len(subsector_agg)
    breadth_up = sum(1 for a in subsector_agg.values() if a["avg_rs_mom"] > 0)
    breadth_pct = round(100 * breadth_up / n_groups, 0) if n_groups else 0.0

    # Composite scores + classification
    for sub, a in subsector_agg.items():
        long_score = sum([
            a["pct_rs_trend_mid_up"]  >= 50,
            a["pct_rs_trend_long_up"] >= 50,
            a["avg_rs_mom"] > 0,
            a["pct_above_50"]  >= 50,
            a["pct_above_200"] >= 50,
            a["avg_ret3m"] > 0,
            a["resilient"],
        ])
        short_score = sum([
            a["pct_rs_trend_mid_up"]  < 50,
            a["pct_rs_trend_long_up"] < 50,
            a["avg_rs_mom"] < 0,
            a["pct_above_50"]  < 50,
            a["pct_above_200"] < 50,
            a["avg_ret3m"] < 0,
            a["vulnerable"],
        ])
        a["long_score"]  = long_score
        a["short_score"] = short_score

        confirmed_long = (long_score >= CONFIRMED_SCORE and a["pct_above_50"] >= 50
                           and a["pct_above_200"] >= 50 and a["avg_ret3m"] > 0)
        starter_long = (not confirmed_long
                         and a["pct_rs_trend_mid_up"] >= 50
                         and (a["pct_early_leadership"] >= EARLY_FRACTION * 100 or a["resilient"]))

        confirmed_short = (short_score >= CONFIRMED_SCORE and a["pct_above_50"] < 50
                            and a["pct_above_200"] < 50 and a["avg_ret3m"] < 0)
        early_weak_short = (not confirmed_short
                             and a["pct_rs_trend_mid_up"] < 50
                             and (a["pct_early_weakness"] >= EARLY_FRACTION * 100 or a["vulnerable"]))

        if confirmed_long:
            cls = "CONFIRMED LONG"
        elif starter_long and a["leading_within_sector"]:
            cls = "STARTER LONG (leadership)"
        elif starter_long:
            cls = "STARTER LONG (broad-rotation)"
        elif confirmed_short:
            cls = "CONFIRMED SHORT"
        elif early_weak_short and not a["leading_within_sector"]:
            cls = "EARLY WEAKNESS SHORT (lagging sector)"
        elif early_weak_short:
            cls = "EARLY WEAKNESS SHORT (broad decline)"
        else:
            cls = "NEUTRAL / NO SETUP"

        a["classification"] = cls

    return subsector_agg, breadth_pct, n_groups


CLASSIFICATION_ORDER = [
    "CONFIRMED LONG",
    "STARTER LONG (leadership)",
    "STARTER LONG (broad-rotation)",
    "CONFIRMED SHORT",
    "EARLY WEAKNESS SHORT (lagging sector)",
    "EARLY WEAKNESS SHORT (broad decline)",
    "NEUTRAL / NO SETUP",
]
