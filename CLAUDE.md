# CLAUDE.md

Guidance for Claude Code working in this repo.

## What this project is

Artifactory is a public-demo Flask app that lets visitors design their own
React frontend (in a Claude chat) against a shared house-build backend. The
user's submitted JSX is rehosted at `/u/<their-id>` via in-browser Babel
Standalone. Everyone sees the same fake data, rendered whichever way they
vibed it into existence.

Live: https://artifactory-io.uc.r.appspot.com
GCP project: `artifactory-io`
GitHub: https://github.com/tillo13/artifactory

## Deviations from flask-kumori-stack (intentional)

- **Secrets live in `artifactory-io` Secret Manager, not `kumori-404602`.**
  The skill says new apps put `${PREFIX}_POSTGRES_*` secrets in kumori's
  project. We duplicated them in artifactory-io's own project. Both work;
  this variant is slightly off-pattern. If unified later, update
  `utilities/db.py:_pg_credentials()` to point Secret Manager at
  `project="kumori-404602"`.
- **F1 instance + `max_instances: 1`** (skill says F2 + 2). F1 fits App
  Engine free tier, max=1 hard-caps cost for a public demo. Don't raise.
- **Dual-backend `utilities/db.py`** (SQLite local, Postgres on GAE).
  Most kumori apps are Postgres-only. The split here lets `python main.py`
  work with zero GCP auth on a fresh clone — important for this being a
  shareable demo repo.

## Non-obvious behavior worth remembering

- `init_schema()` uses `pg_advisory_lock(72614001)` to serialize DDL
  across gunicorn workers. **Don't remove.** The bare `CREATE TABLE IF
  NOT EXISTS` racing 2 workers produced `UniqueViolation on
  pg_class_relname_nsp_index` for sequence creation — see commit after
  first prod deploy on 2026-04-22.
- `cursor()` does a `SELECT 1` probe per checkout and rebuilds the pool
  if the connection is dead. Mandatory — Cloud SQL drops idle conns
  after ~10 min, App Engine scales to 0, first request would 500
  without this. Same pattern as kumori/postgres_utils.py.
- Rate limits are **per-gunicorn-worker** (in-memory dict), so with
  `--workers 2` the effective cap is 2× what's in `utilities/limit.py`.
  Fine for a demo. If you ever need real limits, move to a DB-backed
  counter (there's no Redis in this stack).
- Current-user resolution priority in `main.py:current_user()`:
  `session cookie → ?user=N → user 1`. Session cookie is set by
  `/pick-role`; the `?user=N` fallback lets the demo-view top-bar
  work without a session.

## Run locally

```bash
python -m venv venv_artifactory
source venv_artifactory/bin/activate
pip install -r requirements.txt
python main.py           # backend=sqlite, listens on :8080
```

DB auto-creates + seeds on first boot. The 45 role templates upsert on
every boot (safe to re-run).

## Run tests

```bash
python -m tests.full_test
```

The skill requires passing tests before any deploy. Tests use the Flask
test client against a temporary SQLite file in `/tmp/`.

## Deploy

```bash
deploy "commit message"
```

Standard `~/.local/bin/deploy`. First deploy after a `requirements.txt`
change is ~5 min (Cloud Build rebuilds container layers from scratch);
subsequent deploys with unchanged deps are ~90s. Don't run deploys in
parallel — the `/tmp/gcloud_deploy.lock` enforces it anyway.

## Directory map

```
main.py                       single-file Flask routes
config.py                     Config class (GCP project, sqlite path, ports)
app.yaml / deploy.json        GAE + deploy-tool config
utilities/
  db.py                       dual-backend layer. SQLite + Postgres dispatch
  schema_doc.py               build_preamble() + OPENAPI dict
  roles.py                    the 45-role catalog + seed_roles()
  seed.py                     demo users + tasks + comments + materials
  limit.py                    in-memory rate limiter
templates/
  _base.html                  portal chrome
  landing.html                role dropdown
  schema.html                 role-aware preamble + "Open in Claude" button
  submit.html                 JSX paste form
  user_shell.html             React/Babel shell for /u/<id>
  capped.html                 shown when WARM_USERS hit
docs/
  template_artifact.jsx       working starter the README points users to
  screenshots/                README assets
tests/full_test.py            integration tests
```

## What NOT to do

- Don't use blueprints. All routes in `main.py`.
- Don't use an ORM. Raw SQL via `utilities/db.py`.
- Don't add npm/Node runtime to the server. The JSX compile happens
  client-side via Babel Standalone from unpkg; that's the whole point.
- Don't touch the Postgres advisory-lock key `72614001` without
  migrating every live instance — two workers with different keys
  would defeat the serialization.
- Don't attribute commits to Claude (user's global preference; skill
  also says this).
