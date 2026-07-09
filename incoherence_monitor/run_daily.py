"""
run_daily.py - the whole monitor in one command, no Jupyter needed.

    python run_daily.py

What it does, in order:
  1. Pull fresh history from Bloomberg for the whole universe
  2. Cache it to data/prices.csv
  3. Run detection on the hand-picked CORE_PAIRS
  4. Auto-discover every other strongly-correlated pair and detect on those
  5. Score the latest economic surprises
  6. Write everything to incoherence.db and a dated log in logs/

Schedule it with Windows Task Scheduler (see README, "Making it automatic")
and check notebook 04_dashboard whenever you want to look.
"""

import datetime as dt
import os
import sys

import pandas as pd

import bbg
import db
import engine
from pairs_config import CORE_PAIRS, AUTO_DISCOVER, all_tickers

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)  # so data/ and logs/ always land next to this file


def log(handle, message):
    """Print to screen AND write to the log file."""
    print(message)
    handle.write(message + "\n")


def main():
    os.makedirs("logs", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    log_path = os.path.join("logs", f"{dt.date.today()}.txt")

    with open(log_path, "a") as f:
        log(f, f"===== run started {dt.datetime.now():%Y-%m-%d %H:%M} "
               f"(mock mode: {bbg.MOCK_MODE}) =====")

        # --- 1+2: pull and cache ---
        end = dt.date.today()
        start = end - dt.timedelta(days=365 * 3)
        prices = bbg.bdh(all_tickers(), "PX_LAST", start, end).ffill().dropna()
        prices.to_csv(os.path.join("data", "prices.csv"))
        log(f, f"Pulled {len(prices)} days x {len(prices.columns)} tickers")

        # --- 3: core pairs ---
        conn = db.get_connection()
        log(f, "--- core pairs ---")
        core_summary = engine.run_detection(prices, CORE_PAIRS, conn, verbose=False)

        # --- 4: auto-discovered pairs ---
        auto_summary = core_summary.iloc[0:0]
        if AUTO_DISCOVER:
            auto_pairs = engine.build_auto_pairs(prices, CORE_PAIRS)
            log(f, f"--- auto-discovery: {len(auto_pairs)} extra pairs ---")
            auto_summary = engine.run_detection(prices, auto_pairs, conn, verbose=False)

        # --- 5: economic surprises (same scoring as notebook 03) ---
        eco_tickers = ["NFP TCH Index", "CPI YOY Index", "CPUPXCHG Index",
                       "GDP CQOQ Index", "INJCJC Index", "CONSSENT Index",
                       "NAPMPMI Index", "RSTAMOM Index"]
        fields = ["ACTUAL_RELEASE", "BN_SURVEY_MEDIAN",
                  "BN_SURVEY_HIGH", "BN_SURVEY_LOW", "ECO_RELEASE_DT"]
        try:
            eco = bbg.bdp(eco_tickers, fields)
            for ticker in eco.index:
                actual = eco.loc[ticker, "ACTUAL_RELEASE"]
                median = eco.loc[ticker, "BN_SURVEY_MEDIAN"]
                high = eco.loc[ticker, "BN_SURVEY_HIGH"]
                low = eco.loc[ticker, "BN_SURVEY_LOW"]
                if None in (actual, median, high, low) or high == low:
                    continue
                score = (actual - median) / (high - low)
                db.insert_surprise(conn, ticker, eco.loc[ticker, "ECO_RELEASE_DT"],
                                   actual, median, round(score, 3))
            log(f, "Surprises updated")
        except Exception as e:  # don't let an eco hiccup kill the market run
            log(f, f"Surprise step failed (non-fatal): {e}")

        # --- 6: summary ---
        summary = pd.concat([core_summary, auto_summary])
        broken = summary[summary["state"] == "BROKEN"]
        new_events = summary["events"].sum()

        log(f, f"Monitored pairs : {len(summary)}")
        log(f, f"Currently BROKEN: {len(broken)}")
        for _, row in broken.iterrows():
            log(f, f"  !! {row['pair']}  (1m corr {row['corr_short']:+.2f}, "
                   f"1y corr {row['corr_long']:+.2f})")
        log(f, f"===== run finished, log: {log_path} =====")

    # exit code 1 if anything is broken -> Task Scheduler can flag the run
    return 1 if len(broken) > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
