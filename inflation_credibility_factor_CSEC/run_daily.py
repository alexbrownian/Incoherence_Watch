"""
run_daily.py - the factor pipeline in one command, Bloomberg-ready output.

    python run_daily.py

What it does, in order:
  1. Pull all component data from Bloomberg up to today
  2. Rebuild the factor with the adopted method (chosen_method.json)
  3. Fit AR(1), forecast 21 business days ahead
  4. Regenerate factor_live.png (factor + benchmark + fan + events)
  5. Write Terminal-ready files into bloomberg_upload/:
       factor_history.csv   - date,value    (for CDE <GO> import)
       factor_forecast.csv  - date,value    (the predicted path)
       cix_formula.txt      - refreshed frozen-constant CIX formula
  6. Append a summary line to logs/

Schedule it with Windows Task Scheduler (see README) and the Bloomberg
side stays current: re-import factor_history.csv in CDE to update the
custom field, paste cix_formula.txt into CIX when constants drift.
"""

import datetime as dt
import json
import os

import pandas as pd
import matplotlib
matplotlib.use("Agg")  # no window needed when run by the scheduler
import matplotlib.pyplot as plt

import bbg
import factor_lib as fl

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

HORIZON = 21


def main():
    os.makedirs("bloomberg_upload", exist_ok=True)
    os.makedirs("logs", exist_ok=True)

    # --- 1+2: pull and rebuild ---
    method = {"ewm_kind": "halflife", "z_on": "level", "oil": "CL1 Comdty"}
    if os.path.exists("chosen_method.json"):
        with open("chosen_method.json") as f:
            method = json.load(f)

    raw = bbg.bdh(fl.TICKERS, "PX_LAST",
                  pd.Timestamp(2025, 1, 1).date()).ffill().dropna()
    signed_z = fl.build_signed_zscores(raw, ewm_kind=method["ewm_kind"],
                                       z_on=method["z_on"], oil=method["oil"])
    factor = fl.build_factor(signed_z)

    # --- 3: forecast ---
    fdates, path, spread, info = fl.ar1_forecast(factor, HORIZON)

    # --- 4: chart ---
    benchmark = None
    if os.path.exists("benchmark.csv"):
        benchmark = pd.read_csv("benchmark.csv", index_col=0,
                                parse_dates=True).iloc[:, 0]

    fig, ax = plt.subplots(figsize=(13, 5.5))
    ax.plot(factor.index, factor.values, color="#1a1a5e", linewidth=1.1,
            label="factor (live)")
    if benchmark is not None:
        ax.plot(benchmark.index, benchmark.values, color="darkred",
                linewidth=0.9, alpha=0.5, label="benchmark")
    ax.plot(fdates, path, color="darkorange", linewidth=2,
            label=f"AR(1) forecast ({HORIZON}d)")
    ax.fill_between(fdates, path - spread, path + spread,
                    color="darkorange", alpha=0.25)
    ax.axhline(0, color="grey", linewidth=0.7)
    ax.set_ylim(-2.5, 2.5)
    fl.format_time_axis(ax)
    ax.set_title(f"Inflation Credibility Factor - live to "
                 f"{factor.index[-1].date()}")
    ax.legend(loc="upper left", fontsize=9)
    plt.tight_layout()
    plt.savefig("factor_live.png", dpi=120)
    plt.close(fig)

    # --- 5: Bloomberg-ready files ---
    factor.round(4).rename("value").rename_axis("date") \
        .to_csv(os.path.join("bloomberg_upload", "factor_history.csv"))
    pd.DataFrame({"date": fdates.date, "value": path.round(4)}) \
        .to_csv(os.path.join("bloomberg_upload", "factor_forecast.csv"),
                index=False)

    # refreshed CIX formula (same logic as make_cix_formula.py)
    frozen = {}
    components = fl.build_components(raw, oil=method["oil"])
    for name in components.columns:
        series = components[name]
        if method["ewm_kind"] == "span":
            ewm = series.ewm(span=21)
        elif method["ewm_kind"] == "com":
            ewm = series.ewm(com=21)
        else:
            ewm = series.ewm(halflife=21)
        frozen[name] = (round(float(ewm.mean().iloc[-1]), 4),
                        round(float(ewm.std().iloc[-1]), 4))

    m, s = frozen["fomc_hike"]
    terms = [f"((((100-FFQ6 Comdty)-FEDL01 Index)*100-{m})/{s})"]
    for name, ticker, sign in [("yield_30y", "USGG30YR Index", "-"),
                               ("infl_swap_5y", "USSWIT5 Curncy", "-"),
                               ("dxy", "DXY Curncy", "+"),
                               ("gold", "XAU Curncy", "-"),
                               ("oil", method["oil"], "-")]:
        m, s = frozen[name]
        terms.append(f"{sign}(({ticker}-{m})/{s})")
    formula = "(" + "".join(terms) + ")/6"

    with open(os.path.join("bloomberg_upload", "cix_formula.txt"), "w") as f:
        f.write(f"Refreshed {dt.date.today()} "
                f"(data through {raw.index[-1].date()})\n")
        f.write("Paste into CIXN <GO> expression box (tickers go inline):\n\n")
        f.write(formula + "\n")

    # --- 6: log ---
    line = (f"{dt.datetime.now():%Y-%m-%d %H:%M}  "
            f"factor={factor.iloc[-1]:+.2f}  "
            f"forecast_{HORIZON}d={path[-1]:+.2f}  "
            f"half_life={info['half_life']:.1f}d  mock={bbg.MOCK_MODE}")
    with open(os.path.join("logs", "factor_daily.log"), "a") as f:
        f.write(line + "\n")
    print(line)
    print("Wrote factor_live.png + bloomberg_upload/ (history, forecast, CIX)")


if __name__ == "__main__":
    main()
