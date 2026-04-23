# Artifactory

**One backend. Many AI-designed frontends.** Pick a role on a house build, design your own view in Claude, watch it go live alongside everyone else's against the same shared data.

🔗 **Live demo:** https://artifactory-io.uc.r.appspot.com

---

## Try it in 60 seconds

1. Go to **https://artifactory-io.uc.r.appspot.com**
2. Pick a role from the dropdown — plumber, electrician, home stager, tree trimmer, 45 options
3. Click **🚀 Open in Claude with prompt** (Claude opens pre-loaded with the schema + your role-specific starter)
4. Iterate with Claude until the view looks right, then click **Copy** on the artifact
5. Go to **/submit**, paste the JSX, hit submit — your view is live at **/u/\<your-id\>**, share the link

That's it. You just built a custom interface for a shared backend without writing a frontend person.

## Why this exists

Claude Artifacts are a great design surface but the sandbox is airtight — your artifact can't reach your own backend, and storage caps at 20MB. If you want many people to design UIs against *your* shared data, you flip the script: host the backend yourself, publish the schema contract, let users vibe-code frontends in Claude, and host their submissions on your domain where the sandbox rules don't apply.

That's Artifactory. The demo uses a fake house build. Same idea works for any shared schema — internal tools over a CMDB, dashboards over Salesforce, whatever.

## Four example views of the same data

- **[/u/1 Andy](https://artifactory-io.uc.r.appspot.com/u/1)** — 5-column kanban, all 16 tasks
- **[/u/2 Paul (plumber)](https://artifactory-io.uc.r.appspot.com/u/2)** — filtered task queue
- **[/u/3 Ellie (electrician)](https://artifactory-io.uc.r.appspot.com/u/3)** — filtered task queue
- **[/u/4 Sam (inspector)](https://artifactory-io.uc.r.appspot.com/u/4)** — column-count dashboard

Same 16 fake tasks underneath all four.

## The shared contract (what every submitted artifact can call)

```
GET    /api/v1/users/me
GET    /api/v1/users
GET    /api/v1/tasks?column=&assigned_role=
POST   /api/v1/tasks
PATCH  /api/v1/tasks/<id>
DELETE /api/v1/tasks/<id>
GET    /api/v1/comments?task_id=
POST   /api/v1/comments
GET    /api/v1/materials?task_id=
POST   /api/v1/materials
PATCH  /api/v1/materials/<id>
```

Full spec: **[/openapi.json](https://artifactory-io.uc.r.appspot.com/openapi.json)**

## Platform constraints your JSX must respect

- Start with `function App() { ... }` (no `import`/`export` — React is a global)
- Use `React.useState` / `React.useEffect`
- Tailwind classes work, no other CDNs or npm packages
- `window.CURRENT_USER` is pre-injected: `{ id, name, role }`
- `fetch('/api/v1/...')` just works (same origin, cookies handled)
- Don't use `localStorage`, `window.storage`, or `window.claude.complete` — those only exist inside Claude's own sandbox

See **[docs/template_artifact.jsx](docs/template_artifact.jsx)** for a working starter kanban.

## Run it yourself

```bash
git clone https://github.com/tillo13/artifactory.git
cd artifactory
python -m venv venv_artifactory
source venv_artifactory/bin/activate
pip install -r requirements.txt
python main.py    # opens on :8080, uses SQLite locally
```

## Architecture

```
┌──────────────────────┐       OpenAPI contract        ┌───────────────────┐
│  Claude artifact     │◄────  /schema (preamble)  ────│   artifactory     │
│  session (user's)    │                               │   Flask + CloudSQL│
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

- **Local dev:** SQLite (`data/artifactory.db`)
- **Production (App Engine):** Postgres on shared kumori Cloud SQL
- **Frontend hosting:** In-browser Babel Standalone — no build pipeline, no Webpack
- **Rate limiting:** per-IP in-memory counters; max 5 submits/min/IP, 30/day/IP
- **Hard caps:** max 10,000 total users (free-tier sanity)

## Three ingestion paths (v1 ships #1)

| # | Path | Status |
|---|---|---|
| 1 | Paste JSX into the form | ✅ live |
| 2 | Chrome extension (fork of [elgertam/claude-artifact-downloader](https://github.com/elgertam/claude-artifact-downloader)) | 🚧 planned |
| 3 | Paste URL + session cookie | 🚧 planned |

Public Claude artifact URLs are Cloudflare-Turnstile-gated, so server-side URL fetching without a user's session cookie doesn't work. Extension and cookie paths route around that.

## What's deliberately not here

- **Real auth** — cookie-based session only; no email/OAuth
- **Submitted-code sandboxing** — all artifacts run on this origin. Fine for fake demo data, not fine for production
- **Schema versioning** — if I change the schema, submitted artifacts may break
- **Uptime guarantees** — it's a hobby demo on App Engine F1 free tier

## Demo disclaimer

All data is fake. Submitted artifacts run in-browser on this origin with read/write access to the shared fake dataset. Don't submit anything malicious. Don't expect uptime. If the visitor cap is reached, new role picks get rejected until the demo resets.

## Credits

- [`claudio-silva/claude-artifact-runner`](https://github.com/claudio-silva/claude-artifact-runner) — local JSX compile/deploy
- [`elgertam/claude-artifact-downloader`](https://github.com/elgertam/claude-artifact-downloader) — Chrome-extension pattern
- [OpenZeppelin Contracts UI Builder](https://www.openzeppelin.com/news/introducing-contracts-ui-builder) — closest existing "schema → auto-generated frontend" commercial product (blockchain-only though)
