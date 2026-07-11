"""
factor_lib.py - the factor construction as reusable functions.

Notebook 01 teaches the base logic step by step; this file is the
importable version, extended with METHOD VARIANTS so notebook 02 can test
different legitimate readings of "21 day exponentially weighted z-score"
against a benchmark chart and pick the best one.

The variants (all defensible, none of them curve-fitting):
  ewm_kind : "halflife", "span", or "com"  - three ways to read "21 day"
  z_on     : "level" or "change"           - z-score the level, or the 1d change
  oil      : "CL1 Comdty" (WTI) or "CO1 Comdty" (Brent)

If you change the construction itself, change it HERE and re-run both
notebooks.
"""

import pandas as pd

# raw Bloomberg series needed (both oil contracts; FFQ6+FEDL01 = FOMC leg)
TICKERS = ["USGG30YR Index", "USSWIT5 Curncy", "DXY Curncy",
           "XAU Curncy", "CL1 Comdty", "CO1 Comdty",
           "FFQ6 Comdty", "FEDL01 Index"]

# credibility sign of each component
SIGNS = {"fomc_hike": +1, "yield_30y": -1, "infl_swap_5y": -1,
         "dxy": +1, "gold": -1, "oil": -1}


def ewm_zscore(series, ewm_kind="halflife", window=21, z_on="level"):
    """
    Exponentially weighted z-score.

    ewm_kind picks how "21 day" is interpreted:
      "halflife" - weight halves every 21 days (slowest fade)
      "span"     - like a 21-day EMA (fastest fade)
      "com"      - center of mass 21 days (in between)
    z_on="change" z-scores the day-over-day change instead of the level.
    """
    x = series.diff() if z_on == "change" else series

    if ewm_kind == "halflife":
        ewm = x.ewm(halflife=window)
    elif ewm_kind == "span":
        ewm = x.ewm(span=window)
    else:  # "com"
        ewm = x.ewm(com=window)

    return (x - ewm.mean()) / ewm.std()


def build_components(raw, oil="CL1 Comdty"):
    """Raw Bloomberg levels -> the six named component series."""
    hike_bp = ((100.0 - raw["FFQ6 Comdty"]) - raw["FEDL01 Index"]) * 100.0
    return pd.DataFrame({
        "fomc_hike": hike_bp,
        "yield_30y": raw["USGG30YR Index"],
        "infl_swap_5y": raw["USSWIT5 Curncy"],
        "dxy": raw["DXY Curncy"],
        "gold": raw["XAU Curncy"],
        "oil": raw[oil],
    })


def build_signed_zscores(raw, ewm_kind="halflife", window=21,
                         z_on="level", oil="CL1 Comdty"):
    """Raw levels -> signed z-scores (positive = credibility up)."""
    components = build_components(raw, oil=oil)
    zscores = pd.DataFrame({
        name: ewm_zscore(components[name], ewm_kind, window, z_on)
        for name in components.columns
    }).dropna()
    return pd.DataFrame({name: zscores[name] * SIGNS[name]
                         for name in zscores.columns})


def build_factor(signed_z, weights=None):
    """
    Combine signed z-scores into the factor.
    weights: dict component -> weight (should sum to 1). None = equal 1/6.
    The METHOD is equal weights; passing custom weights is for diagnostics.
    """
    if weights is None:
        return signed_z.mean(axis=1)
    factor = 0.0
    for name in signed_z.columns:
        factor = factor + signed_z[name] * weights[name]
    return factor


def format_time_axis(ax):
    """Monthly major ticks, weekly minor gridlines, readable labels."""
    import matplotlib.dates as mdates
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b-%y"))
    ax.xaxis.set_minor_locator(mdates.WeekdayLocator(byweekday=0))  # Mondays
    ax.grid(which="major", axis="x", alpha=0.25)
    ax.grid(which="minor", axis="x", alpha=0.08)
    ax.grid(axis="y", alpha=0.2)
    for label in ax.get_xticklabels():
        label.set_rotation(45)
        label.set_fontsize(8)
