"""SQLite 数据库层：schema 初始化与线程安全访问。

MVP 说明：baseline 里写的是 PostgreSQL + TimescaleDB，这里在「本地可安装桌面应用」场景下
改用 SQLite（标准库、零部署、单文件），指标量级（个人健康数据）完全够用；后续要多人/多机构
部署时再平滑替换为 PostgreSQL（表结构一致，仅换驱动）。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    gender TEXT,
    birth_date TEXT,
    height_cm REAL,
    weight_kg REAL,
    blood_type TEXT,
    medical_history TEXT,
    allergies TEXT,
    current_medications TEXT,
    phone TEXT,
    address TEXT,
    emergency_contacts TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS guardians (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT,
    phone TEXT,
    relation TEXT,
    is_primary INTEGER DEFAULT 0,
    notify_channels TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS doctors (
    id TEXT PRIMARY KEY,
    name TEXT,
    hospital TEXT,
    specialty TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    vendor TEXT,
    model TEXT,
    device_external_id TEXT,
    bound_at TEXT,
    last_sync_at TEXT,
    status TEXT
);
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    device_id TEXT,
    type TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT,
    measured_at TEXT NOT NULL,
    source TEXT NOT NULL,
    quality TEXT DEFAULT 'valid'
);
CREATE INDEX IF NOT EXISTS idx_metrics_user_time ON metrics(user_id, measured_at);
CREATE INDEX IF NOT EXISTS idx_metrics_user_type ON metrics(user_id, type);

CREATE TABLE IF NOT EXISTS symptom_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    transcript TEXT,
    triage_level TEXT,
    extracted TEXT,
    advice TEXT,
    notified INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    type TEXT,
    severity TEXT,
    title TEXT,
    message TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT,
    acknowledged_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts(user_id, created_at);

CREATE TABLE IF NOT EXISTS reminders (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    kind TEXT,
    title TEXT,
    detail TEXT,
    cron TEXT,
    enabled INTEGER DEFAULT 1,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS adherence_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reminder_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    taken INTEGER DEFAULT 0,
    taken_at TEXT,
    note TEXT
);
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    type TEXT,
    period_start TEXT,
    period_end TEXT,
    summary TEXT,
    anomalies TEXT,
    advice TEXT,
    generated_at TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

_conn: sqlite3.Connection | None = None
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def new_id(prefix: str = "") -> str:
    return (prefix + uuid.uuid4().hex)[:36]


def get_conn() -> sqlite3.Connection:
    """返回共享连接（线程安全，由 _lock 串行化写操作）。"""
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(config.DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL;")
        _conn.execute("PRAGMA foreign_keys=ON;")
        _conn.executescript(_SCHEMA)
        _conn.commit()
    return _conn


def query(sql: str, params: tuple = ()) -> list[dict]:
    with _lock:
        cur = get_conn().execute(sql, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def query_one(sql: str, params: tuple = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple = ()) -> int:
    with _lock:
        cur = get_conn().execute(sql, params)
        get_conn().commit()
        return cur.lastrowid


def now() -> str:
    return _now()


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def loads(text, default=None):
    if not text:
        return default
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return default
