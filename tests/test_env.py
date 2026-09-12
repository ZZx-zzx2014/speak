"""Tests for the standard-library ``.env`` loader."""

import os
import tempfile
import unittest
from pathlib import Path

from speak.env import load_dotenv


class LoadDotenvTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.path = Path(self._tmpdir.name) / '.env'
        self._touched = []
        self.addCleanup(self._restore)

    def _restore(self):
        for key in self._touched:
            os.environ.pop(key, None)

    def _track(self, *keys):
        for key in keys:
            os.environ.pop(key, None)
            self._touched.append(key)

    def _write(self, text):
        self.path.write_text(text, encoding='utf-8')

    def test_missing_file_is_not_an_error(self):
        self.assertEqual(load_dotenv(self.path), {})

    def test_parses_values_and_ignores_comments_and_blanks(self):
        self._track('SPEAK_TEST_A', 'SPEAK_TEST_B')
        self._write(
            '# a comment\n'
            '\n'
            'SPEAK_TEST_A=hello\n'
            '  SPEAK_TEST_B = spaced value  \n'
        )
        applied = load_dotenv(self.path)
        self.assertEqual(os.environ['SPEAK_TEST_A'], 'hello')
        self.assertEqual(os.environ['SPEAK_TEST_B'], 'spaced value')
        self.assertEqual(sorted(applied), ['SPEAK_TEST_A', 'SPEAK_TEST_B'])

    def test_strips_quotes_and_export_prefix(self):
        self._track('SPEAK_TEST_C', 'SPEAK_TEST_D')
        self._write('SPEAK_TEST_C="quoted"\nexport SPEAK_TEST_D=\'single\'\n')
        load_dotenv(self.path)
        self.assertEqual(os.environ['SPEAK_TEST_C'], 'quoted')
        self.assertEqual(os.environ['SPEAK_TEST_D'], 'single')

    def test_existing_environment_wins_by_default(self):
        self._track('SPEAK_TEST_E')
        os.environ['SPEAK_TEST_E'] = 'from-shell'
        self._write('SPEAK_TEST_E=from-file\n')
        applied = load_dotenv(self.path)
        self.assertEqual(os.environ['SPEAK_TEST_E'], 'from-shell')
        self.assertNotIn('SPEAK_TEST_E', applied)

    def test_override_replaces_existing_value(self):
        self._track('SPEAK_TEST_F')
        os.environ['SPEAK_TEST_F'] = 'from-shell'
        self._write('SPEAK_TEST_F=from-file\n')
        load_dotenv(self.path, override=True)
        self.assertEqual(os.environ['SPEAK_TEST_F'], 'from-file')

    def test_invalid_lines_are_skipped(self):
        self._track('SPEAK_TEST_G')
        self._write('NOT-A-PAIR\n=novalue\nSPEAK_TEST_G=ok\n')
        load_dotenv(self.path)
        self.assertEqual(os.environ['SPEAK_TEST_G'], 'ok')

    def test_empty_value_is_applied_as_empty_string(self):
        self._track('SPEAK_TEST_H')
        self._write('SPEAK_TEST_H=\n')
        load_dotenv(self.path)
        self.assertEqual(os.environ.get('SPEAK_TEST_H'), '')


if __name__ == '__main__':
    unittest.main()
