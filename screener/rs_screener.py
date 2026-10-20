import yfinance as yf
import pandas as pd
import smtplib
import time
import requests
import json
from io import StringIO
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from collections import Counter, defaultdict
import os
from dotenv import load_dotenv

load_dotenv()

RUSSELL_RESULTS_FILE = os.path.join(os.path.dirname(__file__), "russell_overnight_results.json")
SCREEN_LOG_FILE      = os.path.join(os.path.dirname(__file__), "screen_log.csv")

RECIPIENT_EMAIL = "moshe@thefortunecapital.com"
SENDER_EMAIL    = os.getenv("SENDER_EMAIL", "")
SENDER_APP_PASSWORD = os.getenv("SENDER_APP_PASSWORD", "")

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}


# ── Ticker universe ───────────────────────────────────────────────────────────

def _read_html(url, idx=0):
    r = requests.get(url, headers=_HEADERS, timeout=20)
    r.raise_for_status()
    return pd.read_html(StringIO(r.text))[idx]


def get_tickers():
    tickers, sector_map, subsector_map = set(), {}, {}
    try:
        sp500 = _read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", 0)
        for _, row in sp500.iterrows():
            t = str(row["Symbol"]).replace(".", "-")
            tickers.add(t)
            sector_map[t]    = str(row.get("GICS Sector",       "Unknown"))
            subsector_map[t] = str(row.get("GICS Sub-Industry", "Unknown"))
    except Exception as e:
        print(f"Warning: S&P 500 list unavailable: {e}")
    try:
        ndq = _read_html("https://en.wikipedia.org/wiki/Nasdaq-100", 5)
        for t in ndq["Ticker"].tolist():
            tickers.add(t.replace(".", "-"))
    except Exception as e:
        print(f"Warning: Nasdaq-100 list unavailable: {e}")
    return sorted(tickers), sector_map, subsector_map


def find_subsector_clusters(tickers, subsector_map, min_count=3):
    """Return sub-industries that have min_count or more stocks in the result list.
    Sorted largest cluster first. Only covers S&P 500 tickers (Nasdaq-only won't have a sub-industry).
    """
    groups = defaultdict(list)
    for ticker in tickers:
        sub = subsector_map.get(ticker)
        if sub and sub != "Unknown":
            groups[sub].append(ticker)
    clusters = [
        {"subsector": sub, "tickers": sorted(group)}
        for sub, group in groups.items()
        if len(group) >= min_count
    ]
    clusters.sort(key=lambda x: len(x["tickers"]), reverse=True)
    return clusters


def get_previously_seen(log_file, lookback_days=30):
    """Return {ticker: last_seen_date_str} for tickers seen in the last lookback_days days."""
    if not os.path.exists(log_file):
        return {}
    try:
        df = pd.read_csv(log_file)
        df["date"] = pd.to_datetime(df["date"])
        cutoff = datetime.now() - timedelta(days=lookback_days)
        recent = df[df["date"] >= cutoff]
        last_seen = {}
        for ticker in recent["ticker"].unique():
            last_seen[ticker] = recent[recent["ticker"] == ticker]["date"].max().strftime("%b %d")
        return last_seen
    except Exception:
        return {}


def log_screen_results(tickers, log_file):
    """Append today's tickers to the screen history CSV log."""
    today = datetime.now().strftime("%Y-%m-%d")
    rows  = "\n".join(f"{today},{t}" for t in tickers)
    if os.path.exists(log_file):
        with open(log_file, "a") as f:
            f.write("\n" + rows)
    else:
        with open(log_file, "w") as f:
            f.write("date,ticker\n" + rows)


# ── Phase 1: fast hard-filter screen (runs on all ~516 tickers) ───────────────

def check_rs_new_high_in_base(ticker, spy_hist):
    """
    Returns a dict if the stock passes all hard filters, else None.
    Hard filters:
      1. Stage 2 uptrend (price above 21/50/150/200d MAs)
      2. Within 15% of 52-week high
      3. RS line within 3% of its own 3-month high
      4. Tight 8-week base: ADR < 5.5% AND total price range < 25%
    """
    try:
        hist = yf.Ticker(ticker).history(period="1y")
        if hist.empty or len(hist) < 200:
            return None

        close = hist["Close"]
        price = float(close.iloc[-1])

        ma21  = float(close.rolling(21).mean().iloc[-1])
        ma50  = float(close.rolling(50).mean().iloc[-1])
        ma150 = float(close.rolling(150).mean().iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1])
        ema21 = float(close.ewm(span=21, adjust=False).mean().iloc[-1])

        if not (price > ma21 and price > ma50 and price > ma150 and price > ma200):
            return None

        high_52w     = float(hist["High"].tail(252).max())
        pct_off_high = (high_52w - price) / high_52w * 100
        if pct_off_high > 15:
            return None

        spy_close    = spy_hist["Close"].reindex(close.index, method="ffill").dropna()
        common       = close.index.intersection(spy_close.index)
        if len(common) < 65:
            return None
        rs           = close[common] / spy_close[common]
        rs_3m        = rs.tail(65)
        if float(rs_3m.iloc[-1]) < float(rs_3m.max()) * 0.97:
            return None

        last_40   = hist.tail(40)
        pre_close = last_40["Close"]
        pre_vol   = last_40["Volume"]

        adr             = float(((last_40["High"] - last_40["Low"]) / pre_close * 100).mean())
        eight_week_range = float((pre_close.max() - pre_close.min()) / pre_close.min() * 100)
        if adr > 5.5 or eight_week_range > 25:
            return None

        # OBV
        obv = [0]
        for i in range(1, len(pre_close)):
            if   pre_close.iloc[i] > pre_close.iloc[i-1]: obv.append(obv[-1] + float(pre_vol.iloc[i]))
            elif pre_close.iloc[i] < pre_close.iloc[i-1]: obv.append(obv[-1] - float(pre_vol.iloc[i]))
            else:                                           obv.append(obv[-1])
        obv_rising = bool(obv[-1] > obv[0])

        df     = last_40.copy()
        df["p"] = df["Close"].shift(1)
        up_vol  = float(df.loc[df["Close"] >= df["p"], "Volume"].sum())
        dn_vol  = float(df.loc[df["Close"] <  df["p"], "Volume"].sum())
        ud_ratio = round(up_vol / dn_vol, 2) if dn_vol > 0 else 9.9

        # Tight close cluster: longest run of days closing within 1% of prior close
        streaks = [0]
        for i in range(1, len(pre_close)):
            if abs(float(pre_close.iloc[i]) / float(pre_close.iloc[i-1]) - 1) <= 0.01:
                streaks.append(streaks[-1] + 1)
            else:
                streaks.append(0)
        max_run           = max(streaks)
        tight_cluster     = max_run >= 3
        tight_cluster_len = max_run

        ext_ema21 = round((price - ema21) / ema21 * 100, 1)
        ext_ma50  = round((price - ma50)  / ma50  * 100, 1)
        move_3m   = round((price / float(close.iloc[-65]) - 1) * 100, 1) if len(close) >= 65 else 0.0

        verdict_label, verdict_color, verdict_note = _verdict(ext_ema21, ext_ma50, ema21)

        return {
            "ticker":           ticker,
            "price":            round(price, 2),
            "ema21":            round(ema21, 2),
            "pct_off_52w_high": round(pct_off_high, 1),
            "adr":              round(adr, 1),
            "eight_week_range": round(eight_week_range, 1),
            "obv_rising":       obv_rising,
            "ud_ratio":         ud_ratio,
            "tight_cluster":    tight_cluster,
            "tight_cluster_len": tight_cluster_len,
            "ext_ema21":        ext_ema21,
            "ext_ma50":         ext_ma50,
            "move_3m":          move_3m,
            "verdict":          verdict_label,
            "verdict_color":    verdict_color,
            "verdict_note":     verdict_note,
            # enriched fields filled in phase 2
            "base_stage":       None,
            "short_pct":        None,
            "score":            0,
            "grade":            "C",
            "grade_color":      "#888888",
            "signals":          [],
        }

    except Exception:
        return None


def _verdict(ext_ema21, ext_ma50, ema21_price):
    if ext_ema21 > 15 or ext_ma50 > 22:
        return "TOO EXTENDED", "#cc0000", f"Already {ext_ema21:+.1f}% above 21d EMA — wait for a pullback first"
    if abs(ext_ema21) <= 5 and ext_ma50 <= 15:
        return "BUY NOW", "#1a7a1a", "Within 5% of 21d EMA — still in the actionable buy zone"
    return "WAIT FOR PULLBACK", "#b8860b", f"A 2–4% dip toward the 21d EMA (${ema21_price:.2f}) would be ideal"


# ── VCP (Volatility Contraction Pattern) Scan ─────────────────────────────────

def _find_vcp_contractions(close_vals, vol_vals, swing_window=5):
    """
    Finds swing highs and lows in a price series, then measures the % pullback
    from each swing high to the next swing low (one contraction per H→L pair).
    Returns a list of dicts: {depth (%), avg_vol} for each contraction found.
    """
    n = len(close_vals)

    # Find raw swing highs and lows using a rolling window
    raw = []
    for i in range(swing_window, n - swing_window):
        seg = close_vals[i - swing_window: i + swing_window + 1]
        if close_vals[i] >= max(seg):
            raw.append([i, close_vals[i], 'H'])
        elif close_vals[i] <= min(seg):
            raw.append([i, close_vals[i], 'L'])
    if not raw:
        return []

    # Merge consecutive same-direction points — keep the most extreme
    clean = [raw[0]]
    for pt in raw[1:]:
        if pt[2] == clean[-1][2]:
            if pt[2] == 'H' and pt[1] > clean[-1][1]:
                clean[-1] = pt
            elif pt[2] == 'L' and pt[1] < clean[-1][1]:
                clean[-1] = pt
        else:
            clean.append(pt)

    # Each H→L pair is one contraction
    contractions = []
    for i in range(len(clean) - 1):
        if clean[i][2] == 'H' and clean[i + 1][2] == 'L':
            h_idx, h_price = clean[i][0], clean[i][1]
            l_idx, l_price = clean[i + 1][0], clean[i + 1][1]
            depth   = (h_price - l_price) / h_price * 100
            avg_vol = float(sum(vol_vals[h_idx: l_idx + 1])) / max(1, l_idx - h_idx + 1)
            contractions.append({"depth": depth, "avg_vol": avg_vol})

    return contractions


def check_vcp(ticker, spy_hist):
    """
    Screens a stock for a VCP (Volatility Contraction Pattern) setup.

    A VCP has 2-4 progressively shallower pullbacks where each contraction in
    price and volume is smaller than the last, forming a tight coil before a
    potential breakout. Named by Mark Minervini in 'Trade Like a Stock Market Wizard'.

    Returns a dict with VCP metrics if the stock qualifies, None otherwise.
    """
    try:
        hist = yf.Ticker(ticker).history(period="1y")
        if hist.empty or len(hist) < 150:
            return None

        close  = hist["Close"]
        volume = hist["Volume"]
        price  = float(close.iloc[-1])

        # Gate 1: Stage 2 uptrend — price above both the 150d and 200d moving averages
        ma150 = float(close.rolling(150).mean().iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1])
        ma50  = float(close.rolling(50).mean().iloc[-1])
        if price < ma150 or price < ma200:
            return None

        # Gate 2: within 25% of 52-week high (VCP forms near the top, not at the bottom)
        high_52w     = float(hist["High"].tail(252).max())
        pct_off_high = (high_52w - price) / high_52w * 100
        if pct_off_high > 25:
            return None

        # Gate 3: prior uptrend — must have risen 30%+ from the 52-week low before the base
        low_52w = float(hist["Low"].tail(252).min())
        if price < low_52w * 1.30:
            return None

        # Gate 4: stock must be consolidating, not bouncing from a crash.
        # A V-shaped 50% recovery is not a VCP base — the 90-bar range must be < 35%.
        base       = hist.tail(90)
        base_high  = float(base["High"].max())
        base_low   = float(base["Low"].min())
        base_range = (base_high - base_low) / base_high * 100
        if base_range > 35:
            return None

        # Find contractions using an 8-bar swing window — wide enough to skip daily noise
        bc       = base["Close"].values.tolist()
        bv       = base["Volume"].values.tolist()
        all_cont = _find_vcp_contractions(bc, bv, swing_window=8)

        if len(all_cont) < 2:
            return None

        # Analyse the most recent 4 contractions
        recent = all_cont[-4:]
        depths = [c["depth"] for c in recent]

        # The final contraction must be smaller than the first (overall contraction present)
        if depths[-1] >= depths[0]:
            return None

        # The final contraction must also be smaller than the one immediately before it —
        # a pattern like 25%→7%→12% is a re-expanding base, not a VCP
        if depths[-1] >= depths[-2]:
            return None

        # When there are 3+ contractions, the last must also be below the average of the others
        # (prevents a scenario where only the last pair happened to shrink)
        if len(depths) > 2 and depths[-1] >= sum(depths[:-1]) / len(depths[:-1]):
            return None

        # Final contraction must be tight enough to be a real VCP pivot
        final_depth = depths[-1]
        if final_depth > 15:
            return None

        # Volume dry-up: compare the last 5 days against the 20-day average
        recent_vol = float(volume.tail(5).mean())
        avg_vol_20 = float(volume.tail(20).mean())
        vol_dry    = recent_vol / avg_vol_20 if avg_vol_20 > 0 else 1.0

        # RS vs SPY over the last 60 trading days
        rs_60d = 0.0
        try:
            spy_close = spy_hist["Close"]
            common = close.index.intersection(spy_close.index)
            if len(common) >= 60:
                stock_ret = float(close[common].iloc[-1]) / float(close[common].iloc[-60]) - 1
                spy_ret   = float(spy_close[common].iloc[-1]) / float(spy_close[common].iloc[-60]) - 1
                rs_60d    = round((stock_ret - spy_ret) * 100, 1)
        except Exception:
            pass

        # Score the setup (max 11 points)
        score = 0
        if len(recent) >= 4:     score += 2
        elif len(recent) >= 3:   score += 1
        if final_depth <= 5:     score += 3
        elif final_depth <= 8:   score += 2
        elif final_depth <= 12:  score += 1
        if vol_dry < 0.50:       score += 2
        elif vol_dry < 0.70:     score += 1
        if pct_off_high <= 5:    score += 2
        elif pct_off_high <= 10: score += 1
        if rs_60d >= 20:         score += 2
        elif rs_60d >= 5:        score += 1

        if score < 3:
            return None

        if   score >= 8: label = "TIGHT"
        elif score >= 5: label = "FORMING"
        else:            label = "WATCH"

        return {
            "ticker":       ticker,
            "price":        round(price, 2),
            "ma50":         round(ma50, 2),
            "pct_off_high": round(pct_off_high, 1),
            "num_cont":     len(recent),
            "depths":       [round(d, 1) for d in depths],
            "final_depth":  round(final_depth, 1),
            "vol_dry_pct":  round(vol_dry * 100, 1),
            "rs_60d":       rs_60d,
            "vcp_score":    score,
            "vcp_label":    label,
        }

    except Exception:
        return None


# ── Phase 2: enrichment (runs only on the ~10–15 qualifiers) ──────────────────

def count_base_stages(ticker):
    """
    Estimates which stage base the stock is currently forming.
    Uses 2 years of weekly data and counts distinct breakout events.

    Stage 1 = first base (most powerful, ~70% breakout success rate)
    Stage 2 = second base (~50%)
    Stage 3+ = late-stage, institutions increasingly use rallies to exit
    """
    try:
        hist = yf.Ticker(ticker).history(period="2y")
        if hist.empty or len(hist) < 60:
            return None

        weekly = hist["Close"].resample("W-FRI").last().dropna()
        if len(weekly) < 20:
            return None

        # A breakout week = closes 8%+ above the prior 10-week rolling high
        prior_high = weekly.shift(1).rolling(10).max()
        is_breakout = (weekly / prior_high - 1) >= 0.08

        # Count distinct breakout events, ignoring consecutive breakout weeks
        breakout_count = 0
        in_event       = False
        quiet_weeks    = 0

        for i in range(len(is_breakout)):
            if pd.isna(is_breakout.iloc[i]):
                continue
            if is_breakout.iloc[i]:
                if not in_event:
                    breakout_count += 1
                    in_event = True
                quiet_weeks = 0
            else:
                quiet_weeks += 1
                if quiet_weeks >= 3:
                    in_event = False

        # Current stage = prior breakouts + 1
        return max(1, breakout_count + 1)

    except Exception:
        return None


def get_short_interest(ticker):
    """Returns short interest as % of float, or None."""
    try:
        info = yf.Ticker(ticker).info
        val  = info.get("shortPercentOfFloat", None)
        if val is not None and float(val) > 0:
            return round(float(val) * 100, 1)
        return None
    except Exception:
        return None


def enrich(result):
    """
    Adds base stage, short interest, score, grade, and signal list
    to a result dict that already passed phase-1 screening.
    """
    ticker = result["ticker"]

    base_stage = count_base_stages(ticker)
    short_pct  = get_short_interest(ticker)

    score   = 0
    signals = []

    # Existing accumulation signals
    if result["obv_rising"]:
        score += 1
        signals.append("OBV rising")
    if result["ud_ratio"] >= 1.5:
        score += 1
        signals.append(f"U/D vol {result['ud_ratio']}x")

    # ── New signal 1: tight close cluster ──────────────────────────────────
    # 3+ consecutive days closing within 1% of the prior close = supply
    # is essentially zero. Someone is holding all the shares and not selling.
    if result["tight_cluster"]:
        score += 2
        signals.append(f"{result['tight_cluster_len']}-day tight close cluster ✦")

    # ── New signal 2: base stage count ─────────────────────────────────────
    # O'Neil research: 1st-stage bases succeed ~70% of the time.
    # By the 3rd stage, institutions are using rallies to exit position.
    if base_stage is not None:
        if base_stage == 1:
            score += 2
            signals.append("Stage 1 base ✦")
        elif base_stage == 2:
            score += 1
            signals.append("Stage 2 base")
        else:
            signals.append(f"Stage {base_stage} base (late-stage, lower odds)")

    # ── New signal 3: short interest as squeeze fuel ───────────────────────
    # High short interest in a stock that's breaking out = forced buying
    # when shorts cover, amplifying the move significantly.
    if short_pct is not None:
        if short_pct >= 15:
            score += 2
            signals.append(f"{short_pct}% short float ✦")
        elif short_pct >= 8:
            score += 1
            signals.append(f"{short_pct}% short float")
        else:
            signals.append(f"{short_pct}% short float (low — no squeeze fuel)")

    # Grade
    if score >= 5:
        grade, grade_color = "A", "#1a7a1a"
    elif score >= 3:
        grade, grade_color = "B", "#b8860b"
    else:
        grade, grade_color = "C", "#777777"

    return {
        **result,
        "base_stage":  base_stage,
        "short_pct":   short_pct,
        "score":       score,
        "grade":       grade,
        "grade_color": grade_color,
        "signals":     signals,
    }


# ── Email ─────────────────────────────────────────────────────────────────────

def _timing_note(results):
    """One-line note about Grade-A setup count and buy zones."""
    buy_now = sum(1 for r in results if r["verdict"] == "BUY NOW")
    grade_a = sum(1 for r in results if r["grade"]   == "A")
    if grade_a == 0:
        return ("No Grade-A setups today. Stocks on this list pass base criteria "
                "but none carry all three high-conviction signals. Set alerts at "
                "the 21d EMA levels rather than entering aggressively.")
    if buy_now == 0:
        return (f"{grade_a} Grade-A setup{'s' if grade_a>1 else ''} present but "
                f"none in the ideal buy zone yet. Set price alerts near the 21d EMA levels shown above.")
    return (f"{buy_now} setup{'s' if buy_now>1 else ''} in the buy zone now, "
            f"{grade_a} of which {'are' if grade_a>1 else 'is'} Grade A.")


# Major sector and industry ETFs tracked for the daily heat map
_SECTOR_ETFS = [
    ("XLK",  "Technology"),
    ("SMH",  "Semiconductors"),
    ("XLC",  "Comm. Services"),
    ("XLY",  "Cons. Discret."),
    ("XLF",  "Financials"),
    ("XLI",  "Industrials"),
    ("XLV",  "Healthcare"),
    ("XLE",  "Energy"),
    ("XLP",  "Cons. Staples"),
    ("XLU",  "Utilities"),
    ("XLB",  "Materials"),
    ("XLRE", "Real Estate"),
]


def _sector_heat_map(spy_hist):
    """
    Fetches each major sector ETF and measures its RS vs SPY over three
    time windows (1 week, 1 month, 3 months) plus the direction of the RS
    line over the last 4 weeks.

    This replaces the old approach of inferring sector strength from which
    stocks happened to pass the tight-base filter — which was misleading
    whenever leading sectors were extended rather than basing.
    """
    spy_close = spy_hist["Close"]
    rows = []

    for etf, name in _SECTOR_ETFS:
        try:
            h = yf.Ticker(etf).history(period="1y")
            if h.empty or len(h) < 70:
                continue
            c = h["Close"]
            common = c.index.intersection(spy_close.index)
            if len(common) < 70:
                continue

            ec = c[common]
            sc = spy_close[common]
            price   = float(ec.iloc[-1])
            ma50    = float(ec.rolling(50).mean().iloc[-1])
            vs_ma50 = round((price / ma50 - 1) * 100, 1)

            def rs(n):
                return round((float(ec.iloc[-1]) / float(ec.iloc[-n]) - 1
                              - float(sc.iloc[-1]) / float(sc.iloc[-n]) + 1) * 100, 1)

            rs_1w  = rs(5)
            rs_1mo = rs(20)
            rs_3mo = rs(65)

            # RS line = ETF / SPY ratio. Compare now vs 4 weeks ago to get direction.
            rs_line      = ec / sc
            rs_slope_pct = (float(rs_line.iloc[-1]) / float(rs_line.iloc[-20]) - 1) * 100

            # Also check if the RS line is near a 3-month high or low
            rs_3mo_high  = float(rs_line.iloc[-65:].max())
            rs_3mo_low   = float(rs_line.iloc[-65:].min())
            rs_now       = float(rs_line.iloc[-1])
            pct_of_range = (rs_now - rs_3mo_low) / (rs_3mo_high - rs_3mo_low) if rs_3mo_high > rs_3mo_low else 0.5

            if   rs_slope_pct > 1.5 and pct_of_range > 0.60:
                trend, trend_color = "LEADING",  "#1a7a1a"
            elif rs_slope_pct < -1.5 and pct_of_range < 0.40:
                trend, trend_color = "LAGGING",  "#cc0000"
            elif rs_slope_pct > 0.5:
                trend, trend_color = "IMPROVING","#2a8a2a"
            elif rs_slope_pct < -0.5:
                trend, trend_color = "FADING",   "#b8860b"
            else:
                trend, trend_color = "NEUTRAL",  "#666666"

            rows.append({
                "etf": etf, "name": name, "price": price,
                "vs_ma50": vs_ma50,
                "rs_1w": rs_1w, "rs_1mo": rs_1mo, "rs_3mo": rs_3mo,
                "rs_slope": round(rs_slope_pct, 1),
                "trend": trend, "trend_color": trend_color,
            })
        except Exception:
            continue

    if not rows:
        return ""

    # Sort by 1-month RS descending (strongest sectors at the top)
    rows.sort(key=lambda x: x["rs_1mo"], reverse=True)

    def _c(val):
        if val > 3:   return "#1a7a1a"
        if val > 0:   return "#2a6a2a"
        if val > -3:  return "#b8860b"
        return "#cc0000"

    leaders  = [r["name"] for r in rows if r["trend"] in ("LEADING", "IMPROVING")][:3]
    laggers  = [r["name"] for r in rows if r["trend"] in ("LAGGING",  "FADING")][:3]
    summary  = ""
    if leaders: summary += f'<span style="color:#1a7a1a;font-weight:bold">Leading:</span> {", ".join(leaders)}'
    if laggers: summary += f'&nbsp;&nbsp;|&nbsp;&nbsp;<span style="color:#cc0000;font-weight:bold">Lagging:</span> {", ".join(laggers)}'

    tbl_rows = []
    for r in rows:
        badge = (f'<span style="background:{r["trend_color"]};color:#fff;padding:2px 6px;'
                 f'border-radius:3px;font-size:11px;font-weight:bold">{r["trend"]}</span>')
        ma50_c = "#1a7a1a" if r["vs_ma50"] >= 0 else "#cc0000"
        tbl_rows.append(f"""
        <tr>
          <td style="font-weight:bold">{r['name']}</td>
          <td style="color:#555">{r['etf']}</td>
          <td>${r['price']:.2f}</td>
          <td style="color:{ma50_c};text-align:center">{r['vs_ma50']:+.1f}%</td>
          <td style="color:{_c(r['rs_1w'])};text-align:center;font-weight:bold">{r['rs_1w']:+.1f}%</td>
          <td style="color:{_c(r['rs_1mo'])};text-align:center;font-weight:bold">{r['rs_1mo']:+.1f}%</td>
          <td style="color:{_c(r['rs_3mo'])};text-align:center;font-weight:bold">{r['rs_3mo']:+.1f}%</td>
          <td style="text-align:center">{badge}</td>
        </tr>""")

    return f"""
    <b style="font-size:14px">Sector Heat Map</b>
    <p style="color:#444;font-size:13px;margin:4px 0 8px">{summary}</p>
    <table border="1" cellpadding="6" cellspacing="0"
           style="border-collapse:collapse;font-size:12px;width:100%">
      <tr style="background:#1a1a2e;color:white;text-align:left">
        <th>Sector</th><th>ETF</th><th>Price</th>
        <th>vs 50d MA</th>
        <th>RS 1-Week</th><th>RS 1-Month</th><th>RS 3-Month</th>
        <th>Trend</th>
      </tr>
      {"".join(tbl_rows)}
    </table>
    <p style="color:#777;font-size:11px;margin-top:4px">
      RS = return vs SPY over the period. Trend = direction of the ETF/SPY ratio line over
      the last 4 weeks: LEADING (rising RS, near 3-month high), LAGGING (falling RS, near 3-month low).
    </p>"""


def _stock_row(r):
    m3c  = "green" if r["move_3m"]  >= 0 else "#cc0000"
    e21c = "green" if r["ext_ema21"] <= 5 else ("#cc0000" if r["ext_ema21"] > 15 else "#b8860b")
    e50c = "green" if r["ext_ma50"]  <= 12 else ("#cc0000" if r["ext_ma50"] > 22  else "#b8860b")
    stage_str = str(r["base_stage"]) if r["base_stage"] else "—"
    short_str = f"{r['short_pct']}%" if r["short_pct"] is not None else "—"
    signals_html = " &nbsp;·&nbsp; ".join(r["signals"]) if r["signals"] else "—"

    # Signal age: "New" (green) or "Seen Aug 15" (grey) based on 30-day history
    sig = r.get("signal_age", "New")
    if sig == "New":
        sig_html = '<span style="background:#1a7a1a;color:#fff;padding:2px 6px;border-radius:3px;font-size:11px;font-weight:bold">New</span>'
    else:
        sig_html = f'<span style="color:#888;font-size:11px">{sig}</span>'

    return f"""
    <tr>
      <td style="font-weight:bold;font-size:15px;white-space:nowrap">{r['ticker']}</td>
      <td style="text-align:center">{sig_html}</td>
      <td style="text-align:center;font-size:18px;font-weight:bold;color:{r['grade_color']}">{r['grade']}</td>
      <td style="text-align:center">{r['score']}/8</td>
      <td style="font-size:12px;color:#444">{signals_html}</td>
      <td style="text-align:center">{stage_str}</td>
      <td style="text-align:center">{short_str}</td>
      <td>${r['price']}</td>
      <td style="color:{m3c}">{"+" if r["move_3m"]>=0 else ""}{r['move_3m']}%</td>
      <td style="color:{e21c};font-weight:bold">{"+" if r["ext_ema21"]>=0 else ""}{r['ext_ema21']}%</td>
      <td style="color:{e50c};font-weight:bold">{"+" if r["ext_ma50"]>=0 else ""}{r['ext_ma50']}%</td>
      <td style="color:{r['verdict_color']};font-weight:bold;white-space:nowrap">{r['verdict']}</td>
      <td style="font-size:12px;color:#555">{r['verdict_note']}</td>
    </tr>"""


def _load_russell_results():
    """
    Reads the overnight Russell scan JSON if it exists and was created
    within the last 20 hours (i.e., from last night's run).
    Returns the parsed dict, or None if the file is missing or stale.
    """
    if not os.path.exists(RUSSELL_RESULTS_FILE):
        return None
    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(RUSSELL_RESULTS_FILE))
        if datetime.now() - mtime > timedelta(hours=26):
            return None   # file is stale (more than 26 hours old), skip it
        with open(RUSSELL_RESULTS_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def _vcp_email_section(vcp_results):
    """
    Builds the HTML block showing VCP (Volatility Contraction Pattern) setups.
    Returns an empty string if no VCP setups were found.
    """
    if not vcp_results:
        return ""

    label_order = {"TIGHT": 0, "FORMING": 1, "WATCH": 2}
    vcp_sorted = sorted(
        vcp_results,
        key=lambda x: (label_order.get(x["vcp_label"], 9), -x["vcp_score"], x["pct_off_high"])
    )

    def _badge(label, score):
        colors = {"TIGHT": ("#1a7a1a", "#fff"), "FORMING": ("#b8860b", "#fff"), "WATCH": ("#555", "#fff")}
        bg, fg = colors.get(label, ("#999", "#fff"))
        return (f'<span style="background:{bg};color:{fg};padding:2px 6px;'
                f'border-radius:3px;font-size:11px;font-weight:bold">'
                f'{label} {score}/11</span>')

    rows = []
    for r in vcp_sorted:
        # Show contraction depths as a chain: e.g. "24% → 12% → 6%"
        depth_str = " → ".join(f"{d:.0f}%" for d in r["depths"])
        rs_color  = "#1a7a1a" if r["rs_60d"] > 20 else ("#b8860b" if r["rs_60d"] > 0 else "#c00")
        vol_color = "#1a7a1a" if r["vol_dry_pct"] < 60 else ("#b8860b" if r["vol_dry_pct"] < 80 else "#555")
        rows.append(f"""
        <tr>
          <td style="font-weight:bold;white-space:nowrap">{r['ticker']}</td>
          <td>${r['price']:.2f}</td>
          <td style="text-align:center">{r['num_cont']}</td>
          <td style="font-size:11px;color:#444">{depth_str}</td>
          <td style="font-weight:bold;text-align:center">{r['final_depth']:.1f}%</td>
          <td style="color:{vol_color};font-weight:bold;text-align:center">{r['vol_dry_pct']:.0f}%</td>
          <td style="color:{rs_color};font-weight:bold;text-align:center">{r['rs_60d']:+.1f}%</td>
          <td style="text-align:center">{r['pct_off_high']:.1f}%</td>
          <td>{_badge(r['vcp_label'], r['vcp_score'])}</td>
        </tr>""")

    return f"""
  <hr style="margin:28px 0;border-color:#ddd">
  <h3 style="color:#1a1a2e;margin-bottom:4px">
    VCP Setups — {len(vcp_results)} found (S&amp;P 500 + Nasdaq 100)
  </h3>
  <p style="color:#555;font-size:13px;margin-top:0">
    Volatility Contraction Pattern (Minervini). Each stock shows progressively smaller
    pullbacks — price coiling tighter as sellers exhaust. Sorted by quality label, then score.
    <b>TIGHT</b> = right at the ideal buy zone. <b>FORMING</b> = pattern developing.
    <b>WATCH</b> = early stage, not yet actionable.
  </p>
  <table border="1" cellpadding="7" cellspacing="0"
         style="border-collapse:collapse;font-size:12px;width:100%;margin-bottom:10px">
    <tr style="background:#1a1a2e;color:white;text-align:left">
      <th>Ticker</th><th>Price</th><th># Contractions</th>
      <th>Pullback Depths</th><th>Final Tight</th>
      <th>Vol vs 20d Avg</th><th>RS vs SPY 60d</th>
      <th>Off 52w High</th><th>VCP Quality</th>
    </tr>
    {"".join(rows)}
  </table>
  <p style="color:#777;font-size:11px">
    <b>Pullback Depths</b>: each arrow (→) is one contraction from high to low (e.g. 22%→12%→5%
    = three tightening pullbacks, getting smaller each time). &nbsp;
    <b>Final Tight</b>: depth of the last/smallest contraction — under 10% is ideal, under 6% is excellent. &nbsp;
    <b>Vol vs 20d Avg</b>: recent 5-day avg volume as % of 20-day avg — lower means sellers have gone quiet.
  </p>"""


def _russell_email_section():
    """
    Builds the HTML block for Russell 2000 overnight signals.
    Returns an empty string if no results file exists.
    """
    data = _load_russell_results()
    if not data:
        return ""

    pullback = data.get("pullback", [])
    momentum = data.get("momentum", [])
    if not pullback and not momentum:
        return ""

    scan_time = data.get("scan_time", "overnight")
    universe  = data.get("universe", "?")

    def _bp_badge(label, score):
        """Coloured badge showing entry quality."""
        if label == "NEAR ENTRY":
            bg, fg = "#1a7a1a", "#fff"
        elif label == "WATCH":
            bg, fg = "#b8860b", "#fff"
        else:
            bg, fg = "#999", "#fff"
        return (f'<span style="background:{bg};color:{fg};padding:2px 6px;'
                f'border-radius:3px;font-size:11px;font-weight:bold">'
                f'{label} {score}</span>')

    def _pb_rows(signals):
        rows = []
        for r in signals[:15]:
            rs_color = "#1a7a1a" if r["rs_60d"] > 30 else ("#b8860b" if r["rs_60d"] > 0 else "#c00")
            badge = _bp_badge(r.get("bp_label", "?"), r.get("bp_score", 0))
            rows.append(f"""
            <tr>
              <td><b>{r['ticker']}</b></td>
              <td>{r['date']}</td>
              <td>${r['entry']:.2f}</td>
              <td>{r['score']}/5</td>
              <td>{r['base_depth']:.0f}%</td>
              <td>{r['pct_off_high']:.1f}%</td>
              <td style="color:{rs_color};font-weight:bold">{r['rs_60d']:+.1f}%</td>
              <td>{badge}</td>
            </tr>""")
        return "".join(rows)

    def _mom_rows(signals):
        rows = []
        for r in signals[:15]:
            rs_color = "#1a7a1a" if r["rs_60d"] > 50 else ("#b8860b" if r["rs_60d"] > 20 else "#555")
            badge = _bp_badge(r.get("bp_label", "?"), r.get("bp_score", 0))
            rows.append(f"""
            <tr>
              <td><b>{r['ticker']}</b></td>
              <td>{r['date']}</td>
              <td>${r['entry']:.2f}</td>
              <td>{r['base_depth']:.0f}%</td>
              <td>{r['price_pos']:.0f}%</td>
              <td style="color:{rs_color};font-weight:bold">{r['rs_60d']:+.1f}%</td>
              <td>{badge}</td>
            </tr>""")
        return "".join(rows)

    pb_html  = ""
    mom_html = ""

    if pullback:
        pb_html = f"""
        <h4 style="color:#1a1a2e;margin-bottom:4px">
          Pullback Setups ({len(pullback)}) — supply exhaustion in a base
        </h4>
        <table border="1" cellpadding="7" cellspacing="0"
               style="border-collapse:collapse;font-size:12px;width:100%;margin-bottom:14px">
          <tr style="background:#e8eaf6">
            <th>Ticker</th><th>Date</th><th>Price</th><th>Score</th>
            <th>Base Width</th><th>Off High</th><th>RS vs SPY 60d</th>
            <th>Entry Quality</th>
          </tr>
          {_pb_rows(pullback)}
        </table>"""

    if momentum:
        mom_html = f"""
        <h4 style="color:#1a1a2e;margin-bottom:4px">
          Momentum Leaders ({len(momentum)}) — RS leaders holding near highs
        </h4>
        <p style="color:#555;font-size:12px;margin:2px 0 8px">
          Sorted by entry quality. NEAR ENTRY = within buy zone (EMA, tight range, quiet volume).
          EXTENDED = ran too far, wait for next consolidation.
        </p>
        <table border="1" cellpadding="7" cellspacing="0"
               style="border-collapse:collapse;font-size:12px;width:100%;margin-bottom:14px">
          <tr style="background:#e8f5e9">
            <th>Ticker</th><th>Date</th><th>Price</th>
            <th>Base Width</th><th>Price Position</th><th>RS vs SPY 60d</th>
            <th>Entry Quality</th>
          </tr>
          {_mom_rows(momentum)}
        </table>"""

    overflow_note = ""
    total = len(pullback) + len(momentum)
    if total > 30:
        overflow_note = f"<p style='color:#888;font-size:11px'>Showing top 15 per type. {total} total signals found.</p>"

    return f"""
  <hr style="margin:28px 0;border-color:#ddd">
  <h3 style="color:#1a1a2e;margin-bottom:4px">Russell 2000 — Overnight Scan ({scan_time})</h3>
  <p style="color:#555;font-size:13px;margin-top:0">
    {universe} Russell-only stocks scanned (excluding S&P 500 / Nasdaq 100).
    Signals from the last 3 trading days. Sorted by RS vs SPY strength.
  </p>
  {pb_html}
  {mom_html}
  {overflow_note}"""


# ── Portfolio daily analysis ──────────────────────────────────────────────────

PORTFOLIO_FILE = os.path.join(os.path.dirname(__file__), "portfolio.json")


def _load_portfolio():
    """Reads the portfolio ticker list from portfolio.json."""
    try:
        with open(PORTFOLIO_FILE) as f:
            return json.load(f).get("tickers", [])
    except Exception:
        return []


def _analyse_portfolio_stock(ticker, spy_hist):
    """
    Fetches one stock and returns a dict with the metrics needed for
    the portfolio section of the email. Returns None on failure.
    """
    try:
        h = yf.Ticker(ticker).history(period="1y")
        if h.empty or len(h) < 20:
            return None
        c      = h["Close"]
        price  = float(c.iloc[-1])
        ma21e  = float(c.ewm(span=21, adjust=False).mean().iloc[-1])
        ma50   = float(c.rolling(50).mean().iloc[-1])  if len(c) >= 50  else None
        ma200  = float(c.rolling(200).mean().iloc[-1]) if len(c) >= 200 else None
        high52 = float(h["High"].tail(252).max())

        ext_ema21  = round((price - ma21e) / ma21e * 100, 1)
        off_high   = round((high52 - price) / high52 * 100, 1)
        vs_ma200   = round((price / ma200 - 1) * 100, 1) if ma200 else None
        above_200  = (price > ma200) if ma200 else True

        rs_60d = None
        try:
            spy_close = spy_hist["Close"]
            common = c.index.intersection(spy_close.index)
            if len(common) >= 60:
                sr     = float(c[common].iloc[-1]) / float(c[common].iloc[-60]) - 1
                sp     = float(spy_close[common].iloc[-1]) / float(spy_close[common].iloc[-60]) - 1
                rs_60d = round((sr - sp) * 100, 1)
        except Exception:
            pass

        # Stage 2: price > 21 EMA > 50 MA > 200 MA (all aligned upward)
        stage2 = bool(
            ma200 and ma50 and
            price > ma21e and ma21e > ma50 and ma50 > ma200
        )

        # Signal classification
        rs = rs_60d if rs_60d is not None else 0.0
        if not above_200 or rs < -10:
            signal, sig_color = "TRIM",     "#cc0000"
        elif stage2 and ext_ema21 <= 5 and rs >= 0:
            signal, sig_color = "ADD TO",   "#1a7a1a"
        elif stage2 and ext_ema21 > 12:
            signal, sig_color = "EXTENDED", "#b8860b"
        else:
            signal, sig_color = "HOLD",     "#444444"

        return {
            "ticker":    ticker,
            "price":     round(price, 2),
            "ext_ema21": ext_ema21,
            "vs_ma200":  vs_ma200,
            "off_high":  off_high,
            "rs_60d":    rs_60d,
            "stage2":    stage2,
            "above_200": above_200,
            "signal":    signal,
            "sig_color": sig_color,
        }
    except Exception:
        return None


def _portfolio_email_section(portfolio_results):
    """
    Builds the HTML block for the daily portfolio review.
    Positions are grouped: ADD TO → EXTENDED → HOLD → TRIM.
    """
    valid = [r for r in portfolio_results if r is not None]
    if not valid:
        return ""

    order = {"ADD TO": 0, "EXTENDED": 1, "HOLD": 2, "TRIM": 3}
    valid.sort(key=lambda x: (order.get(x["signal"], 9), -(x["rs_60d"] or 0)))

    def _rs_color(rs):
        if rs is None:    return "#888"
        if rs >= 15:      return "#1a7a1a"
        if rs >= 0:       return "#2a6a2a"
        if rs >= -10:     return "#b8860b"
        return "#cc0000"

    rows = []
    for r in valid:
        rs_str   = f"{r['rs_60d']:+.1f}%" if r["rs_60d"] is not None else "n/a"
        m200_str = f"{r['vs_ma200']:+.1f}%" if r["vs_ma200"] is not None else "n/a"
        ema_color = ("#1a7a1a" if abs(r["ext_ema21"]) <= 5
                     else "#cc0000" if r["ext_ema21"] > 15
                     else "#b8860b")
        badge = (f'<span style="background:{r["sig_color"]};color:#fff;'
                 f'padding:2px 7px;border-radius:3px;font-size:11px;'
                 f'font-weight:bold">{r["signal"]}</span>')
        rows.append(f"""
        <tr>
          <td style="font-weight:bold;white-space:nowrap">{r['ticker']}</td>
          <td>${r['price']:.2f}</td>
          <td style="color:{ema_color};font-weight:bold;text-align:center">{r['ext_ema21']:+.1f}%</td>
          <td style="text-align:center">{m200_str}</td>
          <td style="text-align:center">-{r['off_high']:.1f}%</td>
          <td style="color:{_rs_color(r['rs_60d'])};font-weight:bold;text-align:center">{rs_str}</td>
          <td>{badge}</td>
        </tr>""")

    add_count  = sum(1 for r in valid if r["signal"] == "ADD TO")
    trim_count = sum(1 for r in valid if r["signal"] == "TRIM")

    summary = []
    if add_count:
        names = ", ".join(r["ticker"] for r in valid if r["signal"] == "ADD TO")
        summary.append(f'<span style="color:#1a7a1a;font-weight:bold">Add to ({add_count}):</span> {names}')
    if trim_count:
        names = ", ".join(r["ticker"] for r in valid if r["signal"] == "TRIM")
        summary.append(f'<span style="color:#cc0000;font-weight:bold">Trim/Exit ({trim_count}):</span> {names}')
    summary_html = " &nbsp;|&nbsp; ".join(summary) if summary else "No urgent action today."

    return f"""
  <hr style="margin:28px 0;border-color:#ddd">
  <h3 style="color:#1a1a2e;margin-bottom:4px">
    Portfolio — Daily Review ({len(valid)} positions)
  </h3>
  <p style="font-size:13px;color:#444;margin:4px 0 10px">{summary_html}</p>
  <table border="1" cellpadding="7" cellspacing="0"
         style="border-collapse:collapse;font-size:12px;width:100%;margin-bottom:10px">
    <tr style="background:#1a1a2e;color:white;text-align:left">
      <th>Ticker</th><th>Price</th>
      <th>vs 21d EMA</th><th>vs 200d MA</th>
      <th>Off 52w High</th><th>RS vs SPY 60d</th><th>Signal</th>
    </tr>
    {"".join(rows)}
  </table>
  <p style="color:#777;font-size:11px">
    <b>ADD TO</b>: Stage 2 uptrend, within 5% of 21d EMA, outperforming SPY — ideal add zone. &nbsp;
    <b>EXTENDED</b>: Stage 2 but &gt;12% above EMA — hold, don't chase. &nbsp;
    <b>TRIM</b>: Below 200d MA or underperforming SPY by &gt;10% — reduce exposure.
  </p>"""


def build_email(results, sector_map, scan_date, vcp_results=None, portfolio_html="", sector_html="", clusters=None):
    if not results:
        subject = f"RS Scan — No setups found — {scan_date}"
        body    = (f"<html><body style='font-family:Arial'>"
                   f"<h2>RS New High in Base — {scan_date}</h2>"
                   f"<p>No qualifying setups today.</p></body></html>")
        return subject, body

    # Sort by score desc, then verdict (BUY NOW first), then pct_off_52w_high
    verdict_order = {"BUY NOW": 0, "WAIT FOR PULLBACK": 1, "TOO EXTENDED": 2}
    results_sorted = sorted(
        results,
        key=lambda x: (-x["score"],
                       verdict_order.get(x["verdict"], 9),
                       x["pct_off_52w_high"])
    )

    grade_a = [r for r in results_sorted if r["grade"] == "A"]
    grade_b = [r for r in results_sorted if r["grade"] == "B"]
    grade_c = [r for r in results_sorted if r["grade"] == "C"]

    th = """<tr style="background:#1a1a2e;color:white;text-align:left">
      <th>Stock</th><th>Signal</th><th>Grade</th><th>Score</th><th>Signals Present</th>
      <th>Stage</th><th>Short %</th><th>Price</th>
      <th>3m Move</th><th>vs 21d EMA</th><th>vs 50d MA</th>
      <th>Verdict</th><th>Note</th>
    </tr>"""

    # Build cluster warning block (shown near top of email if any sub-industry has 3+ stocks)
    cluster_html = ""
    if clusters:
        items = "".join(
            f'<li><b>{c["subsector"]}</b> ({len(c["tickers"])} stocks): {", ".join(c["tickers"])}</li>'
            for c in clusters
        )
        cluster_html = f"""
        <div style="background:#fff8e1;border-left:4px solid #b8860b;padding:12px 16px;margin:16px 0;border-radius:2px">
          <b style="color:#b8860b;font-size:14px">&#9888; Sub-sector cluster detected</b>
          <p style="color:#555;font-size:13px;margin:6px 0 4px">
            3 or more stocks from the same GICS sub-industry passed today's screen.
            This often signals a sector-level move — treat these as a group, not just individual setups.
          </p>
          <ul style="margin:4px 0;padding-left:20px;font-size:13px;color:#333">{items}</ul>
        </div>"""

    def section(title, color, rows_html, note=""):
        return f"""
        <h3 style="color:{color};margin-top:24px;margin-bottom:4px">{title}</h3>
        {"<p style='color:#555;font-size:13px;margin-top:0'>" + note + "</p>" if note else ""}
        <table border="1" cellpadding="8" cellspacing="0"
               style="border-collapse:collapse;font-size:13px;width:100%">
          {th}
          {"".join(rows_html)}
        </table>"""

    body_parts = []

    if grade_a:
        body_parts.append(section(
            f"Grade A — Highest Conviction ({len(grade_a)} setup{'s' if len(grade_a)>1 else ''})",
            "#1a7a1a",
            [_stock_row(r) for r in grade_a],
            "Has at least two of the three high-conviction signals: tight close cluster, "
            "Stage 1 base, or high short interest. ✦ marks each confirmed signal."
        ))

    if grade_b:
        body_parts.append(section(
            f"Grade B — Good Quality ({len(grade_b)} setup{'s' if len(grade_b)>1 else ''})",
            "#b8860b",
            [_stock_row(r) for r in grade_b],
            "Has one high-conviction signal plus solid existing criteria. Worth watching closely."
        ))

    if grade_c:
        body_parts.append(section(
            f"Grade C — Basic Criteria Only ({len(grade_c)} setup{'s' if len(grade_c)>1 else ''})",
            "#777777",
            [_stock_row(r) for r in grade_c],
            "Passes the RS + tight base filters but does not have a tight close cluster, "
            "Stage 1 base, or meaningful short interest. These are valid setups — the "
            "pattern is there — but historical success rates are lower than the grades above."
        ))

    timing_note = _timing_note(results_sorted)

    body = f"""
<html>
<body style="font-family:Arial,sans-serif;margin:24px;color:#222;max-width:1100px">
  <h2 style="color:#1a1a2e;border-bottom:2px solid #1a1a2e;padding-bottom:6px">
    RS New High in Base — {scan_date}
  </h2>
  <p>
    Stocks outperforming SPY (RS at a new high) while coiling in a tight base,
    ranked by setup quality. ✦ = one of three high-conviction signals confirmed.
  </p>

  {cluster_html}

  {"".join(body_parts)}

  <br>
  <div style="background:#f7f7f7;border-left:4px solid #1a1a2e;padding:14px;margin:16px 0">
    {sector_html}
    <br>
    <b>Today's setups:</b> {timing_note}
  </div>

  <table cellpadding="4" style="font-size:12px;color:#555;border-top:1px solid #ccc">
    <tr><td><b>Tight close cluster ✦</b></td>
        <td>3+ consecutive days closing within 1% of the prior close. Supply has dried up to near-zero.</td></tr>
    <tr><td><b>Stage 1 base ✦</b></td>
        <td>First base after a long flat/decline. O'Neil research: ~70% of big winners broke out of a Stage 1 base.</td></tr>
    <tr><td><b>Short float ✦</b></td>
        <td>≥15% of float sold short. A strong breakout forces short-covering (forced buying), amplifying the move.</td></tr>
    <tr><td><b>vs 21d EMA</b></td>
        <td>Green (≤+5%) = still in the buy zone. Orange = getting stretched. Red (>+15%) = too extended to chase.</td></tr>
    <tr><td><b>Score</b></td>
        <td>0–8 points. OBV rising (+1), U/D vol >1.5x (+1), tight cluster (+2), Stage 1 (+2), short ≥15% (+2).</td></tr>
  </table>

  <p style="color:#aaa;font-size:11px;margin-top:16px">
    Universe: S&P 500 + Nasdaq-100. Data via Yahoo Finance.
  </p>
  {portfolio_html}
  {_vcp_email_section(vcp_results or [])}
  {_russell_email_section()}
</body></html>"""

    a_count   = len(grade_a)
    v_count   = len(vcp_results or [])
    r_data    = _load_russell_results()
    r_count   = len(r_data.get("pullback", [])) + len(r_data.get("momentum", [])) if r_data else 0
    if a_count > 0:
        subject = f"RS Watch: {a_count} Grade-A, {len(results)} total"
    else:
        subject = f"RS Watch: {len(results)} setup{'s' if len(results)>1 else ''}, no Grade-A"
    if v_count > 0:
        tight = sum(1 for r in (vcp_results or []) if r["vcp_label"] == "TIGHT")
        subject += f" | VCP: {v_count} ({tight} TIGHT)"
    if r_count > 0:
        subject += f" | Russell: {r_count} new signal{'s' if r_count>1 else ''}"
    subject += f" — {scan_date}"

    return subject, body


def send_email(subject, body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECIPIENT_EMAIL
    msg.attach(MIMEText(body, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    today = datetime.now()
    if today.weekday() >= 5:
        print(f"Today is {today.strftime('%A')} — no market, skipping.")
        return

    print(f"[{today.strftime('%H:%M:%S')}] RS screener starting...")

    tickers, sector_map, subsector_map = get_tickers()
    if not tickers:
        print("Could not load tickers.")
        return
    print(f"Universe: {len(tickers)} stocks")

    # Load 30-day history before the scan so this run doesn't count as "seen before"
    previously_seen = get_previously_seen(SCREEN_LOG_FILE)

    print("Fetching SPY data...")
    spy_hist = yf.Ticker("SPY").history(period="1y")

    # Phase 1 — fast screen across all tickers
    qualifiers = []
    for i, ticker in enumerate(tickers):
        if i % 100 == 0 and i > 0:
            print(f"  {i}/{len(tickers)} scanned — {len(qualifiers)} qualifiers so far")
        r = check_rs_new_high_in_base(ticker, spy_hist)
        if r:
            qualifiers.append(r)
        time.sleep(0.05)

    print(f"\nPhase 1 done: {len(qualifiers)} stocks passed hard filters.")

    # Phase 2 — enrich qualifiers with base stage, short interest, score
    print("Phase 2: enriching qualifiers with base stage + short interest...")
    results = []
    for r in qualifiers:
        print(f"  Enriching {r['ticker']}...")
        results.append(enrich(r))
        time.sleep(0.1)

    # Tag each result as "New" or "Seen {date}" based on 30-day history
    for r in results:
        t = r["ticker"]
        r["signal_age"] = f"Seen {previously_seen[t]}" if t in previously_seen else "New"

    # Find sub-industry clusters (3+ stocks from same sub-industry)
    result_tickers = [r["ticker"] for r in results]
    clusters = find_subsector_clusters(result_tickers, subsector_map)
    if clusters:
        for c in clusters:
            print(f"  Cluster: {c['subsector']} — {', '.join(c['tickers'])}")

    # Log today's results so tomorrow can check what's new vs repeat
    log_screen_results(result_tickers, SCREEN_LOG_FILE)

    # Phase 3 — VCP scan (separate pass over the same ticker universe)
    print("\nPhase 3: VCP scan...")
    vcp_results = []
    for i, ticker in enumerate(tickers):
        if i % 100 == 0 and i > 0:
            print(f"  {i}/{len(tickers)} scanned — {len(vcp_results)} VCP setups found")
        r = check_vcp(ticker, spy_hist)
        if r:
            vcp_results.append(r)
        time.sleep(0.05)
    print(f"VCP scan done: {len(vcp_results)} setups found.")

    portfolio_html = ""

    print("\nSector heat map...")
    sector_html = _sector_heat_map(spy_hist)

    scan_date = today.strftime("%A, %B %d, %Y")
    subject, body = build_email(results, sector_map, scan_date,
                                vcp_results=vcp_results,
                                portfolio_html=portfolio_html,
                                sector_html=sector_html,
                                clusters=clusters)

    if not SENDER_EMAIL or not SENDER_APP_PASSWORD:
        print("ERROR: email credentials missing from .env")
        return

    print(f"Sending email...")
    send_email(subject, body)
    print(f"Done — {subject}")


if __name__ == "__main__":
    main()
