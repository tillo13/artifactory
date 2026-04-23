"""
The catalog of ~45 house-build roles visitors can pick from.

Each role has:
  slug            stable identifier, used in URLs
  display_name    shown in dropdown
  category        one of: trades | outdoor | inspection | interior | service | management
  description     one-line blurb explaining what this role cares about
  example_prompt  seed prompt Claude can riff on — sets the tone for the user's view

The prompts are deliberately specific. Vague prompts get vague artifacts.
"""

# (slug, display_name, category, description, example_prompt)
ROLES = [
    # -------- MANAGEMENT --------
    ("owner", "Owner / Homeowner", "management",
     "Big-picture view of the whole build.",
     "Build me a 5-column kanban with every task, colored by tag. I want to see what's blocked at a glance and drag cards between columns."),
    ("architect", "Architect", "management",
     "Design phase and drawing approvals.",
     "Build a document-review dashboard: list every Design-tagged task, show who's assigned, click-to-approve buttons."),
    ("general_contractor", "General Contractor", "management",
     "Crew coordination and critical path.",
     "Build a crew schedule view: group tasks by assigned_role, stack by column, highlight anything in 'blocked' in red."),
    ("project_manager", "Project Manager", "management",
     "Deadlines and dependencies.",
     "Build a timeline / Gantt-lite view using due_date, group by tag, show a progress bar per tag."),

    # -------- TRADES --------
    ("electrician_general", "Electrician (General)", "trades",
     "Wiring, panel, outlets.",
     "Build a punchlist filtered to assigned_role='electrician', grouped by column. Checkbox each task as I complete it (PATCH column_name='done')."),
    ("electrician_lighting", "Electrician — Lighting Specialist", "trades",
     "Light fixtures, dimmers, recessed cans.",
     "Build a lighting-specific view: filter to Fixtures-tagged tasks, count fixtures by room (use description), show install status."),
    ("plumber_general", "Plumber", "trades",
     "Supply lines, drains, vents.",
     "Build a plumbing task queue with inline comment add for each task (POST /api/v1/comments)."),
    ("plumber_gas", "Plumber — Gas Fitter", "trades",
     "Gas lines and appliance hookups.",
     "Build a gas-line checklist with safety-inspection status per connection."),
    ("carpenter", "Carpenter", "trades",
     "Framing, trim, finish carpentry.",
     "Build a Labor-tagged task board, timer-per-task optional, materials-needed drawer (GET /api/v1/materials?task_id=)."),
    ("roofer", "Roofer", "trades",
     "Shingles, flashing, underlayment.",
     "Build a simple list of roof tasks with weather-sensitive flagging and a material order count for shingles."),
    ("hvac_tech", "HVAC Tech", "trades",
     "Ducting, furnace, AC.",
     "Build a zoned-home map view: show HVAC-related tasks grouped by room (extract from description)."),
    ("drywall_finisher", "Drywall Finisher", "trades",
     "Hang, tape, mud, sand.",
     "Build a phase-tracker: each Drywall task has 4 sub-phases (hang, tape, mud, sand); display as a 4-dot status per task."),
    ("tile_setter", "Tile Setter", "trades",
     "Floor and wall tile.",
     "Build a tile-order tracker filtered to Fixtures tag, show material counts per task."),
    ("cabinet_installer", "Cabinet Installer", "trades",
     "Cabinet boxes and hardware.",
     "Build a cabinet install schedule with lead-time countdown per cabinet order."),
    ("flooring_installer", "Flooring Installer", "trades",
     "Hardwood, tile, carpet install.",
     "Build a room-by-room flooring checklist. Room = description. Toggle done state."),
    ("painter", "Painter", "trades",
     "Interior and exterior paint.",
     "Build a paint-room checklist: color per room, coats applied, dry time remaining."),
    ("window_installer", "Window Installer", "trades",
     "Window install and seal.",
     "Build a window-inventory view: count of windows per task, installed vs pending."),
    ("door_installer", "Door Installer", "trades",
     "Interior and exterior doors.",
     "Build a door punchlist with lockset-ordered status per door."),

    # -------- OUTDOOR --------
    ("landscaper", "Landscaper", "outdoor",
     "Grading, planting, beds.",
     "Build a seasonal plant list with install windows, tasks filtered to anything Labor-tagged outdoors."),
    ("lawncare", "Lawncare / Groundskeeper", "outdoor",
     "Mow, trim, fertilize schedule.",
     "Build a weekly-recurring task view that lists mow / trim / edge; show last-done times from created_at."),
    ("tree_trimmer", "Tree Trimmer / Arborist", "outdoor",
     "Trimming, removal, health.",
     "Build a tree inventory: list trees with risk level, next-trim date, species."),
    ("irrigation", "Irrigation Specialist", "outdoor",
     "Sprinklers and drip.",
     "Build a zone-by-zone irrigation map with runtime per zone, flag zones with issues."),
    ("fence_builder", "Fence Builder", "outdoor",
     "Perimeter and gates.",
     "Build a linear-feet tracker: total fence length, posts installed, panels hung."),
    ("deck_builder", "Deck Builder", "outdoor",
     "Deck framing and decking.",
     "Build a deck-sections view with materials count and post-hole depth log."),
    ("solar_installer", "Solar Installer", "outdoor",
     "Panels and inverters.",
     "Build a panel-count + kW-capacity view with install-phase progress."),

    # -------- INSPECTION --------
    ("building_inspector", "Building Inspector", "inspection",
     "Code compliance and sign-offs.",
     "Build an inspection queue: all Inspection-tagged tasks, with pass/fail buttons that PATCH column_name."),
    ("code_enforcement", "Code Enforcement", "inspection",
     "Violations and re-inspects.",
     "Build a violation log with photo links (use description) and resolution status."),
    ("surveyor", "Surveyor", "inspection",
     "Boundaries and site plans.",
     "Build a survey-deliverables list: plat, topo, stake-out, with deliverable dates."),
    ("structural_engineer", "Structural Engineer", "inspection",
     "Load paths and stamps.",
     "Build a stamp-tracker: drawings requiring engineer sign-off, with status."),
    ("permit_runner", "Permit Runner", "inspection",
     "Filing and pickup.",
     "Build a permit checklist: list Permits-tagged tasks, status + city-submission date."),

    # -------- INTERIOR --------
    ("interior_decorator", "Interior Decorator", "interior",
     "Style and palette.",
     "Build a moodboard-style grid: task description as card title, tag as category color."),
    ("home_stager", "Home Stager", "interior",
     "Furnishing for showings.",
     "Build a room-by-room staging checklist with 'staged / not staged' toggle per room."),
    ("lighting_designer", "Lighting Designer", "interior",
     "Light layout and ambiance.",
     "Build a lighting-plan overview: count of fixtures per room, scene presets."),
    ("hardware_specialist", "Hardware Specialist", "interior",
     "Knobs, pulls, hinges.",
     "Build a hardware schedule: fixture count per task, finish, status."),
    ("window_treatment", "Window-Treatment Installer", "interior",
     "Blinds, curtains, shades.",
     "Build a window-treatment inventory: opening dimensions, treatment type, install status."),

    # -------- SERVICE --------
    ("handyman", "Handyman", "service",
     "Small fixes everywhere.",
     "Build a 'small tasks' list: anything not tagged, rolled up into one simple punchlist."),
    ("cleaner", "Cleaner", "service",
     "Construction and final cleans.",
     "Build a room-by-room cleaning checklist with last-cleaned timestamps."),
    ("mover", "Mover", "service",
     "Move-in coordination.",
     "Build a move-in load plan: rooms, estimated boxes, delivery date."),
    ("appliance_installer", "Appliance Installer", "service",
     "Major appliance hookups.",
     "Build an appliance-install tracker: fridge, range, dishwasher, etc., with hookup type."),
    ("security_installer", "Security System Installer", "service",
     "Alarms and cameras.",
     "Build a sensor/camera layout view grouped by area."),
    ("locksmith", "Locksmith", "service",
     "Re-key and smart locks.",
     "Build a door-hardware re-key sheet: door, old keying, new keying, done flag."),
    ("pest_control", "Pest Control", "service",
     "Termite and prevention.",
     "Build a treatment schedule: zones, chemicals, last-treated, next-due."),
    ("chimney_sweep", "Chimney Sweep", "service",
     "Sweep and inspection.",
     "Build a fireplace/chimney inspection sheet."),
    ("organizer", "Home Organizer", "service",
     "Closets and storage.",
     "Build a room-by-room organization plan with container counts."),
    ("insulation_installer", "Insulation Installer", "service",
     "Batts, blown, spray.",
     "Build an R-value tracker per room with square footage and type."),
]


def seed_roles(db_module):
    """Idempotently upsert all roles into artifactory_role_templates."""
    for position, (slug, display_name, category, description, example_prompt) in enumerate(ROLES):
        db_module.upsert_role_template(
            slug=slug,
            display_name=display_name,
            category=category,
            description=description,
            example_prompt=example_prompt,
            position=position,
        )
    return len(ROLES)


CATEGORY_ORDER = ['management', 'trades', 'outdoor', 'inspection', 'interior', 'service']
CATEGORY_LABEL = {
    'management':  '📋 Management',
    'trades':      '🔨 Trades',
    'outdoor':     '🌳 Outdoor',
    'inspection':  '📐 Inspection',
    'interior':    '🎨 Interior',
    'service':     '🧰 Service',
}
