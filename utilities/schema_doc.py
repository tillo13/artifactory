"""
Schema documentation — the *contract* shared with every user's Claude session.

`build_preamble(base_url)` returns the text block users paste into Claude so
the artifact they design will consume our REST API correctly.

`OPENAPI` is the machine-readable spec served at /openapi.json.
"""


def build_preamble(base_url: str) -> str:
    return f"""You are designing a React artifact frontend for the Artifactory shared backend.

CONTRACT — you must only call these endpoints. Do NOT invent new ones.

Base URL: {base_url}  (but use relative paths, we'll rehost your artifact on our origin)

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
    → [{{ id, task_id, name, quantity, unit, cost_usd, ordered }}, ...]

  POST   /api/v1/materials
    body {{ task_id, name, quantity?, unit?, cost_usd?, ordered? }}

  PATCH  /api/v1/materials/<id>
    body any subset; use to toggle `ordered`.

ENUMS (use these exact strings):
  column_name : "todo" | "sourcing" | "inprogress" | "blocked" | "done"
  tag         : "Permits" | "Inspection" | "Labor" | "Materials" | "Fixtures" | "Design"
  role        : "owner" | "architect" | "plumber" | "electrician" | "inspector" | "vendor"

PLATFORM CONSTRAINTS — this artifact will run in a Babel-Standalone shell:
  - Start with: function App() {{ ... }}  (no `import`/`export` — React is a global)
  - Use React.useState / React.useEffect (hooks are on the React global)
  - Tailwind utility classes are available; no CDN libraries beyond React + Tailwind
  - window.CURRENT_USER is injected before your artifact runs: {{ id, name, role }}
  - All fetch() calls to /api/v1/* just work — same origin, cookies handled
  - Do NOT use localStorage, window.storage, or window.claude.complete — those are Claude-sandbox-only
  - Do NOT import any npm packages or external CDNs

STYLE:
  - Dense information, no empty-states-with-illustrations
  - Respect the current user's role — e.g. a plumber view should filter tasks to assigned_role="plumber" by default
  - Show how many things, not just "things"

When you're done, I'll copy your artifact's JSX and paste it into {base_url}/submit.
"""


OPENAPI = {
    "openapi": "3.0.3",
    "info": {
        "title": "Artifactory Shared Backend",
        "version": "0.1.0",
        "description": "The contract every user-submitted frontend rides on. House-build demo.",
    },
    "servers": [{"url": "/"}],
    "components": {
        "schemas": {
            "User": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "role": {"type": "string", "enum": ["owner", "architect", "plumber", "electrician", "inspector", "vendor"]},
                    "created_at": {"type": "string", "format": "date-time"},
                },
            },
            "Task": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "title": {"type": "string"},
                    "description": {"type": "string", "nullable": True},
                    "column_name": {"type": "string", "enum": ["todo", "sourcing", "inprogress", "blocked", "done"]},
                    "tag": {"type": "string", "nullable": True, "enum": ["Permits", "Inspection", "Labor", "Materials", "Fixtures", "Design", None]},
                    "assigned_role": {"type": "string", "nullable": True},
                    "due_date": {"type": "string", "format": "date", "nullable": True},
                    "created_at": {"type": "string", "format": "date-time"},
                },
            },
            "Comment": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "task_id": {"type": "integer"},
                    "user_id": {"type": "integer"},
                    "user_name": {"type": "string"},
                    "user_role": {"type": "string"},
                    "body": {"type": "string"},
                    "created_at": {"type": "string", "format": "date-time"},
                },
            },
            "Material": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "task_id": {"type": "integer"},
                    "name": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit": {"type": "string", "nullable": True},
                    "cost_usd": {"type": "number", "nullable": True},
                    "ordered": {"type": "boolean"},
                },
            },
        }
    },
    "paths": {
        "/api/v1/users/me":   {"get": {"summary": "Current user", "responses": {"200": {"description": "OK", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/User"}}}}}}},
        "/api/v1/users":      {"get": {"summary": "All users",    "responses": {"200": {"description": "OK", "content": {"application/json": {"schema": {"type": "array", "items": {"$ref": "#/components/schemas/User"}}}}}}}},
        "/api/v1/tasks": {
            "get": {
                "summary": "List tasks",
                "parameters": [
                    {"name": "column",        "in": "query", "schema": {"type": "string"}},
                    {"name": "assigned_role", "in": "query", "schema": {"type": "string"}},
                ],
                "responses": {"200": {"description": "OK", "content": {"application/json": {"schema": {"type": "array", "items": {"$ref": "#/components/schemas/Task"}}}}}},
            },
            "post": {"summary": "Create task", "responses": {"201": {"description": "Created"}}},
        },
        "/api/v1/tasks/{id}": {
            "get":    {"summary": "Get task",    "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}]},
            "patch":  {"summary": "Update task", "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}]},
            "delete": {"summary": "Delete task", "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}]},
        },
        "/api/v1/comments":   {"get": {"summary": "List comments"}, "post": {"summary": "Create comment"}},
        "/api/v1/materials":  {"get": {"summary": "List materials"}, "post": {"summary": "Create material"}},
        "/api/v1/materials/{id}": {
            "patch": {"summary": "Update material", "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}]}
        },
    },
}
