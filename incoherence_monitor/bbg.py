"""
bbg.py - a small, simple helper around the Bloomberg Desktop API (blpapi).

HOW THIS FILE WORKS
-------------------
1. We try to `import blpapi`. That package only exists on a machine where you
   installed Bloomberg's Python API (pip install blpapi --index-url=https://blpapi.bloomberg.com/repository/releases/python/simple/).
2. If the import works, every function below sends real requests to the
   Bloomberg Terminal running on your machine (localhost, port 8194).
3. If the import fails, MOCK_MODE becomes True and the same functions return
   *synthetic* data instead. This lets you test all the notebook logic
   without a Terminal. The mock data has a deliberate "breakdown" period
   built in (equity falls but credit tightens) so the detection notebook
   has something to find.

The two functions you will use everywhere:
    bdh(tickers, field, start, end)  -> historical daily data (like Excel BDH)
    bdp(tickers, fields)             -> latest single values  (like Excel BDP)
"""

import datetime as dt

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Step 1: detect whether Bloomberg is available
# ---------------------------------------------------------------------------
try:
    import blpapi  # noqa: F401
    MOCK_MODE = False
except ImportError:
    blpapi = None
    MOCK_MODE = True


# ---------------------------------------------------------------------------
# Step 2: real Bloomberg plumbing (only used when MOCK_MODE is False)
# ---------------------------------------------------------------------------
def _start_session():
    """
    Open a connection to the Bloomberg Terminal on this machine.

    The Desktop API always lives at localhost:8194. If this fails, the
    usual reason is that the Terminal is not running / not logged in.
    """
    options = blpapi.SessionOptions()
    options.setServerHost("localhost")
    options.setServerPort(8194)

    session = blpapi.Session(options)
    if not session.start():
        raise ConnectionError(
            "Could not start Bloomberg session. Is the Terminal running and logged in?"
        )
    if not session.openService("//blp/refdata"):
        raise ConnectionError("Could not open the //blp/refdata service.")
    return session


def _bdh_real(tickers, field, start, end):
    """
    Send a HistoricalDataRequest to Bloomberg, one ticker at a time,
    and stitch the answers into one DataFrame (dates x tickers).

    Doing one ticker per request is slightly slower but MUCH easier to
    read and debug than parsing a multi-ticker response.
    """
    session = _start_session()
    service = session.getService("//blp/refdata")
    all_series = {}

    for ticker in tickers:
        request = service.createRequest("HistoricalDataRequest")
        request.getElement("securities").appendValue(ticker)
        request.getElement("fields").appendValue(field)
        request.set("startDate", start.strftime("%Y%m%d"))
        request.set("endDate", end.strftime("%Y%m%d"))
        request.set("periodicitySelection", "DAILY")

        session.sendRequest(request)

        dates, values = [], []
        done = False
        while not done:
            event = session.nextEvent(500)  # wait up to 500 ms
            for msg in event:
                if msg.hasElement("securityData"):
                    field_data = msg.getElement("securityData").getElement("fieldData")
                    for i in range(field_data.numValues()):
                        row = field_data.getValueAsElement(i)
                        if row.hasElement(field):
                            dates.append(row.getElementAsDatetime("date"))
                            values.append(row.getElementAsFloat(field))
            if event.eventType() == blpapi.Event.RESPONSE:
                done = True  # RESPONSE means this request is finished

        all_series[ticker] = pd.Series(values, index=pd.to_datetime(dates))

    session.stop()
    return pd.DataFrame(all_series).sort_index()


def _bdp_real(tickers, fields):
    """
    Send a ReferenceDataRequest ('latest value' request) to Bloomberg.
    Returns a DataFrame: one row per ticker, one column per field.
    """
    session = _start_session()
    service = session.getService("//blp/refdata")

    request = service.createRequest("ReferenceDataRequest")
    for ticker in tickers:
        request.getElement("securities").appendValue(ticker)
    for f in fields:
        request.getElement("fields").appendValue(f)

    session.sendRequest(request)

    rows = {}
    done = False
    while not done:
        event = session.nextEvent(500)
        for msg in event:
            if msg.hasElement("securityData"):
                sec_data = msg.getElement("securityData")
                for i in range(sec_data.numValues()):
                    sec = sec_data.getValueAsElement(i)
                    ticker = sec.getElementAsString("security")
                    field_data = sec.getElement("fieldData")
                    row = {}
                    for f in fields:
                        if field_data.hasElement(f):
                            row[f] = field_data.getElement(f).getValue()
                        else:
                            row[f] = None
                    rows[ticker] = row
        if event.eventType() == blpapi.Event.RESPONSE:
            done = True

    session.stop()
    return pd.DataFrame.from_dict(rows, orient="index")


# ---------------------------------------------------------------------------
# Step 3: mock data (only used when MOCK_MODE is True)
# ---------------------------------------------------------------------------
# Each ticker gets a "beta" to one of two common factors:
#   MKT = a risk-on/risk-off factor (equities up = risk-on)
#   OIL = an oil factor
# That is how real markets get their cross-correlations, so faking it this
# way gives realistic-looking relationships.
#
# (beta_mkt, beta_oil, start_level, daily_vol, kind)
#   kind "price" -> level moves in % terms (like an index or FX)
#   kind "level" -> level moves in absolute points (like a yield or spread)
_MOCK_CONFIG = {
    # equities
    "SPX Index":                     (+1.0, 0.0, 5000.0, 0.010, "price"),
    "NDX Index":                     (+1.1, 0.0, 18000.0, 0.013, "price"),
    "RTY Index":                     (+1.0, 0.0, 2100.0, 0.013, "price"),
    "SX5E Index":                    (+0.9, 0.0, 4900.0, 0.010, "price"),
    "NKY Index":                     (+0.8, 0.0, 39000.0, 0.011, "price"),
    "MXEF Index":                    (+0.9, 0.0, 1050.0, 0.010, "price"),
    # volatility
    "VIX Index":                     (-1.0, 0.0, 16.0,   0.900, "level"),
    "MOVE Index":                    (-0.7, 0.0, 100.0,  2.500, "level"),
    # credit
    "CDX HY CDSI GEN 5Y SPRD Corp":  (-1.0, 0.0, 350.0,  4.000, "level"),
    "CDX IG CDSI GEN 5Y Corp":       (-0.9, 0.0, 55.0,   1.200, "level"),
    "ITRX XOVER CDSI GEN 5Y Corp":   (-0.9, 0.0, 320.0,  4.000, "level"),
    "LF98OAS Index":                 (-1.0, 0.0, 3.20,   0.040, "level"),
    "LUACOAS Index":                 (-0.9, 0.0, 1.00,   0.015, "level"),
    # rates
    "USGG2YR Index":                 (+0.4, 0.0, 4.50,   0.040, "level"),
    "USGG10YR Index":                (+0.5, 0.0, 4.20,   0.045, "level"),
    "USGG30YR Index":                (+0.4, 0.0, 4.60,   0.040, "level"),
    "USGGBE10 Index":                (+0.1, 0.6, 2.30,   0.025, "level"),
    "USGGT10Y Index":                (+0.5, 0.0, 1.90,   0.040, "level"),
    "GDBR10 Index":                  (+0.4, 0.0, 2.50,   0.035, "level"),
    # FX
    "DXY Curncy":                    (+0.3, 0.0, 104.0,  0.004, "price"),
    "EURUSD Curncy":                 (-0.3, 0.0, 1.08,   0.005, "price"),
    "USDJPY Curncy":                 (+0.5, 0.0, 155.0,  0.006, "price"),
    "USDCAD Curncy":                 (-0.1, -0.8, 1.37,  0.004, "price"),
    "AUDUSD Curncy":                 (+0.4, 0.3, 0.66,   0.006, "price"),
    "USDMXN Curncy":                 (-0.6, 0.0, 17.2,   0.007, "price"),
    # commodities
    "CL1 Comdty":                    (+0.2, 1.0, 75.0,   0.018, "price"),
    "CO1 Comdty":                    (+0.2, 1.0, 79.0,   0.017, "price"),
    "HG1 Comdty":                    (+0.3, 0.4, 4.30,   0.013, "price"),
    "XAU Curncy":                    (-0.3, 0.0, 2400.0, 0.009, "price"),
    "XAG Curncy":                    (-0.3, 0.0, 29.0,   0.016, "price"),
}

# During this window (measured in business days from the END of the sample),
# credit and vol betas FLIP sign: equity sells off but credit tightens.
# This is the "incoherence" the detection notebook should catch.
_BREAK_START_DAYS_AGO = 120
_BREAK_END_DAYS_AGO = 55
_FLIPPED_TICKERS = ["CDX HY CDSI GEN 5Y SPRD Corp", "CDX IG CDSI GEN 5Y Corp",
                    "ITRX XOVER CDSI GEN 5Y Corp", "LF98OAS Index",
                    "LUACOAS Index", "VIX Index", "MOVE Index"]


def _bdh_mock(tickers, field, start, end):
    """Build synthetic daily levels for the requested tickers."""
    rng = np.random.default_rng(42)  # fixed seed -> same data every run
    dates = pd.bdate_range(start, end)
    n = len(dates)

    # two common factors, standard normal daily shocks
    mkt = rng.standard_normal(n)
    oil = rng.standard_normal(n)

    # positions of the planted breakdown window
    break_start = max(0, n - _BREAK_START_DAYS_AGO)
    break_end = max(0, n - _BREAK_END_DAYS_AGO)

    out = {}
    for ticker in tickers:
        if ticker in _MOCK_CONFIG:
            beta_mkt, beta_oil, level0, vol, kind = _MOCK_CONFIG[ticker]
        else:
            # unknown ticker: random but repeatable behaviour
            trng = np.random.default_rng(abs(hash(ticker)) % (2**32))
            beta_mkt, beta_oil = trng.uniform(-1, 1), 0.0
            level0, vol, kind = 100.0, 0.01, "price"

        beta = np.full(n, beta_mkt)
        if ticker in _FLIPPED_TICKERS:
            beta[break_start:break_end] = -beta_mkt  # the incoherence!

        noise = rng.standard_normal(n) * 0.5
        shocks = (beta * mkt + beta_oil * oil + noise) * vol

        if kind == "price":
            levels = level0 * np.cumprod(1.0 + shocks)
        else:  # "level": add absolute changes
            levels = level0 + np.cumsum(shocks)

        out[ticker] = pd.Series(levels, index=dates)

    return pd.DataFrame(out)


def _bdp_mock(tickers, fields):
    """Fake 'latest value' data, used by the surprise notebook."""
    rng = np.random.default_rng(7)
    rows = {}
    for ticker in tickers:
        survey = round(rng.uniform(0.5, 5.0), 1)
        actual = round(survey + rng.normal(0, 0.4), 1)
        row = {
            "ACTUAL_RELEASE": actual,
            "BN_SURVEY_MEDIAN": survey,
            "BN_SURVEY_HIGH": round(survey + 0.5, 1),
            "BN_SURVEY_LOW": round(survey - 0.5, 1),
            "ECO_RELEASE_DT": dt.date.today().strftime("%Y%m%d"),
            "NAME": ticker.replace(" Index", ""),
        }
        rows[ticker] = {f: row.get(f) for f in fields}
    return pd.DataFrame.from_dict(rows, orient="index")


# ---------------------------------------------------------------------------
# Step 4: the public functions the notebooks call
# ---------------------------------------------------------------------------
def bdh(tickers, field="PX_LAST", start=None, end=None):
    """
    Historical daily data. Returns a DataFrame: rows = dates, cols = tickers.

    Example:
        prices = bdh(["SPX Index", "VIX Index"], "PX_LAST",
                     start=dt.date(2023, 1, 1), end=dt.date.today())
    """
    if end is None:
        end = dt.date.today()
    if start is None:
        start = end - dt.timedelta(days=365 * 3)

    if MOCK_MODE:
        return _bdh_mock(tickers, field, start, end)
    return _bdh_real(tickers, field, start, end)


def bdp(tickers, fields):
    """
    Latest values for a list of tickers and fields.
    Returns a DataFrame: rows = tickers, cols = fields.
    """
    if MOCK_MODE:
        return _bdp_mock(tickers, fields)
    return _bdp_real(tickers, fields)
