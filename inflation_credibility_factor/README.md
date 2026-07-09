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
| 1 | `01_build_factor.ipynb` | Pulls the 6 series from Bloomberg, builds the FOMC-pricing leg from fed funds futures, computes the 21d EWM z-scores, combines into the factor, plots it plus a per-component contribution stack. Caches results to CSV. |
| 2 | `02_validate_and_predict.ipynb` | **Match:** overlays the factor on a benchmark trace digitized from the target chart (editable anchor points), scores 12 method variants (halflife/span/com x level/change x WTI/Brent) and adopts the best — model *selection*, not curve-fitting; weights stay equal, with a regularized weight fit used only as a diagnostic. **Decompose:** attributes the latest peak-to-now move to components (checked against planted ground truth in mock mode). **Predict:** AR(1) fan chart, 3-month horizon, plus a `live_refresh()` that re-pulls to today and extrapolates. |

## Supporting files

| File | What it is |
|------|-----------|
| `factor_lib.py` | The construction as importable functions (with the method variants). Notebook 01 is the lesson; this is the source of truth for `live_refresh()`. |
| `bbg.py` | Bloomberg plumbing + mock mode. The mock plants a known spike-and-unwind pattern with known component shares, giving the notebooks ground truth to test against. |
| `signed_zscores.csv`, `factor.csv` | Caches written by notebook 01, read by notebook 02. |
| `factor_recreation.png`, `factor_forecast.png` | The charts, saved on every run. |

## Tuning knobs

"21 day exponentially weighted" can be read as `halflife=21` (default here)
or `span=21` — one line to flip in notebook 01. The FOMC leg can be upgraded
from the FFQ6 futures proxy to meeting-dated OIS if entitled.

## Requirements

Same as the incoherence monitor: `pandas numpy matplotlib` + `blpapi` with a
logged-in Terminal. Without `blpapi` it runs on the synthetic mock data
(announced clearly at the top of each notebook).
