import hashlib
import json
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_PATH, DEMO_EMAIL, DEMO_PASSWORD

_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'reviewer',
    password_hash TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS batches (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    preset_id INTEGER,
    output_format TEXT NOT NULL DEFAULT 'xlsx',
    status TEXT NOT NULL,
    total_files INTEGER NOT NULL DEFAULT 0,
    is_sample INTEGER NOT NULL DEFAULT 0,
    user_id INTEGER,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    processing_ms INTEGER
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    filename TEXT NOT NULL,
    stored_path TEXT,
    kind TEXT,
    status TEXT NOT NULL,
    stage TEXT,
    engine TEXT,
    pages_json TEXT,
    fields_json TEXT,
    items_json TEXT,
    checks_json TEXT,
    warnings_json TEXT,
    error TEXT,
    processing_ms INTEGER,
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    reviewed_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_docs_batch ON documents(batch_id, position);
CREATE TABLE IF NOT EXISTS presets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    config_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "company_name": "DocuFlow",
    "accent_color": "#1d4ed8",
    "logo_url": "",
    "language": "en",
    "retention": "30d",          # immediate | 7d | 30d
    "date_format": "DD/MM/YYYY",
    "default_currency": "PKR",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


_conn = None


@contextmanager
def tx():
    global _conn
    with _lock:
        if _conn is None:
            _conn = _connect()
        try:
            yield _conn
            _conn.commit()
        except Exception:
            _conn.rollback()
            raise


def query(sql, params=()):
    with tx() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def one(sql, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql, params=()):
    with tx() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid


def hash_password(pw: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 120_000).hex()
    return f"{salt}${h}"


def check_password(pw: str, stored: str | None) -> bool:
    if not stored or "$" not in stored:
        return False
    salt = stored.split("$", 1)[0]
    return secrets.compare_digest(hash_password(pw, salt), stored)


def get_settings() -> dict:
    out = dict(DEFAULT_SETTINGS)
    for r in query("SELECT key, value FROM settings"):
        out[r["key"]] = json.loads(r["value"])
    return out


def set_settings(values: dict):
    with tx() as c:
        for k, v in values.items():
            if k in DEFAULT_SETTINGS:
                c.execute("INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                          (k, json.dumps(v)))


def init_db():
    with tx() as c:
        c.executescript(SCHEMA)
        if not c.execute("SELECT 1 FROM users WHERE email=?", (DEMO_EMAIL,)).fetchone():
            c.execute("INSERT INTO users(email, name, role, password_hash, created_at) VALUES(?,?,?,?,?)",
                      (DEMO_EMAIL, "Demo Admin", "admin", hash_password(DEMO_PASSWORD), now()))
            c.execute("INSERT INTO users(email, name, role, password_hash, created_at) VALUES(?,?,?,?,?)",
                      ("ayesha@example.com", "Ayesha Khan", "reviewer", None, now()))
    from .presets import seed_presets
    seed_presets()
