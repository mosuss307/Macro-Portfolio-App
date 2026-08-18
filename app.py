"""
Rotation & Accumulation Analyzer
Enter any tickers to see all accumulation, distribution, and volume surge signals
plus a composite rating and 4-panel technical chart.

Run: streamlit run app.py
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import warnings
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import rotation_engine
from data import get_etf_holdings
warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Rotation Analyzer",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ──────────────────────────────────────────────────────────────────
# PASSWORD PROTECTION
# Set APP_PASSWORD in Streamlit Cloud → App settings → Secrets.
# Locally: no secrets file = no password required (open access).
# ──────────────────────────────────────────────────────────────────
_required_password = st.secrets.get("APP_PASSWORD", None)

if _required_password:
    if not st.session_state.get("authenticated"):
        st.markdown(
            '<div style="max-width:360px; margin:120px auto 0; text-align:center">'
            '<div style="font-family:Georgia,serif; font-size:1.6rem; color:#E8E2CC; margin-bottom:6px">'
            'Macro Portfolio App</div>'
            '<div style="font-size:0.78rem; color:#5A5640; margin-bottom:28px; letter-spacing:.06em">'
            'FORTUNE CAPITAL FUNDING</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        col_l, col_c, col_r = st.columns([1, 2, 1])
        with col_c:
            pwd = st.text_input("", type="password", placeholder="Enter password", label_visibility="collapsed")
            if pwd:
                if pwd == _required_password:
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("Incorrect password.")
        st.stop()

# ──────────────────────────────────────────────────────────────────
# STYLES — Fortune Capital Funding brand palette
#   Gold  #C49A2A  ·  Green  #4A7C35  ·  Near-black  #0B0E0B
# ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* ── Global app background ── */
  .stApp { background-color: #0B0E0B; }
  .block-container { padding-top: 1.8rem; }

  /* ── Sidebar ── */
  [data-testid="stSidebar"] {
    background: linear-gradient(180deg, #080F08 0%, #0C130C 100%);
    border-right: 1px solid rgba(196,154,42,0.25);
  }
  [data-testid="stSidebar"] hr {
    border-color: rgba(196,154,42,0.2);
  }
  [data-testid="stSidebarContent"] { padding-top: 1.4rem; }

  /* ── Sidebar radio buttons ── */
  [data-testid="stSidebar"] label {
    color: #c8c4b8 !important;
    font-size: 0.88rem;
  }
  [data-testid="stSidebar"] [aria-checked="true"] label {
    color: #C49A2A !important;
    font-weight: 700;
  }

  /* ── Headings — serif, gold accent ── */
  h1 { font-family: Georgia, "Times New Roman", serif !important;
       color: #E8E2CC !important; letter-spacing: -0.01em; }
  h2, h3 { font-family: Georgia, "Times New Roman", serif !important;
            color: #D4C898 !important; }

  /* ── Primary button — gold ── */
  .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #C49A2A 0%, #A87E1E 100%);
    color: #0B0E0B; border: none; font-weight: 700;
    letter-spacing: 0.04em; border-radius: 4px;
  }
  .stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #D4AF37 0%, #C49A2A 100%);
    color: #0B0E0B;
  }
  .stButton > button[kind="secondary"] {
    border: 1px solid rgba(196,154,42,0.35);
    color: #C49A2A;
  }

  /* ── Metric cards ── */
  [data-testid="stMetricValue"] {
    font-family: Georgia, serif;
    color: #E8E2CC !important;
    font-size: 1.5rem !important;
  }
  [data-testid="stMetricLabel"] { color: #7A7660 !important; font-size: 0.72rem !important; letter-spacing: .1em; text-transform: uppercase; }

  /* ── Signal badges ── */
  .sig-yes {
    background: rgba(74,124,53,0.25); color: #6EC247;
    padding: 2px 9px; border-radius: 3px;
    border: 1px solid rgba(74,124,53,0.4);
    font-size: 0.73rem; font-weight: 700; letter-spacing: .05em;
  }
  .sig-no {
    background: rgba(180,50,50,0.2); color: #E06060;
    padding: 2px 9px; border-radius: 3px;
    border: 1px solid rgba(180,50,50,0.35);
    font-size: 0.73rem; font-weight: 700; letter-spacing: .05em;
  }
  .sig-warn {
    background: rgba(196,154,42,0.18); color: #C49A2A;
    padding: 2px 9px; border-radius: 3px;
    border: 1px solid rgba(196,154,42,0.3);
    font-size: 0.73rem; font-weight: 700; letter-spacing: .05em;
  }

  /* ── Signal rows ── */
  .sig-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 5px 0;
    border-bottom: 1px solid rgba(196,154,42,0.08);
    font-size: 0.82rem; color: #A8A490;
  }

  /* ── Eyebrow / section labels ── */
  .eyebrow {
    font-size: 0.60rem; font-weight: 700; letter-spacing: .15em;
    text-transform: uppercase; color: #C49A2A;
    margin-bottom: 7px; margin-top: 2px;
    border-bottom: 1px solid rgba(196,154,42,0.2);
    padding-bottom: 4px;
  }

  /* ── Score pill ── */
  .score-pill {
    display: inline-block; padding: 3px 14px;
    border-radius: 3px; font-size: 0.78rem; font-weight: 700;
    margin-top: 9px; letter-spacing: .03em;
  }

  /* ── Ticker separator ── */
  .ticker-sep {
    border: none;
    border-top: 1px solid rgba(196,154,42,0.15);
    margin: 30px 0 20px 0;
  }

  /* ── Large numbers ── */
  .big-num {
    font-family: Georgia, serif;
    font-size: 1.5rem; font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: #E8E2CC;
  }

  /* ── Signal chip ── */
  .chip-on  { display:inline-block; padding:3px 10px; margin:3px 3px 3px 0;
              background:rgba(74,124,53,0.18); border:1px solid rgba(74,124,53,0.35);
              border-radius:4px; font-size:0.76rem; color:#6EC247; }
  .chip-off { display:inline-block; padding:3px 10px; margin:3px 3px 3px 0;
              background:rgba(255,255,255,0.03); border:1px solid rgba(196,154,42,0.1);
              border-radius:4px; font-size:0.76rem; color:#8A8470; }
  .chip-bad { display:inline-block; padding:3px 10px; margin:3px 3px 3px 0;
              background:rgba(192,57,43,0.18); border:1px solid rgba(192,57,43,0.35);
              border-radius:4px; font-size:0.76rem; color:#E06060; }
  .chip-clear { display:inline-block; padding:3px 10px; margin:3px 3px 3px 0;
                background:rgba(74,124,53,0.06); border:1px solid rgba(74,124,53,0.15);
                border-radius:4px; font-size:0.76rem; color:#4A7C35; }

  /* ── Stat card ── */
  .stat-card {
    background:#0E120E; border:1px solid rgba(196,154,42,0.14);
    border-radius:8px; padding:16px 20px; height:100%;
  }
  .stat-card-label {
    font-size:0.60rem; color:#C49A2A; letter-spacing:.15em;
    text-transform:uppercase; margin-bottom:8px;
    border-bottom:1px solid rgba(196,154,42,0.15); padding-bottom:5px;
  }
  .stat-big {
    font-family:Georgia,serif; font-size:2rem; font-weight:700;
    font-variant-numeric:tabular-nums; line-height:1.1;
  }
  .stat-sub { font-size:0.76rem; color:#8A8470; margin-top:6px; }

  /* ── Expander headers ── */
  [data-testid="stExpander"] summary {
    color: #C8C4A8 !important; font-size: 0.87rem;
  }
  [data-testid="stExpander"] summary:hover { color: #C49A2A !important; }

  /* ── Dataframe ── */
  [data-testid="stDataFrame"] { border: 1px solid rgba(196,154,42,0.15); border-radius: 6px; }

  /* ── Gold divider via st.divider() ── */
  hr { border-color: rgba(196,154,42,0.15) !important; }

  /* ── Tab styling ── */
  [data-testid="stTabs"] [role="tab"] { color: #7A7660; font-size: 0.85rem; }
  [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #C49A2A !important;
    border-bottom-color: #C49A2A !important;
  }

  /* ── Caption / small text ── */
  [data-testid="stCaptionContainer"] { color: #8A8470 !important; }

  /* ── Override Streamlit default blues and widget label greys ── */
  [data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] p,
  [data-testid="stWidgetLabel"] label { color: #A8A490 !important; }
  .stTextInput label, .stSelectbox label,
  .stNumberInput label, .stRadio label { color: #A8A490 !important; }
  [data-testid="stSidebar"] [data-testid="stWidgetLabel"],
  [data-testid="stSidebar"] label { color: #C8C4A8 !important; }
  a, a:visited { color: #C49A2A !important; }
  [data-testid="stDataFrame"] thead th { color: #C49A2A !important; }
  [data-testid="stExpander"] p { color: #B8B49E !important; }
  [data-testid="stExpander"] li { color: #B8B49E !important; }
  [data-testid="stAlert"] { background: rgba(196,154,42,0.07) !important;
                             border-color: rgba(196,154,42,0.25) !important; }
  [data-testid="stMetricDelta"] { color: #8A8470 !important; }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────
# SIGNAL COMPUTATION
# ──────────────────────────────────────────────────────────────────
def compute_obv(c, v):
    """On-Balance Volume: add volume on up days, subtract on down days."""
    obv = [0.0]
    for i in range(1, len(c)):
        if c.iloc[i] > c.iloc[i - 1]:
            obv.append(obv[-1] + float(v.iloc[i]))
        elif c.iloc[i] < c.iloc[i - 1]:
            obv.append(obv[-1] - float(v.iloc[i]))
        else:
            obv.append(obv[-1])
    return pd.Series(obv, index=c.index)


def analyze_ticker(ticker, close_all, volume_all, spy):
    """
    Computes all accumulation, distribution, and volume signals for one ticker.
    Returns a dict with every signal value, or None if data is insufficient.
    """
    if ticker not in close_all.columns:
        return None

    c = close_all[ticker].dropna()
    v = volume_all[ticker].dropna()
    # Align to common dates
    aligned = pd.DataFrame({"c": c, "v": v}).dropna()
    if len(aligned) < 50:
        return None
    c, v = aligned["c"], aligned["v"]

    # Align SPY to same dates as ticker
    spy_a = spy.reindex(c.index).dropna()
    c = c.reindex(spy_a.index).dropna()
    v = v.reindex(c.index).dropna()
    if len(c) < 50:
        return None

    # ── OBV signals ────────────────────────────────────────────────
    obv = compute_obv(c, v)
    obv90 = int(len(obv) >= 90 and float(obv.iloc[-1]) > float(obv.iloc[-90]))
    obv30 = int(len(obv) >= 30 and float(obv.iloc[-1]) > float(obv.iloc[-30]))

    # OBV divergence: price flat/down but OBV rising (smart money buying quietly)
    p30_chg = float((c.iloc[-1] - c.iloc[-30]) / c.iloc[-30] * 100) if len(c) >= 30 else 0
    obv_div = int(p30_chg <= 2.0 and bool(obv30))

    # ── Pace signals ────────────────────────────────────────────────
    # r10 = average daily % move over last 10 days
    # r20 = average daily % move over the 20 days before that (days -30 to -10)
    if len(c) >= 30:
        r10 = float((c.iloc[-1] / c.iloc[-10] - 1)) / 10 * 100
        r20 = float((c.iloc[-10] / c.iloc[-30] - 1)) / 20 * 100
        decel      = int(r20 < -0.05 and r10 > r20)   # selling was faster, now slowing
        sell_accel = int(r10 < -0.03 and r10 < r20)   # selling getting worse
    else:
        decel = 0
        sell_accel = 0

    # ── Relative Strength vs SPY ────────────────────────────────────
    rs = (c / spy_a).dropna()
    rs90 = int(len(rs) >= 90 and float(rs.iloc[-1]) > float(rs.iloc[-90]))
    rs30 = int(len(rs) >= 30 and float(rs.iloc[-1]) > float(rs.iloc[-30]))

    # ── Return metrics ──────────────────────────────────────────────
    ret3m  = float((c.iloc[-1] - c.iloc[-63]) / c.iloc[-63] * 100) if len(c) >= 63 else 0.0
    ret1m  = float((c.iloc[-1] - c.iloc[-21]) / c.iloc[-21] * 100) if len(c) >= 21 else 0.0
    ret10d = float((c.iloc[-1] - c.iloc[-10]) / c.iloc[-10] * 100) if len(c) >= 10 else 0.0
    mom    = int(ret3m > 0)

    # ── Moving averages ──────────────────────────────────────────────
    ma50      = float(c.rolling(50).mean().iloc[-1])
    ma200_val = float(c.rolling(200).mean().iloc[-1]) if len(c) >= 200 else None
    a50       = bool(c.iloc[-1] > ma50)
    a200      = bool(c.iloc[-1] > ma200_val) if ma200_val else False
    phase     = "CONFIRMED" if (a50 and a200) else ("EARLY" if a50 else "ACCUMUL")
    vs50      = float((c.iloc[-1] - ma50) / ma50 * 100)
    vs200     = float((c.iloc[-1] - ma200_val) / ma200_val * 100) if ma200_val else None

    # ── 52-week range ────────────────────────────────────────────────
    window   = min(252, len(c))
    high_52w = float(c.rolling(window).max().iloc[-1])
    low_52w  = float(c.rolling(window).min().iloc[-1])
    near_high = bool(c.iloc[-1] >= 0.95 * high_52w)
    pct_range = (
        float((c.iloc[-1] - low_52w) / (high_52w - low_52w) * 100)
        if high_52w > low_52w else 50.0
    )

    # ── Distribution signals ────────────────────────────────────────
    # Price near 52w high but OBV falling = smart money selling into strength
    dist_div    = int(near_high and not bool(obv30))
    # Was outperforming over 90 days, now underperforming over 30 — momentum fading
    rs_rollover = int(bool(rs90) and not bool(rs30))

    # Down-volume dominance: >60% of last 10 days' volume was on down days
    if len(c) >= 11:
        c10 = c.iloc[-10:]
        v10 = v.iloc[-10:]
        down_vol  = sum(float(v10.iloc[i]) for i in range(1, len(c10)) if c10.iloc[i] < c10.iloc[i - 1])
        total_vol = float(v10.sum())
        down_vol_dom = int(total_vol > 0 and down_vol / total_vol > 0.60)
    else:
        down_vol_dom = 0

    # ── Volume surge (vs pre-surge quiet baseline) ──────────────────
    avg_10 = float(v.iloc[-10:].mean())
    avg_30 = float(v.iloc[-30:].mean())
    avg_60 = float(v.iloc[-60:].mean()) if len(v) >= 60 else avg_10
    # Use days -252 to -90 as the quiet baseline — avoids contaminating
    # the average if the surge started months ago (the FCEL problem).
    old_slice    = v.iloc[-252:-90] if len(v) >= 252 else v.iloc[:-60]
    avg_baseline = float(old_slice.mean()) if len(old_slice) >= 20 else float(v.iloc[-90:].mean())
    surge_10 = round(avg_10 / avg_baseline, 1) if avg_baseline > 0 else 1.0
    surge_30 = round(avg_30 / avg_baseline, 1) if avg_baseline > 0 else 1.0

    # Volume trend: is the surge building, holding, peaked, or fading?
    if avg_10 >= avg_30 * 1.15:
        vol_trend = "RISING"
    elif avg_10 >= avg_60 * 2.0 and avg_30 >= avg_60 * 1.8:
        vol_trend = "SUSTAINED"
    elif avg_30 > avg_60 * 1.5 and avg_10 < avg_30 * 0.75:
        vol_trend = "PEAKED"
    elif surge_10 >= 1.5 or surge_30 >= 1.5:
        vol_trend = "ELEVATED"
    else:
        vol_trend = "NORMAL"

    # ── Composite scores ─────────────────────────────────────────────
    acc_score  = obv90 + obv30 + obv_div + decel + rs90 + rs30 + mom  # 0-7
    dist_count = dist_div + rs_rollover + sell_accel + down_vol_dom    # 0-4

    return {
        "ticker": ticker,
        "price":  round(float(c.iloc[-1]), 2),
        # Returns
        "ret3m":  round(ret3m,  1),
        "ret1m":  round(ret1m,  1),
        "ret10d": round(ret10d, 1),
        # Accumulation signals (each is 0 or 1)
        "obv90":   obv90,
        "obv30":   obv30,
        "obv_div": obv_div,
        "decel":   decel,
        "rs90":    rs90,
        "rs30":    rs30,
        "mom":     mom,
        "acc_score": acc_score,
        # Distribution signals (each is 0 or 1)
        "dist_div":     dist_div,
        "rs_rollover":  rs_rollover,
        "sell_accel":   sell_accel,
        "down_vol_dom": down_vol_dom,
        "dist_count":   dist_count,
        # Volume surge
        "surge_10":   surge_10,
        "surge_30":   surge_30,
        "vol_trend":  vol_trend,
        "baseline_k": int(avg_baseline / 1_000),  # in thousands
        # Price context
        "phase":     phase,
        "vs50":      round(vs50, 1),
        "vs200":     round(vs200, 1) if vs200 is not None else None,
        "ma50":      round(ma50, 2),
        "ma200":     round(ma200_val, 2) if ma200_val else None,
        "pct_range": round(pct_range, 0),
        "high_52w":  round(high_52w, 2),
        "low_52w":   round(low_52w, 2),
        "near_high": near_high,
        # Raw series for charting
        "c":   c,
        "v":   v,
        "obv": obv,
        "rs":  rs,
    }


# ──────────────────────────────────────────────────────────────────
# ETF SIGNAL ENGINE  (price/RS-based — no OBV, no volume)
# ──────────────────────────────────────────────────────────────────
def analyze_etf(ticker, close_all, spy):
    """
    Price and relative-strength signals for a sector ETF.
    ETF volume reflects the wrapper (retail flows, arb), not institutional
    accumulation in the holdings — so we use price action only.
    Returns a signals dict or None if data is insufficient.
    """
    if ticker not in close_all.columns:
        return None

    c = close_all[ticker].dropna()
    if len(c) < 60:
        return None

    spy_a = spy.reindex(c.index).dropna()
    c     = c.reindex(spy_a.index).dropna()
    if len(c) < 60:
        return None

    price = float(c.iloc[-1])

    # ── Returns ────────────────────────────────────────────────────
    ret3m  = float((c.iloc[-1] / c.iloc[-63]  - 1) * 100) if len(c) >= 63  else 0.0
    ret1m  = float((c.iloc[-1] / c.iloc[-21]  - 1) * 100) if len(c) >= 21  else 0.0
    ret10d = float((c.iloc[-1] / c.iloc[-10]  - 1) * 100) if len(c) >= 10  else 0.0
    ret6m  = float((c.iloc[-1] / c.iloc[-126] - 1) * 100) if len(c) >= 126 else 0.0

    # ── Moving averages ────────────────────────────────────────────
    ma50      = float(c.rolling(50).mean().iloc[-1])
    ma200_val = float(c.rolling(200).mean().iloc[-1]) if len(c) >= 200 else None
    above_50d  = price > ma50
    above_200d = price > ma200_val if ma200_val else False
    phase  = ("CONFIRMED" if above_50d and above_200d
              else "EARLY"    if above_50d
              else "DISTRIBUT" if above_200d
              else "DOWNTREND")
    vs50  = (price / ma50  - 1) * 100
    vs200 = (price / ma200_val - 1) * 100 if ma200_val else None

    # ── 52-week range ──────────────────────────────────────────────
    window   = min(252, len(c))
    high_52w = float(c.rolling(window).max().iloc[-1])
    low_52w  = float(c.rolling(window).min().iloc[-1])
    pct_range = (
        (price - low_52w) / (high_52w - low_52w) * 100
        if high_52w > low_52w else 50.0
    )

    # ── Relative strength vs SPY ────────────────────────────────────
    rs = (c / spy_a).dropna()

    rs_3m = bool(len(rs) >= 63  and float(rs.iloc[-1]) > float(rs.iloc[-63]))
    rs_1m = bool(len(rs) >= 21  and float(rs.iloc[-1]) > float(rs.iloc[-21]))
    rs_6m = bool(len(rs) >= 126 and float(rs.iloc[-1]) > float(rs.iloc[-126]))

    # RS improving: 1M rate of change in RS > 3M rate of change
    # Means: outperformance is accelerating → fresh rotation money coming in
    if len(rs) >= 63:
        mom_3m = float(rs.iloc[-1]) / float(rs.iloc[-63]) - 1
        mom_1m = float(rs.iloc[-1]) / float(rs.iloc[-21]) - 1 if len(rs) >= 21 else 0.0
        rs_improving = mom_1m > mom_3m
    else:
        rs_improving = False

    # RS rollover: was outperforming 3M, now lagging 1M — rotation fading
    rs_rollover = rs_3m and not rs_1m

    # ── 7-signal RS score (all price-based) ───────────────────────
    high_pct  = pct_range > 60  # in upper portion of 52w range
    abs_3m_pos = ret3m > 0

    rs_score = sum([
        rs_3m,         # sector outperforming SPY over 3 months
        rs_1m,         # sector outperforming SPY over 1 month
        rs_6m,         # sector outperforming SPY over 6 months
        rs_improving,  # outperformance accelerating (fresh rotation)
        abs_3m_pos,    # absolute gain over 3M (not just less-bad)
        above_50d,     # in near-term uptrend
        above_200d,    # in long-term uptrend
    ])

    # ── Warning flags (0-4, more = more caution) ──────────────────
    flag_rs_rollover  = rs_rollover
    flag_below_50d    = not above_50d
    flag_mom_neg      = ret3m < -5.0   # meaningful absolute decline
    flag_rs_both_neg  = not rs_3m and not rs_1m  # lagging on both timeframes

    flag_count = sum([
        flag_rs_rollover, flag_below_50d, flag_mom_neg, flag_rs_both_neg
    ])

    return {
        "ticker":    ticker,
        "price":     round(price, 2),
        "phase":     phase,
        # Returns
        "ret6m":     round(ret6m,  1),
        "ret3m":     round(ret3m,  1),
        "ret1m":     round(ret1m,  1),
        "ret10d":    round(ret10d, 1),
        # Price context
        "vs50":      round(vs50, 1),
        "vs200":     round(vs200, 1) if vs200 is not None else None,
        "pct_range": round(pct_range, 0),
        "high_52w":  round(high_52w, 2),
        "low_52w":   round(low_52w,  2),
        "above_50d":  above_50d,
        "above_200d": above_200d,
        # RS signals
        "rs_3m":        rs_3m,
        "rs_1m":        rs_1m,
        "rs_6m":        rs_6m,
        "rs_improving": rs_improving,
        "rs_rollover":  rs_rollover,
        "abs_3m_pos":   abs_3m_pos,
        "high_pct":     high_pct,
        # Composite
        "rs_score":   rs_score,
        # Warning flags
        "flag_rs_rollover":  flag_rs_rollover,
        "flag_below_50d":    flag_below_50d,
        "flag_mom_neg":      flag_mom_neg,
        "flag_rs_both_neg":  flag_rs_both_neg,
        "flag_count":        flag_count,
        # Raw series for charting
        "c":  c,
        "rs": rs,
    }


# ──────────────────────────────────────────────────────────────────
# RATING ENGINE
# ──────────────────────────────────────────────────────────────────
def get_rating(s):
    """
    Returns (label, hex_color) based on accumulation score, distribution
    flags, and volume surge.
    """
    acc   = s["acc_score"]
    dist  = s["dist_count"]
    surge = s["surge_10"]

    # Strong distribution overrides accumulation
    if dist >= 3:
        return "DISTRIBUTING", "#C0392B"
    if dist == 2 and s["near_high"]:
        return "DIST-WATCH", "#C06030"

    # Base rating from accumulation score
    if acc >= 6:
        label, color = "STRONG",   "#6EC247"   # brand green light
    elif acc >= 4:
        label, color = "BUILDING", "#4A7C35"   # brand green
    elif acc >= 2:
        label, color = "WATCH",    "#C49A2A"   # brand gold
    elif acc >= 1:
        label, color = "WEAK",     "#C06030"   # amber-red
    else:
        label, color = "BEARISH",  "#C0392B"   # red

    # Distribution modifier
    if dist == 2:
        label += " [CAUTION]"
        color  = "#C06030"
    elif dist == 1 and acc >= 4:
        label += " [WATCH]"

    # Volume surge boost (only meaningful if already accumulating)
    if surge >= 3.0 and acc >= 4:
        label += " +SURGE"

    return label, color


def get_etf_rating(s):
    """
    Rating for ETFs based on price/RS signals.
    Labels match sector-rotation language, not stock accumulation language.
    """
    score = s["rs_score"]
    flags = s["flag_count"]

    # Flag overrides
    if flags >= 3:
        return "EXITING", "#C0392B"
    if s["flag_rs_rollover"] and flags >= 2:
        return "ROTATING OUT", "#C06030"

    if score >= 6:
        return "LEADING",   "#6EC247"
    if score >= 4:
        return "IMPROVING", "#4A7C35"
    if score >= 2:
        return "NEUTRAL",   "#C49A2A"
    if score >= 1:
        return "LAGGING",   "#C06030"
    return "AVOID", "#C0392B"


def get_plain_english_summary(s):
    """
    Writes 2-3 plain-English sentences summarizing the most important signals.
    """
    parts = []

    # Phase / MA context
    if s["phase"] == "CONFIRMED":
        parts.append(
            f"{s['ticker']} is in an uptrend — trading above both its 50-day and 200-day moving averages."
        )
    elif s["phase"] == "EARLY":
        parts.append(
            f"{s['ticker']} is above its 50-day average but still below the 200-day, "
            "suggesting an early-stage recovery."
        )
    else:
        parts.append(
            f"{s['ticker']} is below both its 50-day and 200-day averages — "
            "it's in a downtrend or early accumulation phase."
        )

    # Accumulation summary
    if s["acc_score"] >= 5:
        extras = []
        if s["obv90"] and s["obv30"]:
            extras.append("OBV has been rising steadily")
        if s["rs90"]:
            extras.append("the stock is outperforming the S&P 500")
        if s["obv_div"]:
            extras.append("OBV is diverging positively from price")
        extra_str = (", " + ", ".join(extras)) if extras else ""
        parts.append(
            f"Accumulation signals are strong ({s['acc_score']}/7){extra_str} — "
            "indicating sustained institutional buying."
        )
    elif s["acc_score"] >= 3:
        parts.append(
            f"Some accumulation is present ({s['acc_score']}/7) but conviction is mixed "
            "— not all signals align yet."
        )
    else:
        parts.append(
            f"Accumulation is weak ({s['acc_score']}/7) — the stock is not showing "
            "signs of institutional buying."
        )

    # Distribution warnings
    if s["dist_count"] >= 3:
        flags = []
        if s["dist_div"]:
            flags.append("price is near its 52-week high but OBV is falling (smart money selling into strength)")
        if s["rs_rollover"]:
            flags.append("the relative-strength line is rolling over")
        if s["sell_accel"]:
            flags.append("selling is accelerating")
        parts.append(
            "Warning: multiple distribution signals are active — "
            + (", ".join(flags) if flags else "multiple flags triggered")
            + ". This is a caution sign after a big run."
        )
    elif s["dist_count"] == 2:
        parts.append(
            "Two distribution flags are active — watch closely for a possible trend change."
        )
    elif s["dist_count"] == 1:
        parts.append("One mild distribution signal detected — worth monitoring but not alarming on its own.")

    # Volume surge
    if s["surge_10"] >= 3.0:
        trend_desc = {
            "RISING": "still accelerating",
            "SUSTAINED": "holding at elevated levels",
            "PEAKED": "starting to fade",
            "ELEVATED": "above normal",
        }.get(s["vol_trend"], "elevated")
        flat_note = " Flat price + rising volume often precedes a breakout." if abs(s["ret3m"]) < 8 else ""
        parts.append(
            f"Volume is surging at {s['surge_10']:.1f}x the pre-surge baseline "
            f"and the trend is {trend_desc}.{flat_note}"
        )

    return " ".join(parts)


# ──────────────────────────────────────────────────────────────────
# CHART
# ──────────────────────────────────────────────────────────────────
def build_chart(s):
    """4-panel Plotly chart: price + MAs, volume bars, OBV, RS vs SPY."""
    c   = s["c"]
    v   = s["v"]
    obv = s["obv"]
    rs  = s["rs"]

    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        row_heights=[0.44, 0.18, 0.19, 0.19],
        vertical_spacing=0.015,
        subplot_titles=[
            "Price + Moving Averages", "Volume",
            "OBV (On-Balance Volume)", "Relative Strength vs SPY",
        ],
    )

    # Brand palette constants
    GOLD       = "#C49A2A"
    GREEN      = "#4A7C35"
    GREEN_LT   = "#6EC247"
    CREAM      = "#E0DAC0"
    RED        = "#C0392B"
    PLOT_BG    = "#080E08"
    GRID       = "rgba(196,154,42,0.07)"

    # Row 1: Price (cream) + 50d MA (gold) + 200d MA (green)
    fig.add_trace(go.Scatter(
        x=c.index, y=c.values, name="Price",
        line=dict(color=CREAM, width=2)
    ), row=1, col=1)

    ma50_line = c.rolling(50).mean()
    fig.add_trace(go.Scatter(
        x=ma50_line.index, y=ma50_line.values, name="50d MA",
        line=dict(color=GOLD, width=1.5, dash="dot")
    ), row=1, col=1)

    if len(c) >= 200:
        ma200_line = c.rolling(200).mean()
        fig.add_trace(go.Scatter(
            x=ma200_line.index, y=ma200_line.values, name="200d MA",
            line=dict(color=GREEN_LT, width=1.5, dash="dash")
        ), row=1, col=1)

    # Row 2: Volume bars — brand green on up days, red on down days
    c_vals = c.values
    bar_colors = []
    for i in range(len(c_vals)):
        if i == 0 or c_vals[i] >= c_vals[i - 1]:
            bar_colors.append("rgba(74,124,53,0.65)")
        else:
            bar_colors.append("rgba(192,57,43,0.60)")

    fig.add_trace(go.Bar(
        x=v.index, y=v.values, name="Volume",
        marker_color=bar_colors, showlegend=False,
    ), row=2, col=1)

    # Row 3: OBV — brand green if rising, red if falling
    obv_rising = float(obv.iloc[-1]) > float(obv.iloc[-30 if len(obv) >= 30 else 0])
    obv_color  = GREEN_LT if obv_rising else "#E06060"
    fill_color = "rgba(74,124,53,0.10)" if obv_rising else "rgba(192,57,43,0.08)"
    fig.add_trace(go.Scatter(
        x=obv.index, y=obv.values, name="OBV",
        line=dict(color=obv_color, width=1.5),
        fill="tozeroy", fillcolor=fill_color,
    ), row=3, col=1)

    # Row 4: RS vs SPY — gold if outperforming, muted red if lagging
    rs_leading = len(rs) >= 90 and float(rs.iloc[-1]) > float(rs.iloc[-90])
    rs_color   = GOLD if rs_leading else "#C06030"
    fig.add_trace(go.Scatter(
        x=rs.index, y=rs.values, name="RS vs SPY",
        line=dict(color=rs_color, width=1.5),
        fill="tozeroy", fillcolor="rgba(196,154,42,0.07)",
    ), row=4, col=1)

    # Layout
    fig.update_layout(
        height=640,
        plot_bgcolor=PLOT_BG,
        paper_bgcolor=PLOT_BG,
        font=dict(color="#7A7660", size=11, family="Georgia, serif"),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            bgcolor="rgba(0,0,0,0)", font=dict(size=11),
        ),
        margin=dict(l=8, r=8, t=28, b=8),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="#1A1E1A",
            bordercolor=GOLD,
            font=dict(color=CREAM, size=11),
        ),
    )
    for r in range(1, 5):
        fig.update_xaxes(gridcolor=GRID, row=r, col=1, tickfont=dict(color="#5A5640"))
        fig.update_yaxes(gridcolor=GRID, row=r, col=1, tickfont=dict(size=10, color="#5A5640"))
    for r in [1, 2, 3]:
        fig.update_xaxes(showticklabels=False, row=r, col=1)

    return fig


def build_etf_chart(s):
    """
    3-panel chart for ETFs: price+MAs, RS vs SPY line, RS momentum bars.
    Replaces volume/OBV panels — those signals don't apply to ETF wrappers.
    """
    c  = s["c"]
    rs = s["rs"]

    PLOT_BG  = "#0C100C"
    GRID     = "rgba(196,154,42,0.07)"
    CREAM    = "#E8E2CC"
    GOLD     = "#C49A2A"
    GREEN_LT = "#6EC247"

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.52, 0.32, 0.16],
        vertical_spacing=0.03,
        subplot_titles=["Price", "RS vs SPY", "RS Momentum (21d)"],
    )

    # Panel 1: Price + 50d + 200d MAs
    fig.add_trace(go.Scatter(
        x=c.index, y=c.values, name="Price",
        line=dict(color=CREAM, width=2)
    ), row=1, col=1)

    ma50_line = c.rolling(50).mean()
    fig.add_trace(go.Scatter(
        x=ma50_line.index, y=ma50_line.values, name="50d MA",
        line=dict(color=GOLD, width=1.5, dash="dot")
    ), row=1, col=1)

    if len(c) >= 200:
        ma200_line = c.rolling(200).mean()
        fig.add_trace(go.Scatter(
            x=ma200_line.index, y=ma200_line.values, name="200d MA",
            line=dict(color=GREEN_LT, width=1.5, dash="dash")
        ), row=1, col=1)

    # Panel 2: RS vs SPY — the primary ETF signal
    rs_leading = len(rs) >= 63 and float(rs.iloc[-1]) > float(rs.iloc[-63])
    rs_color   = GREEN_LT if rs_leading else "#C06030"
    fill_color = "rgba(74,124,53,0.09)" if rs_leading else "rgba(192,57,43,0.08)"
    fig.add_trace(go.Scatter(
        x=rs.index, y=rs.values, name="RS vs SPY",
        line=dict(color=rs_color, width=2),
        fill="tozeroy", fillcolor=fill_color,
    ), row=2, col=1)

    # Panel 3: RS momentum — 21-day rate of change of the RS line
    # Positive = RS improving (more outperformance); negative = RS fading
    rs_mom = rs.pct_change(21) * 100
    mom_colors = [
        "rgba(74,124,53,0.70)" if (v is not None and v >= 0) else "rgba(192,57,43,0.60)"
        for v in rs_mom.fillna(0)
    ]
    fig.add_trace(go.Bar(
        x=rs_mom.index, y=rs_mom.values, name="RS Mom",
        marker_color=mom_colors, showlegend=False,
    ), row=3, col=1)

    fig.update_layout(
        height=560,
        plot_bgcolor=PLOT_BG,
        paper_bgcolor=PLOT_BG,
        font=dict(color="#7A7660", size=11, family="Georgia, serif"),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            bgcolor="rgba(0,0,0,0)", font=dict(size=11),
        ),
        margin=dict(l=8, r=8, t=28, b=8),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#1A1E1A", bordercolor=GOLD, font=dict(color=CREAM, size=11)),
    )
    for r in range(1, 4):
        fig.update_xaxes(gridcolor=GRID, row=r, col=1, tickfont=dict(color="#5A5640"))
        fig.update_yaxes(gridcolor=GRID, row=r, col=1, tickfont=dict(size=10, color="#5A5640"))
    for r in [1, 2]:
        fig.update_xaxes(showticklabels=False, row=r, col=1)
    fig.add_hline(y=0, line_color="rgba(196,154,42,0.25)", line_width=1, row=3, col=1)

    return fig


# ──────────────────────────────────────────────────────────────────
# RENDER ONE TICKER CARD
# ──────────────────────────────────────────────────────────────────
def render_ticker(s):
    """Renders the full analysis card for one ticker — chart-first layout."""
    rating_label, rating_color = get_rating(s)

    st.markdown("<hr class='ticker-sep'>", unsafe_allow_html=True)

    # ── Header bar ────────────────────────────────────────────────
    phase_colors  = {"CONFIRMED": "#6EC247", "EARLY": "#C49A2A", "ACCUMUL": "#7A7660"}
    ph_color      = phase_colors[s["phase"]]
    acc_score     = s["acc_score"]
    dist_count    = s["dist_count"]
    acc_meter_on  = "#6EC247" if acc_score >= 5 else ("#C49A2A" if acc_score >= 3 else "#E06060")
    acc_meter_bar = "&#9608;" * acc_score + '<span style="color:#2A2E2A">' + "&#9608;" * (7 - acc_score) + "</span>"

    st.markdown(f"""
    <div style="display:flex; align-items:center; justify-content:space-between;
                padding:14px 22px; background:#0D110D;
                border:1px solid rgba(196,154,42,0.18); border-radius:8px; margin-bottom:10px">
      <div style="display:flex; align-items:center; gap:20px">
        <div>
          <div style="font-family:Georgia,serif; font-size:1.9rem; font-weight:700;
                      color:#E8E2CC; letter-spacing:-0.01em; line-height:1.1">{s["ticker"]}</div>
          <div style="font-size:1.05rem; color:#A8A490; font-variant-numeric:tabular-nums;
                      margin-top:1px">
            ${s["price"]:,.2f}
            <span style="font-size:0.73rem; color:{ph_color}; font-weight:700;
                         letter-spacing:0.07em; margin-left:8px">&#9679; {s["phase"]}</span>
          </div>
        </div>
      </div>
      <div style="text-align:right">
        <div style="font-family:Georgia,serif; font-size:1.7rem; font-weight:700;
                    color:{rating_color}; line-height:1.1">{rating_label}</div>
        <div style="font-size:0.70rem; color:#8A8470; letter-spacing:0.08em;
                    text-transform:uppercase; margin-top:3px">
          Acc <span style="color:{acc_meter_on}">{acc_score}/7</span>
          &nbsp;&middot;&nbsp;
          Dist <span style="color:{"#E06060" if dist_count >= 2 else ("#C49A2A" if dist_count == 1 else "#6EC247")}">{dist_count}/4</span>
          &nbsp;&middot;&nbsp;
          Surge <span style="color:{"#6EC247" if s["surge_10"] >= 2.5 else "#5A5640"}">{s["surge_10"]:.1f}x</span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Returns strip ─────────────────────────────────────────────
    def mini_card(label, val, suffix="%", is_pct=False):
        if is_pct:
            c = "#6EC247" if val > 70 else ("#C49A2A" if val > 40 else "#E06060")
            formatted = f"{val:.0f}<span style='font-size:0.75rem'>th</span>"
        else:
            c = "#6EC247" if val > 0 else "#E06060"
            formatted = f"{val:+.1f}{suffix}"
        return (f'<div style="flex:1; text-align:center; padding:8px 12px; background:#0E120E; '
                f'border:1px solid rgba(196,154,42,0.10); border-radius:6px">'
                f'<div style="font-size:0.58rem; color:#8A8470; letter-spacing:.13em; '
                f'text-transform:uppercase; margin-bottom:3px">{label}</div>'
                f'<div style="font-family:Georgia,serif; font-size:1.05rem; font-weight:700; '
                f'color:{c}; font-variant-numeric:tabular-nums">{formatted}</div></div>')

    vs200_val  = s["vs200"] if s["vs200"] is not None else 0.0
    vs200_html = mini_card("vs 200d", vs200_val) if s["vs200"] is not None else (
        f'<div style="flex:1; text-align:center; padding:8px 12px; background:#0E120E; '
        f'border:1px solid rgba(196,154,42,0.10); border-radius:6px">'
        f'<div style="font-size:0.58rem; color:#8A8470; letter-spacing:.13em; '
        f'text-transform:uppercase; margin-bottom:3px">vs 200d</div>'
        f'<div style="font-size:0.85rem; color:#7A7660">N/A</div></div>'
    )

    st.markdown(f"""
    <div style="display:flex; gap:6px; margin-bottom:14px">
      {mini_card("3-Month", s["ret3m"])}
      {mini_card("1-Month", s["ret1m"])}
      {mini_card("10-Day",  s["ret10d"])}
      {mini_card("vs 50d",  s["vs50"])}
      {vs200_html}
      {mini_card("52w Range", s["pct_range"], is_pct=True)}
      <div style="flex:1; text-align:center; padding:8px 12px; background:#0E120E;
                  border:1px solid rgba(196,154,42,0.10); border-radius:6px">
        <div style="font-size:0.58rem; color:#8A8470; letter-spacing:.13em;
                    text-transform:uppercase; margin-bottom:3px">52w High</div>
        <div style="font-family:Georgia,serif; font-size:1.05rem; font-weight:700;
                    color:#A8A490; font-variant-numeric:tabular-nums">${s["high_52w"]:,.2f}</div>
      </div>
      <div style="flex:1; text-align:center; padding:8px 12px; background:#0E120E;
                  border:1px solid rgba(196,154,42,0.10); border-radius:6px">
        <div style="font-size:0.58rem; color:#8A8470; letter-spacing:.13em;
                    text-transform:uppercase; margin-bottom:3px">52w Low</div>
        <div style="font-family:Georgia,serif; font-size:1.05rem; font-weight:700;
                    color:#A8A490; font-variant-numeric:tabular-nums">${s["low_52w"]:,.2f}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Chart (hero — moved to top) ───────────────────────────────
    st.plotly_chart(build_chart(s), use_container_width=True)

    # ── Signal + score cards ──────────────────────────────────────
    col_acc, col_dist, col_vol = st.columns([2, 2, 1.4])

    def chip(label, active, positive=True):
        if active and positive:
            return f'<span class="chip-on">&#9679; {label}</span>'
        elif not active and positive:
            return f'<span class="chip-off">&#9675; {label}</span>'
        elif active and not positive:
            return f'<span class="chip-bad">&#9679; {label}</span>'
        else:
            return f'<span class="chip-clear">&#9675; {label}</span>'

    # Accumulation card
    with col_acc:
        meter_color = "#6EC247" if acc_score >= 5 else ("#C49A2A" if acc_score >= 3 else "#E06060")
        filled      = "&#9608;" * acc_score
        empty       = '<span style="color:#1E231E">&#9608;</span>' * (7 - acc_score)
        st.markdown(f"""
        <div class="stat-card">
          <div class="stat-card-label">Accumulation Score</div>
          <div style="display:flex; align-items:baseline; gap:6px; margin-bottom:8px">
            <span class="stat-big" style="color:{meter_color}">{acc_score}</span>
            <span style="color:#7A7660; font-size:1.2rem">/7</span>
          </div>
          <div style="font-size:1.2rem; color:{meter_color}; letter-spacing:2px;
                      font-family:monospace; margin-bottom:12px">{filled}{empty}</div>
          <div>
            {chip("OBV 90d",       s["obv90"])}
            {chip("OBV 30d",       s["obv30"])}
            {chip("OBV Divergence",s["obv_div"])}
            {chip("Sell Decel",    s["decel"])}
            {chip("RS vs SPY 90d", s["rs90"])}
            {chip("RS vs SPY 30d", s["rs30"])}
            {chip("3M Momentum",   s["mom"])}
          </div>
        </div>
        """, unsafe_allow_html=True)

    # Distribution card
    with col_dist:
        dist_color = "#E06060" if dist_count >= 2 else ("#C49A2A" if dist_count == 1 else "#6EC247")
        flag_dots  = '<span style="color:#E06060">&#9679;</span> ' * dist_count + \
                     '<span style="color:#1E231E">&#9679;</span> ' * (4 - dist_count)
        st.markdown(f"""
        <div class="stat-card">
          <div class="stat-card-label">Distribution Flags</div>
          <div style="display:flex; align-items:baseline; gap:6px; margin-bottom:8px">
            <span class="stat-big" style="color:{dist_color}">{dist_count}</span>
            <span style="color:#7A7660; font-size:1.2rem">/4</span>
          </div>
          <div style="font-size:1.4rem; letter-spacing:6px; margin-bottom:12px">{flag_dots}</div>
          <div>
            {chip("Near High + OBV Fall", s["dist_div"],     positive=False)}
            {chip("RS Rollover",          s["rs_rollover"],  positive=False)}
            {chip("Selling Accelerating", s["sell_accel"],   positive=False)}
            {chip("Down-Vol Dominance",   s["down_vol_dom"], positive=False)}
          </div>
        </div>
        """, unsafe_allow_html=True)

    # Volume surge card
    with col_vol:
        surge_color = "#6EC247" if s["surge_10"] >= 2.5 else ("#C49A2A" if s["surge_10"] >= 1.5 else "#5A5640")
        trend_colors = {"RISING":"#6EC247","SUSTAINED":"#4A7C35","ELEVATED":"#C49A2A","PEAKED":"#C06030","NORMAL":"#5A5640"}
        t_color      = trend_colors.get(s["vol_trend"], "#5A5640")
        st.markdown(f"""
        <div class="stat-card">
          <div class="stat-card-label">Volume Surge</div>
          <div style="display:flex; align-items:baseline; gap:4px; margin-bottom:6px">
            <span class="stat-big" style="color:{surge_color}">{s["surge_10"]:.1f}</span>
            <span style="color:#7A7660; font-size:1.1rem">x</span>
          </div>
          <div style="font-size:0.78rem; font-weight:700; color:{t_color};
                      letter-spacing:0.1em; margin-bottom:14px">{s["vol_trend"]}</div>
          <div style="font-size:0.75rem; color:#8A8470; line-height:1.9">
            <span style="color:#7A7660">30d</span> &nbsp;{s["surge_30"]:.1f}x<br>
            <span style="color:#7A7660">Base</span> &nbsp;{s["baseline_k"]:,}K/day
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom:12px'></div>", unsafe_allow_html=True)


def render_etf_deep_dive(s):
    """Deep-dive card for one ETF — price/RS signals, ETF-specific chart."""
    rating_label, rating_color = get_etf_rating(s)

    st.markdown("<hr class='ticker-sep'>", unsafe_allow_html=True)

    # ── Header ────────────────────────────────────────────────────
    phase_colors = {"CONFIRMED": "#6EC247", "EARLY": "#C49A2A", "DISTRIBUT": "#E06060", "DOWNTREND": "#C0392B"}
    ph_color  = phase_colors.get(s["phase"], "#7A7660")
    score     = s["rs_score"]
    flags     = s["flag_count"]
    sc_color  = "#6EC247" if score >= 5 else ("#C49A2A" if score >= 3 else "#E06060")
    fl_color  = "#E06060" if flags >= 2 else ("#C49A2A" if flags == 1 else "#6EC247")

    st.markdown(f"""
    <div style="display:flex; align-items:center; justify-content:space-between;
                padding:14px 22px; background:#0D110D;
                border:1px solid rgba(196,154,42,0.18); border-radius:8px; margin-bottom:10px">
      <div>
        <div style="font-family:Georgia,serif; font-size:1.9rem; font-weight:700;
                    color:#E8E2CC; letter-spacing:-0.01em; line-height:1.1">{s["ticker"]}</div>
        <div style="font-size:1.05rem; color:#A8A490; font-variant-numeric:tabular-nums; margin-top:1px">
          ${s["price"]:,.2f}
          <span style="font-size:0.73rem; color:{ph_color}; font-weight:700;
                       letter-spacing:0.07em; margin-left:8px">&#9679; {s["phase"]}</span>
        </div>
      </div>
      <div style="text-align:right">
        <div style="font-family:Georgia,serif; font-size:1.7rem; font-weight:700;
                    color:{rating_color}; line-height:1.1">{rating_label}</div>
        <div style="font-size:0.70rem; color:#8A8470; letter-spacing:0.08em;
                    text-transform:uppercase; margin-top:3px">
          RS Score <span style="color:{sc_color}">{score}/7</span>
          &nbsp;&middot;&nbsp;
          Flags <span style="color:{fl_color}">{flags}/4</span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Returns strip ─────────────────────────────────────────────
    def mini_card(label, val, is_pct=False):
        if is_pct:
            c_col = "#6EC247" if val > 70 else ("#C49A2A" if val > 40 else "#E06060")
            fmtd  = f"{val:.0f}<span style='font-size:0.75rem'>th</span>"
        else:
            c_col = "#6EC247" if val > 0 else "#E06060"
            fmtd  = f"{val:+.1f}%"
        return (f'<div style="flex:1; text-align:center; padding:8px 12px; background:#0E120E; '
                f'border:1px solid rgba(196,154,42,0.10); border-radius:6px">'
                f'<div style="font-size:0.58rem; color:#8A8470; letter-spacing:.13em; '
                f'text-transform:uppercase; margin-bottom:3px">{label}</div>'
                f'<div style="font-family:Georgia,serif; font-size:1.05rem; font-weight:700; '
                f'color:{c_col}; font-variant-numeric:tabular-nums">{fmtd}</div></div>')

    vs200_html = mini_card("vs 200d", s["vs200"]) if s["vs200"] is not None else (
        '<div style="flex:1; text-align:center; padding:8px 12px; background:#0E120E; '
        'border:1px solid rgba(196,154,42,0.10); border-radius:6px">'
        '<div style="font-size:0.58rem; color:#8A8470; letter-spacing:.13em; '
        'text-transform:uppercase; margin-bottom:3px">vs 200d</div>'
        '<div style="font-size:0.85rem; color:#7A7660">N/A</div></div>'
    )

    st.markdown(f"""
    <div style="display:flex; gap:6px; margin-bottom:14px">
      {mini_card("1-Month", s["ret1m"])}
      {mini_card("3-Month", s["ret3m"])}
      {mini_card("6-Month", s["ret6m"])}
      {mini_card("10-Day",  s["ret10d"])}
      {mini_card("vs 50d",  s["vs50"])}
      {vs200_html}
      {mini_card("52w Range", s["pct_range"], is_pct=True)}
    </div>
    """, unsafe_allow_html=True)

    # ── Chart ─────────────────────────────────────────────────────
    st.plotly_chart(build_etf_chart(s), use_container_width=True)

    # ── Signal cards ──────────────────────────────────────────────
    col_rs, col_flags, col_ctx = st.columns([2, 2, 1.4])

    def chip(label, active, positive=True):
        if active and positive:
            return f'<span class="chip-on">&#9679; {label}</span>'
        elif not active and positive:
            return f'<span class="chip-off">&#9675; {label}</span>'
        elif active and not positive:
            return f'<span class="chip-bad">&#9679; {label}</span>'
        else:
            return f'<span class="chip-clear">&#9675; {label}</span>'

    with col_rs:
        filled = "&#9608;" * score
        empty  = '<span style="color:#1E231E">&#9608;</span>' * (7 - score)
        st.markdown(f"""
        <div class="stat-card">
          <div class="stat-card-label">RS Score</div>
          <div style="display:flex; align-items:baseline; gap:6px; margin-bottom:8px">
            <span class="stat-big" style="color:{sc_color}">{score}</span>
            <span style="color:#7A7660; font-size:1.2rem">/7</span>
          </div>
          <div style="font-size:1.2rem; color:{sc_color}; letter-spacing:2px;
                      font-family:monospace; margin-bottom:12px">{filled}{empty}</div>
          <div>
            {chip("RS vs SPY 3M",        s["rs_3m"])}
            {chip("RS vs SPY 1M",        s["rs_1m"])}
            {chip("RS vs SPY 6M",        s["rs_6m"])}
            {chip("RS Accelerating",     s["rs_improving"])}
            {chip("3M Return Positive",  s["abs_3m_pos"])}
            {chip("Above 50d MA",        s["above_50d"])}
            {chip("Above 200d MA",       s["above_200d"])}
          </div>
        </div>
        """, unsafe_allow_html=True)

    with col_flags:
        flag_dots = (
            '<span style="color:#E06060">&#9679;</span> ' * flags +
            '<span style="color:#1E231E">&#9679;</span> ' * (4 - flags)
        )
        st.markdown(f"""
        <div class="stat-card">
          <div class="stat-card-label">Warning Flags</div>
          <div style="display:flex; align-items:baseline; gap:6px; margin-bottom:8px">
            <span class="stat-big" style="color:{fl_color}">{flags}</span>
            <span style="color:#7A7660; font-size:1.2rem">/4</span>
          </div>
          <div style="font-size:1.4rem; letter-spacing:6px; margin-bottom:12px">{flag_dots}</div>
          <div>
            {chip("RS Rollover",       s["flag_rs_rollover"],  positive=False)}
            {chip("Below 50d MA",      s["flag_below_50d"],    positive=False)}
            {chip("3M Return &lt;-5%", s["flag_mom_neg"],      positive=False)}
            {chip("Lagging Both TF",   s["flag_rs_both_neg"],  positive=False)}
          </div>
        </div>
        """, unsafe_allow_html=True)

    with col_ctx:
        vs50_c  = "#6EC247" if s["vs50"] > 0 else "#E06060"
        ret3_c  = "#6EC247" if s["ret3m"] > 0 else "#E06060"
        pct_c   = "#6EC247" if s["pct_range"] > 70 else ("#C49A2A" if s["pct_range"] > 40 else "#E06060")
        st.markdown(f"""
        <div class="stat-card">
          <div class="stat-card-label">Price Context</div>
          <div style="font-size:0.76rem; color:#8A8470; line-height:2.2; margin-top:4px">
            <span style="color:#7A7660">vs 50d</span> &nbsp;
            <span style="color:{vs50_c}; font-weight:700">{s["vs50"]:+.1f}%</span><br>
            <span style="color:#7A7660">3M ret</span> &nbsp;
            <span style="color:{ret3_c}; font-weight:700">{s["ret3m"]:+.1f}%</span><br>
            <span style="color:#7A7660">52w high</span> &nbsp;
            <span style="color:#A8A490">${s["high_52w"]:,.2f}</span><br>
            <span style="color:#7A7660">52w low</span> &nbsp;
            <span style="color:#A8A490">${s["low_52w"]:,.2f}</span><br>
            <span style="color:#7A7660">52w %ile</span> &nbsp;
            <span style="color:{pct_c}">{s["pct_range"]:.0f}th</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Holdings ──────────────────────────────────────────────────
    with st.expander(f"Top Holdings — {s['ticker']}"):
        holdings = get_etf_holdings(s["ticker"])
        if holdings is not None and not holdings.empty:
            df = holdings.copy()
            # Normalize: find the weight column regardless of exact name
            weight_col = next((c for c in df.columns if "percent" in c.lower() or "weight" in c.lower()), None)
            if weight_col:
                df = df[[weight_col]].copy()
                df.columns = ["Weight"]
                df["Weight"] = df["Weight"].apply(lambda x: f"{float(x)*100:.2f}%")
            df.index.name = "Holding"
            st.dataframe(df, use_container_width=True)
        else:
            st.caption("Holdings data not available for this ETF.")

    st.markdown("<div style='margin-bottom:12px'></div>", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────
# ETF UNIVERSE  (ticker -> (name, category))
# ──────────────────────────────────────────────────────────────────
ETF_UNIVERSE = {
    # Broad sectors — SPDR
    "XLK":  ("Technology",            "Broad Sector"),
    "XLF":  ("Financials",            "Broad Sector"),
    "XLV":  ("Health Care",           "Broad Sector"),
    "XLE":  ("Energy",                "Broad Sector"),
    "XLI":  ("Industrials",           "Broad Sector"),
    "XLC":  ("Comm Services",         "Broad Sector"),
    "XLY":  ("Cons Discretionary",    "Broad Sector"),
    "XLP":  ("Cons Staples",          "Broad Sector"),
    "XLU":  ("Utilities",             "Broad Sector"),
    "XLRE": ("Real Estate",           "Broad Sector"),
    "XLB":  ("Materials",             "Broad Sector"),
    # Broad sectors — Vanguard
    "VGT":  ("Info Technology",       "Broad Sector"),
    "VNQ":  ("Real Estate",           "Broad Sector"),
    "VHT":  ("Health Care",           "Broad Sector"),
    # Technology sub-sectors
    "SOXX": ("Semiconductors",        "Technology"),
    "SMH":  ("Semiconductors",        "Technology"),
    "DRAM": ("Memory Chips",          "Technology"),
    "IGV":  ("Software",              "Technology"),
    "CIBR": ("Cybersecurity",         "Technology"),
    "SKYY": ("Cloud Computing",       "Technology"),
    "BOTZ": ("Robotics & AI",         "Technology"),
    "FDN":  ("Internet",              "Technology"),
    "AIQ":  ("AI & Big Data",         "Technology"),
    "DTCR": ("Data Centers",          "Technology"),
    # Health Care sub-sectors
    "XBI":  ("Biotech",               "Health Care"),
    "IBB":  ("Biotech Large Cap",     "Health Care"),
    "IHI":  ("Medical Devices",       "Health Care"),
    "IHF":  ("Healthcare Providers",  "Health Care"),
    "PJP":  ("Pharmaceuticals",       "Health Care"),
    "ARKG": ("Genomic Revolution",    "Health Care"),
    # Financials sub-sectors
    "KRE":  ("Regional Banks",        "Financials"),
    "KBE":  ("Banks",                 "Financials"),
    "IAI":  ("Investment Brokers",    "Financials"),
    "FINX": ("Fintech",               "Financials"),
    "BIZD": ("BDC Income",            "Financials"),
    # Energy sub-sectors
    "XOP":  ("Oil & Gas E&P",         "Energy"),
    "OIH":  ("Oil Services",          "Energy"),
    "ICLN": ("Clean Energy",          "Energy"),
    "AMLP": ("Midstream Pipelines",   "Energy"),
    "TAN":  ("Solar",                 "Energy"),
    "URA":  ("Uranium",               "Energy"),
    # Industrials sub-sectors
    "ITA":  ("Aerospace & Defense",   "Industrials"),
    "IYT":  ("Transportation",        "Industrials"),
    "JETS": ("Airlines",              "Industrials"),
    "ITB":  ("Homebuilders",          "Industrials"),
    "PAVE": ("Infrastructure",        "Industrials"),
    # Materials sub-sectors
    "GDX":  ("Gold Miners",           "Materials"),
    "MOO":  ("Agribusiness",          "Materials"),
    "SLX":  ("Steel",                 "Materials"),
    "LIT":  ("Lithium & Battery",     "Materials"),
    "COPX": ("Copper Miners",         "Materials"),
    "REMX": ("Rare Earth Metals",     "Materials"),
    # Consumer sub-sectors
    "XRT":  ("Retail",                "Consumer"),
    "PEJ":  ("Hotels/Restaurants",    "Consumer"),
    "AWAY": ("Travel Tech",           "Consumer"),
    "IBUY": ("E-Commerce",            "Consumer"),
    "BETZ": ("Sports Betting",        "Consumer"),
    # Utilities sub-sectors
    "PHO":  ("Water Utilities",       "Utilities"),
}


# ──────────────────────────────────────────────────────────────────
# NAVIGATION
# ──────────────────────────────────────────────────────────────────
st.sidebar.markdown(
    '<div style="padding:0 4px 12px 4px">'
    '<div style="font-family:Georgia,serif; font-size:1.05rem; font-weight:700; '
    'color:#C49A2A; letter-spacing:0.04em">FORTUNE CAPITAL</div>'
    '<div style="font-size:0.65rem; letter-spacing:0.18em; color:#8A8470; '
    'text-transform:uppercase; margin-top:1px">Macro Portfolio</div>'
    '</div>',
    unsafe_allow_html=True,
)
st.sidebar.markdown("---")
page = st.sidebar.radio("View", ["📊  ETF Scan", "🔍  Ticker Analyzer", "🔁  Sector Rotation", "📋  Portfolio Framework", "🏦  Holdings"])
st.sidebar.markdown("---")
st.sidebar.caption("ETF Scan scores 40 sector ETFs. Ticker Analyzer deep-dives any symbol. Sector Rotation classifies ~40 sub-sectors into long/short tiers.")


# ──────────────────────────────────────────────────────────────────
# PAGE: ETF SCAN
# ──────────────────────────────────────────────────────────────────
if page == "📊  ETF Scan":
    st.markdown(
        '<div style="margin-bottom:4px">'
        '<span style="font-family:Georgia,serif; font-size:1.5rem; font-weight:700; '
        'color:#E8E2CC">Sector &amp; Industry ETF Scan</span> '
        '<span style="font-size:0.72rem; color:#8A8470; letter-spacing:.12em; '
        'text-transform:uppercase; margin-left:10px; vertical-align:middle">'
        '53 ETFs &middot; 7 RS + 4 flag signals</span></div>'
        '<p style="color:#8A8470; font-size:0.80rem; margin-bottom:18px; margin-top:2px">'
        'Scores all sector and industry ETFs ranked by accumulation strength.</p>',
        unsafe_allow_html=True,
    )

    if st.button("▶  Run Full Scan", type="primary"):
        tickers_to_dl = sorted(set(list(ETF_UNIVERSE.keys()) + ["SPY"]))

        with st.spinner(f"Downloading 1 year of data for {len(ETF_UNIVERSE)} ETFs …"):
            raw = yf.download(tickers_to_dl, period="1y", auto_adjust=True, progress=False)

        close_all = raw["Close"]
        if isinstance(close_all, pd.Series):
            close_all = close_all.to_frame()

        if "SPY" not in close_all.columns:
            st.error("Could not download SPY. Check your internet connection.")
            st.stop()

        spy = close_all["SPY"].dropna()

        etf_signals = {}
        results = []
        progress = st.progress(0, text="Analyzing ETFs …")
        etf_list = list(ETF_UNIVERSE.items())

        for i, (ticker, (name, category)) in enumerate(etf_list):
            s = analyze_etf(ticker, close_all, spy)
            progress.progress((i + 1) / len(etf_list), text=f"Analyzing {ticker} …")
            if s is None:
                continue
            etf_signals[ticker] = s
            rating_label, _ = get_etf_rating(s)

            if s["rs_improving"] and s["rs_1m"]:
                rs_trend = "ACCELERATING"
            elif s["rs_rollover"]:
                rs_trend = "ROLLING OVER"
            elif s["rs_3m"] and s["rs_1m"]:
                rs_trend = "LEADING"
            elif not s["rs_3m"] and not s["rs_1m"]:
                rs_trend = "LAGGING"
            else:
                rs_trend = "MIXED"

            results.append({
                "Ticker":   ticker,
                "Name":     name,
                "Category": category,
                "Rating":   rating_label,
                "RS Score": s["rs_score"],
                "Flags":    s["flag_count"],
                "Phase":    s["phase"],
                "1M Ret %": s["ret1m"],
                "3M Ret %": s["ret3m"],
                "6M Ret %": s["ret6m"],
                "RS Trend": rs_trend,
                "52w %ile": int(s["pct_range"]),
            })

        progress.empty()

        if not results:
            st.error("No ETF data could be loaded.")
            st.stop()

        results.sort(key=lambda x: (-x["RS Score"], x["Flags"], -x["3M Ret %"]))

        # Persist across reruns so selectboxes and deep dive keep working
        st.session_state["etf_results"]  = results
        st.session_state["etf_signals"]  = etf_signals

    results     = st.session_state.get("etf_results", [])
    etf_signals = st.session_state.get("etf_signals", {})

    if not results:
        st.markdown(
            '<div style="text-align:center; padding:70px 0">'
            '<div style="font-family:Georgia,serif; font-size:1.0rem; color:#7A7660; '
            'margin-bottom:8px">Click <b style="color:#C49A2A">Run Full Scan</b> '
            'to score all ETFs</div>'
            '<div style="font-size:0.78rem; color:#7A7660">~10–15 seconds to download and analyze</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        # ── Summary metrics ───────────────────────────────────────
        leading   = [r for r in results if r["RS Score"] >= 5 and r["Flags"] <= 1]
        improving = [r for r in results if r["RS Score"] in (3, 4) and r["Flags"] <= 1]
        caution   = [r for r in results if r["Flags"] >= 2]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("ETFs Scanned",        len(results))
        col2.metric("Leading / Improving",  f"{len(leading)} / {len(improving)}")
        col3.metric("Warning Flags ≥ 2",   len(caution))
        col4.metric("Best RS Score",        results[0]["RS Score"] if results else "—")

        st.markdown("")

        # ── Ranked table ──────────────────────────────────────────
        def color_score(val):
            if val >= 5: return "color: #6EC247; font-weight: 700"
            if val >= 3: return "color: #C49A2A; font-weight: 700"
            return "color: #E06060; font-weight: 700"

        def color_flags(val):
            if val >= 2: return "color: #E06060; font-weight: 700"
            if val == 1: return "color: #C49A2A"
            return "color: #6EC247"

        def color_ret(val):
            if val > 0: return "color: #6EC247"
            if val < 0: return "color: #E06060"
            return ""

        def color_phase(val):
            if val == "CONFIRMED": return "color: #6EC247"
            if val == "EARLY":     return "color: #C49A2A"
            if val == "DISTRIBUT": return "color: #E06060"
            if val == "DOWNTREND": return "color: #C0392B; font-weight: 700"
            return "color: #5A5640"

        def color_rs_trend(val):
            if val == "ACCELERATING": return "color: #6EC247; font-weight: 700"
            if val == "LEADING":      return "color: #4A7C35"
            if val == "ROLLING OVER": return "color: #C06030; font-weight: 700"
            if val == "LAGGING":      return "color: #E06060"
            return "color: #5A5640"

        display_cols = ["Ticker", "Name", "Category", "Rating", "RS Score",
                        "Flags", "Phase", "1M Ret %", "3M Ret %", "6M Ret %",
                        "RS Trend", "52w %ile"]
        df = pd.DataFrame(results)[display_cols]

        styled = (
            df.style
            .map(color_score,    subset=["RS Score"])
            .map(color_flags,    subset=["Flags"])
            .map(color_ret,      subset=["6M Ret %", "3M Ret %", "1M Ret %"])
            .map(color_phase,    subset=["Phase"])
            .map(color_rs_trend, subset=["RS Trend"])
            .format({"6M Ret %": "{:+.1f}%", "3M Ret %": "{:+.1f}%", "1M Ret %": "{:+.1f}%"})
        )

        st.dataframe(styled, use_container_width=True, hide_index=True, height=700)

        # ── Holdings expanders ────────────────────────────────────
        st.markdown("---")
        st.markdown(
            '<div style="font-family:Georgia,serif; font-size:1.0rem; font-weight:700; '
            'color:#D4C898; margin-bottom:6px">Holdings</div>',
            unsafe_allow_html=True,
        )
        for r in sorted(results, key=lambda x: x["Ticker"]):
            ticker = r["Ticker"]
            label  = f"{ticker} — {r['Name']}  ·  {r['Rating']}  ·  RS {r['RS Score']}/7"
            with st.expander(label):
                holdings = get_etf_holdings(ticker)
                if holdings is not None and not holdings.empty:
                    df_h = holdings.copy()
                    weight_col = next(
                        (c for c in df_h.columns if "percent" in c.lower() or "weight" in c.lower()), None
                    )
                    if weight_col:
                        df_h = df_h[[weight_col]].copy()
                        df_h.columns = ["Weight"]
                        df_h["Weight"] = df_h["Weight"].apply(lambda x: f"{float(x)*100:.2f}%")
                    df_h.index.name = "Holding"
                    st.dataframe(df_h, use_container_width=True, hide_index=False)
                else:
                    st.caption("Holdings data not available for this ETF.")

        # ── Category breakdown ────────────────────────────────────
        st.markdown("---")
        st.markdown(
            '<div style="font-family:Georgia,serif; font-size:1.0rem; font-weight:700; '
            'color:#D4C898; margin-bottom:10px">By Category</div>',
            unsafe_allow_html=True,
        )
        cats = sorted(set(r["Category"] for r in results))
        for cat in cats:
            group    = [r for r in results if r["Category"] == cat]
            avg_rs   = sum(r["RS Score"] for r in group) / len(group)
            avg_ret  = sum(r["3M Ret %"] for r in group) / len(group)
            avg_flag = sum(r["Flags"]    for r in group) / len(group)
            color    = "#6EC247" if avg_rs >= 4 else ("#C49A2A" if avg_rs >= 2.5 else "#E06060")
            leaders  = ", ".join(
                r["Ticker"] for r in sorted(group, key=lambda x: -x["RS Score"])[:3]
            )
            st.markdown(
                f'<div style="padding:8px 14px; margin:4px 0; border-left:4px solid {color}; '
                f'background:rgba(255,255,255,0.02); border-radius:0 6px 6px 0; color:#B8B49E; font-size:0.84rem">'
                f'<b style="color:#E8E2CC">{cat}</b> &nbsp;&middot;&nbsp; '
                f'<span style="color:#8A8470">RS avg</span> <span style="color:{color}; font-weight:700">{avg_rs:.1f}/7</span> &nbsp;&middot;&nbsp; '
                f'<span style="color:#8A8470">3M avg</span> <span style="color:{"#6EC247" if avg_ret > 0 else "#E06060"}; font-weight:700">{avg_ret:+.1f}%</span>'
                f' &nbsp;&middot;&nbsp; <span style="color:#8A8470">flags</span> {avg_flag:.1f}'
                f' &nbsp;&middot;&nbsp; <span style="color:#8A8470">Leaders:</span> <span style="color:#A8A490">{leaders}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # ── Deep-dive picker ──────────────────────────────────────
        st.markdown("---")
        st.markdown(
            '<div style="font-family:Georgia,serif; font-size:1.0rem; font-weight:700; '
            'color:#D4C898; margin-bottom:10px">Deep Dive</div>',
            unsafe_allow_html=True,
        )
        pick = st.selectbox(
            "Select an ETF for the full breakdown and chart:",
            options=[r["Ticker"] for r in results],
            format_func=lambda t: f"{t} — {ETF_UNIVERSE[t][0]} ({ETF_UNIVERSE[t][1]})",
        )
        if pick and pick in etf_signals:
            render_etf_deep_dive(etf_signals[pick])


# ──────────────────────────────────────────────────────────────────
# PAGE: TICKER ANALYZER
# ──────────────────────────────────────────────────────────────────
elif page == "🔍  Ticker Analyzer":
    st.markdown(
        '<div style="margin-bottom:4px">'
        '<span style="font-family:Georgia,serif; font-size:1.5rem; font-weight:700; '
        'color:#E8E2CC">Ticker Analyzer</span> '
        '<span style="font-size:0.72rem; color:#8A8470; letter-spacing:.12em; '
        'text-transform:uppercase; margin-left:10px; vertical-align:middle">'
        '7 acc &middot; 4 dist &middot; volume surge</span></div>'
        '<p style="color:#8A8470; font-size:0.80rem; margin-bottom:14px; margin-top:2px">'
        'Accumulation, distribution, and volume signals for any ticker.</p>',
        unsafe_allow_html=True,
    )

    # Input row
    col_input, col_btn = st.columns([5, 1])
    with col_input:
        tickers_raw = st.text_input(
            "Tickers",
            placeholder="e.g.  FCEL, CRWD, NVDA, AAPL  —  separate with commas",
            label_visibility="collapsed",
        )
    with col_btn:
        run = st.button("Analyze", type="primary", use_container_width=True)

    # Collapsible legend
    with st.expander("How to read the signals", expanded=False):
        st.markdown("""
**Accumulation signals** (each worth 1 point, max score = 7):
- **OBV 90d / 30d** — On-Balance Volume rising means more volume comes in on up days than down days — a sign of institutional buying
- **OBV Divergence** — OBV rising while price is flat/falling → institutions quietly accumulating before the move
- **Selling decelerating** — the pace of price declines is slowing → sellers may be running out
- **Outperform SPY 90d / 30d** — ticker rising faster than the S&P 500 (relative strength)
- **3M Momentum** — is the stock up over the last 3 months?

**Distribution signals** (each adds 1 flag, max = 4 — more flags = more caution):
- **Near high + OBV falling** — price near 52-week high but volume skews to down days → smart money may be selling into strength
- **RS Rollover** — was beating the S&P 500 over 90 days, now lagging over 30 days → momentum fading
- **Selling accelerating** — pace of price declines is speeding up → new sellers entering
- **Down-vol dominance** — 60%+ of the last 10 days' volume was on red (down) days

**Volume surge**: compares recent trading volume to the quiet period from 90–252 days ago (before any surge started).
A 3.0x surge = 3× the average daily volume of that quiet period. RISING = surge still building; PEAKED = may have played out.

**Ratings**: STRONG (6-7 acc) → BUILDING (4-5) → WATCH (2-3) → WEAK (1) → BEARISH (0)
Override: DISTRIBUTING (3+ dist flags), DIST-WATCH (2 dist flags near 52w high)
""")

    # Guard: no input yet
    if not tickers_raw.strip():
        st.markdown(
            '<div style="text-align:center; padding:70px 0">'
            '<div style="font-family:Georgia,serif; font-size:1.0rem; color:#7A7660; '
            'margin-bottom:8px">Enter one or more tickers and click '
            '<b style="color:#C49A2A">Analyze</b></div>'
            '<div style="font-size:0.78rem; color:#7A7660">e.g. NVDA, CRWD, SOXX</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.stop()

    if not run:
        st.stop()

    # Parse tickers
    tickers = [t.strip().upper() for t in tickers_raw.split(",") if t.strip()]
    if not tickers:
        st.warning("No valid tickers found — enter symbols separated by commas.")
        st.stop()

    # Download 1 year of data for all tickers + SPY
    download_list = sorted(set(tickers + ["SPY"]))
    with st.spinner(f"Downloading 1 year of data for {', '.join(tickers)} …"):
        raw = yf.download(download_list, period="1y", auto_adjust=True, progress=False)

    close_all  = raw["Close"]
    volume_all = raw["Volume"]

    if isinstance(close_all, pd.Series):
        close_all  = close_all.to_frame(name=download_list[0])
        volume_all = volume_all.to_frame(name=download_list[0])

    if "SPY" not in close_all.columns:
        st.error("Could not download SPY data. Check your internet connection and try again.")
        st.stop()

    spy = close_all["SPY"].dropna()

    found = 0
    for ticker in tickers:
        with st.spinner(f"Analyzing {ticker} …"):
            signals = analyze_ticker(ticker, close_all, volume_all, spy)

        if signals is None:
            st.warning(
                f"**{ticker}** — not enough data (fewer than 50 trading days). "
                "Check that the symbol is correct, or try a different ticker."
            )
            continue

        render_ticker(signals)
        found += 1

    if found == 0:
        st.error("No tickers could be analyzed. Double-check the symbols and try again.")


# ──────────────────────────────────────────────────────────────────
# PAGE: SECTOR ROTATION
# ──────────────────────────────────────────────────────────────────
elif page == "🔁  Sector Rotation":
    st.markdown(
        '<div style="margin-bottom:4px">'
        '<span style="font-family:Georgia,serif; font-size:1.5rem; font-weight:700; '
        'color:#E8E2CC">Sector Rotation</span> '
        '<span style="font-size:0.72rem; color:#8A8470; letter-spacing:.12em; '
        'text-transform:uppercase; margin-left:10px; vertical-align:middle">'
        '~40 sub-sectors &middot; ~140 tickers &middot; RS/price only</span></div>'
        '<p style="color:#8A8470; font-size:0.80rem; margin-bottom:18px; margin-top:2px">'
        'Classifies every sub-sector into long/short entry-exit tiers using EMA-smoothed '
        'relative strength, early-leadership detection, and vol-normalized resilience ranking.</p>',
        unsafe_allow_html=True,
    )

    if st.button("▶  Run Rotation Scan", type="primary"):
        universe_tickers = sorted(set(rotation_engine.all_universe_tickers() + ["SPY"]))

        with st.spinner(f"Downloading 1 year of data for {len(universe_tickers)} tickers…"):
            raw = yf.download(universe_tickers, period="1y", auto_adjust=True, progress=False)

        close_all = raw["Close"]
        if isinstance(close_all, pd.Series):
            close_all = close_all.to_frame()

        if "SPY" not in close_all.columns:
            st.error("Could not download SPY. Check your internet connection.")
            st.stop()

        spy = close_all["SPY"].dropna()

        with st.spinner("Scoring universe and classifying sub-sectors…"):
            subsector_agg, breadth_pct, n_groups = rotation_engine.run_rotation_scan(close_all, spy)

        if not subsector_agg:
            st.error("No sub-sectors could be scored.")
            st.stop()

        # ── Summary metrics ───────────────────────────────────────
        counts = {cls: 0 for cls in rotation_engine.CLASSIFICATION_ORDER}
        for a in subsector_agg.values():
            counts[a["classification"]] += 1
        n_long  = (counts["CONFIRMED LONG"] + counts["STARTER LONG (leadership)"]
                   + counts["STARTER LONG (broad-rotation)"])
        n_short = (counts["CONFIRMED SHORT"] + counts["EARLY WEAKNESS SHORT (lagging sector)"]
                   + counts["EARLY WEAKNESS SHORT (broad decline)"])

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Sub-sectors scored", n_groups)
        col2.metric("Breadth (RS-positive)", f"{breadth_pct:.0f}%")
        col3.metric("Long candidates",  n_long)
        col4.metric("Short candidates", n_short)

        st.markdown("")

        # ── Classification sections ───────────────────────────────
        SECTION_COLOR = {
            "CONFIRMED LONG":                          "#6EC247",
            "STARTER LONG (leadership)":               "#4A7C35",
            "STARTER LONG (broad-rotation)":           "#4A7C35",
            "CONFIRMED SHORT":                         "#C0392B",
            "EARLY WEAKNESS SHORT (lagging sector)":   "#C06030",
            "EARLY WEAKNESS SHORT (broad decline)":    "#C06030",
            "NEUTRAL / NO SETUP":                      "#5A5640",
        }

        for cls in rotation_engine.CLASSIFICATION_ORDER:
            members = [(sub, a) for sub, a in subsector_agg.items() if a["classification"] == cls]
            if not members:
                continue
            reverse = "SHORT" not in cls
            members.sort(key=lambda x: x[1]["avg_rs_mom"], reverse=reverse)
            color = SECTION_COLOR[cls]

            st.markdown(
                f'<div style="font-family:Georgia,serif; font-size:1.0rem; font-weight:700; '
                f'color:{color}; margin:20px 0 8px 0">{cls} '
                f'<span style="font-size:0.70rem; color:#8A8470">({len(members)})</span></div>',
                unsafe_allow_html=True,
            )

            for sub, a in members:
                rv_flag    = "RESILIENT" if a["resilient"] else ("VULNERABLE" if a["vulnerable"] else "")
                lead_flag  = "leads sector" if a["leading_within_sector"] else "tracks sector"
                names      = a["leaders"] if "SHORT" not in cls else a["laggards"]
                names_lbl  = "Leaders" if "SHORT" not in cls else "Laggards"
                flag_html  = (f' &nbsp;&middot;&nbsp; <span style="color:{color}">{rv_flag}</span>'
                              if rv_flag else "")
                mom_c      = "#6EC247" if a["avg_rs_mom"] > 0 else "#E06060"
                ret_c      = "#6EC247" if a["avg_ret3m"]  > 0 else "#E06060"
                st.markdown(
                    f'<div style="padding:8px 14px; margin:4px 0; border-left:4px solid {color}; '
                    f'background:rgba(255,255,255,0.02); border-radius:0 6px 6px 0; '
                    f'color:#B8B49E; font-size:0.84rem">'
                    f'<b style="color:#E8E2CC; font-size:0.92rem">{sub}</b> '
                    f'<span style="color:#8A8470">[{a["sector"]}]</span>'
                    f' &nbsp;&middot;&nbsp; '
                    f'<span style="color:#8A8470">Long</span> <span style="color:#6EC247; font-weight:700">{a["long_score"]}/7</span>'
                    f' &nbsp;<span style="color:#8A8470">Short</span> <span style="color:#E06060; font-weight:700">{a["short_score"]}/7</span>'
                    f' &nbsp;&middot;&nbsp; '
                    f'<span style="color:#8A8470">RS-mom</span> <span style="color:{mom_c}; font-weight:700">{a["avg_rs_mom"]:+.2f}%</span>'
                    f' &nbsp;&middot;&nbsp; '
                    f'<span style="color:#8A8470">3M</span> <span style="color:{ret_c}; font-weight:700">{a["avg_ret3m"]:+.1f}%</span>'
                    f' &nbsp;&middot;&nbsp; <span style="color:#8A8470">{lead_flag}</span>{flag_html}<br>'
                    f'<span style="color:#7A7660; font-size:0.78rem">'
                    f'{names_lbl}: <span style="color:#A8A490">{names or "n/a"}</span></span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    else:
        st.markdown(
            '<div style="text-align:center; padding:70px 0">'
            '<div style="font-family:Georgia,serif; font-size:1.0rem; color:#7A7660; '
            'margin-bottom:8px">Click <b style="color:#C49A2A">Run Rotation Scan</b> '
            'to classify all sub-sectors</div>'
            '<div style="font-size:0.78rem; color:#7A7660">'
            '~20–40 seconds to download and score ~140 tickers</div>'
            '</div>',
            unsafe_allow_html=True,
        )

# ──────────────────────────────────────────────────────────────────
# PAGE: PORTFOLIO FRAMEWORK
# ──────────────────────────────────────────────────────────────────
elif page == "📋  Portfolio Framework":
    st.markdown(
        '<div style="margin-bottom:4px">'
        '<span style="font-family:Georgia,serif; font-size:1.5rem; font-weight:700; '
        'color:#E8E2CC">Portfolio Construction Framework</span></div>'
        '<p style="color:#8A8470; font-size:0.80rem; margin-bottom:22px; margin-top:2px">'
        'Continuous reallocation toward themes where macro thesis and price action confirm '
        'each other &middot; systematic reduction as leadership deteriorates.</p>',
        unsafe_allow_html=True,
    )

    # ── Allocation overview bar ──────────────────────────────────
    st.markdown(
        '<div style="margin-bottom:6px">'
        '<div style="display:flex; height:10px; border-radius:5px; overflow:hidden; gap:2px">'
        '<div style="width:40%; background:#5B9BD5; opacity:0.7; border-radius:3px"></div>'
        '<div style="width:45%; background:#6EC247; opacity:0.75; border-radius:3px"></div>'
        '<div style="width:12%; background:#C49A2A; opacity:0.7; border-radius:3px"></div>'
        '<div style="width:3%; background:#5A5640; opacity:0.4; border-radius:3px"></div>'
        '</div>'
        '<div style="display:flex; gap:20px; font-size:0.72rem; color:#8A8470; margin-top:6px">'
        '<span><span style="color:#5B9BD5">■</span> Core 40%</span>'
        '<span><span style="color:#6EC247">■</span> Leadership 45%</span>'
        '<span><span style="color:#C49A2A">■</span> Emerging 12%</span>'
        '<span style="opacity:0.5">■ Cash 3%</span>'
        '</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown("")

    # ── Bucket cards ─────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)

    def bucket_card(col, name, color, pct, range_str, desc, etfs):
        chips = "".join(
            f'<span style="font-size:0.72rem; padding:2px 7px; border-radius:3px; '
            f'background:rgba(255,255,255,0.06); color:#9A9480; '
            f'border:1px solid rgba(255,255,255,0.08); margin:2px 2px 0 0; display:inline-block">{t}</span>'
            for t in etfs
        )
        col.markdown(
            f'<div style="background:rgba(255,255,255,0.03); border:1px solid rgba(110,194,71,0.10); '
            f'border-radius:6px; padding:14px 16px; height:100%">'
            f'<div style="display:flex; justify-content:space-between; margin-bottom:8px">'
            f'<span style="font-size:0.72rem; text-transform:uppercase; letter-spacing:.09em; '
            f'font-weight:700; color:{color}">{name}</span>'
            f'<span style="font-size:0.70rem; color:#5A5640">{range_str}</span></div>'
            f'<div style="font-family:Georgia,serif; font-size:1.4rem; color:{color}; margin-bottom:6px">{pct}</div>'
            f'<div style="font-size:0.75rem; color:#7A7660; line-height:1.55; margin-bottom:8px">{desc}</div>'
            f'<div style="line-height:1.8">{chips}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    bucket_card(c1, "Core", "#5B9BD5", "40%", "35–45%",
        "Broad market foundation. Always held. Keeps you in the dominant trend regardless of rotation.",
        ["SPY", "QQQ", "XLF", "XLK", "XLE"])
    bucket_card(c2, "Leadership", "#6EC247", "45%", "40–50%",
        "4–6 confirmed themes. Stage 2 trend + strong RS. Don't sell just because a winner ran — hold while trend intact.",
        ["SOXX", "ITA", "PAVE", "XLI", "COPX", "KRE"])
    bucket_card(c3, "Emerging", "#C49A2A", "12%", "10–20%",
        "2–4 themes with improving RS but not yet Stage 2. Small starter — front-runs confirmation without a heavy bet.",
        ["URA", "DRAM", "TAN", "REMX", "ARKG"])

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Signal ladder ─────────────────────────────────────────────
    st.markdown(
        '<div style="font-size:0.72rem; text-transform:uppercase; letter-spacing:.1em; '
        'color:#5A5640; margin-bottom:10px">Signal Ladder — Allocation by Confirmation</div>',
        unsafe_allow_html=True,
    )
    lc1, lc2, lc3, lc4 = st.columns(4)

    def ladder_cell(col, stage, label, color, weight, desc):
        col.markdown(
            f'<div style="background:rgba(255,255,255,0.03); border:1px solid rgba(110,194,71,0.10); '
            f'border-radius:6px; padding:12px 14px; height:100%">'
            f'<div style="font-size:0.68rem; text-transform:uppercase; letter-spacing:.08em; '
            f'color:#5A5640; margin-bottom:6px">{stage}</div>'
            f'<div style="font-size:0.82rem; font-weight:700; color:{color}; margin-bottom:4px">{label}</div>'
            f'<div style="font-family:Georgia,serif; font-size:1.25rem; color:{color}; margin-bottom:6px">{weight}</div>'
            f'<div style="font-size:0.73rem; color:#7A7660; line-height:1.5">{desc}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    ladder_cell(lc1, "Stage 1 — Bottoming", "Watch", "#5A5640", "0%",
        "Price stopped falling · MA flattening · RS improving but not confirmed. No capital — opportunity cost is real.")
    ladder_cell(lc2, "Stage 1→2 — Emerging", "Starter", "#C49A2A", "2–3%",
        "RS improving · Base forming · Not yet above rising 40w MA. Front-runs confirmation without betting early.")
    ladder_cell(lc3, "Stage 2 — Confirmed", "Full Position", "#6EC247", "5–8%",
        "Price > rising 40w MA · RS > 70 · Breakout from base · Volume confirms. Highest-value entry zone.")
    ladder_cell(lc4, "Stage 2/3 — Leadership", "Overweight", "#6EC247", "8–10%+",
        "RS > 80 + improving · Strong outperformance · Clear macro thesis. Maximum allocation. Don't sell just because it ran.")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 2×2 RS Matrix ─────────────────────────────────────────────
    st.markdown(
        '<div style="font-size:0.72rem; text-transform:uppercase; letter-spacing:.1em; '
        'color:#5A5640; margin-bottom:10px">RS Level × RS Trend — The Decision Matrix</div>',
        unsafe_allow_html=True,
    )

    def mx_cell(col, dot_color, label, weight, weight_color, action, bg):
        col.markdown(
            f'<div style="background:{bg}; border:1px solid rgba(110,194,71,0.10); '
            f'border-radius:6px; padding:14px 16px; height:100%">'
            f'<div style="display:flex; align-items:center; gap:6px; font-size:0.82rem; '
            f'font-weight:700; color:#E8E2CC; margin-bottom:4px">'
            f'<span style="color:{dot_color}">●</span> {label}</div>'
            f'<div style="font-family:Georgia,serif; font-size:1.2rem; color:{weight_color}; margin-bottom:6px">{weight}</div>'
            f'<div style="font-size:0.73rem; color:#7A7660; line-height:1.5">{action}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    hdr1, hdr2 = st.columns([1, 1])
    hdr1.markdown('<div style="text-align:center; font-size:0.72rem; color:#5A5640; padding:4px 0; text-transform:uppercase; letter-spacing:.07em">RS Improving</div>', unsafe_allow_html=True)
    hdr2.markdown('<div style="text-align:center; font-size:0.72rem; color:#5A5640; padding:4px 0; text-transform:uppercase; letter-spacing:.07em">RS Deteriorating</div>', unsafe_allow_html=True)

    r1c1, r1c2 = st.columns(2)
    mx_cell(r1c1, "#6EC247", "Leadership (High RS)", "7–10%+", "#6EC247",
        "Best setup — own / overweight. Don't sell just because it ran. Only trim on excessive sizing or extension.",
        "rgba(110,194,71,0.08)")
    mx_cell(r1c2, "#C49A2A", "Former Leader (High RS)", "4–6% → trim", "#C49A2A",
        "Stop adding. Reduce on failed rallies, lower highs, or sustained underperformance vs SPY.",
        "rgba(196,154,42,0.07)")

    r2c1, r2c2 = st.columns(2)
    mx_cell(r2c1, "#C49A2A", "Emerging (Low RS)", "2–3%", "#C49A2A",
        "Starter position only. Wait for Stage 2 breakout with volume confirmation to add meaningfully.",
        "rgba(196,154,42,0.05)")
    mx_cell(r2c2, "#E06060", "Avoid (Low RS)", "0%", "#E06060",
        "Watchlist only. No capital. Bottoming ≠ buy signal — wait for RS to inflect before allocating anything.",
        "rgba(224,96,96,0.06)")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Sell discipline ───────────────────────────────────────────
    st.markdown(
        '<div style="font-size:0.72rem; text-transform:uppercase; letter-spacing:.1em; '
        'color:#5A5640; margin-bottom:10px">Sell Discipline — Three Levels</div>',
        unsafe_allow_html=True,
    )
    sell_df = pd.DataFrame([
        {"Signal": "⚠  Yellow — Stop adding",
         "Characteristics": "RS stops improving · Price loses short-term momentum · Sector starts lagging a few weeks",
         "Action": "Stop adding",
         "Result": "100% → hold"},
        {"Signal": "▼  Orange — Trim",
         "Characteristics": "RS falls materially · Price breaks intermediate trend · Failed breakout · Lower high develops",
         "Action": "Trim tactical exposure",
         "Result": "100% → 50–75%"},
        {"Signal": "✕  Red — Exit",
         "Characteristics": "Price below 40w MA · MA turns down · RS in bottom half of universe · Lower highs + lower lows",
         "Action": "Exit tactical position",
         "Result": "100% → 0%"},
    ])
    st.dataframe(sell_df, use_container_width=True, hide_index=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Position sizing by ETF type ───────────────────────────────
    st.markdown(
        '<div style="font-size:0.72rem; text-transform:uppercase; letter-spacing:.1em; '
        'color:#5A5640; margin-bottom:10px">Position Sizing by ETF Type</div>',
        unsafe_allow_html=True,
    )
    sizing_df = pd.DataFrame([
        {"ETF Type": "Broad Sector / Index",       "Max Size": "8–12%", "Entry Requirement": "Stage 2 trend · Any RS level",                             "Examples": "SPY, QQQ, XLK, XLE, XLF, XLI, XLV"},
        {"ETF Type": "Diversified Thematic",        "Max Size": "6–10%", "Entry Requirement": "RS percentile > 70 · Stage 2 breakout",                    "Examples": "SOXX, ITA, PAVE, IBB, KRE, GDX, OIH"},
        {"ETF Type": "Narrow / Concentrated",       "Max Size": "3–7%",  "Entry Requirement": "RS > 80 · Clear base breakout · Volume confirms",          "Examples": "DRAM, URA, BETZ, SLX, REMX, BIZD, COPX"},
        {"ETF Type": "Pre-confirmation (Emerging)", "Max Size": "2–3%",  "Entry Requirement": "RS improving · Stage 1→2 transition · Not yet confirmed",  "Examples": "Any of the above before breakout triggers"},
    ])
    st.dataframe(sizing_df, use_container_width=True, hide_index=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Illustrative 12-position portfolio ────────────────────────
    st.markdown(
        '<div style="font-size:0.72rem; text-transform:uppercase; letter-spacing:.1em; '
        'color:#5A5640; margin-bottom:4px">Illustrative 12-Position Portfolio</div>'
        '<div style="font-size:0.73rem; color:#5A5640; font-style:italic; margin-bottom:10px">'
        'Example structure — swap tickers to whatever currently ranks highest in the ETF scan. '
        'Target ≤12 active positions; don\'t force 12 if the market isn\'t giving you 12 good setups.</div>',
        unsafe_allow_html=True,
    )
    port_df = pd.DataFrame([
        {"Ticker": "SPY",  "Theme": "S&P 500",        "Bucket": "Core",     "Weight": "20%", "Add When": "Always",                            "Reduce When": "Never — core position"},
        {"Ticker": "QQQ",  "Theme": "Nasdaq 100",      "Bucket": "Core",     "Weight": "12%", "Add When": "Stage 2 broad market intact",        "Reduce When": "Broad market Stage 4"},
        {"Ticker": "XLF",  "Theme": "Financials",      "Bucket": "Core",     "Weight": "8%",  "Add When": "Stage 2 + yield curve supportive",   "Reduce When": "Below 40w MA + RS falls"},
        {"Ticker": "SOXX", "Theme": "Semiconductors",  "Bucket": "Leader",   "Weight": "9%",  "Add When": "RS > 80 + Stage 2 breakout",         "Reduce When": "RS drops below 60 or lower high"},
        {"Ticker": "ITA",  "Theme": "Defense & Aero",  "Bucket": "Leader",   "Weight": "8%",  "Add When": "RS > 75 + Stage 2",                  "Reduce When": "RS trend rolls over"},
        {"Ticker": "PAVE", "Theme": "Infrastructure",  "Bucket": "Leader",   "Weight": "7%",  "Add When": "RS > 70 + Stage 2",                  "Reduce When": "Price loses 40w MA"},
        {"Ticker": "XLE",  "Theme": "Energy",          "Bucket": "Leader",   "Weight": "7%",  "Add When": "RS > 65 + commodity trend up",       "Reduce When": "RS < 50 sustained 3+ wks"},
        {"Ticker": "COPX", "Theme": "Copper Miners",   "Bucket": "Leader",   "Weight": "6%",  "Add When": "RS > 70 + commodity cycle up",       "Reduce When": "RS deteriorates + failed breakout"},
        {"Ticker": "URA",  "Theme": "Uranium",         "Bucket": "Emerging", "Weight": "5%",  "Add When": "RS improving + base forming",        "Reduce When": "RS stops improving"},
        {"Ticker": "DRAM", "Theme": "Memory Chips",    "Bucket": "Emerging", "Weight": "4%",  "Add When": "RS improving + AI capex theme",      "Reduce When": "RS stalls or reverses"},
        {"Ticker": "TAN",  "Theme": "Solar",           "Bucket": "Emerging", "Weight": "3%",  "Add When": "Policy catalyst + RS turning up",    "Reduce When": "RS fails to confirm"},
        {"Ticker": "—",    "Theme": "Cash / Buffer",   "Bucket": "Cash",     "Weight": "3%",  "Add When": "When <10 positions qualify",         "Reduce When": "Deploy when signals improve"},
    ])
    st.dataframe(port_df, use_container_width=True, hide_index=True)


# ──────────────────────────────────────────────────────────────────
# PAGE: HOLDINGS
# ──────────────────────────────────────────────────────────────────
elif page == "🏦  Holdings":
    st.markdown(
        '<div style="margin-bottom:4px">'
        '<span style="font-family:Georgia,serif; font-size:1.5rem; font-weight:700; '
        'color:#E8E2CC">ETF Holdings Lookup</span></div>'
        '<p style="color:#8A8470; font-size:0.80rem; margin-bottom:18px; margin-top:2px">'
        'Select any ETF in the universe to see its top holdings.</p>',
        unsafe_allow_html=True,
    )

    # Build a sorted list of options: "TICKER — Name (Category)"
    etf_options = sorted(
        [f"{ticker} — {name}  [{cat}]" for ticker, (name, cat) in ETF_UNIVERSE.items()]
    )
    selected = st.selectbox("Choose an ETF", etf_options)

    if selected:
        ticker = selected.split(" — ")[0].strip()
        name, category = ETF_UNIVERSE.get(ticker, ("", ""))

        col_ticker, col_fetch = st.columns([3, 1])
        with col_fetch:
            fetch = st.button("Get Holdings", type="primary")

        if fetch:
            holdings = get_etf_holdings(ticker)

            if holdings is not None and not holdings.empty:
                df_h = holdings.copy()
                weight_col = next(
                    (c for c in df_h.columns if "percent" in c.lower() or "weight" in c.lower()),
                    None,
                )
                if weight_col:
                    df_h = df_h.copy()
                    df_h["Weight %"] = df_h[weight_col].apply(lambda x: f"{float(x)*100:.2f}%")
                    display_cols = [c for c in df_h.columns if c != weight_col]
                    df_h = df_h[display_cols]

                st.markdown(
                    f'<div style="font-family:Georgia,serif; font-size:1.0rem; '
                    f'font-weight:700; color:#D4C898; margin:16px 0 8px 0">'
                    f'Top Holdings — {ticker}  '
                    f'<span style="font-size:0.72rem; color:#8A8470; font-weight:normal">'
                    f'{name} &middot; {category}</span></div>',
                    unsafe_allow_html=True,
                )
                st.dataframe(df_h, use_container_width=True)
            else:
                st.warning(f"No holdings data found for {ticker}.")
