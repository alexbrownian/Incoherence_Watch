"""
engine.py - the detection logic, in one importable place.

This is EXACTLY the logic taught step-by-step in notebook
02_detect_incoherence. It lives here as well so that:
  - run_daily.py can run the whole monitor without opening Jupyter
  - notebook 05 can auto-discover pairs without re-typing the code

If you change a threshold here, notebook 02's copy won't know about it -
treat THIS file as the source of truth and notebook 02 as the lesson.
"""

from itertools import combinations

import numpy as np
import pandas as pd

import db
from pairs_config import UNIVERSE, MIN_AUTO_CORR

# --- tuning knobs (same meaning as in notebook 02) ---
LONG_WINDOW = 252
SHORT_WINDOW = 21
FLIP_LEVEL = 0.15
CONFIRM_DAYS = 3
MIN_LONG_CORR = 0.20


def to_moves(series, transform):
    """Levels -> daily moves. 'pct' for prices, 'diff' for yields/spreads."""
    if transform == "pct":
        return series.pct_change()
    return series.diff()


def pair_correlations(prices, pair):
    """Short (21d) and long (252d) rolling correlation of a pair's moves."""
    moves_a = to_moves(prices[pair["ticker_a"]], pair["transform_a"])
    moves_b = to_moves(prices[pair["ticker_b"]], pair["transform_b"])
    out = pd.DataFrame({
        "corr_short": moves_a.rolling(SHORT_WINDOW).corr(moves_b),
        "corr_long":  moves_a.rolling(LONG_WINDOW).corr(moves_b),
    })
    return out.dropna()


def detect_events(pair, corrs):
    """
    Walk forward in time with a NORMAL/BROKEN state machine.
    Returns (list of events, final state). See notebook 02 for the lesson.
    """
    base = pair["expected_sign"]
    state = "NORMAL"
    breakdown_count = 0
    reversion_count = 0
    events = []

    for date, row in corrs.iterrows():
        sign = base if base != 0 else np.sign(row["corr_long"])

        if abs(row["corr_long"]) < MIN_LONG_CORR:
            breakdown_count = reversion_count = 0
            continue

        signed_short = row["corr_short"] * sign

        if state == "NORMAL":
            breakdown_count = breakdown_count + 1 if signed_short < -FLIP_LEVEL else 0
            if breakdown_count >= CONFIRM_DAYS:
                state = "BROKEN"
                breakdown_count = 0
                events.append(("breakdown", date, row["corr_short"], row["corr_long"]))
        else:
            reversion_count = reversion_count + 1 if signed_short > FLIP_LEVEL else 0
            if reversion_count >= CONFIRM_DAYS:
                state = "NORMAL"
                reversion_count = 0
                events.append(("reversion", date, row["corr_short"], row["corr_long"]))

    return events, state


def build_auto_pairs(prices, core_pairs):
    """
    Auto-discovery: look at EVERY combination of two universe tickers and
    keep the ones whose full-sample correlation of daily moves is at least
    MIN_AUTO_CORR (in absolute value). Pairs already covered by CORE_PAIRS
    are skipped so nothing is monitored twice.

    Returned pairs have expected_sign = 0, meaning "the baseline is your
    own long-run correlation" - flag when you break from it.
    """
    # daily moves for every universe ticker we actually have data for
    moves = pd.DataFrame({
        t: to_moves(prices[t], tr)
        for t, tr in UNIVERSE.items() if t in prices.columns
    })
    corr_matrix = moves.corr()

    # tickers already paired by hand
    covered = {frozenset([p["ticker_a"], p["ticker_b"]]) for p in core_pairs}

    auto_pairs = []
    for ticker_a, ticker_b in combinations(corr_matrix.columns, 2):
        if frozenset([ticker_a, ticker_b]) in covered:
            continue
        c = corr_matrix.loc[ticker_a, ticker_b]
        if abs(c) >= MIN_AUTO_CORR:
            short_a = ticker_a.split()[0]
            short_b = ticker_b.split()[0]
            auto_pairs.append({
                "name": f"AUTO: {short_a} vs {short_b}",
                "ticker_a": ticker_a, "ticker_b": ticker_b,
                "transform_a": UNIVERSE[ticker_a],
                "transform_b": UNIVERSE[ticker_b],
                "expected_sign": 0,
                "description": f"Auto-discovered (full-sample corr {c:+.2f}). "
                               "Baseline = own 1y correlation.",
            })
    return auto_pairs


def run_detection(prices, pairs, conn=None, verbose=True):
    """
    Run the full pipeline for a list of pairs. Writes events + status to
    SQLite (unless conn is None) and returns a summary DataFrame.
    """
    if conn is None:
        conn = db.get_connection()

    rows = []
    for pair in pairs:
        corrs = pair_correlations(prices, pair)
        if len(corrs) == 0:
            continue

        events, final_state = detect_events(pair, corrs)
        for event_type, date, c_short, c_long in events:
            db.insert_event(conn, pair["name"], event_type, date,
                            round(c_short, 3), round(c_long, 3),
                            note=pair["description"])

        last = corrs.iloc[-1]
        db.upsert_status(conn, pair["name"], final_state, corrs.index[-1],
                         round(last["corr_short"], 3), round(last["corr_long"], 3))

        rows.append({"pair": pair["name"], "state": final_state,
                     "events": len(events),
                     "corr_short": round(last["corr_short"], 2),
                     "corr_long": round(last["corr_long"], 2)})
        if verbose:
            print(f"{pair['name']:<32} state={final_state:<7} events: {len(events)}")

    return pd.DataFrame(rows)
