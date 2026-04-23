"""
Dual-backend DB layer: SQLite for local dev, Postgres (shared kumori Cloud SQL)
for App Engine. All call sites import from this module and stay ignorant of
which engine is actually running.

Backend selection:
- GAE_ENV=standard                    → Postgres via unix socket /cloudsql/<conn>
- POSTGRES_DSN env var set            → Postgres over TCP (direct/local dev)
- else                                → SQLite file at Config.SQLITE_PATH

Queries use `?` placeholders (sqlite3 qmark style). For Postgres we swap to
`%s` at execute time. Same function signatures across engines.
"""
import logging
import os
import secrets
import sqlite3
import threading
from contextlib import contextmanager

from config import Config

logger = logging.getLogger('artifactory.db')


def backend():
    if os.environ.get('GAE_ENV', '').startswith('standard'):
        return 'postgres'
    if os.environ.get('POSTGRES_DSN'):
        return 'postgres'
    return 'sqlite'


# =============================================================================
# Postgres plumbing — connection pooling + credential fetch
# =============================================================================

_pg_pool = None
_pg_pool_lock = threading.Lock()
_pg_creds_cache = None


def _pg_credentials():
    """Pull credentials from Secret Manager (prod) or env (local dev)."""
    global _pg_creds_cache
    if _pg_creds_cache:
        return _pg_creds_cache

    dsn = os.environ.get('POSTGRES_DSN')
    if dsn:
        _pg_creds_cache = {'dsn': dsn}
        return _pg_creds_cache

    from google.cloud import secretmanager
    client = secretmanager.SecretManagerServiceClient()
    project = Config.GCP_PROJECT_ID

    def get(key):
        name = f"projects/{project}/secrets/{key}/versions/latest"
        return client.access_secret_version(request={"name": name}).payload.data.decode('utf-8').strip()

    _pg_creds_cache = {
        'host':            get('ARTIFACTORY_POSTGRES_IP'),
        'dbname':          get('ARTIFACTORY_POSTGRES_DB_NAME'),
        'user':            get('ARTIFACTORY_POSTGRES_USERNAME'),
        'password':        get('ARTIFACTORY_POSTGRES_PASSWORD'),
        'connection_name': get('ARTIFACTORY_POSTGRES_CONNECTION_NAME'),
    }
    return _pg_creds_cache


def _pg_connection_pool():
    """Lazy-init a ThreadedConnectionPool. Respects kumori's 3-conn-per-app budget."""
    global _pg_pool
    if _pg_pool is not None:
        return _pg_pool
    with _pg_pool_lock:
        if _pg_pool is not None:
            return _pg_pool

        import psycopg2.pool
        creds = _pg_credentials()

        if creds.get('dsn'):
            kwargs = {'dsn': creds['dsn']}
        else:
            is_gae = os.environ.get('GAE_ENV', '').startswith('standard')
            host = f"/cloudsql/{creds['connection_name']}" if is_gae else creds['host']
            kwargs = {
                'host': host,
                'dbname': creds['dbname'],
                'user': creds['user'],
                'password': creds['password'],
            }

        _pg_pool = psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=3, **kwargs)
        logger.info("Postgres pool initialized")
        return _pg_pool


# =============================================================================
# Unified cursor / exec helpers
# =============================================================================

@contextmanager
def cursor():
    """Yields a (connection, cursor) usable by all callers. Commits on success."""
    if backend() == 'sqlite':
        os.makedirs(os.path.dirname(Config.SQLITE_PATH), exist_ok=True)
        conn = sqlite3.connect(Config.SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    else:
        import psycopg2.extras
        pool = _pg_connection_pool()
        conn = pool.getconn()
        conn.cursor_factory = psycopg2.extras.RealDictCursor
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            pool.putconn(conn)


def _ph(sql):
    """Swap ? placeholders → %s for psycopg2. No-op on sqlite."""
    return sql.replace('?', '%s') if backend() == 'postgres' else sql


def _exec(conn, sql, args=()):
    """Execute and return cursor. Normalizes placeholder style."""
    cur = conn.cursor()
    cur.execute(_ph(sql), args)
    return cur


def _fetchone_dict(cur):
    row = cur.fetchone()
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


def _fetchall_dict(cur):
    return [dict(r) if not isinstance(r, dict) else r for r in cur.fetchall()]


def _lastid(cur, table, pk='id'):
    """Return the just-inserted PK. Works on both engines."""
    if backend() == 'sqlite':
        return cur.lastrowid
    # Postgres: RETURNING already read or use currval
    try:
        return cur.fetchone()[pk]
    except Exception:
        pass
    # Fallback if RETURNING wasn't used
    cur.execute(f"SELECT currval(pg_get_serial_sequence(%s, %s)) AS id", (table, pk))
    return cur.fetchone()['id']


# =============================================================================
# Schema — idempotent DDL for both engines
# =============================================================================

_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS artifactory_role_templates (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    slug           TEXT UNIQUE NOT NULL,
    display_name   TEXT NOT NULL,
    category       TEXT NOT NULL CHECK (category IN ('trades','outdoor','inspection','interior','service','management')),
    description    TEXT,
    example_prompt TEXT,
    position       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS artifactory_users (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,
    email            TEXT UNIQUE,
    role             TEXT NOT NULL,
    role_template_id INTEGER REFERENCES artifactory_role_templates(id),
    session_token    TEXT UNIQUE,
    extra            TEXT NOT NULL DEFAULT '{}',
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_art_users_session ON artifactory_users(session_token);

CREATE TABLE IF NOT EXISTS artifactory_tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL,
    description   TEXT,
    column_name   TEXT NOT NULL DEFAULT 'todo'
                  CHECK (column_name IN ('todo','sourcing','inprogress','blocked','done')),
    tag           TEXT CHECK (tag IS NULL OR tag IN ('Permits','Inspection','Labor','Materials','Fixtures','Design')),
    assigned_role TEXT,
    due_date      TEXT,
    position      INTEGER NOT NULL DEFAULT 0,
    extra         TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_art_tasks_col  ON artifactory_tasks(column_name);
CREATE INDEX IF NOT EXISTS idx_art_tasks_role ON artifactory_tasks(assigned_role);

CREATE TABLE IF NOT EXISTS artifactory_comments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    INTEGER NOT NULL REFERENCES artifactory_tasks(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES artifactory_users(id) ON DELETE CASCADE,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_art_comments_task ON artifactory_comments(task_id);

CREATE TABLE IF NOT EXISTS artifactory_materials (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    INTEGER NOT NULL REFERENCES artifactory_tasks(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    quantity   REAL NOT NULL DEFAULT 1,
    unit       TEXT,
    cost_usd   REAL,
    ordered    INTEGER NOT NULL DEFAULT 0,
    supplier   TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_art_materials_task ON artifactory_materials(task_id);

CREATE TABLE IF NOT EXISTS artifactory_user_artifacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES artifactory_users(id) ON DELETE CASCADE,
    source_jsx      TEXT NOT NULL,
    method          TEXT NOT NULL CHECK (method IN ('paste','extension','url')),
    is_active       INTEGER NOT NULL DEFAULT 1,
    submission_meta TEXT NOT NULL DEFAULT '{}',
    submitted_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_art_artifacts_user_recent ON artifactory_user_artifacts(user_id, submitted_at DESC);
"""

_DDL_POSTGRES = """
CREATE TABLE IF NOT EXISTS artifactory_role_templates (
    id             SERIAL PRIMARY KEY,
    slug           TEXT UNIQUE NOT NULL,
    display_name   TEXT NOT NULL,
    category       TEXT NOT NULL CHECK (category IN ('trades','outdoor','inspection','interior','service','management')),
    description    TEXT,
    example_prompt TEXT,
    position       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS artifactory_users (
    id               SERIAL PRIMARY KEY,
    name             TEXT NOT NULL,
    email            TEXT UNIQUE,
    role             TEXT NOT NULL,
    role_template_id INTEGER REFERENCES artifactory_role_templates(id),
    session_token    TEXT UNIQUE,
    extra            JSONB NOT NULL DEFAULT '{}',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_art_users_session ON artifactory_users(session_token);

CREATE TABLE IF NOT EXISTS artifactory_tasks (
    id            SERIAL PRIMARY KEY,
    title         TEXT NOT NULL,
    description   TEXT,
    column_name   TEXT NOT NULL DEFAULT 'todo'
                  CHECK (column_name IN ('todo','sourcing','inprogress','blocked','done')),
    tag           TEXT CHECK (tag IS NULL OR tag IN ('Permits','Inspection','Labor','Materials','Fixtures','Design')),
    assigned_role TEXT,
    due_date      DATE,
    position      INTEGER NOT NULL DEFAULT 0,
    extra         JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_art_tasks_col  ON artifactory_tasks(column_name);
CREATE INDEX IF NOT EXISTS idx_art_tasks_role ON artifactory_tasks(assigned_role);

CREATE TABLE IF NOT EXISTS artifactory_comments (
    id         SERIAL PRIMARY KEY,
    task_id    INTEGER NOT NULL REFERENCES artifactory_tasks(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES artifactory_users(id) ON DELETE CASCADE,
    body       TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_art_comments_task ON artifactory_comments(task_id);

CREATE TABLE IF NOT EXISTS artifactory_materials (
    id         SERIAL PRIMARY KEY,
    task_id    INTEGER NOT NULL REFERENCES artifactory_tasks(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    quantity   NUMERIC(12,2) NOT NULL DEFAULT 1,
    unit       TEXT,
    cost_usd   NUMERIC(12,2),
    ordered    BOOLEAN NOT NULL DEFAULT FALSE,
    supplier   TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_art_materials_task ON artifactory_materials(task_id);

CREATE TABLE IF NOT EXISTS artifactory_user_artifacts (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES artifactory_users(id) ON DELETE CASCADE,
    source_jsx      TEXT NOT NULL,
    method          TEXT NOT NULL CHECK (method IN ('paste','extension','url')),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    submission_meta JSONB NOT NULL DEFAULT '{}',
    submitted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_art_artifacts_user_recent
    ON artifactory_user_artifacts(user_id, submitted_at DESC);
"""


def init_schema():
    """Create tables if missing. Safe to run every boot."""
    if backend() == 'sqlite':
        os.makedirs(os.path.dirname(Config.SQLITE_PATH), exist_ok=True)
        conn = sqlite3.connect(Config.SQLITE_PATH)
        conn.executescript(_DDL_SQLITE)
        conn.commit()
        conn.close()
    else:
        with cursor() as conn:
            conn.cursor().execute(_DDL_POSTGRES)


# =============================================================================
# Queries — engine-agnostic
# =============================================================================

def _insert_returning_id(conn, sql, args, table, pk='id'):
    """Common pattern: insert, get new id. Postgres uses RETURNING, sqlite uses lastrowid."""
    if backend() == 'postgres':
        cur = conn.cursor()
        cur.execute(_ph(sql + f" RETURNING {pk}"), args)
        return cur.fetchone()[pk]
    cur = conn.cursor()
    cur.execute(sql, args)
    return cur.lastrowid


# ---- role templates ----

def list_role_templates():
    with cursor() as conn:
        cur = _exec(conn, "SELECT * FROM artifactory_role_templates ORDER BY category, position, id")
        return _fetchall_dict(cur)


def get_role_template(template_id):
    with cursor() as conn:
        cur = _exec(conn, "SELECT * FROM artifactory_role_templates WHERE id = ?", (template_id,))
        return _fetchone_dict(cur)


def get_role_template_by_slug(slug):
    with cursor() as conn:
        cur = _exec(conn, "SELECT * FROM artifactory_role_templates WHERE slug = ?", (slug,))
        return _fetchone_dict(cur)


def upsert_role_template(slug, display_name, category, description, example_prompt, position):
    with cursor() as conn:
        existing = _fetchone_dict(_exec(conn,
            "SELECT id FROM artifactory_role_templates WHERE slug = ?", (slug,)))
        if existing:
            _exec(conn,
                """UPDATE artifactory_role_templates
                   SET display_name=?, category=?, description=?, example_prompt=?, position=?
                   WHERE id=?""",
                (display_name, category, description, example_prompt, position, existing['id']))
            return existing['id']
        return _insert_returning_id(conn,
            """INSERT INTO artifactory_role_templates
               (slug, display_name, category, description, example_prompt, position)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (slug, display_name, category, description, example_prompt, position),
            'artifactory_role_templates')


# ---- users ----

def get_user(user_id):
    with cursor() as conn:
        return _fetchone_dict(_exec(conn, "SELECT * FROM artifactory_users WHERE id = ?", (user_id,)))


def get_user_by_session(session_token):
    if not session_token:
        return None
    with cursor() as conn:
        return _fetchone_dict(_exec(conn,
            "SELECT * FROM artifactory_users WHERE session_token = ?", (session_token,)))


def list_users(limit=200):
    with cursor() as conn:
        return _fetchall_dict(_exec(conn,
            "SELECT * FROM artifactory_users ORDER BY id LIMIT ?", (limit,)))


def count_users():
    with cursor() as conn:
        cur = _exec(conn, "SELECT COUNT(*) AS n FROM artifactory_users")
        row = _fetchone_dict(cur)
        return row['n'] if row else 0


def create_user(name, role, email=None, role_template_id=None, session_token=None):
    token = session_token or secrets.token_urlsafe(24)
    with cursor() as conn:
        uid = _insert_returning_id(conn,
            """INSERT INTO artifactory_users (name, role, email, role_template_id, session_token)
               VALUES (?, ?, ?, ?, ?)""",
            (name, role, email, role_template_id, token),
            'artifactory_users')
        return uid, token


# ---- tasks ----

def list_tasks(column=None, assigned_role=None):
    sql = "SELECT * FROM artifactory_tasks WHERE 1=1"
    args = []
    if column:
        sql += " AND column_name = ?"
        args.append(column)
    if assigned_role:
        sql += " AND assigned_role = ?"
        args.append(assigned_role)
    sql += " ORDER BY position, id"
    with cursor() as conn:
        return _fetchall_dict(_exec(conn, sql, args))


def get_task(task_id):
    with cursor() as conn:
        return _fetchone_dict(_exec(conn, "SELECT * FROM artifactory_tasks WHERE id = ?", (task_id,)))


def create_task(title, description=None, column_name='todo', tag=None, assigned_role=None, due_date=None):
    with cursor() as conn:
        return _insert_returning_id(conn,
            """INSERT INTO artifactory_tasks (title, description, column_name, tag, assigned_role, due_date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, description, column_name, tag, assigned_role, due_date),
            'artifactory_tasks')


def update_task(task_id, **fields):
    allowed = {'title', 'description', 'column_name', 'tag', 'assigned_role', 'due_date', 'position'}
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not clean:
        return False
    sets = ', '.join(f"{k} = ?" for k in clean)
    args = list(clean.values()) + [task_id]
    with cursor() as conn:
        _exec(conn, f"UPDATE artifactory_tasks SET {sets} WHERE id = ?", args)
    return True


def delete_task(task_id):
    with cursor() as conn:
        _exec(conn, "DELETE FROM artifactory_tasks WHERE id = ?", (task_id,))


# ---- comments ----

def list_comments(task_id=None):
    sql = """SELECT c.*, u.name AS user_name, u.role AS user_role
             FROM artifactory_comments c
             JOIN artifactory_users u ON u.id = c.user_id"""
    args = []
    if task_id:
        sql += " WHERE c.task_id = ?"
        args.append(task_id)
    sql += " ORDER BY c.created_at DESC"
    with cursor() as conn:
        return _fetchall_dict(_exec(conn, sql, args))


def create_comment(task_id, user_id, body):
    with cursor() as conn:
        return _insert_returning_id(conn,
            "INSERT INTO artifactory_comments (task_id, user_id, body) VALUES (?, ?, ?)",
            (task_id, user_id, body),
            'artifactory_comments')


# ---- materials ----

def list_materials(task_id=None):
    sql = "SELECT * FROM artifactory_materials WHERE 1=1"
    args = []
    if task_id:
        sql += " AND task_id = ?"
        args.append(task_id)
    sql += " ORDER BY id"
    with cursor() as conn:
        return _fetchall_dict(_exec(conn, sql, args))


def create_material(task_id, name, quantity=1, unit=None, cost_usd=None, ordered=False, supplier=None):
    ordered_val = bool(ordered) if backend() == 'postgres' else (1 if ordered else 0)
    with cursor() as conn:
        return _insert_returning_id(conn,
            """INSERT INTO artifactory_materials (task_id, name, quantity, unit, cost_usd, ordered, supplier)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (task_id, name, quantity, unit, cost_usd, ordered_val, supplier),
            'artifactory_materials')


def update_material(material_id, **fields):
    allowed = {'name', 'quantity', 'unit', 'cost_usd', 'ordered', 'supplier'}
    clean = {}
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == 'ordered':
            v = bool(v) if backend() == 'postgres' else (1 if v else 0)
        clean[k] = v
    if not clean:
        return False
    sets = ', '.join(f"{k} = ?" for k in clean)
    args = list(clean.values()) + [material_id]
    with cursor() as conn:
        _exec(conn, f"UPDATE artifactory_materials SET {sets} WHERE id = ?", args)
    return True


# ---- user_artifacts ----

def save_user_artifact(user_id, source_jsx, method='paste', submission_meta=None):
    import json
    meta = json.dumps(submission_meta or {})
    with cursor() as conn:
        # Deactivate older versions so get_latest picks the newest cleanly.
        if backend() == 'postgres':
            _exec(conn, "UPDATE artifactory_user_artifacts SET is_active = FALSE WHERE user_id = ?", (user_id,))
        else:
            _exec(conn, "UPDATE artifactory_user_artifacts SET is_active = 0 WHERE user_id = ?", (user_id,))
        return _insert_returning_id(conn,
            """INSERT INTO artifactory_user_artifacts (user_id, source_jsx, method, submission_meta)
               VALUES (?, ?, ?, ?)""",
            (user_id, source_jsx, method, meta),
            'artifactory_user_artifacts')


def get_latest_user_artifact(user_id):
    with cursor() as conn:
        return _fetchone_dict(_exec(conn,
            """SELECT * FROM artifactory_user_artifacts
               WHERE user_id = ?
               ORDER BY submitted_at DESC LIMIT 1""",
            (user_id,)))
