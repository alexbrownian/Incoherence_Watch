# incoherence-watch

Bloomberg-powered monitors for when markets stop making sense.

| Folder | What it does |
|---|---|
| `incoherence_monitor/` | Watches ~30 tickers / 240+ cross-asset relationships (equity vs credit, equity vs vol, oil vs CAD...) and logs to SQLite whenever a relationship **breaks** (correlation flips against its normal sign) or **reverts**. Includes economic-surprise scoring, headline-tone scoring, a dashboard, and `run_daily.py` for scheduled automation. |
| `inflation_credibility_factor/` | Builds a market-based "Inflation Credibility Factor" (21d exponential z-score of July FOMC pricing, 30y yields, 5y inflation swaps, DXY, gold and oil, equal-weighted with economic signs), decomposes its moves into component contributions, and forecasts it with an AR(1) fan chart. |

Each folder has its own README with run order and file-by-file explanations.

## Data & requirements

All market data comes from the Bloomberg Desktop API (`blpapi`) — a logged-in
Terminal is required for real data. Without it, everything runs in a clearly
announced **mock mode** with synthetic data, so the logic can be developed and
tested anywhere.

```
pip install pandas numpy matplotlib
pip install blpapi --index-url=https://blpapi.bloomberg.com/repository/releases/python/simple/
```
