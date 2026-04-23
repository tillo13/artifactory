"""
Schema documentation — the *contract* shared with every user's Claude session.

build_preamble() returns the text block users paste into Claude so the
artifact they design consumes our REST API correctly. When a role_template
is passed in, the preamble ends with a role-specific starter prompt.
"""


def build_preamble(base_url: str, role_template: dict = None) -> str:
    role_section = ""
    if role_template:
        role_section = f"""

YOUR ROLE: {role_template['display_name']}
{role_template.get('description') or ''}

SUGGESTED STARTER PROMPT (you can paraphrase):
  {role_template.get('example_prompt') or ''}
"""

    return f"""You are designing a React artifact frontend for the Artifactory shared backend.

CONTRACT — you must only call these endpoints. Do NOT invent new ones.

Base URL: {base_url}  (use relative paths — we'll rehost your artifact on our origin)

  GET    /api/v1/users/me
    → {{ id, name, role, created_at }}

  GET    /api/v1/users
    → [{{ id, name, role }}, ...]

  GET    /api/v1/tasks?column=todo&assigned_role=plumber
    → [{{ id, title, description, column_name, tag, assigned_role, due_date, created_at }}, ...]

  POST   /api/v1/tasks
    body {{ title, description?, column_name?, tag?, assigned_role?, due_date? }}
    → created task

  PATCH  /api/v1/tasks/<id>
    body any subset of {{ title, description, column_name, tag, assigned_role, due_date }}
    → updated task

  DELETE /api/v1/tasks/<id>

  GET    /api/v1/comments?task_id=<id>
    → [{{ id, task_id, user_id, user_name, user_role, body, created_at }}, ...]

  POST   /api/v1/comments
    body {{ task_id, body }} (user_id comes from session)

  GET    /api/v1/materials?task_id=<id>
    → [{{ id, task_id, name, quantity, unit, cost_usd, ordered, supplier }}, ...]

  POST   /api/v1/materials
    body {{ task_id, name, quantity?, unit?, cost_usd?, ordered?, supplier? }}

  PATCH  /api/v1/materials/<id>
    body any subset; use to toggle `ordered`.

ENUMS (use these exact strings):
  column_name : "todo" | "sourcing" | "inprogress" | "blocked" | "done"
  tag         : "Permits" | "Inspection" | "Labor" | "Materials" | "Fixtures" | "Design"

PLATFORM CONSTRAINTS — your code will run in an in-browser Babel Standalone shell:
  - Start with: function App() {{ ... }}  (no `import`/`export` — React is a global)
  - Use React.useState / React.useEffect (hooks are on the React global)
  - Tailwind utility classes are available; no CDN libraries beyond React + Tailwind
  - window.CURRENT_USER is injected before your artifact runs: {{ id, name, role }}
  - All fetch() calls to /api/v1/* just work — same origin, cookies handled
  - Do NOT use localStorage, window.storage, window.claude.complete — those are Claude-sandbox-only
  - Do NOT import any npm packages or external CDNs

STYLE:
  - Dense information, no empty-states-with-illustrations
  - Respect the current user's role — filter to the data they care about
  - Show how many things, not just "things"
{role_section}
When you're done, copy the artifact's JSX source and paste it at {base_url}/submit to go live.
"""


# OpenAPI spec unchanged from v1 — served at /openapi.json
OPENAPI = {
    "openapi": "3.0.3",
    "info": {
        "title": "Artifactory Shared Backend",
        "version": "0.2.0",
        "description": "One shared backend, many AI-designed frontends. Pick a role, design a view in Claude, submit the JSX.",
    },
    "servers": [{"url": "/"}],
    "components": {
        "schemas": {
            "User":     {"type": "object", "properties": {"id": {"type": "integer"}, "name": {"type": "string"}, "role": {"type": "string"}}},
            "Task":     {"type": "object", "properties": {"id": {"type": "integer"}, "title": {"type": "string"}, "description": {"type": "string"}, "column_name": {"type": "string"}, "tag": {"type": "string"}, "assigned_role": {"type": "string"}, "due_date": {"type": "string"}}},
            "Comment":  {"type": "object", "properties": {"id": {"type": "integer"}, "task_id": {"type": "integer"}, "user_id": {"type": "integer"}, "body": {"type": "string"}}},
            "Material": {"type": "object", "properties": {"id": {"type": "integer"}, "task_id": {"type": "integer"}, "name": {"type": "string"}, "quantity": {"type": "number"}, "cost_usd": {"type": "number"}, "ordered": {"type": "boolean"}}},
        }
    },
    "paths": {
        "/api/v1/users/me":       {"get":  {"summary": "Current user"}},
        "/api/v1/users":          {"get":  {"summary": "All users"}},
        "/api/v1/tasks":          {"get":  {"summary": "List tasks"}, "post":  {"summary": "Create task"}},
        "/api/v1/tasks/{id}":     {"get":  {"summary": "Get task"},   "patch": {"summary": "Update task"}, "delete": {"summary": "Delete task"}},
        "/api/v1/comments":       {"get":  {"summary": "List comments"}, "post": {"summary": "Create comment"}},
        "/api/v1/materials":      {"get":  {"summary": "List materials"}, "post": {"summary": "Create material"}},
        "/api/v1/materials/{id}": {"patch":{"summary": "Update material"}},
    },
}
