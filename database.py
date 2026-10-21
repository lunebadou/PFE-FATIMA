"""Accès à la base SQLite."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime

from config import DB_PATH


def now():
    """Horodatage local au format ISO (ex : 2026-10-21T21:45:03)."""
    return datetime.now().isoformat(timespec="seconds")


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db():
    """Ouvre une connexion, valide à la fin, annule en cas d'erreur."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def rows(cursor):
    return [dict(r) for r in cursor.fetchall()]


def row(cursor):
    r = cursor.fetchone()
    return dict(r) if r else None
