"""
pairs_config.py - what the monitor watches.

TWO LAYERS OF MONITORING
------------------------
1. CORE_PAIRS - hand-picked relationships where we KNOW the sign it should
   have (SPX down -> VIX up). These carry an economic prior.

2. AUTO-DISCOVERY - every possible pair from the UNIVERSE below whose
   1-year correlation of daily moves is strong (|corr| >= MIN_AUTO_CORR).
   For those, the "baseline" is simply the sign of their own long-run
   correlation: "whatever this pair has done for the last year is normal,
   flag when it stops". This is how we catch incoherence in relationships
   nobody thought to hand-pick. The discovery logic lives in engine.py.

TO ADD A TICKER: add one line to UNIVERSE with its move transform:
    "pct"  -> percent change (prices, FX, equity indices, commodities)
    "diff" -> point change   (yields, spreads, VIX/MOVE, breakevens)
Auto-discovery picks it up automatically on the next run.
"""

# ---------------------------------------------------------------------------
# The universe: ticker -> how to compute its daily move
# ---------------------------------------------------------------------------
UNIVERSE = {
    # equities
    "SPX Index": "pct",          # S&P 500
    "NDX Index": "pct",          # Nasdaq 100
    "RTY Index": "pct",          # Russell 2000
    "SX5E Index": "pct",         # Euro Stoxx 50
    "NKY Index": "pct",          # Nikkei 225
    "MXEF Index": "pct",         # MSCI Emerging Markets
    # volatility
    "VIX Index": "diff",         # equity vol
    "MOVE Index": "diff",        # rates vol
    # credit
    "CDX HY CDSI GEN 5Y SPRD Corp": "diff",   # US high yield CDS spread
    "CDX IG CDSI GEN 5Y Corp": "diff",        # US investment grade CDS spread
    "ITRX XOVER CDSI GEN 5Y Corp": "diff",    # European crossover CDS spread
    "LF98OAS Index": "diff",     # US HY cash OAS
    "LUACOAS Index": "diff",     # US IG cash OAS
    # rates
    "USGG2YR Index": "diff",     # US 2y yield
    "USGG10YR Index": "diff",    # US 10y yield
    "USGG30YR Index": "diff",    # US 30y yield
    "USGGBE10 Index": "diff",    # US 10y breakeven
    "USGGT10Y Index": "diff",    # US 10y real yield
    "GDBR10 Index": "diff",      # German 10y yield
    # FX
    "DXY Curncy": "pct",         # dollar index
    "EURUSD Curncy": "pct",
    "USDJPY Curncy": "pct",
    "USDCAD Curncy": "pct",
    "AUDUSD Curncy": "pct",
    "USDMXN Curncy": "pct",
    # commodities
    "CL1 Comdty": "pct",         # WTI crude
    "CO1 Comdty": "pct",         # Brent crude
    "HG1 Comdty": "pct",         # copper
    "XAU Curncy": "pct",         # gold
    "XAG Curncy": "pct",         # silver
}

# auto-discovery settings (used by engine.py)
MIN_AUTO_CORR = 0.40   # only monitor auto-pairs at least this correlated
AUTO_DISCOVER = True   # set False to only monitor CORE_PAIRS


def _pair(name, a, b, sign, desc):
    """Small helper so the list below stays readable."""
    return {
        "name": name,
        "ticker_a": a, "ticker_b": b,
        "transform_a": UNIVERSE[a], "transform_b": UNIVERSE[b],
        "expected_sign": sign, "description": desc,
    }


# ---------------------------------------------------------------------------
# Hand-picked pairs with an economic prior on the sign
# ---------------------------------------------------------------------------
CORE_PAIRS = [
    _pair("Equity vs CDX HY", "SPX Index", "CDX HY CDSI GEN 5Y SPRD Corp", -1,
          "Equities down should mean HY spreads WIDEN. Stocks falling with "
          "spreads tightening is incoherent."),
    _pair("Equity vs CDX IG", "SPX Index", "CDX IG CDSI GEN 5Y Corp", -1,
          "Same logic in investment grade - breaks here matter even more."),
    _pair("Equity vs HY cash OAS", "SPX Index", "LF98OAS Index", -1,
          "Cash bond version of the credit check."),
    _pair("EU equity vs Crossover", "SX5E Index", "ITRX XOVER CDSI GEN 5Y Corp", -1,
          "European version: Stoxx down should widen iTraxx Crossover."),
    _pair("Equity vs VIX", "SPX Index", "VIX Index", -1,
          "Equities down should mean vol UP."),
    _pair("Rates vol vs Equity vol", "MOVE Index", "VIX Index", +1,
          "Vol markets usually stress together; MOVE spiking while VIX "
          "sleeps (or vice versa) = one market is not getting the memo."),
    _pair("Rates vs Equity", "USGG10YR Index", "SPX Index", 0,
          "Regime pair: +ve in growth-driven markets, -ve in inflation-"
          "driven ones. We flag breaks from its OWN recent regime."),
    _pair("Rates vs USDJPY", "USGG10YR Index", "USDJPY Curncy", +1,
          "Higher US yields normally push USDJPY up."),
    _pair("Bunds vs Treasuries", "GDBR10 Index", "USGG10YR Index", +1,
          "Global duration usually trades together."),
    _pair("Oil vs USDCAD", "CL1 Comdty", "USDCAD Curncy", -1,
          "Oil up = CAD stronger = USDCAD down."),
    _pair("Oil vs 10y breakevens", "CL1 Comdty", "USGGBE10 Index", +1,
          "Oil up normally lifts inflation breakevens."),
    _pair("Copper vs AUDUSD", "HG1 Comdty", "AUDUSD Curncy", +1,
          "Copper up = commodity-currency AUD stronger."),
    _pair("Gold vs 10y real yield", "XAU Curncy", "USGGT10Y Index", -1,
          "Higher real yields normally hurt gold."),
    _pair("Gold vs Silver", "XAU Curncy", "XAG Curncy", +1,
          "Precious metals normally move together."),
    _pair("EM equity vs Dollar", "MXEF Index", "DXY Curncy", -1,
          "Strong dollar is normally a headwind for EM."),
    _pair("Risk FX vs Equity", "USDMXN Curncy", "SPX Index", -1,
          "Risk-off pushes USDMXN up while equities fall."),
]

# kept for backwards compatibility - notebooks 01/02 loop over PAIRS
PAIRS = CORE_PAIRS


def all_tickers():
    """Every ticker we need to pull = the whole universe."""
    return list(UNIVERSE.keys())
