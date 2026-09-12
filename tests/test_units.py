"""Unit tests for the dependency-free helpers."""

import unittest

import engineio

from speak.events import ChatState
from speak.security import SlidingWindowLimiter
from speak.socketio_client import (
    cdn_urls, detect_cdn_templates, detect_client_version, engineio_major,
    engineio_version, resolve_client_version,
)
from speak.validators import (
    ValidationError, safe_redirect_target, sanitise_message, validate_password,
    validate_username,
)

CONFIG = {
    'USERNAME_MIN_LENGTH': 3,
    'USERNAME_MAX_LENGTH': 20,
    'PASSWORD_MIN_LENGTH': 8,
    'PASSWORD_MAX_LENGTH': 128,
    'CHAT_MAX_MESSAGE_LENGTH': 20,
    'CHAT_ROOM': 'main_room',
    'CHAT_HISTORY_SIZE': 3,
    'CHAT_MESSAGES_PER_WINDOW': 2,
    'CHAT_RATE_WINDOW_SECONDS': 60,
}


class UsernameValidationTest(unittest.TestCase):
    def test_accepts_ascii_and_chinese(self):
        self.assertEqual(validate_username('  alice ', CONFIG), 'alice')
        self.assertEqual(validate_username('张三丰', CONFIG), '张三丰')
        self.assertEqual(validate_username('user_1', CONFIG), 'user_1')

    def test_rejects_short_long_and_illegal_names(self):
        for candidate in ('ab', 'a' * 21, 'has space', 'bad!', '', '   ', '<script>'):
            with self.assertRaises(ValidationError):
                validate_username(candidate, CONFIG)


class PasswordValidationTest(unittest.TestCase):
    def test_accepts_matching_password(self):
        self.assertEqual(validate_password('password123', 'password123', CONFIG),
                         'password123')

    def test_rejects_short_or_mismatched(self):
        with self.assertRaises(ValidationError):
            validate_password('short', 'short', CONFIG)
        with self.assertRaises(ValidationError):
            validate_password('password123', 'password124', CONFIG)

    def test_confirmation_is_optional(self):
        self.assertEqual(validate_password('password123', None, CONFIG), 'password123')


class MessageSanitisingTest(unittest.TestCase):
    def test_strips_control_characters(self):
        self.assertEqual(sanitise_message('he\x00llo\x07', CONFIG), 'hello')

    def test_keeps_newlines_and_tabs(self):
        self.assertEqual(sanitise_message('a\nb\tc', CONFIG), 'a\nb\tc')

    def test_trims_whitespace(self):
        self.assertEqual(sanitise_message('  hi  ', CONFIG), 'hi')

    def test_rejects_empty_oversized_and_non_string(self):
        for candidate in ('', '   ', '\x00\x01', 'x' * 21, None, 42, {'a': 1}):
            with self.assertRaises(ValidationError):
                sanitise_message(candidate, CONFIG)

    def test_html_is_preserved_for_the_client_to_escape(self):
        payload = '<b>hi</b>'
        self.assertEqual(sanitise_message(payload, CONFIG), payload)


class SafeRedirectTest(unittest.TestCase):
    def test_allows_local_paths(self):
        self.assertEqual(safe_redirect_target('/manage'), '/manage')

    def test_blocks_external_and_protocol_relative_targets(self):
        for target in ('//evil.example.com', 'http://evil.example.com',
                       '/\\evil.example.com', 'javascript:alert(1)', '', None):
            self.assertIsNone(safe_redirect_target(target), target)


class SlidingWindowLimiterTest(unittest.TestCase):
    def test_blocks_after_the_limit(self):
        limiter = SlidingWindowLimiter(limit=2, window_seconds=60)
        self.assertTrue(limiter.check('k')[0])
        self.assertTrue(limiter.check('k')[0])
        allowed, retry_after = limiter.check('k')
        self.assertFalse(allowed)
        self.assertGreater(retry_after, 0)

    def test_keys_are_independent_and_resettable(self):
        limiter = SlidingWindowLimiter(limit=1, window_seconds=60)
        self.assertTrue(limiter.check('a')[0])
        self.assertTrue(limiter.check('b')[0])
        self.assertFalse(limiter.check('a')[0])
        limiter.reset('a')
        self.assertTrue(limiter.check('a')[0])

    def test_old_hits_expire(self):
        limiter = SlidingWindowLimiter(limit=1, window_seconds=0.05)
        import time

        self.assertTrue(limiter.check('k')[0])
        time.sleep(0.06)
        self.assertTrue(limiter.check('k')[0])


class SocketIOClientVersionTest(unittest.TestCase):
    def test_detection_matches_the_installed_engineio(self):
        expected = '2.5.0' if engineio_major() < 4 else '4.8.3'
        self.assertEqual(detect_client_version(), expected)

    def test_version_lookup_survives_missing_module_attribute(self):
        """python-engineio 4.14 removed ``engineio.__version__``.

        This mirrors the CI failure where every version lookup raised
        ``AttributeError``; the lookup must fall back to distribution metadata.
        """
        saved = getattr(engineio, '__version__', None)
        try:
            if hasattr(engineio, '__version__'):
                del engineio.__version__
            self.assertTrue(engineio_version(), '应能从发行包元数据读到版本')
            self.assertIn(engineio_major(), (3, 4))
        finally:
            if saved is not None:
                engineio.__version__ = saved

    def test_cdn_file_names_match_the_client_generation(self):
        """socket.io-client 2.x has no dist/socket.io.min.js on npm."""
        for template in detect_cdn_templates():
            if '/socket.io-client@' not in template:
                continue  # cdnjs uses a different layout
            if engineio_major() < 4:
                self.assertTrue(template.endswith('/dist/socket.io.js'), template)
            else:
                self.assertTrue(template.endswith('/dist/socket.io.min.js'), template)

    def test_configuration_overrides_the_mirror_list(self):
        urls = cdn_urls({
            'SOCKETIO_CLIENT_VERSION': None,
            'SOCKETIO_CDN_BASES': ['https://example.com/io-{version}.js'],
        })
        self.assertEqual(urls, ['https://example.com/io-%s.js' % detect_client_version()])

    def test_explicit_configuration_wins(self):
        self.assertEqual(resolve_client_version('9.9.9'), '9.9.9')


class ChatStateTest(unittest.TestCase):
    def test_history_is_bounded(self):
        state = ChatState(CONFIG)
        for index in range(10):
            state.remember({'msg': str(index)})
        self.assertEqual([m['msg'] for m in state.snapshot()], ['7', '8', '9'])

    def test_presence_tracking(self):
        state = ChatState(CONFIG)
        self.assertEqual(state.add_presence('sid-1', 'alice'), 1)
        self.assertEqual(state.add_presence('sid-2', 'bob'), 2)
        self.assertEqual(state.drop_presence('sid-1'), 'alice')
        self.assertEqual(state.online_count(), 1)
        self.assertIsNone(state.drop_presence('missing'))

    def test_message_rate_limit(self):
        state = ChatState(CONFIG)
        self.assertTrue(state.limiter.check('alice')[0])
        self.assertTrue(state.limiter.check('alice')[0])
        self.assertFalse(state.limiter.check('alice')[0])


if __name__ == '__main__':
    unittest.main()
