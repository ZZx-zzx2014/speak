"""HTTP level tests: authentication, authorisation, CSRF and hardening."""

import os
import sqlite3
import tempfile
import unittest

from werkzeug.security import generate_password_hash

from speak import create_app
from speak.db import get_db

from .base import TURNSTILE_OFF, AppTestCase, extract_csrf


class PublicPagesTest(AppTestCase):
    def test_index_renders(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('欢迎来到 Speak 聊天室', response.get_data(as_text=True))

    def test_unknown_page_uses_custom_error_page(self):
        response = self.client.get('/does-not-exist')
        self.assertEqual(response.status_code, 404)
        self.assertIn('页面不存在', response.get_data(as_text=True))

    def test_security_headers_are_present(self):
        response = self.client.get('/')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
        self.assertIn("default-src 'self'", response.headers['Content-Security-Policy'])

    def test_html_is_not_cached_but_static_assets_are(self):
        """Stale HTML would point the browser at a mismatched Socket.IO client."""
        page = self.client.get('/')
        self.assertEqual(page.headers.get('Cache-Control'), 'no-store')

        asset = self.client.get('/static/style.css')
        self.assertNotEqual(asset.headers.get('Cache-Control'), 'no-store')

    def test_bundled_socketio_client_is_served(self):
        """The vendored client must be reachable so a blocked CDN cannot break chat."""
        response = self.client.get('/static/vendor/socket.io.min.js')
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.get_data()), 10000)

    def test_chat_redirects_anonymous_users(self):
        response = self.client.get('/chat')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])

    def test_manage_redirects_anonymous_users(self):
        response = self.client.get('/manage')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])


class RegistrationTest(AppTestCase):
    def test_register_then_login_then_chat(self):
        response = self.register()
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])

        response = self.login()
        self.assertEqual(response.status_code, 302)
        self.assertIn('/chat', response.headers['Location'])

        response = self.client.get('/chat')
        self.assertEqual(response.status_code, 200)
        self.assertIn('alice', response.get_data(as_text=True))

    def test_weak_password_is_rejected(self):
        response = self.register(password='short')
        self.assertEqual(response.status_code, 400)
        self.assertIn('至少为 8 个字符', response.get_data(as_text=True))

    def test_mismatched_confirmation_is_rejected(self):
        response = self.register(password='password123', confirmation='password124')
        self.assertEqual(response.status_code, 400)
        self.assertIn('两次输入的密码不一致', response.get_data(as_text=True))

    def test_invalid_username_is_rejected(self):
        response = self.register(username='a b')
        self.assertEqual(response.status_code, 400)
        self.assertIn('用户名', response.get_data(as_text=True))

    def test_duplicate_username_is_rejected(self):
        self.register()
        response = self.register()
        self.assertEqual(response.status_code, 409)
        self.assertIn('用户名已存在', response.get_data(as_text=True))

    def test_registration_without_csrf_token_is_blocked(self):
        response = self.client.post('/register', data={
            'username': 'bob', 'password': 'password123', 'password2': 'password123',
        })
        self.assertEqual(response.status_code, 400)

    def test_stored_password_is_hashed(self):
        self.register()
        with self.app.app_context():
            row = get_db().execute(
                'SELECT password FROM users WHERE username = ?', ('alice',)
            ).fetchone()
        self.assertNotIn('password123', row['password'])
        self.assertTrue(row['password'].startswith('pbkdf2:sha256'))


class SessionHardeningTest(AppTestCase):
    def test_session_cookie_is_httponly_and_samesite(self):
        # /login renders the CSRF field, which is what first writes the session.
        response = self.client.get('/login')
        cookie = response.headers.get('Set-Cookie', '')
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Lax', cookie)

    def test_oversized_request_body_is_rejected(self):
        response = self.client.post('/login', data={
            'username': 'a' * (70 * 1024), 'password': 'x',
        })
        self.assertEqual(response.status_code, 413)


class LoginTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.register()

    def test_wrong_password_is_rejected(self):
        response = self.login(password='wrong-password')
        self.assertEqual(response.status_code, 401)

    def test_unknown_user_is_rejected(self):
        response = self.login(username='nobody')
        self.assertEqual(response.status_code, 401)

    def test_login_without_csrf_token_is_blocked(self):
        response = self.client.post('/login', data={
            'username': 'alice', 'password': 'password123',
        })
        self.assertEqual(response.status_code, 400)

    def test_open_redirect_is_ignored(self):
        response = self.login(query='?next=//evil.example.com')
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('evil.example.com', response.headers['Location'])
        self.assertIn('/chat', response.headers['Location'])

    def test_local_next_target_is_honoured(self):
        response = self.login(query='?next=/manage')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/manage', response.headers['Location'])

    def test_logout_clears_the_session(self):
        self.login()
        self.assertEqual(self.client.get('/chat').status_code, 200)

        response = self.post('/logout')
        self.assertEqual(response.status_code, 302)

        response = self.client.get('/chat')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])

    def test_logout_requires_post(self):
        self.assertEqual(self.client.get('/logout').status_code, 405)


class RateLimitTest(unittest.TestCase):
    """The limiter is per application instance, so this needs its own app."""

    def test_repeated_failures_are_throttled(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                SECRET_KEY='test-secret-key',
                TESTING=True,
                DATABASE=os.path.join(tmp, 'rate.db'),
                ADMIN_PASSWORD='admin-secret-123',
                LOGIN_MAX_ATTEMPTS=3,
                LOGIN_WINDOW_SECONDS=60,
                **TURNSTILE_OFF
            )
            client = app.test_client()
            statuses = []
            for _ in range(4):
                statuses.append(client.post('/login', data={
                    'csrf_token': extract_csrf(client),
                    'username': 'nobody',
                    'password': 'nope',
                }).status_code)

            self.assertEqual(statuses[:3], [401, 401, 401])
            self.assertEqual(statuses[3], 429)


class AdminTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.register(username='alice')
        self.login_admin()

    def _user_id(self, username):
        with self.app.app_context():
            row = get_db().execute(
                'SELECT id FROM users WHERE username = ?', (username,)
            ).fetchone()
        return row['id']

    def test_manage_lists_regular_users_only(self):
        response = self.client.get('/manage')
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('<td>alice</td>', body)
        self.assertNotIn('<td>root</td>', body)

    def test_admin_can_delete_a_regular_user(self):
        response = self.post('/manage/users/%d/delete' % self._user_id('alice'))
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            remaining = get_db().execute(
                'SELECT COUNT(*) AS n FROM users WHERE username = ?', ('alice',)
            ).fetchone()['n']
        self.assertEqual(remaining, 0)

    def test_admin_account_cannot_be_deleted(self):
        admin_id = self._user_id(self.ADMIN_USERNAME)
        response = self.post('/manage/users/%d/delete' % admin_id, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('不能通过此页面删除管理员账户', response.get_data(as_text=True))
        with self.app.app_context():
            remaining = get_db().execute(
                'SELECT COUNT(*) AS n FROM users WHERE id = ?', (admin_id,)
            ).fetchone()['n']
        self.assertEqual(remaining, 1)

    def test_deleting_a_missing_user_is_handled(self):
        response = self.post('/manage/users/999999/delete', follow_redirects=True)
        self.assertIn('该用户不存在', response.get_data(as_text=True))

    def test_regular_user_cannot_open_manage(self):
        self.post('/logout')
        self.login()
        response = self.client.get('/manage')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/chat', response.headers['Location'])

    def test_delete_requires_post(self):
        response = self.client.get('/manage/users/%d/delete' % self._user_id('alice'))
        self.assertEqual(response.status_code, 405)

    def test_delete_requires_csrf_token(self):
        response = self.client.post(
            '/manage/users/%d/delete' % self._user_id('alice')
        )
        self.assertEqual(response.status_code, 400)


class LegacyDatabaseTest(unittest.TestCase):
    """A database created by the original version must keep working."""

    OLD_SCHEMA = (
        "CREATE TABLE users ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  username TEXT UNIQUE NOT NULL,"
        "  password TEXT NOT NULL,"
        "  is_admin INTEGER NOT NULL DEFAULT 0"
        ")"
    )

    def test_existing_database_is_migrated_and_still_usable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'legacy.db')
            connection = sqlite3.connect(path)
            connection.executescript(self.OLD_SCHEMA)
            connection.execute(
                'INSERT INTO users (username, password, is_admin) VALUES (?, ?, 1)',
                ('root', generate_password_hash('legacy-pw', method='pbkdf2:sha256')),
            )
            connection.commit()
            connection.close()

            app = create_app(SECRET_KEY='test-secret-key', TESTING=True,
                             DATABASE=path, **TURNSTILE_OFF)
            client = app.test_client()

            # The pre-existing administrator can still log in ...
            response = client.post('/login', data={
                'csrf_token': extract_csrf(client),
                'username': 'root',
                'password': 'legacy-pw',
            })
            self.assertEqual(response.status_code, 302)

            # ... and the user list (which reads the new column) renders.
            self.assertEqual(client.get('/manage').status_code, 200)

            with app.app_context():
                columns = {
                    row['name'] for row in get_db().execute('PRAGMA table_info(users)')
                }
            self.assertIn('created_at', columns)


if __name__ == '__main__':
    unittest.main()
