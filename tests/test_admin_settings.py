"""Tests for the administrator settings screen.

Covers the runtime editable settings store, the Cloudflare setup wizard and the
one-off welcome dialog an administrator sees after logging in.
"""

import json
import os
import tempfile
import unittest

from speak import create_app
from speak.settings import DEFAULTS, save as save_settings
from speak.turnstile import TEST_KEYS, verify_secret_key

from .base import TURNSTILE_OFF, extract_csrf
from .test_turnstile import FakeResponse


class SettingsHttpTest(unittest.TestCase):
    """Settings page behaviour for an authenticated administrator."""

    ADMIN_PASSWORD = 'admin-secret-123'

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.app = create_app(
            SECRET_KEY='test-secret-key',
            TESTING=True,
            DATABASE=os.path.join(tmp.name, 'test.db'),
            ADMIN_PASSWORD=self.ADMIN_PASSWORD,
            **TURNSTILE_OFF
        )
        self.client = self.app.test_client()
        self.login()

    def login(self, password=None):
        return self.client.post('/login', data={
            'csrf_token': extract_csrf(self.client),
            'username': 'root',
            'password': password or self.ADMIN_PASSWORD,
        })

    def post(self, path, **data):
        data.setdefault('csrf_token', extract_csrf(self.client))
        return self.client.post(path, data=data, follow_redirects=True)

    # -- access control ---------------------------------------------------
    def test_anonymous_is_redirected(self):
        response = self.app.test_client().get('/admin/settings')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])

    def test_regular_user_is_rejected(self):
        client = self.app.test_client()
        client.post('/register', data={
            'csrf_token': extract_csrf(client, ('/register',)),
            'username': 'alice', 'password': 'password123', 'password2': 'password123',
        })
        client.post('/login', data={
            'csrf_token': extract_csrf(client),
            'username': 'alice', 'password': 'password123',
        })
        response = client.get('/admin/settings')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/chat', response.headers['Location'])

    def test_page_renders_with_the_cloudflare_guide(self):
        body = self.client.get('/admin/settings').get_data(as_text=True)
        self.assertIn('Cloudflare 人机验证', body)
        self.assertIn('dash.cloudflare.com', body)
        self.assertIn('填入测试密钥', body)
        self.assertIn('修改管理密码', body)

    def test_settings_page_requires_csrf(self):
        response = self.client.post('/admin/settings/site', data={'site_name': 'x'})
        self.assertEqual(response.status_code, 400)

    # -- welcome dialog ---------------------------------------------------
    def test_welcome_dialog_is_shown_once_after_admin_login(self):
        first = self.client.get('/chat').get_data(as_text=True)
        self.assertIn('id="admin-setup"', first)

        second = self.client.get('/chat').get_data(as_text=True)
        self.assertNotIn('id="admin-setup"', second)

    def test_welcome_dialog_is_not_shown_for_regular_users(self):
        client = self.app.test_client()
        client.post('/register', data={
            'csrf_token': extract_csrf(client, ('/register',)),
            'username': 'bob', 'password': 'password123', 'password2': 'password123',
        })
        client.post('/login', data={
            'csrf_token': extract_csrf(client),
            'username': 'bob', 'password': 'password123',
        })
        self.assertNotIn('id="admin-setup"', client.get('/chat').get_data(as_text=True))

    # -- basic info -------------------------------------------------------
    def test_site_name_and_announcement_are_editable_and_rendered(self):
        response = self.post('/admin/settings/site',
                             site_name='测试站点', site_announcement='今晚维护')
        body = response.get_data(as_text=True)
        self.assertIn('基础信息已保存', body)

        home = self.client.get('/').get_data(as_text=True)
        self.assertIn('测试站点', home)
        self.assertIn('今晚维护', home)

    def test_blank_site_name_is_rejected(self):
        response = self.post('/admin/settings/site', site_name='   ')
        self.assertIn('站点名称不能为空', response.get_data(as_text=True))

    def test_overlong_announcement_is_rejected(self):
        response = self.post('/admin/settings/site', site_name='ok',
                             site_announcement='x' * 501)
        self.assertIn('公告过长', response.get_data(as_text=True))

    # -- Cloudflare -------------------------------------------------------
    def test_saving_keys_enables_turnstile_and_renders_the_widget(self):
        response = self.post('/admin/settings/turnstile',
                             action='save',
                             turnstile_site_key=TEST_KEYS['site_key_always_passes'],
                             turnstile_secret_key=TEST_KEYS['secret_key_always_passes'])
        self.assertIn('已开启', response.get_data(as_text=True))

        login_page = self.app.test_client().get('/login').get_data(as_text=True)
        self.assertIn('cf-turnstile', login_page)
        self.assertIn(TEST_KEYS['site_key_always_passes'], login_page)

    def test_test_key_button_fills_the_dummy_pair(self):
        response = self.post('/admin/settings/turnstile', action='use_test_keys')
        self.assertIn('官方测试密钥', response.get_data(as_text=True))
        body = self.client.get('/admin/settings').get_data(as_text=True)
        self.assertIn(TEST_KEYS['site_key_always_passes'], body)

    def test_pairing_is_enforced(self):
        response = self.post('/admin/settings/turnstile', action='save',
                             turnstile_site_key='0xONLYSITE', turnstile_secret_key='')
        self.assertIn('必须成对填写', response.get_data(as_text=True))

    def test_clearing_both_keys_disables_turnstile(self):
        self.post('/admin/settings/turnstile', action='use_test_keys')
        response = self.post('/admin/settings/turnstile', action='save',
                             turnstile_site_key='', turnstile_secret_key='')
        self.assertIn('已关闭', response.get_data(as_text=True))
        self.assertNotIn('cf-turnstile',
                         self.app.test_client().get('/login').get_data(as_text=True))

    def test_enabled_turnstile_blocks_login_without_a_token(self):
        self.post('/admin/settings/turnstile', action='use_test_keys')
        client = self.app.test_client()
        response = client.post('/login', data={
            'csrf_token': extract_csrf(client),
            'username': 'root',
            'password': self.ADMIN_PASSWORD,
        })
        self.assertEqual(response.status_code, 400)

    # -- password ---------------------------------------------------------
    def test_password_change_requires_the_current_password(self):
        response = self.post('/admin/settings/password',
                             current_password='wrong',
                             new_password='newpassword123',
                             new_password2='newpassword123')
        self.assertIn('当前密码不正确', response.get_data(as_text=True))

    def test_password_change_rejects_mismatch_and_weak_values(self):
        response = self.post('/admin/settings/password',
                             current_password=self.ADMIN_PASSWORD,
                             new_password='newpassword123',
                             new_password2='different123')
        self.assertIn('两次输入的密码不一致', response.get_data(as_text=True))

        response = self.post('/admin/settings/password',
                             current_password=self.ADMIN_PASSWORD,
                             new_password='short', new_password2='short')
        self.assertIn('至少为 8 个字符', response.get_data(as_text=True))

    def test_password_change_rejects_reusing_the_same_password(self):
        response = self.post('/admin/settings/password',
                             current_password=self.ADMIN_PASSWORD,
                             new_password=self.ADMIN_PASSWORD,
                             new_password2=self.ADMIN_PASSWORD)
        self.assertIn('不能与当前密码相同', response.get_data(as_text=True))

    def test_password_change_takes_effect(self):
        response = self.post('/admin/settings/password',
                             current_password=self.ADMIN_PASSWORD,
                             new_password='brand-new-password',
                             new_password2='brand-new-password')
        self.assertIn('管理密码已更新', response.get_data(as_text=True))

        self.client.post('/logout', data={'csrf_token': extract_csrf(self.client)})
        self.assertEqual(self.login(password=self.ADMIN_PASSWORD).status_code, 401)
        self.assertEqual(self.login(password='brand-new-password').status_code, 302)


class SettingsStoreTest(unittest.TestCase):
    """The settings store itself, exercised through an app context."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.app = create_app(
            SECRET_KEY='test-secret-key',
            TESTING=True,
            DATABASE=os.path.join(tmp.name, 'test.db'),
            **TURNSTILE_OFF
        )

    def test_defaults_when_nothing_is_saved(self):
        from speak.settings import get, source
        with self.app.app_context():
            self.assertEqual(get('site_name'), DEFAULTS['site_name'])
            self.assertEqual(source('site_name'), 'default')

    def test_environment_beats_the_default(self):
        from speak.settings import get, source
        with self.app.app_context():
            self.app.config['SITE_NAME'] = '来自环境变量'
            self.assertEqual(get('site_name'), '来自环境变量')
            self.assertEqual(source('site_name'), 'environment')

    def test_database_beats_the_environment(self):
        from speak.settings import get, source
        with self.app.app_context():
            self.app.config['SITE_NAME'] = '来自环境变量'
            save_settings({'site_name': '来自数据库'})
            self.assertEqual(get('site_name'), '来自数据库')
            self.assertEqual(source('site_name'), 'database')

    def test_unknown_keys_are_ignored(self):
        from speak.settings import get
        with self.app.app_context():
            applied = save_settings({'not_a_real_setting': 'x'})
            self.assertEqual(applied, [])
            self.assertIsNone(get('not_a_real_setting'))


class VerifySecretKeyTest(unittest.TestCase):
    """``verify_secret_key`` tells a bad key apart from a bad token."""

    def _opener(self, payload):
        def opener(request, timeout=None):
            return FakeResponse(json.dumps(payload).encode('utf-8'))
        return opener

    def test_rejects_an_empty_key_without_calling_cloudflare(self):
        ok, message = verify_secret_key('')
        self.assertFalse(ok)
        self.assertIn('Secret Key', message)

    def test_valid_key_reported_when_only_the_dummy_token_is_rejected(self):
        ok, message = verify_secret_key(
            'good-key',
            opener=self._opener({'success': False,
                                 'error-codes': ['invalid-input-response']}),
        )
        self.assertTrue(ok)
        self.assertIn('有效', message)

    def test_invalid_secret_is_reported_as_invalid(self):
        ok, message = verify_secret_key(
            'bad-key',
            opener=self._opener({'success': False,
                                 'error-codes': ['invalid-input-secret']}),
        )
        self.assertFalse(ok)
        self.assertIn('无效', message)

    def test_network_failure_is_reported(self):
        def opener(request, timeout=None):
            raise OSError('down')

        ok, message = verify_secret_key('key', opener=opener)
        self.assertFalse(ok)
        self.assertIn('无法连接', message)


if __name__ == '__main__':
    unittest.main()
