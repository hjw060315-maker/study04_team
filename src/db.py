"""DB 연결. 연결은 한 번만 만들어 모든 질의가 다시 쓰고, 끊기면 다시 연결한다."""
import threading
import time
from contextlib import contextmanager

from .config import get_secret

PING_AFTER = 30  # 이 시간(초)보다 오래 안 썼으면 쓰기 전에 연결이 살아 있는지 확인


class Tx:
    """한 트랜잭션 안에서 쓰는 질의 도구. q는 행 목록(dict), x는 실행만 한다."""

    def __init__(self, cur):
        self.cur = cur

    def q(self, sql, params=()):
        self.cur.execute(sql, params or None)
        return [dict(r) for r in self.cur.fetchall()]

    def x(self, sql, params=()):
        self.cur.execute(sql, params or None)


def is_integrity_error(exc):
    return any(c.__name__ == "IntegrityError" for c in type(exc).__mro__)


class PgDatabase:
    def __init__(self, url):
        self.url = url
        self.lock = threading.RLock()
        self.conn = None
        self.last_used = 0.0

    def _connect(self):
        """순간적인 네트워크 끊김(DNS 실패 등)에 대비해 짧게 두 번 더 시도한다."""
        import psycopg2

        for attempt in range(3):
            try:
                self._connect_once()
                return
            except psycopg2.OperationalError:
                if attempt == 2:
                    raise
                time.sleep(1.5 * (attempt + 1))

    def _connect_once(self):
        import psycopg2

        self.conn = psycopg2.connect(
            self.url,
            connect_timeout=10,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=3,
            options="-c statement_timeout=30000",
        )
        self.last_used = time.monotonic()

    def _ensure(self):
        if self.conn is None or self.conn.closed:
            self._connect()
            return
        if time.monotonic() - self.last_used > PING_AFTER:
            try:
                with self.conn.cursor() as cur:
                    cur.execute("select 1")
                self.conn.rollback()
            except Exception:  # noqa: BLE001  죽은 연결이면 새로 만든다
                try:
                    self.conn.close()
                except Exception:  # noqa: BLE001
                    pass
                self._connect()

    @contextmanager
    def tx(self):
        from psycopg2.extras import RealDictCursor

        with self.lock:
            self._ensure()
            cur = self.conn.cursor(cursor_factory=RealDictCursor)
            try:
                yield Tx(cur)
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            finally:
                cur.close()
                self.last_used = time.monotonic()


def create_database():
    url = get_secret("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL이 없음")
    return PgDatabase(url)
