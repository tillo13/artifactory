# Artifactory

**One backend. Many AI-designed frontends.**

Users design their own views in Claude Artifacts against a shared schema. Submit the JSX here. Your view lights up at `/u/<your-id>`, riding the same backend everyone else sees.

House-build kanban is the demo: owner gets a kanban, plumber gets a task queue, inspector gets a calendar — all over the same tasks table.

## Why this exists

Claude Artifacts are a fantastic design surface but their sandbox is airtight — you can't reach your own backend, and storage is capped at 20MB per artifact. If you want multiple people to use a Claude-designed UI against shared data, you have to flip the script: host the backend yourself, let users design frontends against your schema, deploy their submissions on your domain where the sandbox rules don't apply.

That's Artifactory.

## Architecture (v1)

```
┌──────────────────────┐       OpenAPI contract        ┌───────────────────┐
│  Claude artifact     │◄────  /schema (preamble)  ────│   artifactory     │
│  session (user's)    │                               │   Flask + SQLite  │
└──────────┬───────────┘                               └─────────┬─────────┘
           │ user copies JSX out                                 │
           ▼                                                     │
┌──────────────────────┐        POST /submit                     │
│  /submit textarea    │────────────────────────────────────────►│
└──────────────────────┘                                         │
                                                                 ▼
                                         /u/<id> renders JSX via Babel Standalone
                                         against /api/v1/* (same-origin fetch)
```

No build step. JSX is compiled in-browser by `@babel/standalone`. No auth server. `?user=<N>` switches identity for the demo. No arbitrary user code sandboxing. All trust boundaries are fine for the demo; tighten before any real production use.

## Run locally

```bash
cd ~/Desktop/code/artifactory
python -m venv venv_artifactory
source venv_artifactory/bin/activate
pip install -r requirements.txt
python main.py
```

Opens on `:8080`. DB auto-creates + auto-seeds on first boot.

- `http://localhost:8080/` — landing
- `http://localhost:8080/schema` — preamble to paste into Claude
- `http://localhost:8080/submit` — paste your artifact JSX
- `http://localhost:8080/u/1` — Andy's view
- `http://localhost:8080/u/2` — Paul Plumber's view
- `http://localhost:8080/u/3` — Ellie Elec's view
- `http://localhost:8080/u/4` — Sam Inspector's view
- `http://localhost:8080/api/v1/tasks` — the REST API
- `http://localhost:8080/openapi.json` — machine spec

## The flow (for a user)

1. Open `/schema`, copy the preamble, paste it into a fresh Claude chat.
2. Tell Claude what you want: *"build me a plumber-only task queue grouped by tag"*.
3. Claude generates an artifact. Click its **Copy** button.
4. Open `/submit`, paste the JSX, pick which user slot it belongs to, submit.
5. Visit `/u/<your-id>` — your view is live against the same backend everyone else uses.

See [`docs/template_artifact.jsx`](docs/template_artifact.jsx) for a working starter component.

## Schema

Tables (all prefixed `artifactory_`):

- `artifactory_users` — id, name, role
- `artifactory_tasks` — id, title, description, column_name, tag, assigned_role, due_date
- `artifactory_comments` — id, task_id, user_id, body
- `artifactory_materials` — id, task_id, name, quantity, unit, cost_usd, ordered
- `artifactory_user_artifacts` — id, user_id, source_jsx, method

Enums:
- `column_name` ∈ `todo | sourcing | inprogress | blocked | done`
- `tag` ∈ `Permits | Inspection | Labor | Materials | Fixtures | Design`
- `role` ∈ `owner | architect | plumber | electrician | inspector | vendor`

## Three ingestion paths

v1 ships path 1. Paths 2 and 3 are stubs on the submit page.

| Path | Status | Notes |
|---|---|---|
| Paste JSX | ✅ shipping | Claude's built-in Copy button → our textarea. |
| Chrome extension | 🚧 planned | Fork of [elgertam/claude-artifact-downloader](https://github.com/elgertam/claude-artifact-downloader) — runs in the user's logged-in Claude tab, POSTs artifact JSON to `/submit`. |
| URL + session cookie | 🚧 planned | Server hits `claude.ai/api/published_artifacts/<uuid>` with user's cookie. Brittle, but works. |

Direct server-side fetch of `claude.ai/public/artifacts/<uuid>` without a user's cookie is blocked by Cloudflare Turnstile — tested, confirmed.

## What's NOT in v1

- Real auth (Auth0 wire-in comes next; currently demo is `?user=<N>`)
- Cloud SQL wiring (SQLite for now; trivial swap to the shared kumori Postgres when wanted)
- Per-user subdomains (everyone is on `/u/<id>`; fine for a trusted demo, not for strangers)
- Code sandboxing of submitted JSX (user submissions run on our origin with our cookies — fine for a small trusted crew, not for public use)
- Schema versioning / drift handling (if you change the schema, re-submit your artifact)

## Deploy

Project: `artifactory-io` (GCP). Appspot URL: `https://artifactory-io.uc.r.appspot.com`.

Hasn't been deployed yet. To deploy, link billing to the project, then use Andy's [master deploy tool](https://github.com/tillo13) pattern:

```bash
deploy "initial ship"
```

## Prior art / credits

- [`claudio-silva/claude-artifact-runner`](https://github.com/claudio-silva/claude-artifact-runner) — proved the JSX-compile-locally pattern
- [`elgertam/claude-artifact-downloader`](https://github.com/elgertam/claude-artifact-downloader) — the Chrome extension pattern we'll fork for path 2
- [`risonsimon/claude-artifacts-react`](https://github.com/risonsimon/claude-artifacts-react) — the fork-and-deploy pattern
- [OpenZeppelin Contracts UI Builder](https://www.openzeppelin.com/news/introducing-contracts-ui-builder) — closest existing "schema → auto-generated frontend" pattern (blockchain-specific)
