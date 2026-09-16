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

# The modern CIX editor (CIXN) takes FULL TICKERS inline in the formula -
# typing a ticker means "that security's last price" (see the on-screen
# examples like (GOOG US Equity + META US Equity)/2).
oil = method["oil"]
m, s = frozen["fomc_hike"]
terms = [f"((((100-FFQ6 Comdty)-FEDL01 Index)*100-{m})/{s})"]
for name, ticker, sign in [("yield_30y", "USGG30YR Index", "-"),
                           ("infl_swap_5y", "USSWIT5 Curncy", "-"),
                           ("dxy", "DXY Curncy", "+"),
                           ("gold", "XAU Curncy", "-"),
                           ("oil", oil, "-")]:
    m, s = frozen[name]
    terms.append(f"{sign}(({ticker}-{m})/{s})")

formula = "(" + "".join(terms) + ")/6"

print("=" * 70)
print("1) Terminal: CIXN <GO>  ->  1) Create")
print("2) Ticker: INFLCRED   Name: Inflation Credibility Factor")
print("3) Paste this into the big expression box:\n")
print(formula)
print()
print("4) Check the Preview Chart, then save. Ticker = .INFLCRED Index")
print("=" * 70)
print(f"(constants frozen from data through {raw.index[-1].date()};")
print(" re-run this script every week or two and re-paste)")


# ---------------------------------------------------------------------------
# ALTERNATIVE: the same formula expanded to LINEAR form (fewest parentheses,
# friendliest possible syntax for the CIX parser).
# Math: each leg sign*(x-m)/s/6 = (sign/(6s))*x - sign*m/(6s); the FOMC leg
# ((100-a-b)*100-m)/s/6 contributes -100/(6s) per futures/funds leg. All the
# constant pieces collapse into one number K.
# ---------------------------------------------------------------------------
def linear_formula(frozen, oil):
    K = 0.0
    coeffs = []  # (coefficient, ticker)

    m, s = frozen["fomc_hike"]
    K += (10000.0 - m) / (6 * s)
    coeffs.append((-100.0 / (6 * s), "FFQ6 Comdty"))
    coeffs.append((-100.0 / (6 * s), "FEDL01 Index"))

    for name, ticker, sign in [("yield_30y", "USGG30YR Index", -1),
                               ("infl_swap_5y", "USSWIT5 Curncy", -1),
                               ("dxy", "DXY Curncy", +1),
                               ("gold", "XAU Curncy", -1),
                               ("oil", oil, -1)]:
        m, s = frozen[name]
        coeffs.append((sign / (6 * s), ticker))
        K += -sign * m / (6 * s)

    parts = [f"{K:.6f}"]
    for c, ticker in coeffs:
        op = "+" if c >= 0 else "-"
        parts.append(f"{op}{abs(c):.6f}*{ticker}")
    return "".join(parts)


print()
print("ALTERNATIVE (same factor, linear form - simplest syntax):")
print()
print(linear_formula(frozen, method["oil"]))
