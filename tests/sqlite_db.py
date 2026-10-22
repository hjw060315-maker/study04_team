"""시험용 가짜 DB. schema.sql을 SQLite 문법으로 바꿔 같은 서비스 코드를 돌린다."""
import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from src.db import Tx

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"


class _Cur:
    def __init__(self, cur):
        self.cur = cur

    def execute(self, sql, params=()):
        if "create table if not exists" in sql:  # 앱 시작 때 보내는 스키마는 이미 적용되어 있다
            self.cur.execute("select 1")
            return
        self.cur.execute(sql.replace("%s", "?"), params or ())

    def fetchall(self):
        return self.cur.fetchall()


class SqliteDatabase:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        sql = SCHEMA.read_text(encoding="utf-8")
        sql = sql.replace("serial primary key", "integer primary key autoincrement")
        sql = sql.replace("timestamptz not null default now()", "text not null default current_timestamp")
        sql = sql.replace("real", "real")
        self.conn.executescript(sql)
        self.conn.execute("pragma foreign_keys = on")

    @contextmanager
    def tx(self):
        with self.lock:
            cur = self.conn.cursor()
            try:
                yield Tx(_Cur(cur))
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
