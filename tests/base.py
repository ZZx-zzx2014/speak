"""Shared helpers for the test suite."""

import os
import re
import tempfile
import unittest

from speak import create_app

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
#: Anonymous sessions only expose a token on /login; logged-in sessions get one
#: from the logout form in the layout, so both are tried.
CSRF_PAGES = ('/login', '/')


def extract_csrf(client, pages=CSRF_PAGES):
    """Return the per-session CSRF token rendered into any page."""
    for path in pages:
        response = client.get(path)
        if response.status_code != 200:
            continue
        match = CSRF_RE.search(response.get_data(as_text=True))
        if match:
            return match.group(1)
    raise AssertionError('无法从 %s 中获取 CSRF 令牌' % (pages,))


class AppTestCase(unittest.TestCase):
    """Creates a fresh application backed by a throwaway database."""

    ADMIN_PASSWORD = 'admin-secret-123'
    ADMIN_USERNAME = 'root'

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.database = os.path.join(self._tmpdir.name, 'test.db')
        self.app = create_app(
            SECRET_KEY='test-secret-key',
            TESTING=True,
            DATABASE=self.database,
            ADMIN_PASSWORD=self.ADMIN_PASSWORD,
            ADMIN_USERNAME=self.ADMIN_USERNAME,
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self._tmpdir.cleanup()

    # -- helpers ---------------------------------------------------------
    def csrf_token(self, path=None):
        """CSRF token of the currently authenticated session."""
        return extract_csrf(self.client, (path,) if path else CSRF_PAGES)

    def register(self, username='alice', password='password123', confirmation=None):
        return self.client.post('/register', data={
            'csrf_token': self.csrf_token('/register'),
            'username': username,
            'password': password,
            'password2': password if confirmation is None else confirmation,
        })

    def login(self, username='alice', password='password123', query=''):
        return self.client.post('/login' + query, data={
            'csrf_token': self.csrf_token('/login'),
            'username': username,
            'password': password,
        })

    def login_admin(self):
        return self.login(self.ADMIN_USERNAME, self.ADMIN_PASSWORD)

    def post(self, path, follow_redirects=False, expect_token=True, **data):
        if expect_token:
            data.setdefault('csrf_token', self.csrf_token())
        return self.client.post(path, data=data, follow_redirects=follow_redirects)
