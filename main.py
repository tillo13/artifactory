"""
Artifactory — shared-backend + pluggable AI-designed frontends portal.

v1 scope:
- House-build schema + REST API (/api/v1/*)
- Landing page with three submission paths (paste / URL+cookie / extension)
- /u/<id> renders the user's submitted JSX in a Babel-Standalone shell
- /schema shows the copy-paste preamble for Claude
- /openapi.json — machine-readable spec

No real auth yet. ?user=<N> sets the current user. Good enough for demo.
"""
import json
import logging
import os

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, url_for

from config import Config
from utilities import db
from utilities.schema_doc import OPENAPI, build_preamble
from utilities.seed import seed as run_seed


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s | %(message)s')
logger = logging.getLogger('artifactory')


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('ARTIFACTORY_SECRET_KEY', 'dev-secret-key-change-me')

    # Init DB on boot so a fresh clone "just works"
    db.init_schema()
    seed_result = run_seed()
    logger.info(f"DB ready: {seed_result}")

    # ------------------------------------------------------------------
    # Current-user resolver. Demo auth: ?user=<N> in the URL, or default 1.
    # ------------------------------------------------------------------
    def current_user():
        try:
            uid = int(request.args.get('user', 1))
        except (TypeError, ValueError):
            uid = 1
        u = db.get_user(uid) or db.get_user(1)
        return u

    # ------------------------------------------------------------------
    # Landing / portal pages
    # ------------------------------------------------------------------
    @app.route('/')
    def index():
        users = db.list_users()
        return render_template('landing.html',
                               users=users,
                               current_user=current_user(),
                               preamble=build_preamble(request.host_url.rstrip('/')),
                               app_name=Config.APP_NAME,
                               version=Config.VERSION)

    @app.route('/schema')
    def schema_page():
        return render_template('schema.html',
                               preamble=build_preamble(request.host_url.rstrip('/')),
                               users=db.list_users(),
                               current_user=current_user())

    @app.route('/openapi.json')
    def openapi():
        spec = dict(OPENAPI)
        spec['servers'] = [{"url": request.host_url.rstrip('/')}]
        return jsonify(spec)

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------
    @app.route('/submit', methods=['GET', 'POST'])
    def submit():
        user = current_user()
        if request.method == 'POST':
            source = (request.form.get('source_jsx') or '').strip()
            method = request.form.get('method', 'paste')
            target_user_id = int(request.form.get('user_id') or user['id'])
            if not source:
                return render_template('submit.html',
                                       users=db.list_users(),
                                       current_user=user,
                                       error="Source can't be empty.")
            db.save_user_artifact(user_id=target_user_id, source_jsx=source, method=method)
            return redirect(url_for('user_app', user_id=target_user_id))
        return render_template('submit.html',
                               users=db.list_users(),
                               current_user=user,
                               error=None)

    # ------------------------------------------------------------------
    # User's rendered app — the whole point of this project
    # ------------------------------------------------------------------
    @app.route('/u/<int:user_id>')
    def user_app(user_id):
        user = db.get_user(user_id)
        if not user:
            abort(404)
        artifact = db.get_latest_user_artifact(user_id)
        return render_template('user_shell.html',
                               user=user,
                               artifact=artifact,
                               all_users=db.list_users())

    # ------------------------------------------------------------------
    # REST API — /api/v1/*
    # This is the contract every submitted frontend rides on.
    # ------------------------------------------------------------------
    @app.route('/api/v1/users/me')
    def api_me():
        return jsonify(current_user())

    @app.route('/api/v1/users')
    def api_users():
        return jsonify(db.list_users())

    @app.route('/api/v1/tasks', methods=['GET', 'POST'])
    def api_tasks():
        if request.method == 'POST':
            data = request.json or {}
            tid = db.create_task(
                title=data.get('title', 'Untitled'),
                description=data.get('description'),
                column_name=data.get('column_name', 'todo'),
                tag=data.get('tag'),
                assigned_role=data.get('assigned_role'),
                due_date=data.get('due_date'),
            )
            return jsonify(db.get_task(tid)), 201
        column = request.args.get('column')
        assigned_role = request.args.get('assigned_role')
        return jsonify(db.list_tasks(column=column, assigned_role=assigned_role))

    @app.route('/api/v1/tasks/<int:task_id>', methods=['GET', 'PATCH', 'DELETE'])
    def api_task(task_id):
        if request.method == 'DELETE':
            db.delete_task(task_id)
            return '', 204
        if request.method == 'PATCH':
            data = request.json or {}
            db.update_task(task_id, **data)
            return jsonify(db.get_task(task_id))
        t = db.get_task(task_id)
        if not t:
            abort(404)
        return jsonify(t)

    @app.route('/api/v1/comments', methods=['GET', 'POST'])
    def api_comments():
        if request.method == 'POST':
            data = request.json or {}
            user = current_user()
            cid = db.create_comment(
                task_id=int(data['task_id']),
                user_id=user['id'],
                body=data.get('body', ''),
            )
            # Return freshly-joined row
            comments = db.list_comments(task_id=int(data['task_id']))
            created = next((c for c in comments if c['id'] == cid), None)
            return jsonify(created), 201
        task_id = request.args.get('task_id', type=int)
        return jsonify(db.list_comments(task_id=task_id))

    @app.route('/api/v1/materials', methods=['GET', 'POST'])
    def api_materials():
        if request.method == 'POST':
            data = request.json or {}
            mid = db.create_material(
                task_id=int(data['task_id']),
                name=data.get('name', ''),
                quantity=float(data.get('quantity', 1)),
                unit=data.get('unit'),
                cost_usd=float(data['cost_usd']) if data.get('cost_usd') is not None else None,
                ordered=bool(data.get('ordered', False)),
            )
            mats = db.list_materials(task_id=int(data['task_id']))
            return jsonify(next((m for m in mats if m['id'] == mid), None)), 201
        task_id = request.args.get('task_id', type=int)
        return jsonify(db.list_materials(task_id=task_id))

    @app.route('/api/v1/materials/<int:material_id>', methods=['PATCH'])
    def api_material(material_id):
        data = request.json or {}
        db.update_material(material_id, **data)
        # No get-by-id helper; cheap fallback
        with db.cursor() as c:
            row = c.execute("SELECT * FROM artifactory_materials WHERE id = ?", (material_id,)).fetchone()
        return jsonify(dict(row) if row else {})

    # ------------------------------------------------------------------
    # Dev helpers
    # ------------------------------------------------------------------
    @app.route('/_reseed')
    def reseed():
        if not Config.DEBUG:
            abort(403)
        # wipe and reseed
        with db.cursor() as c:
            c.execute("DELETE FROM artifactory_comments")
            c.execute("DELETE FROM artifactory_materials")
            c.execute("DELETE FROM artifactory_tasks")
            c.execute("DELETE FROM artifactory_user_artifacts")
            c.execute("DELETE FROM artifactory_users")
        return jsonify(run_seed())

    @app.route('/healthz')
    def healthz():
        return 'ok'

    return app


app = create_app()


if __name__ == '__main__':
    logger.info(f"Starting {Config.APP_NAME} v{Config.VERSION} on :{Config.PORT}")
    app.run(host='0.0.0.0', port=Config.PORT, debug=True)
