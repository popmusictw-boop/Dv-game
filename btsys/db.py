"""資料庫：本機用 SQLite；雲端（BT_DATABASE_URL=postgres://…）用 PostgreSQL（Supabase）。
學生相關內容欄位一律存加密後的密文（含上傳檔案本體）。"""
import os, re, sqlite3, time
from flask import g, current_app

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL,
  password_hash TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, must_change INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS drafts(
  id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id),
  title TEXT NOT NULL, content_enc BLOB NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS files(
  id INTEGER PRIMARY KEY, draft_id INTEGER NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
  owner_id INTEGER NOT NULL, student_key TEXT NOT NULL, filename_enc BLOB NOT NULL, mime TEXT NOT NULL,
  size INTEGER NOT NULL, blob_enc BLOB NOT NULL, extract_enc BLOB, status TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS curriculum_imports(
  id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, title TEXT NOT NULL, version TEXT NOT NULL,
  source_url TEXT, items_json TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT NOT NULL, target TEXT, at REAL NOT NULL);
"""

SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS users(
  id BIGSERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL,
  password_hash TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, must_change INTEGER NOT NULL DEFAULT 0,
  created_at DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS drafts(
  id BIGSERIAL PRIMARY KEY, owner_id BIGINT NOT NULL REFERENCES users(id),
  title TEXT NOT NULL, content_enc BYTEA NOT NULL, created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS files(
  id BIGSERIAL PRIMARY KEY, draft_id BIGINT NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
  owner_id BIGINT NOT NULL, student_key TEXT NOT NULL, filename_enc BYTEA NOT NULL, mime TEXT NOT NULL,
  size INTEGER NOT NULL, blob_enc BYTEA NOT NULL, extract_enc BYTEA, status TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS curriculum_imports(
  id BIGSERIAL PRIMARY KEY, owner_id BIGINT NOT NULL, title TEXT NOT NULL, version TEXT NOT NULL,
  source_url TEXT, items_json TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS audit(
  id BIGSERIAL PRIMARY KEY, user_id BIGINT, action TEXT NOT NULL, target TEXT, at DOUBLE PRECISION NOT NULL);
"""

class _PgCursor:
    def __init__(self, rows, lastrowid=None):
        self._rows, self.lastrowid = rows, lastrowid
    def fetchone(self): return self._rows[0] if self._rows else None
    def fetchall(self): return list(self._rows)
    def __iter__(self): return iter(self._rows)

_WORKING_URL = {}

class PgDB:
    """以 SQLite 相同介面（? 參數、fetchone/fetchall/lastrowid/commit）包裝 PostgreSQL。每個陳述式自動提交。
    Supabase 共用連線池主機名稱有 aws-0-／aws-1- 兩種，連線失敗時自動改試另一個。"""
    def __init__(self, url):
        from .pgwire import Connection
        url = _WORKING_URL.get(url, url)
        cands = [url] + ([url.replace('@aws-0-', '@aws-1-')] if '@aws-0-' in url else []) + ([url.replace('@aws-1-', '@aws-0-')] if '@aws-1-' in url else [])
        err = None
        for u in cands:
            try:
                self.con = Connection(u); _WORKING_URL[url] = u; return
            except Exception as e:
                err = e
        raise err
    def execute(self, sql, params=()):
        n = iter(range(1, 1000))
        q = re.sub(r'\?', lambda _: f'${next(n)}', sql)
        is_insert = q.lstrip().upper().startswith('INSERT')
        if is_insert and 'RETURNING' not in q.upper(): q += ' RETURNING id'
        rows = self.con.query(q, tuple(params))
        return _PgCursor(rows, rows[0]['id'] if is_insert and rows else None)
    def executescript(self, script):
        for stmt in [s.strip() for s in script.split(';') if s.strip()]:
            self.con.query(stmt)
    def commit(self): pass
    def close(self): self.con.close()

def connect(path):
    if path.startswith('postgres'):
        return PgDB(path)
    con = sqlite3.connect(path, detect_types=0)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    return con

def get_db():
    if 'db' not in g:
        g.db = connect(current_app.config['DATABASE'])
    return g.db

def close_db(_=None):
    db = g.pop('db', None)
    if db is not None: db.close()

def init_db(path):
    con = connect(path)
    con.executescript(SCHEMA_PG if path.startswith('postgres') else SCHEMA_SQLITE)
    con.commit(); con.close()

def audit(user_id, action, target=''):
    """稽核紀錄只記錄動作與物件代號，不記錄學生姓名或內容。"""
    db = get_db()
    db.execute('INSERT INTO audit(user_id,action,target,at) VALUES(?,?,?,?)', (user_id, action, str(target), time.time()))
    db.commit()
