"""
Full integration test. Uses the Flask test client against a clean SQLite
file in /tmp. Per the flask-kumori-stack skill, `python -m tests.full_test`
must pass before every deploy.

Covers:
  - Boot: init_schema + seed produce 45 roles, 4 demo users, 16 tasks
  - GET /healthz
  - REST: /api/v1/users, /api/v1/tasks, /api/v1/comments, /api/v1/materials
  - POST/PATCH/DELETE on /api/v1/tasks
  - /pick-role sets session cookie, lands at /schema, creates a user row
  - /schema with session cookie contains role-specific text
  - /submit persists JSX and /u/<id> renders it (Babel scripts present)
  - Rate limiter blocks at the configured threshold
  - 100KB source_jsx cap rejects oversize
"""
import json
import os
import sys
import tempfile
import unittest


# Force SQLite backend for tests — use a throwaway file so the dev db is safe.
os.environ.pop('GAE_ENV', None)
os.environ.pop('POSTGRES_DSN', None)
_tmp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
_tmp_db.close()
os.environ['SQLITE_PATH_OVERRIDE'] = _tmp_db.name

# Patch config BEFORE importing main, so init_schema uses our tmp path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config
Config.SQLITE_PATH = _tmp_db.name
Config.DEBUG = True

from main import app  # noqa: E402
from utilities import db, limit  # noqa: E402


class BootTests(unittest.TestCase):
    def test_roles_seeded(self):
        roles = db.list_role_templates()
        self.assertGreaterEqual(len(roles), 40, "expected ~45 roles")
        slugs = {r['slug'] for r in roles}
        for must in ('owner', 'plumber_general', 'electrician_lighting', 'tree_trimmer'):
            self.assertIn(must, slugs)

    def test_demo_users_seeded(self):
        users = db.list_users()
        names = [u['name'] for u in users]
        self.assertIn('Andy', names)
        self.assertIn('Paul Plumber', names)

    def test_tasks_seeded(self):
        tasks = db.list_tasks()
        self.assertEqual(len(tasks), 16)


class HealthAndApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_healthz(self):
        self.assertEqual(self.client.get('/healthz').data, b'ok')

    def test_users_endpoint(self):
        r = self.client.get('/api/v1/users')
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(len(r.get_json()), 4)

    def test_tasks_endpoint(self):
        r = self.client.get('/api/v1/tasks')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.get_json()), 16)
        r2 = self.client.get('/api/v1/tasks?column=done')
        self.assertTrue(all(t['column_name'] == 'done' for t in r2.get_json()))

    def test_comments_endpoint(self):
        r = self.client.get('/api/v1/comments')
        self.assertEqual(r.status_code, 200)
        comments = r.get_json()
        self.assertGreaterEqual(len(comments), 4)
        # joined user info should be present
        self.assertIn('user_name', comments[0])

    def test_task_crud(self):
        r = self.client.post('/api/v1/tasks',
                             json={'title': 'test task', 'column_name': 'todo', 'tag': 'Labor'})
        self.assertEqual(r.status_code, 201)
        new_id = r.get_json()['id']
        r2 = self.client.patch(f'/api/v1/tasks/{new_id}', json={'column_name': 'done'})
        self.assertEqual(r2.get_json()['column_name'], 'done')
        self.assertEqual(self.client.delete(f'/api/v1/tasks/{new_id}').status_code, 204)
        self.assertEqual(self.client.get(f'/api/v1/tasks/{new_id}').status_code, 404)

    def test_openapi_served(self):
        r = self.client.get('/openapi.json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['openapi'], '3.0.3')


class PickRoleAndSubmitTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        limit._store.clear()  # fresh rate-limit counters per test

    def test_pick_role_creates_user_and_sets_cookie(self):
        r = self.client.post('/pick-role',
                             data={'role_slug': 'tree_trimmer', 'display_name': 'Test Arb'})
        self.assertIn(r.status_code, (302, 301))
        self.assertIn('/schema', r.headers['Location'])
        # Cookie should be set
        cookies = [c for c in self.client.cookie_jar] if hasattr(self.client, 'cookie_jar') else None
        # Flask test client uses session store differently depending on version; verify via /api/v1/users/me
        me = self.client.get('/api/v1/users/me').get_json()
        self.assertEqual(me['name'], 'Test Arb')
        self.assertEqual(me['role'], 'tree')

    def test_schema_is_role_aware(self):
        self.client.post('/pick-role', data={'role_slug': 'plumber_general'})
        html = self.client.get('/schema').get_data(as_text=True)
        # Role name or example_prompt should appear in the preamble
        self.assertIn('Plumber', html)

    def test_submit_and_render(self):
        self.client.post('/pick-role', data={'role_slug': 'carpenter', 'display_name': 'Test Carp'})
        me = self.client.get('/api/v1/users/me').get_json()
        jsx = """function App() {
          return <div className="p-6"><h1>Carpenter view</h1></div>;
        }"""
        r = self.client.post('/submit',
                             data={'source_jsx': jsx, 'method': 'paste', 'user_id': me['id']})
        self.assertIn(r.status_code, (302, 301))
        self.assertIn(f"/u/{me['id']}", r.headers['Location'])
        # Rendered page should embed the JSX and the Babel runtime
        page = self.client.get(f"/u/{me['id']}").get_data(as_text=True)
        self.assertIn('Carpenter view', page)
        self.assertIn('@babel/standalone', page)
        self.assertIn('window.CURRENT_USER', page)

    def test_source_cap_rejects_oversize(self):
        self.client.post('/pick-role', data={'role_slug': 'handyman'})
        me = self.client.get('/api/v1/users/me').get_json()
        big = 'A' * (101 * 1024)  # 101KB > 100KB cap
        r = self.client.post('/submit',
                             data={'source_jsx': big, 'method': 'paste', 'user_id': me['id']})
        # Error path re-renders the form (200) with an error message
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'too large', r.get_data().lower())


class RateLimitTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        limit._store.clear()

    def test_pick_role_rate_limit(self):
        # pick_role allows 10/min/IP; 11th should 429
        for i in range(10):
            r = self.client.post('/pick-role', data={'role_slug': 'handyman', 'display_name': f'u{i}'})
            self.assertIn(r.status_code, (301, 302), f"request {i} failed")
        r = self.client.post('/pick-role', data={'role_slug': 'handyman', 'display_name': 'over'})
        self.assertEqual(r.status_code, 429)


if __name__ == '__main__':
    # Run with verbose and a non-zero exit on failure (for pre-deploy gating)
    runner = unittest.TextTestRunner(verbosity=2)
    loader = unittest.TestLoader()
    suite = unittest.TestSuite([
        loader.loadTestsFromTestCase(BootTests),
        loader.loadTestsFromTestCase(HealthAndApiTests),
        loader.loadTestsFromTestCase(PickRoleAndSubmitTests),
        loader.loadTestsFromTestCase(RateLimitTests),
    ])
    result = runner.run(suite)
    # Cleanup the temp db
    try:
        os.unlink(_tmp_db.name)
    except Exception:
        pass
    sys.exit(0 if result.wasSuccessful() else 1)
