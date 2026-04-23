"""Artifactory config."""
import os


class Config:
    APP_NAME = "Artifactory"
    VERSION = "0.1.0"
    PORT = int(os.environ.get('PORT', 8080))

    # GCP settings
    GCP_PROJECT_ID = 'artifactory-io'

    # Database — local SQLite for now. When we flip to Cloud SQL, set
    # POSTGRES_DSN env var and the code in utilities/db.py picks it up.
    SQLITE_PATH = os.path.join(os.path.dirname(__file__), 'data', 'artifactory.db')

    # Portal-level
    DEBUG = os.environ.get('FLASK_ENV') == 'development'
    AUTO_OPEN_BROWSER = os.environ.get('AUTO_OPEN_BROWSER', '0') == '1'
    BROWSER_DELAY = 1.2

    # Demo auth: user id comes from ?user=<N> query param (no real auth in v1).
    # Real Auth0 wiring gets added once the demo is convincing.
    DEMO_MODE = True
