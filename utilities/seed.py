"""
Seed demo data. Idempotent: running twice won't double-insert because
we bail if artifactory_users already has rows.

Pulls the 16 house-build kanban cards from Andy's original artifact
(captured in the HAR), assigns them to 4 seeded users, attaches a few
comments and materials for flavor. Also seeds user 1 (Andy) with the
template kanban JSX so /u/1 renders something meaningful before any
real user submits.
"""
import os

from . import db


USERS = [
    ("Andy",         "owner"),        # id 1
    ("Paul Plumber", "plumber"),      # id 2
    ("Ellie Elec",   "electrician"),  # id 3
    ("Sam Inspector","inspector"),    # id 4
]

TASKS = [
    # (title, description, column, tag, assigned_role)
    ("Secure building permits",   "Submit plans to city for approval",                    "todo",       "Permits",    "owner"),
    ("Site survey & soil test",   "Hire surveyor, geotechnical report",                   "todo",       "Inspection", "inspector"),
    ("Pour foundation",           "Footings, slab, foundation walls",                     "sourcing",   "Labor",      "owner"),
    ("Framing lumber order",      "2x4s, 2x6s, sheathing, joists",                        "sourcing",   "Materials",  "owner"),
    ("Choose windows & doors",    "Compare brands, get quotes",                           "sourcing",   "Fixtures",   "owner"),
    ("Rough framing",             "Walls, roof trusses, sheathing",                       "inprogress", "Labor",      "owner"),
    ("Electrical rough-in",       "Panel, wiring, boxes before drywall",                  "todo",       "Labor",      "electrician"),
    ("Plumbing rough-in",         "Supply lines, drains, vents",                          "todo",       "Labor",      "plumber"),
    ("HVAC installation",         "Ductwork, furnace, AC unit",                           "todo",       "Labor",      "owner"),
    ("Insulation",                "Walls, attic, floors",                                 "todo",       "Materials",  "owner"),
    ("Drywall & finish",          "Hang, tape, mud, sand, paint",                         "todo",       "Labor",      "owner"),
    ("Pick cabinets & countertops","Kitchen and bathrooms",                               "sourcing",   "Fixtures",   "owner"),
    ("Flooring selection",        "Hardwood, tile, carpet decisions",                     "sourcing",   "Design",     "owner"),
    ("Waiting on inspector",      "Framing inspection scheduled",                         "blocked",    "Inspection", "inspector"),
    ("Architectural plans finalized","Signed off by architect",                           "done",       "Design",     "owner"),
    ("Lot cleared & graded",      "Excavation complete",                                  "done",       "Labor",      "owner"),
]

COMMENTS = [
    # (task_title_prefix, user_name, body)
    ("Plumbing rough-in",   "Paul Plumber",  "I can start Mon morning if the framing inspection is cleared."),
    ("Electrical rough-in", "Ellie Elec",    "Need the panel spec finalized before I pull wire."),
    ("Waiting on inspector","Sam Inspector", "Framing inspection slot 2026-04-28 9am. Be ready."),
    ("Pour foundation",     "Andy",          "Concrete delivery confirmed for the 24th."),
]

MATERIALS = [
    # (task_title_prefix, name, qty, unit, cost, ordered)
    ("Framing lumber order", "2x4 x 8ft",         200, "ea",   5.40,  False),
    ("Framing lumber order", "2x6 x 10ft",         80, "ea",   9.10,  False),
    ("Framing lumber order", "OSB sheathing 4x8",  60, "ea",  24.00,  False),
    ("Plumbing rough-in",    "PEX tubing 1/2\"",  500, "ft",   0.80,  True),
    ("Electrical rough-in",  "12-2 Romex",       1000, "ft",   0.65,  False),
    ("Insulation",           "R-15 fiberglass batt", 30, "bag", 55.00, False),
]


def seed():
    # Idempotency guard
    if db.list_users():
        return {"status": "already-seeded"}

    user_ids_by_name = {}
    for name, role in USERS:
        uid = db.create_user(name=name, role=role)
        user_ids_by_name[name] = uid

    task_ids_by_title = {}
    for title, desc, col, tag, role in TASKS:
        tid = db.create_task(title=title, description=desc, column_name=col, tag=tag, assigned_role=role)
        task_ids_by_title[title] = tid

    for title_prefix, user_name, body in COMMENTS:
        tid = task_ids_by_title.get(title_prefix)
        uid = user_ids_by_name.get(user_name)
        if tid and uid:
            db.create_comment(task_id=tid, user_id=uid, body=body)

    for title_prefix, name, qty, unit, cost, ordered in MATERIALS:
        tid = task_ids_by_title.get(title_prefix)
        if tid:
            db.create_material(task_id=tid, name=name, quantity=qty, unit=unit, cost_usd=cost, ordered=ordered)

    # Seed the default template artifact for user 1 (Andy) so /u/1 isn't empty.
    template_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'docs', 'template_artifact.jsx')
    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as f:
            tpl_jsx = f.read()
        db.save_user_artifact(user_id=user_ids_by_name['Andy'], source_jsx=tpl_jsx, method='paste')

    return {
        "status": "seeded",
        "users": len(USERS),
        "tasks": len(TASKS),
        "comments": len(COMMENTS),
        "materials": len(MATERIALS),
        "seeded_andy_with_template": os.path.exists(template_path),
    }


if __name__ == "__main__":
    db.init_schema()
    print(seed())
