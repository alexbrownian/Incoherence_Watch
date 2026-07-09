"""
db.py - tiny SQLite helper for the incoherence monitor.

SQLite is a database that lives in ONE local file (incoherence.db).
No server, no setup. The `sqlite3` module ships with Python.

Tables
------
events     one row every time a relationship BREAKS or REVERTS
status     one row per pair = its latest state (overwritten each run)
surprises  one row per economic release we scored
"""

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "incoherence.db")


def get_connection():
    """Open (and create if missing) the database file."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            pair_name   TEXT NOT NULL,
            event_type  TEXT NOT NULL,      -- 'breakdown' or 'reversion'
            event_date  TEXT NOT NULL,      -- YYYY-MM-DD
            corr_short  REAL,
            corr_long   REAL,
            note        TEXT,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (pair_name, event_type, event_date)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS status (
            pair_name   TEXT PRIMARY KEY,
            state       TEXT,               -- 'NORMAL' or 'BROKEN'
            as_of       TEXT,
            corr_short  REAL,
            corr_long   REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS surprises (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker       TEXT NOT NULL,
            release_date TEXT,
            actual       REAL,
            survey       REAL,
            surprise     REAL,              -- normalized surprise score
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (ticker, release_date)
        )
    """)
    conn.commit()
    return conn


def insert_event(conn, pair_name, event_type, event_date, corr_short, corr_long, note=""):
    """Add one breakdown/reversion event. Duplicate (pair, type, date) is ignored."""
    conn.execute(
        "INSERT OR IGNORE INTO events "
        "(pair_name, event_type, event_date, corr_short, corr_long, note) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (pair_name, event_type, str(event_date)[:10], corr_short, corr_long, note),
    )
    conn.commit()


def upsert_status(conn, pair_name, state, as_of, corr_short, corr_long):
    """Overwrite the latest state for one pair."""
    conn.execute(
        "INSERT INTO status (pair_name, state, as_of, corr_short, corr_long) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(pair_name) DO UPDATE SET "
        "state=excluded.state, as_of=excluded.as_of, "
        "corr_short=excluded.corr_short, corr_long=excluded.corr_long",
        (pair_name, state, str(as_of)[:10], corr_short, corr_long),
    )
    conn.commit()


def insert_surprise(conn, ticker, release_date, actual, survey, surprise):
    """Add one economic data surprise. Duplicate (ticker, date) is ignored."""
    conn.execute(
        "INSERT OR IGNORE INTO surprises "
        "(ticker, release_date, actual, survey, surprise) VALUES (?, ?, ?, ?, ?)",
        (ticker, str(release_date)[:10], actual, survey, surprise),
    )
    conn.commit()
