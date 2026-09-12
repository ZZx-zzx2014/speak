"""Tests for the Cloudflare Turnstile integration.

The test keys below are Cloudflare's published "always passes" /
"always blocks" dummy pair, so nothing here touches the real API: the unit
tests inject a fake opener and the form tests never reach the network because a
missing token is rejected before any request is made.
"""

import io
import json
import os
import tempfile
import unittest

from speak import create_app
from speak.turnstile import RESPONSE_FIELD, is_enabled, verify

from .base import extract_csrf

TURNSTILE_CONFIG = {
    'TURNSTILE_SITE_KEY': '1x00000000000000000000AA',
    'TURNSTILE_SECRET_KEY': '1x0000000000000000000000000000000AA',
    'TURNSTILE_TIMEOUT_SECONDS': 5,
}


class FakeResponse(io.BytesIO):
    """Minimal stand-in for the object returned by ``urlopen``."""

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False


def opener_returning(payload):
    def opener(request, timeout=None):
        return FakeResponse(json.dumps(payload).encode('utf-8'))
    return opener


class VerifyUnitTest(unittest.TestCase):
    def test_disabled_unless_both_keys_are_set(self):
        self.assertFalse(is_enabled({}))
        self.assertFalse(is_enabled({'TURNSTILE_SITE_KEY': 'site'}))
        self.assertFalse(is_enabled({'TURNSTILE_SECRET_KEY': 'secret'}))
        self.assertTrue(is_enabled(TURNSTILE_CONFIG))

    def test_passes_through_when_disabled(self):
        self.assertTrue(verify('', None, {}))
        self.assertTrue(verify('anything', None, {'TURNSTILE_SITE_KEY': 'site'}))

    def test_missing_token_is_rejected_when_enabled(self):
        self.assertFalse(verify('', '127.0.0.1', TURNSTILE_CONFIG))

    def test_successful_verification_sends_the_expected_payload(self):
        seen = []

        def opener(request, timeout=None):
            seen.append(request.data.decode('utf-8'))
            return FakeResponse(json.dumps({'success': True}).encode('utf-8'))

        self.assertTrue(verify('tok', '127.0.0.1', TURNSTILE_CONFIG, opener=opener))
        self.assertEqual(len(seen), 1)
        self.assertIn('response=tok', seen[0])
        self.assertIn('remoteip=127.0.0.1', seen[0])

    def test_rejected_challenge_returns_false(self):
        opener = opener_returning(
            {'success': False, 'error-codes': ['invalid-input-response']}
        )
        self.assertFalse(verify('tok', None, TURNSTILE_CONFIG, opener=opener))

    def test_unreachable_endpoint_fails_closed(self):
        def opener(request, timeout=None):
            raise OSError('network down')

        self.assertFalse(verify('tok', None, TURNSTILE_CONFIG, opener=opener))

    def test_unparsable_reply_fails_closed(self):
        def opener(request, timeout=None):
            return FakeResponse(b'<html>not json</html>')

        self.assertFalse(verify('tok', None, TURNSTILE_CONFIG, opener=opener))


class TurnstileFormTest(unittest.TestCase):
    """End-to-end checks that the widget and the server side agree."""

    def _client(self, **overrides):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = {
            'SECRET_KEY': 'test-secret-key',
            'TESTING': True,
            'DATABASE': os.path.join(tmp.name, 'test.db'),
            'ADMIN_PASSWORD': 'admin-secret-123',
        }
        config.update(overrides)
        return create_app(**config).test_client()

    def test_widget_rendered_on_login_and_register_when_enabled(self):
        client = self._client(**TURNSTILE_CONFIG)
        for path in ('/login', '/register'):
            body = client.get(path).get_data(as_text=True)
            self.assertIn('cf-turnstile', body, path)
            self.assertIn(TURNSTILE_CONFIG['TURNSTILE_SITE_KEY'], body, path)
            self.assertIn('challenges.cloudflare.com', body, path)

    def test_widget_absent_when_disabled(self):
        client = self._client()
        for path in ('/login', '/register'):
            body = client.get(path).get_data(as_text=True)
            self.assertNotIn('cf-turnstile', body, path)

    def test_login_without_token_is_rejected(self):
        client = self._client(**TURNSTILE_CONFIG)
        response = client.post('/login', data={
            'csrf_token': extract_csrf(client),
            'username': 'root',
            'password': 'admin-secret-123',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('人机验证', response.get_data(as_text=True))

    def test_register_without_token_is_rejected(self):
        client = self._client(**TURNSTILE_CONFIG)
        response = client.post('/register', data={
            'csrf_token': extract_csrf(client, ('/register',)),
            'username': 'alice',
            'password': 'password123',
            'password2': 'password123',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('人机验证', response.get_data(as_text=True))

    def test_login_still_works_when_turnstile_disabled(self):
        client = self._client()
        response = client.post('/login', data={
            'csrf_token': extract_csrf(client),
            'username': 'root',
            'password': 'admin-secret-123',
        })
        self.assertEqual(response.status_code, 302)

    def test_response_field_name_matches_the_widget(self):
        self.assertEqual(RESPONSE_FIELD, 'cf-turnstile-response')


if __name__ == '__main__':
    unittest.main()
