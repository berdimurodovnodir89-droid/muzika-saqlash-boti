import os
import sqlite3
from datetime import datetime

try:
    import psycopg2
    from psycopg2.pool import SimpleConnectionPool
except Exception:
    psycopg2 = None
    SimpleConnectionPool = None


class Storage:
    def init(self): ...
    def add_song(self, user_id: int, category: str, file_id: str, title: str, file_type: str): ...
    def list_songs(self, user_id: int, category: str): ...
    def search_songs(self, user_id: int, category: str, q: str): ...


class SQLiteStorage(Storage):
    def __init__(self, path="songs.db"):
        self.path = path
        self.db = None

    def init(self):
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL;")
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS songs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                file_id TEXT NOT NULL,
                title TEXT NOT NULL,
                file_type TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_user_cat ON songs(user_id, category);")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_title ON songs(title);")
        self.db.commit()

    def add_song(self, user_id, category, file_id, title, file_type):
        self.db.execute(
            "INSERT INTO songs(user_id,category,file_id,title,file_type,created_at) VALUES(?,?,?,?,?,?)",
            (user_id, category, file_id, title, file_type, datetime.utcnow().isoformat()),
        )
        self.db.commit()

    def list_songs(self, user_id, category):
        cur = self.db.execute(
            "SELECT file_id,title,file_type FROM songs WHERE user_id=? AND category=? ORDER BY id DESC",
            (user_id, category),
        )
        return cur.fetchall()

    def search_songs(self, user_id, category, q):
        cur = self.db.execute(
            "SELECT file_id,title,file_type FROM songs WHERE user_id=? AND category=? AND lower(title) LIKE ? ORDER BY id DESC",
            (user_id, category, f"%{q.lower()}%"),
        )
        return cur.fetchall()


class PostgresStorage(Storage):
    def __init__(self, dsn: str):
        if psycopg2 is None:
            raise RuntimeError("psycopg2 o'rnatilmagan")
        self.pool = SimpleConnectionPool(1, 5, dsn=dsn)

    def init(self):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS songs(
                        id BIGSERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        category TEXT NOT NULL,
                        file_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        file_type TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_user_cat_pg ON songs(user_id, category);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_title_pg ON songs(title);")
            conn.commit()
        finally:
            self.pool.putconn(conn)

    def add_song(self, user_id, category, file_id, title, file_type):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO songs(user_id,category,file_id,title,file_type) VALUES(%s,%s,%s,%s,%s)",
                    (user_id, category, file_id, title, file_type),
                )
            conn.commit()
        finally:
            self.pool.putconn(conn)

    def list_songs(self, user_id, category):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT file_id,title,file_type FROM songs WHERE user_id=%s AND category=%s ORDER BY id DESC",
                    (user_id, category),
                )
                return cur.fetchall()
        finally:
            self.pool.putconn(conn)

    def search_songs(self, user_id, category, q):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT file_id,title,file_type FROM songs WHERE user_id=%s AND category=%s AND LOWER(title) LIKE %s ORDER BY id DESC",
                    (user_id, category, f"%{q.lower()}%"),
                )
                return cur.fetchall()
        finally:
            self.pool.putconn(conn)


def make_storage() -> Storage:
    dsn = os.getenv("DATABASE_URL", "").strip()
    if dsn:
        return PostgresStorage(dsn)
    return SQLiteStorage(os.getenv("DB_PATH", "songs.db").strip())