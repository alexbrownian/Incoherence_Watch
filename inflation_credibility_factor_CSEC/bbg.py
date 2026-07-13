"""
bbg.py - Bloomberg Desktop API helper for the Inflation Credibility Factor.

Same design as the incoherence_monitor version:
- `blpapi` installed + Terminal running  -> real Bloomberg data
- otherwise MOCK_MODE = True             -> synthetic data

THE MOCK DATA HERE IS SPECIAL
-----------------------------
All six components are driven by one hidden "credibility" path that
oscillates, SPIKES at the June 2026 FOMC, then UNWINDS into early July -
with each component's share of the unwind planted at a known value
(_UNWIND_SHARES below: 30y 31%, dollar 17%, 5y swaps 17%, FOMC 16%,
oil 16%, gold 3%).

That gives the notebooks ground truth: if the factor construction and the
decomposition code recover this shape and roughly those shares, the METHOD
is right, and the only remaining step is swapping in real Bloomberg data.
"""
import datetime as dt

import numpy as np
import pandas as pd

try:
    import blpapi  # noqa: F401
    MOCK_MODE = False
except ImportError:
    blpapi = None
    MOCK_MODE = True


# ---------------------------------------------------------------------------
# Real Bloomberg plumbing (identical to incoherence_monitor/bbg.py)
# ---------------------------------------------------------------------------
def _start_session():
    options = blpapi.SessionOptions()
    options.setServerHost("localhost")
    options.setServerPort(8194)
    session = blpapi.Session(options)
    if not session.start():
        raise ConnectionError("Could not start Bloomberg session. Terminal running?")
    if not session.openService("//blp/refdata"):
        raise ConnectionError("Could not open //blp/refdata.")
    return session


_SESSION = None  # one shared connection, reused across every call


def _get_session():
    """Open the Bloomberg session once and reuse it (much faster)."""
    global _SESSION
    if _SESSION is None:
        _SESSION = _start_session()
    return _SESSION


def _bdh_real(tickers, field, start, end):
    """
    ONE HistoricalDataRequest for ALL tickers at once (10-20x faster than
    one request per ticker). Bloomberg streams the answer back one
    security per message; we collect them until the final RESPONSE event.
    """
    import time

    session = _get_session()
    service = session.getService("//blp/refdata")

    request = service.createRequest("HistoricalDataRequest")
    for ticker in tickers:
        request.getElement("securities").appendValue(ticker)
    request.getElement("fields").appendValue(field)
    request.set("startDate", start.strftime("%Y%m%d"))
    request.set("endDate", end.strftime("%Y%m%d"))
    request.set("periodicitySelection", "DAILY")
    session.sendRequest(request)

    all_series = {}
    last_progress = time.time()
    done = False
    while not done:
        event = session.nextEvent(500)  # wait up to 500 ms for the next batch

        if event.eventType() == blpapi.Event.TIMEOUT:
            # nothing arrived in this half second; give up after 30s of silence
            if time.time() - last_progress > 30:
                raise TimeoutError(
                    "No data from Bloomberg for 30s. Check the Terminal is "
                    "logged in and the tickers are valid.")
            continue

        for msg in event:
            if not msg.hasElement("securityData"):
                continue
            sec = msg.getElement("securityData")
            ticker = sec.getElementAsString("security")

            if sec.hasElement("securityError"):
                err = sec.getElement("securityError").getElementAsString("message")
                print(f"WARNING - {ticker}: {err} (skipped)")
                last_progress = time.time()
                continue

            field_data = sec.getElement("fieldData")
            dates, values = [], []
            for i in range(field_data.numValues()):
                row = field_data.getValueAsElement(i)
                if row.hasElement(field):
                    dates.append(row.getElementAsDatetime("date"))
                    values.append(row.getElementAsFloat(field))
            all_series[ticker] = pd.Series(values, index=pd.to_datetime(dates))
            print(f"  got {ticker}: {len(values)} rows")
            last_progress = time.time()

        if event.eventType() == blpapi.Event.RESPONSE:
            done = True  # final message received

    missing = [t for t in tickers if t not in all_series]
    if missing:
        print(f"WARNING - no data returned for: {missing}")

    return pd.DataFrame(all_series).sort_index()


# ---------------------------------------------------------------------------
# Mock data engineered with a planted spike-and-unwind pattern
# ---------------------------------------------------------------------------
import datetime as _dt

# key dates for the planted pattern (June 2026 FOMC, then the unwind)
_FOMC_DATE = _dt.date(2026, 6, 17)
_UNWIND_START = _dt.date(2026, 6, 30)
_UNWIND_END = _dt.date(2026, 7, 8)

# Planted decomposition of the unwind (ground truth for notebook 02).
# w = share * 6 so the AVERAGE is 1 (six equally-weighted components).
_UNWIND_SHARES = {
    "30y":   0.31,
    "dxy":   0.17,
    "swap":  0.17,
    "fomc":  0.16,
    "oil":   0.16,
    "gold":  0.03,
}

# ticker -> (component_key, credibility_sign, base_level, unit_per_z, noise)
_MOCK_CONFIG = {
    "USGG30YR Index": ("30y",  -1, 4.80,   0.22, 0.35),
    "DXY Curncy":     ("dxy",  +1, 100.0,  1.50, 0.35),
    "USSWIT5 Curncy": ("swap", -1, 2.50,   0.07, 0.35),
    "XAU Curncy":     ("gold", -1, 2900.0, 45.0, 0.35),
    "CL1 Comdty":     ("oil",  -1, 70.0,   2.50, 0.35),
    "CO1 Comdty":     ("oil",  -1, 74.0,   2.60, 0.38),
    # extra yield tickers used by notebook 04 (not factor components):
    # 2y tracks hike pricing (+), 5y/10y behave like the long end (-)
    "USGG2YR Index":  ("fomc", +1, 4.30,   0.10, 0.30),
    "USGG5YR Index":  ("30y",  -1, 4.35,   0.15, 0.32),
    "USGG10YR Index": ("30y",  -1, 4.20,   0.18, 0.33),
    "FEDL01 Index":   (None,    0, 4.33,   0.0,  0.01),
    # FFQ6 handled specially in _bdh_mock (built from FEDL01 + hike pricing)
}


def _credibility_path(dates):
    """
    The hidden 'true' factor path:
    oscillation through the sample, spike at June FOMC, plateau, unwind.
    Returns (base_oscillation, spike_profile) as numpy arrays.
    """
    rng = np.random.default_rng(11)
    n = len(dates)

    # slow oscillation: an AR(1) process, scaled to roughly +/- 0.8
    base = np.zeros(n)
    for t in range(1, n):
        base[t] = 0.97 * base[t - 1] + rng.normal(0, 0.18)
    base = 0.8 * base / max(1e-9, np.std(base))

    # spike profile: 0 -> 1 ramp over ~4 days at the FOMC, hold, then handled
    # per-component in the unwind (different components unwind by different
    # amounts, which is what creates the planted pattern decomposition).
    spike = np.zeros(n)
    d = np.array([x.date() if hasattr(x, "date") else x for x in dates])
    ramp_days = 4
    for t in range(n):
        if d[t] >= _FOMC_DATE:
            days_in = np.busday_count(_FOMC_DATE, d[t]) + 1
            spike[t] = min(1.0, days_in / ramp_days)
    return base, spike, d


def _unwind_fraction(d, w):
    """
    How much of the spike has been given back by date d, for a component
    whose total unwind is w (w=1 -> gives back exactly the spike).
    Linear ramp between _UNWIND_START and _UNWIND_END.
    """
    total_days = max(1, np.busday_count(_UNWIND_START, _UNWIND_END))
    out = np.zeros(len(d))
    for t in range(len(d)):
        if d[t] >= _UNWIND_END:
            out[t] = w
        elif d[t] >= _UNWIND_START:
            out[t] = w * (np.busday_count(_UNWIND_START, d[t]) / total_days)
    return out


def _bdh_mock(tickers, field, start, end):
    rng = np.random.default_rng(99)
    dates = pd.bdate_range(start, end)
    base, spike, d = _credibility_path(dates)

    spike_size = 1.5   # peak z-height of the June FOMC move
    unwind_scale = 0.55  # on average, components give back ~80% of the spike

    out = {}
    for ticker in tickers:
        if ticker == "FFQ6 Comdty":
            # Fed funds Aug-26 future. Price = 100 - expected average rate.
            # We plant: expected rate = effective rate + hike pricing,
            # where hike pricing follows the credibility path.
            w = _UNWIND_SHARES["fomc"] * 6 * unwind_scale
            signal = base + spike_size * (spike - _unwind_fraction(d, w) * spike.clip(max=1.0))
            hike_bp = 4.0 + 7.0 * (signal + 0.35 * rng.standard_normal(len(dates)))
            fedl = 4.33
            out[ticker] = pd.Series(100.0 - fedl - hike_bp / 100.0, index=dates)
            continue

        if ticker in _MOCK_CONFIG:
            key, sign, level0, unit, noise = _MOCK_CONFIG[ticker]
            if key is None:  # FEDL01: flat effective funds rate
                out[ticker] = pd.Series(
                    level0 + noise * rng.standard_normal(len(dates)), index=dates)
                continue
            w = _UNWIND_SHARES[key] * 6 * unwind_scale
            signal = base + spike_size * (spike - _unwind_fraction(d, w) * spike.clip(max=1.0))
            levels = level0 + unit * (sign * signal
                                      + noise * rng.standard_normal(len(dates)))
            out[ticker] = pd.Series(levels, index=dates)
        else:
            # unknown ticker: seeded random walk
            trng = np.random.default_rng(abs(hash(ticker)) % (2**32))
            out[ticker] = pd.Series(
                100.0 * np.cumprod(1 + 0.01 * trng.standard_normal(len(dates))),
                index=dates)

    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------
def bdh(tickers, field="PX_LAST", start=None, end=None):
    """Historical daily data: rows = dates, columns = tickers."""
    if end is None:
        end = dt.date.today()
    if start is None:
        start = end - dt.timedelta(days=365 * 2)
    if MOCK_MODE:
        return _bdh_mock(tickers, field, start, end)
    return _bdh_real(tickers, field, start, end)


# ---------------------------------------------------------------------------
# bds: bulk data (lists), used for the economic-event calendar
# ---------------------------------------------------------------------------
def _bds_real(ticker, field):
    """
    Bulk-field request (like Excel's BDS): returns a list of values.
    Used for e.g. ECO_FUTURE_RELEASE_DATE_LIST on "FDTR Index" (FOMC).
    """
    session = _get_session()
    service = session.getService("//blp/refdata")

    request = service.createRequest("ReferenceDataRequest")
    request.getElement("securities").appendValue(ticker)
    request.getElement("fields").appendValue(field)
    session.sendRequest(request)

    values = []
    done = False
    while not done:
        event = session.nextEvent(500)
        for msg in event:
            if msg.hasElement("securityData"):
                sec = msg.getElement("securityData").getValueAsElement(0)
                field_data = sec.getElement("fieldData")
                if field_data.hasElement(field):
                    bulk = field_data.getElement(field)
                    for i in range(bulk.numValues()):
                        row = bulk.getValueAsElement(i)
                        # each row is a tiny record; take its first element
                        values.append(row.getElement(0).getValue())
        if event.eventType() == blpapi.Event.RESPONSE:
            done = True

    return values


# mock calendars: FOMC schedule + monthly CPI/NFP-style dates
_MOCK_CALENDARS = {
    "FDTR Index": ["2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09"],
    "CPI YOY Index": ["2026-07-14", "2026-08-12", "2026-09-11", "2026-10-13"],
    "NFP TCH Index": ["2026-08-07", "2026-09-04", "2026-10-02", "2026-11-06"],
}


def bds(ticker, field):
    """
    Bulk data: list of values for one ticker/field.
    Example: bds("FDTR Index", "ECO_FUTURE_RELEASE_DATE_LIST")
             -> upcoming FOMC decision dates.
    """
    if MOCK_MODE:
        return list(_MOCK_CALENDARS.get(ticker, []))
    return _bds_real(ticker, field)
