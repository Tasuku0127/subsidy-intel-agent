"""
store.py: SQLite によるスナップショット管理
"""
import sqlite3
import gzip
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "snapshots.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id   TEXT    NOT NULL,
            fetched_at  TEXT    NOT NULL,
            content_gz  BLOB    NOT NULL,
            content_hash TEXT   NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_snapshots_source ON snapshots(source_id, fetched_at);

        CREATE TABLE IF NOT EXISTS runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at      TEXT    NOT NULL,
            source_id   TEXT    NOT NULL,
            status      TEXT    NOT NULL,
            message     TEXT
        );
        """)


def save_snapshot(source_id: str, text: str) -> tuple[str, bool]:
    """
    テキストを保存し (hash, is_new) を返す。
    is_new=True のとき前回スナップショットと差分あり。
    """
    import hashlib
    content_hash = hashlib.sha256(text.encode()).hexdigest()
    gz = gzip.compress(text.encode())
    fetched_at = datetime.utcnow().isoformat()

    with _conn() as con:
        # 直近スナップショットを取得
        row = con.execute(
            "SELECT content_hash FROM snapshots WHERE source_id=? ORDER BY fetched_at DESC LIMIT 1",
            (source_id,)
        ).fetchone()

        is_changed = (row is None) or (row["content_hash"] != content_hash)
        con.execute(
            "INSERT INTO snapshots (source_id, fetched_at, content_gz, content_hash) VALUES (?,?,?,?)",
            (source_id, fetched_at, gz, content_hash)
        )

    return content_hash, is_changed


def get_last_two_snapshots(source_id: str) -> tuple[Optional[str], Optional[str]]:
    """最新2件のテキストを (previous, current) で返す。なければ None。"""
    with _conn() as con:
        rows = con.execute(
            "SELECT content_gz FROM snapshots WHERE source_id=? ORDER BY fetched_at DESC LIMIT 2",
            (source_id,)
        ).fetchall()

    if len(rows) == 0:
        return None, None
    current = gzip.decompress(rows[0]["content_gz"]).decode()
    previous = gzip.decompress(rows[1]["content_gz"]).decode() if len(rows) > 1 else None
    return previous, current


def log_run(source_id: str, status: str, message: str = "") -> None:
    with _conn() as con:
        con.execute(
            "INSERT INTO runs (run_at, source_id, status, message) VALUES (?,?,?,?)",
            (datetime.utcnow().isoformat(), source_id, status, message)
        )
