# Inflation Credibility Factor

Builds a single market-based line measuring how much the market believes the
Fed will actually keep inflation under control, and forecasts where it goes
next. All data via the Bloomberg API.

---

## The method

Six market series, each turned into a **21-day exponentially weighted
z-score**, each given an economic **sign**, then combined as an
**equal-weighted average**:

| Component | Ticker | Sign | Credibility rises when... |
|---|---|---|---|
| July FOMC hike pricing | built from `FFQ6 Comdty` − `FEDL01 Index` | + | market prices the Fed to hike |
| 30y yields | `USGG30YR Index` | − | long-end stays anchored (yields fall) |
| 5y inflation swaps | `USSWIT5 Curncy` | − | expected inflation falls |
| Dollar | `DXY Curncy` | + | tight policy = strong dollar |
| Gold | `XAU Curncy` | − | less inflation-hedge demand |
| Oil | `CL1 Comdty` | − | inflation pressure eases |

Because the factor is a plain average of signed z-scores, any move in it
decomposes *exactly* into six component contributions — useful for asking
"who is driving this?" on any day.

## Run order

| # | Notebook | What it does |
|---|----------|--------------|
| 1 | `01_build_factor.ipynb` | Builds the factor the way we believe the original was made: six Bloomberg series -> signed 21d EWM z-scores -> equal-weighted average. The lesson notebook. |
| 2 | `02_validate_and_predict.ipynb` | Validates that method: digitized benchmark trace (checker only), scores 12 method variants and adopts the best, pulls the FOMC/CPI/NFP event calendar from the Bloomberg API and annotates the chart, decomposes the latest move, predicts with AR(1) on the **equal-weight** factor, and provides `live_refresh()` to pull to today and extrapolate. |
| 3 | `03_fit_chart_and_compare.ipynb` | Deliberately fits weights to the chart — with guard rails (ridge pull toward equal weights + out-of-sample validation that catches overfitting live). Predicts with the fitted factor, then compares both predictions: side-by-side plots and an overlay. Agreement = the method carries the signal. |
| 4 | `04_yields_vs_prediction.ipynb` | Three overlay charts — 2y, 5y and 10y Treasury yields each plotted against the factor and its forecast fan (dual axes), with FOMC/CPI/NFP annotations and per-tenor change-correlations. 2y = policy leg (moves WITH the factor), 10y = credibility-premium leg (moves AGAINST it in repricings). |

## Supporting files

| File | What it is |
|------|-----------|
| `make_cix_formula.py` | Generates the frozen-constant CIX formula for the Terminal (see below). |
| `factor_lib.py` | The construction as importable functions (with the method variants). Notebook 01 is the lesson; this is the source of truth for `live_refresh()`. |
| `bbg.py` | Bloomberg plumbing + mock mode. The mock plants a known spike-and-unwind pattern with known component shares, giving the notebooks ground truth to test against. |
| `signed_zscores.csv`, `factor.csv`, `benchmark.csv`, `events.csv`, `chosen_method.json`, `fitted_weights.json`, `forecast_*.csv` | Caches and adopted settings written by the notebooks (all gitignored; regenerated on each run). |
| `factor_recreation.png`, `factor_vs_benchmark_best.png`, `factor_live.png`, `factor_fitted_vs_equal.png`, `forecast_side_by_side.png`, `forecast_overlay.png` | The charts, re-saved on every run. |

## Making it a Bloomberg CIX

`python make_cix_formula.py` prints a paste-ready formula for CIX <GO>
(Custom Index). CIX can't compute rolling EWM z-scores, so the script
freezes today's EWM mean/std of each component into the formula as
constants - the resulting `.INFLCRED Index` tracks the true factor
closely and drifts slowly as vols change. Re-run the script every week
or two and refresh the formula. Once saved, the CIX works in GP, ALRT,
and via the API like any ticker.

## Tuning knobs

"21 day exponentially weighted" can be read as `halflife=21` (default here)
or `span=21` — one line to flip in notebook 01. The FOMC leg can be upgraded
from the FFQ6 futures proxy to meeting-dated OIS if entitled.

## Requirements

Same as the incoherence monitor: `pandas numpy matplotlib` + `blpapi` with a
logged-in Terminal. Without `blpapi` it runs on the synthetic mock data
(announced clearly at the top of each notebook).
