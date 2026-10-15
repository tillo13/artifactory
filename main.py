"""
Artifactory — shared-backend + pluggable AI-designed frontends portal (v0.2).

Public demo:
  1. Visitor lands → picks a role from the 45-role catalog
  2. Gets a session-backed user + personalized Claude preamble
  3. Designs their view in Claude → pastes JSX at /submit
  4. /u/<their-id> goes live against the shared fake house-build data
"""
import logging
import os

from flask import (Flask, abort, jsonify, make_response, redirect,
                   render_template, request, url_for)

from config import Config
from utilities import db
from utilities.limit import MAX_USERS, WARN_USERS, check as rate_check
from utilities.limit import snapshot as rate_snapshot
from utilities.roles import CATEGORY_LABEL, CATEGORY_ORDER
from utilities.schema_doc import OPENAPI, build_preamble
from utilities.seed import seed as run_seed


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s | %(message)s')
logger = logging.getLogger('artifactory')

SESSION_COOKIE_NAME = 'artifactory_session'
SOURCE_JSX_MAX_BYTES = 100 * 1024  # 100 KB


def create_app():
    app = Flask(__name__)
    from utilities.csrf_guard import install as install_csrf_guard
    install_csrf_guard(app)  # refuse cross-site POSTs; session cookie SameSite=Lax (audit 2026-10-14)
    app.config['SECRET_KEY'] = os.environ.get('ARTIFACTORY_SECRET_KEY', 'dev-secret-key-change-me')
    app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB total request, artifacts capped tighter

    db.init_schema()
    try:
        seed_result = run_seed()
        logger.info(f"Boot seed: {seed_result}")
    except Exception as e:
        # Don't block boot on seed failures — useful during schema iteration.
        logger.exception(f"Seed skipped: {e}")

    # ------------------------------------------------------------------
    # Current user — cookie session first, then ?user=N demo fallback.
    # ------------------------------------------------------------------
    def current_user():
        token = request.cookies.get(SESSION_COOKIE_NAME)
        if token:
            u = db.get_user_by_session(token)
            if u:
                return u
        try:
            uid = int(request.args.get('user', 1))
        except (TypeError, ValueError):
            uid = 1
        return db.get_user(uid) or db.get_user(1)

    def client_ip():
        # App Engine sets X-Forwarded-For; strip trailing hops.
        fwd = request.headers.get('X-Forwarded-For', '')
        if fwd:
            return fwd.split(',')[0].strip()
        return request.remote_addr or 'unknown'

    def ratelimited_response(bucket):
        ok, msg = rate_check(client_ip(), bucket)
        if not ok:
            return jsonify({'error': msg}), 429
        return None

    # ==================================================================
    # PORTAL PAGES
    # ==================================================================
    @app.route('/')
    def index():
        roles = db.list_role_templates()
        # Bucket roles by category, preserving order.
        roles_by_category = []
        for cat in CATEGORY_ORDER:
            items = [r for r in roles if r['category'] == cat]
            if items:
                roles_by_category.append({
                    'key': cat,
                    'label': CATEGORY_LABEL[cat],
                    'roles': items,
                })
        return render_template('landing.html',
                               roles_by_category=roles_by_category,
                               current_user=current_user(),
                               demo_users=db.list_users(limit=4),
                               user_count=db.count_users(),
                               soft_cap=WARN_USERS,
                               hard_cap=MAX_USERS)

    @app.route('/about')
    def about_page():
        return render_template('about.html', current_user=current_user())

    @app.route('/schema')
    def schema_page():
        user = current_user()
        role_template = None
        if user and user.get('role_template_id'):
            role_template = db.get_role_template(user['role_template_id'])
        preamble = build_preamble(request.host_url.rstrip('/'), role_template)
        return render_template('schema.html',
                               preamble=preamble,
                               role_template=role_template,
                               current_user=user)

    @app.route('/openapi.json')
    def openapi():
        spec = dict(OPENAPI)
        spec['servers'] = [{"url": request.host_url.rstrip('/')}]
        return jsonify(spec)

    # ==================================================================
    # ROLE PICK — visitor onboarding
    # ==================================================================
    @app.route('/pick-role', methods=['POST'])
    def pick_role():
        rl = ratelimited_response('pick_role')
        if rl:
            return rl

        if db.count_users() >= MAX_USERS:
            return render_template('capped.html'), 503

        slug = (request.form.get('role_slug') or '').strip()
        display_name_override = (request.form.get('display_name') or '').strip()
        template = db.get_role_template_by_slug(slug) if slug else None
        if not template:
            return redirect(url_for('index'))

        visitor_name = display_name_override or template['display_name']
        role_key = template['slug'].split('_')[0]  # loose role tag for tasks.assigned_role matching

        uid, token = db.create_user(
            name=visitor_name,
            role=role_key,
            role_template_id=template['id'],
        )
        resp = make_response(redirect(url_for('schema_page')))
        resp.set_cookie(SESSION_COOKIE_NAME, token,
                        max_age=60 * 60 * 24 * 30,
                        httponly=True,
                        samesite='Lax',
                        secure=not Config.DEBUG)
        logger.info(f"Picked role '{slug}' → user {uid}")
        return resp

    # ==================================================================
    # SUBMIT
    # ==================================================================
    @app.route('/submit', methods=['GET', 'POST'])
    def submit():
        user = current_user()
        if request.method == 'POST':
            rl = ratelimited_response('submit')
            if rl:
                return rl

            source = (request.form.get('source_jsx') or '').strip()
            method = request.form.get('method', 'paste')
            target_user_id = int(request.form.get('user_id') or user['id'])

            if not source:
                return render_template('submit.html',
                                       users=db.list_users(),
                                       current_user=user,
                                       error="Source can't be empty.",
                                       max_bytes=SOURCE_JSX_MAX_BYTES)
            if len(source.encode('utf-8')) > SOURCE_JSX_MAX_BYTES:
                return render_template('submit.html',
                                       users=db.list_users(),
                                       current_user=user,
                                       error=f"Source too large (max {SOURCE_JSX_MAX_BYTES // 1024}KB).",
                                       max_bytes=SOURCE_JSX_MAX_BYTES)

            db.save_user_artifact(
                user_id=target_user_id,
                source_jsx=source,
                method=method,
                submission_meta={'ip': client_ip(), 'user_agent': request.headers.get('User-Agent', '')[:200]},
            )
            return redirect(url_for('user_app', user_id=target_user_id))

        return render_template('submit.html',
                               users=db.list_users(),
                               current_user=user,
                               error=None,
                               max_bytes=SOURCE_JSX_MAX_BYTES)

    # ==================================================================
    # /u/<id> — the rendered view
    # ==================================================================
    @app.route('/u/<int:user_id>')
    def user_app(user_id):
        user = db.get_user(user_id)
        if not user:
            abort(404)
        artifact = db.get_latest_user_artifact(user_id)
        # Top-bar role-switcher shows only the 4 demo users, not all visitors
        return render_template('user_shell.html',
                               user=user,
                               artifact=artifact,
                               all_users=db.list_users(limit=4))

    # ==================================================================
    # REST API — the contract
    # ==================================================================
    @app.route('/api/v1/users/me')
    def api_me():
        return jsonify(current_user())

    @app.route('/api/v1/users')
    def api_users():
        return jsonify(db.list_users())

    @app.route('/api/v1/tasks', methods=['GET', 'POST'])
    def api_tasks():
        if request.method == 'POST':
            rl = ratelimited_response('api_write')
            if rl:
                return rl
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
        return jsonify(db.list_tasks(
            column=request.args.get('column'),
            assigned_role=request.args.get('assigned_role'),
        ))

    @app.route('/api/v1/tasks/<int:task_id>', methods=['GET', 'PATCH', 'DELETE'])
    def api_task(task_id):
        if request.method == 'DELETE':
            rl = ratelimited_response('api_write')
            if rl:
                return rl
            db.delete_task(task_id)
            return '', 204
        if request.method == 'PATCH':
            rl = ratelimited_response('api_write')
            if rl:
                return rl
            db.update_task(task_id, **(request.json or {}))
            return jsonify(db.get_task(task_id))
        t = db.get_task(task_id)
        if not t:
            abort(404)
        return jsonify(t)

    @app.route('/api/v1/comments', methods=['GET', 'POST'])
    def api_comments():
        if request.method == 'POST':
            rl = ratelimited_response('api_write')
            if rl:
                return rl
            data = request.json or {}
            user = current_user()
            cid = db.create_comment(
                task_id=int(data['task_id']),
                user_id=user['id'],
                body=data.get('body', ''),
            )
            comments = db.list_comments(task_id=int(data['task_id']))
            return jsonify(next((c for c in comments if c['id'] == cid), None)), 201
        task_id = request.args.get('task_id', type=int)
        return jsonify(db.list_comments(task_id=task_id))

    @app.route('/api/v1/materials', methods=['GET', 'POST'])
    def api_materials():
        if request.method == 'POST':
            rl = ratelimited_response('api_write')
            if rl:
                return rl
            data = request.json or {}
            mid = db.create_material(
                task_id=int(data['task_id']),
                name=data.get('name', ''),
                quantity=float(data.get('quantity', 1)),
                unit=data.get('unit'),
                cost_usd=float(data['cost_usd']) if data.get('cost_usd') is not None else None,
                ordered=bool(data.get('ordered', False)),
                supplier=data.get('supplier'),
            )
            mats = db.list_materials(task_id=int(data['task_id']))
            return jsonify(next((m for m in mats if m['id'] == mid), None)), 201
        return jsonify(db.list_materials(task_id=request.args.get('task_id', type=int)))

    @app.route('/api/v1/materials/<int:material_id>', methods=['PATCH'])
    def api_material(material_id):
        rl = ratelimited_response('api_write')
        if rl:
            return rl
        db.update_material(material_id, **(request.json or {}))
        # Retrieve — no get-by-id in db, hand-query
        with db.cursor() as conn:
            cur = conn.cursor()
            cur.execute(db._ph("SELECT * FROM artifactory_materials WHERE id = ?"), (material_id,))
            row = cur.fetchone()
        if not row:
            return jsonify({}), 404
        return jsonify(dict(row) if not isinstance(row, dict) else row)

    # ==================================================================
    # DEV / HEALTH
    # ==================================================================
    @app.route('/healthz')
    def healthz():
        return 'ok'

    @app.route('/_rate-limits')
    def _rate_limits():
        if not Config.DEBUG:
            abort(403)
        return jsonify(rate_snapshot())

    return app


app = create_app()


if __name__ == '__main__':
    logger.info(f"Starting {Config.APP_NAME} v{Config.VERSION} on :{Config.PORT} (backend={db.backend()})")
    app.run(host='0.0.0.0', port=Config.PORT, debug=True)
