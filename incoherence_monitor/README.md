# Incoherence Monitor

Watches cross-asset relationships that "should" hold (equity down → credit
spreads wider, equity down → VIX up, oil up → CAD stronger...) and logs to a
database whenever one **breaks** (the logic flips) and whenever it **reverts**
(the old logic comes back). Also scores economic data surprises and headline
tone.

All market data comes from the Bloomberg Desktop API (`blpapi`).

---

## Run order

| # | Notebook | What it does |
|---|----------|--------------|
| 0 | `00_setup_and_connection.ipynb` | Checks Bloomberg connectivity. Explains how blpapi works. Run once. |
| 1 | `01_pull_market_data.ipynb` | Pulls 3y of daily history for every monitored ticker, cleans it, caches to `data/prices.csv`. Run daily (or whenever you want fresh data). |
| 2 | `02_detect_incoherence.ipynb` | The engine. Rolling 21d vs 252d correlations, breakdown/reversion state machine, writes events to `incoherence.db` (SQLite). Run after 01. |
| 3 | `03_surprises_and_sentiment.ipynb` | Scores latest economic releases (actual vs analyst survey) and headline tone. Independent of 01/02. |
| 4 | `04_dashboard.ipynb` | Read-only view: current state of every pair, recent events, biggest surprises, event timeline. Run last. |
| 5 | `05_auto_discovery.ipynb` | Scales detection beyond hand-picked pairs: correlation matrix of the whole ~30-ticker universe, auto-keeps every pair with \|corr\| ≥ 0.40, runs the same state machine on all of them. |

## Supporting files

| File | What it is |
|------|-----------|
| `bbg.py` | All Bloomberg request/response code. Falls back to **mock mode** (synthetic data with a planted breakdown) when `blpapi` isn't installed, so you can test the logic anywhere. |
| `pairs_config.py` | `UNIVERSE` (every ticker + its move transform) and `CORE_PAIRS` (hand-picked relationships with a sign prior). **To monitor a new ticker, add ONE line to UNIVERSE** — auto-discovery does the rest. |
| `engine.py` | The detection logic as an importable module — the source of truth used by `run_daily.py` and notebook 05. Notebook 02 is the step-by-step lesson version of this file. |
| `run_daily.py` | The whole monitor in one command: pull → detect (core + auto pairs) → surprises → database + dated log in `logs/`. This is what you schedule. |
| `db.py` | SQLite helper. Creates/opens `incoherence.db` with three tables: `events`, `status`, `surprises`. |
| `data/prices.csv` | Price cache written by notebook 01 / `run_daily.py`. |
| `incoherence.db` | The event database. Delete it to start fresh. |

## Making it automatic (Windows Task Scheduler)

`run_daily.py` needs your PC on with the Bloomberg Terminal logged in
(the Desktop API only works locally), so schedule it for a time you're
normally logged in — e.g. weekdays 17:30 after US close.

One-time setup, in a Command Prompt (adjust the folder path):

```
schtasks /Create /TN "IncoherenceMonitor" /SC WEEKLY /D MON,TUE,WED,THU,FRI ^
  /ST 17:30 /TR "cmd /c cd /d C:\Users\alexd\Desktop\GIC\Incoherence\incoherence_monitor && python run_daily.py"
```

Or via the GUI: Task Scheduler → Create Basic Task → Daily 17:30 →
Start a program → Program: `python`, Arguments: `run_daily.py`,
Start in: this folder.

Each run appends to `logs/YYYY-MM-DD.txt` and exits with code 1 if any
relationship is currently BROKEN (visible in Task Scheduler's "Last Run
Result"). Your morning routine becomes: open `04_dashboard.ipynb`, run all.

## How detection works (one paragraph)

Daily moves (% for prices, points for yields/spreads) → 21-day rolling
correlation ("now") vs 252-day rolling correlation ("normal") → multiply the
21-day number by the sign the relationship should have, so healthy is always
positive → if it sits below −0.15 for 3 straight days, log a **breakdown**;
once broken, above +0.15 for 3 straight days logs a **reversion**. Tuning
knobs are at the top of `engine.py` (notebook 02 teaches the same logic).

## Requirements

```
pip install pandas numpy matplotlib
pip install blpapi --index-url=https://blpapi.bloomberg.com/repository/releases/python/simple/
```

Bloomberg Terminal must be running and logged in. Without `blpapi` everything
runs in mock mode (clearly announced in every notebook).

## The notebooks are saved WITH mock-mode outputs

So you can see what each cell produces before running anything. The mock data
has a deliberate breakdown planted (equity falls while credit tightens and
vol drops) — you'll see it caught in notebooks 02, 04 and 05.
