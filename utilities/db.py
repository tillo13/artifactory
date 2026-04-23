"""
Database layer. SQLite locally, Postgres on Cloud SQL in prod (not wired yet).

Tables (all prefixed `artifactory_` so they don't collide if we later move
into the shared kumori Postgres):

- artifactory_users           — id, name, role, created_at
- artifactory_tasks           — id, title, description, column, tag, assigned_role, due_date, created_at
- artifactory_comments        — id, task_id, user_id, body, created_at
- artifactory_materials       — id, task_id, name, quantity, unit, cost_usd, ordered
- artifactory_user_artifacts  — id, user_id, source_jsx, method, submitted_at

The schema is intentionally tiny. It is the *shared contract* that users
design against. Anything that makes the schema bigger makes every submitted
frontend more brittle.
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from config import Config


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS artifactory_users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    role          TEXT NOT NULL,        -- owner | architect | plumber | electrician | inspector | vendor
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS artifactory_tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    description     TEXT,
    column_name     TEXT NOT NULL,      -- todo | sourcing | inprogress | blocked | done
    tag             TEXT,               -- Permits | Inspection | Labor | Materials | Fixtures | Design
    assigned_role   TEXT,               -- matches users.role
    due_date        TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS artifactory_comments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    INTEGER NOT NULL REFERENCES artifactory_tasks(id),
    user_id    INTEGER NOT NULL REFERENCES artifactory_users(id),
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS artifactory_materials (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id   INTEGER NOT NULL REFERENCES artifactory_tasks(id),
    name      TEXT NOT NULL,
    quantity  REAL NOT NULL DEFAULT 1,
    unit      TEXT,
    cost_usd  REAL,
    ordered   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS artifactory_user_artifacts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES artifactory_users(id),
    source_jsx   TEXT NOT NULL,
    method       TEXT NOT NULL,        -- paste | extension | url
    submitted_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tasks_col ON artifactory_tasks(column_name);
CREATE INDEX IF NOT EXISTS idx_comments_task ON artifactory_comments(task_id);
CREATE INDEX IF NOT EXISTS idx_materials_task ON artifactory_materials(task_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_user ON artifactory_user_artifacts(user_id);
"""


def _connect():
    os.makedirs(os.path.dirname(Config.SQLITE_PATH), exist_ok=True)
    conn = sqlite3.connect(Config.SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def cursor():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_schema():
    with cursor() as c:
        c.executescript(_SCHEMA_SQL)


# ----- users -----

def get_user(user_id):
    with cursor() as c:
        row = c.execute("SELECT * FROM artifactory_users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def list_users():
    with cursor() as c:
        return [dict(r) for r in c.execute("SELECT * FROM artifactory_users ORDER BY id").fetchall()]


def create_user(name, role):
    with cursor() as c:
        cur = c.execute("INSERT INTO artifactory_users (name, role) VALUES (?, ?)", (name, role))
        return cur.lastrowid


# ----- tasks -----

def list_tasks(column=None, assigned_role=None):
    sql = "SELECT * FROM artifactory_tasks WHERE 1=1"
    args = []
    if column:
        sql += " AND column_name = ?"
        args.append(column)
    if assigned_role:
        sql += " AND assigned_role = ?"
        args.append(assigned_role)
    sql += " ORDER BY id"
    with cursor() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def get_task(task_id):
    with cursor() as c:
        row = c.execute("SELECT * FROM artifactory_tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None


def create_task(title, description=None, column_name='todo', tag=None, assigned_role=None, due_date=None):
    with cursor() as c:
        cur = c.execute(
            """INSERT INTO artifactory_tasks (title, description, column_name, tag, assigned_role, due_date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, description, column_name, tag, assigned_role, due_date),
        )
        return cur.lastrowid


def update_task(task_id, **fields):
    if not fields:
        return False
    allowed = {'title', 'description', 'column_name', 'tag', 'assigned_role', 'due_date'}
    sets = [f"{k} = ?" for k in fields if k in allowed]
    args = [fields[k] for k in fields if k in allowed]
    if not sets:
        return False
    args.append(task_id)
    with cursor() as c:
        c.execute(f"UPDATE artifactory_tasks SET {', '.join(sets)} WHERE id = ?", args)
    return True


def delete_task(task_id):
    with cursor() as c:
        c.execute("DELETE FROM artifactory_comments WHERE task_id = ?", (task_id,))
        c.execute("DELETE FROM artifactory_materials WHERE task_id = ?", (task_id,))
        c.execute("DELETE FROM artifactory_tasks WHERE id = ?", (task_id,))


# ----- comments -----

def list_comments(task_id=None):
    sql = """SELECT c.*, u.name as user_name, u.role as user_role
             FROM artifactory_comments c
             JOIN artifactory_users u ON u.id = c.user_id"""
    args = []
    if task_id:
        sql += " WHERE c.task_id = ?"
        args.append(task_id)
    sql += " ORDER BY c.created_at DESC"
    with cursor() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def create_comment(task_id, user_id, body):
    with cursor() as c:
        cur = c.execute(
            "INSERT INTO artifactory_comments (task_id, user_id, body) VALUES (?, ?, ?)",
            (task_id, user_id, body),
        )
        return cur.lastrowid


# ----- materials -----

def list_materials(task_id=None):
    sql = "SELECT * FROM artifactory_materials WHERE 1=1"
    args = []
    if task_id:
        sql += " AND task_id = ?"
        args.append(task_id)
    sql += " ORDER BY id"
    with cursor() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def create_material(task_id, name, quantity=1, unit=None, cost_usd=None, ordered=False):
    with cursor() as c:
        cur = c.execute(
            """INSERT INTO artifactory_materials (task_id, name, quantity, unit, cost_usd, ordered)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (task_id, name, quantity, unit, cost_usd, 1 if ordered else 0),
        )
        return cur.lastrowid


def update_material(material_id, **fields):
    allowed = {'name', 'quantity', 'unit', 'cost_usd', 'ordered'}
    sets = [f"{k} = ?" for k in fields if k in allowed]
    args = []
    for k in fields:
        if k in allowed:
            v = fields[k]
            if k == 'ordered':
                v = 1 if v else 0
            args.append(v)
    if not sets:
        return False
    args.append(material_id)
    with cursor() as c:
        c.execute(f"UPDATE artifactory_materials SET {', '.join(sets)} WHERE id = ?", args)
    return True


# ----- user_artifacts -----

def save_user_artifact(user_id, source_jsx, method='paste'):
    with cursor() as c:
        cur = c.execute(
            "INSERT INTO artifactory_user_artifacts (user_id, source_jsx, method) VALUES (?, ?, ?)",
            (user_id, source_jsx, method),
        )
        return cur.lastrowid


def get_latest_user_artifact(user_id):
    with cursor() as c:
        row = c.execute(
            """SELECT * FROM artifactory_user_artifacts
               WHERE user_id = ?
               ORDER BY submitted_at DESC LIMIT 1""",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None
