"""
make_cix_formula.py - generate a paste-ready Bloomberg CIX formula for the
Inflation Credibility Factor.

    python make_cix_formula.py

WHY THIS EXISTS
---------------
CIX (Custom Index, CIX <GO>) only does point-in-time arithmetic on other
tickers - it cannot compute our rolling 21d exponentially weighted
mean/std. The workaround: freeze today's EWM mean (m) and std (s) of each
component into the formula as plain numbers, so each leg becomes
    sign * (price - m) / s / 6
which CIX handles fine. The CIX then tracks the true factor closely and
drifts slowly as vols change -> RE-RUN THIS SCRIPT every week or two and
paste the refreshed formula into your CIX.

Note: this freeze only works for the z-on-LEVEL construction. If your
chosen_method.json says z_on="change", CIX cannot represent it (it has no
access to yesterday's price).
"""

import json
import os

import pandas as pd

import bbg
import factor_lib as fl

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# use the adopted method's EWM settings (fall back to defaults)
method = {"ewm_kind": "halflife", "z_on": "level", "oil": "CL1 Comdty"}
if os.path.exists("chosen_method.json"):
    with open("chosen_method.json") as f:
        method = json.load(f)

if method["z_on"] != "level":
    print("WARNING: adopted method z-scores CHANGES - CIX cannot do that.")
    print("The formula below uses the level version as the closest stand-in.")

raw = bbg.bdh(fl.TICKERS, "PX_LAST",
              pd.Timestamp(2025, 1, 1).date()).ffill().dropna()
components = fl.build_components(raw, oil=method["oil"])

# today's EWM mean and std per component (the numbers we freeze)
frozen = {}
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

# CIX lets you assign each security a letter, then write math in letters.
# fomc_hike is built from two tickers, so it uses two letters (a, b).
letters = {"FFQ6 Comdty": "a", "FEDL01 Index": "b",
           "USGG30YR Index": "c", "USSWIT5 Curncy": "d",
           "DXY Curncy": "e", "XAU Curncy": "f", method["oil"]: "g"}

m, s = frozen["fomc_hike"]
terms = [f"+((((100-a)-b)*100-{m})/{s})"]      # fomc_hike, sign +
for name, letter, sign in [("yield_30y", "c", "-"),
                           ("infl_swap_5y", "d", "-"),
                           ("dxy", "e", "+"),
                           ("gold", "f", "-"),
                           ("oil", "g", "-")]:
    m, s = frozen[name]
    terms.append(f"{sign}(({letter}-{m})/{s})")

formula = "(" + "".join(terms) + ")/6"

print("=" * 70)
print("1) On the Terminal: CIX <GO>  ->  Create  ->  Custom Index")
print("2) Suggested name: .INFLCRED  (becomes ticker  .INFLCRED Index)")
print("3) Add these securities and give them these letters:\n")
for ticker, letter in letters.items():
    print(f"     {letter} = {ticker}")
print("\n4) Paste this formula:\n")
print(formula)
print()
print("5) Save. Now GP <GO>, ALRT, and even this project's bbg.bdh()")
print("   can chart/pull  .INFLCRED Index  like any other ticker.")
print("=" * 70)
print(f"(constants frozen from data through {raw.index[-1].date()};")
print(" re-run this script every week or two and update the formula)")
