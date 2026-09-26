"""邮箱相关功能的测试：注册带邮箱、登录用邮箱、找回与重置密码。

发信统一走「控制台模式」（只写日志），因此测试不需要任何 SMTP 服务器。
"""

import unittest

from speak import create_app
from speak import mail, tokens
from speak.db import get_db
from speak.validators import ValidationError, validate_email

from .base import TURNSTILE_OFF, AppTestCase, extract_csrf


class ValidateEmailTest(unittest.TestCase):
    CONFIG = {'EMAIL_REQUIRED': True}

    def test_accepts_normal_addresses_and_normalises(self):
        for raw in ('  User@Example.COM ', 'a.b+tag@sub.example.co.uk'):
            self.assertEqual(validate_email(raw, self.CONFIG),
                             raw.strip().lower())

    def test_rejects_malformed_addresses(self):
        for raw in ('', '   ', 'no-at-sign', 'a@b', 'a@@b.com', 'a b@c.com',
                    'a@b..com', '@example.com'):
            with self.assertRaises(ValidationError, msg=raw):
                validate_email(raw, self.CONFIG)

    def test_rejects_overlong_address(self):
        with self.assertRaises(ValidationError):
            validate_email('a' * 250 + '@example.com', self.CONFIG)

    def test_optional_when_not_required(self):
        config = {'EMAIL_REQUIRED': False}
        self.assertIsNone(validate_email('', config))
        self.assertEqual(validate_email('X@Y.com', config), 'x@y.com')


class MailModuleTest(unittest.TestCase):
    """控制台模式下的发信行为。"""

    def setUp(self):
        import os
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.app = create_app(
            SECRET_KEY='test-secret-key', TESTING=True,
            DATABASE=os.path.join(tmp.name, 'mail.db'),
            MAIL_BACKEND='console', **TURNSTILE_OFF
        )

    def test_console_backend_reports_success_without_network(self):
        with self.app.app_context():
            values = {'mail_backend': 'console', 'mail_sender': 'no-reply@example.com'}
            ok, message = mail.send('someone@example.com', '主题', '正文', values=values)
        self.assertTrue(ok)
        self.assertIn('日志', message)

    def test_smtp_without_host_is_reported(self):
        with self.app.app_context():
            values = {'mail_backend': 'smtp', 'mail_host': '',
                      'mail_sender': 'no-reply@example.com'}
            ok, message = mail.send('someone@example.com', 's', 'b', values=values)
        self.assertFalse(ok)
        self.assertIn('SMTP', message)

    def test_console_mode_works_without_any_configuration(self):
        """控制台模式的目的是零配置跑通流程，因此发件人缺失也要能跑。"""
        with self.app.app_context():
            ok, message = mail.send('someone@example.com', 's', 'b', values={})
        self.assertTrue(ok)
        self.assertIn('日志', message)

    def test_smtp_mode_requires_a_sender(self):
        with self.app.app_context():
            ok, message = mail.send(
                'someone@example.com', 's', 'b',
                values={'mail_backend': 'smtp', 'mail_host': 'smtp.example.com'})
        self.assertFalse(ok)
        self.assertIn('发件人', message)

    def test_describe_explains_the_console_backend(self):
        with self.app.app_context():
            self.assertIn('控制台', mail.describe())
            self.assertFalse(mail.is_configured())


class ResetTokenTest(AppTestCase):
    def test_token_roundtrip(self):
        with self.app.app_context():
            token = tokens.generate(7, 'hash-abc')
            self.assertEqual(tokens.verify(token, 'hash-abc'), 7)

    def test_token_is_invalidated_by_a_password_change(self):
        """改密后旧链接必须失效 —— 指纹对不上。"""
        with self.app.app_context():
            token = tokens.generate(7, 'old-hash')
            self.assertIsNone(tokens.verify(token, 'new-hash'))

    def test_tampered_token_is_rejected(self):
        with self.app.app_context():
            token = tokens.generate(7, 'hash-abc')
            self.assertIsNone(tokens.verify(token + 'x', 'hash-abc'))

    def test_expired_token_is_rejected(self):
        with self.app.app_context():
            token = tokens.generate(7, 'hash-abc')
            self.assertIsNone(tokens.verify(token, 'hash-abc', max_age=-1))


class RegistrationWithEmailTest(AppTestCase):
    def test_email_is_stored_and_shown_in_admin_list(self):
        self.register('alice', email='Alice@Example.com')
        with self.app.app_context():
            row = get_db().execute(
                'SELECT email FROM users WHERE username = ?', ('alice',)
            ).fetchone()
        self.assertEqual(row['email'], 'alice@example.com')   # 已归一化为小写

        self.login_admin()
        body = self.client.get('/manage').get_data(as_text=True)
        self.assertIn('alice@example.com', body)

    def test_duplicate_email_is_rejected(self):
        self.register('alice', email='same@example.com')
        response = self.register('bob', email='same@example.com')
        self.assertEqual(response.status_code, 409)
        self.assertIn('邮箱已被注册', response.get_data(as_text=True))

    def test_missing_email_is_rejected_when_required(self):
        response = self.register('noemail', email='')
        self.assertEqual(response.status_code, 400)
        self.assertIn('请输入邮箱地址', response.get_data(as_text=True))

    def test_invalid_email_is_rejected(self):
        response = self.register('bademail', email='not-an-email')
        self.assertEqual(response.status_code, 400)
        self.assertIn('邮箱格式不正确', response.get_data(as_text=True))


class LoginWithEmailTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.register('alice', email='alice@example.com')

    def test_login_with_email_works(self):
        response = self.login(username='alice@example.com')
        self.assertEqual(response.status_code, 302)

    def test_login_with_email_is_case_insensitive(self):
        response = self.login(username='ALICE@Example.com')
        self.assertEqual(response.status_code, 302)

    def test_login_with_username_still_works(self):
        self.assertEqual(self.login(username='alice').status_code, 302)


class ForgotPasswordTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.register('alice', password='password123', email='alice@example.com')

    def _forgot(self, email):
        return self.client.post('/forgot-password', data={
            'csrf_token': self.csrf_token('/forgot-password'),
            'email': email,
        }, follow_redirects=True)

    def test_known_email_reports_success(self):
        response = self._forgot('alice@example.com')
        self.assertEqual(response.status_code, 200)
        self.assertIn('已发送重置邮件', response.get_data(as_text=True))

    def test_unknown_email_gives_the_same_message(self):
        """不能通过提示差异判断邮箱是否注册过。"""
        known = self._forgot('alice@example.com').get_data(as_text=True)
        unknown = self._forgot('nobody@example.com').get_data(as_text=True)
        marker = '如果该邮箱对应的账号存在'
        self.assertIn(marker, known)
        self.assertIn(marker, unknown)

    def test_page_renders(self):
        self.assertEqual(self.client.get('/forgot-password').status_code, 200)

    def test_rate_limited_after_repeated_requests(self):
        app = create_app(
            SECRET_KEY='test-secret-key', TESTING=True, DATABASE=self.database,
            ADMIN_PASSWORD=self.ADMIN_PASSWORD, LOGIN_MAX_ATTEMPTS=2,
            LOGIN_WINDOW_SECONDS=60, **TURNSTILE_OFF
        )
        client = app.test_client()
        statuses = []
        for _ in range(3):
            statuses.append(client.post('/forgot-password', data={
                'csrf_token': extract_csrf(client),
                'email': 'alice@example.com',
            }).status_code)
        self.assertIn(429, statuses)


class ResetPasswordFlowTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.register('alice', password='password123', email='alice@example.com')

    def _make_token(self):
        with self.app.app_context():
            row = get_db().execute(
                'SELECT id, password FROM users WHERE username = ?', ('alice',)
            ).fetchone()
            return tokens.generate(row['id'], row['password'])

    def test_valid_link_resets_the_password(self):
        token = self._make_token()
        page = self.client.get('/reset-password/' + token)
        self.assertEqual(page.status_code, 200)
        self.assertIn('alice', page.get_data(as_text=True))

        response = self.client.post('/reset-password/' + token, data={
            'csrf_token': self.csrf_token('/reset-password/' + token),
            'password': 'brand-new-pass', 'password2': 'brand-new-pass',
        })
        self.assertEqual(response.status_code, 302)

        self.assertEqual(self.login(password='password123').status_code, 401)
        self.assertEqual(self.login(password='brand-new-pass').status_code, 302)

    def test_link_cannot_be_reused(self):
        token = self._make_token()
        self.client.post('/reset-password/' + token, data={
            'csrf_token': self.csrf_token('/reset-password/' + token),
            'password': 'brand-new-pass', 'password2': 'brand-new-pass',
        })
        again = self.client.get('/reset-password/' + token, follow_redirects=True)
        self.assertIn('重置链接无效或已过期', again.get_data(as_text=True))

    def test_bogus_token_is_rejected(self):
        response = self.client.get('/reset-password/not-a-real-token',
                                   follow_redirects=True)
        self.assertIn('重置链接无效或已过期', response.get_data(as_text=True))

    def test_weak_password_is_rejected(self):
        token = self._make_token()
        response = self.client.post('/reset-password/' + token, data={
            'csrf_token': self.csrf_token('/reset-password/' + token),
            'password': 'short', 'password2': 'short',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('至少为 8 个字符', response.get_data(as_text=True))


class AdminMailSettingsTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.login_admin()

    def _register_user(self, username, email):
        """用独立客户端注册（当前客户端已登录管理员，注册路由会直接跳转）。"""
        client = self.app.test_client()
        client.post('/register', data={
            'csrf_token': extract_csrf(client, ('/register',)),
            'username': username, 'email': email,
            'password': 'password123', 'password2': 'password123',
        })
        with self.app.app_context():
            return get_db().execute(
                'SELECT id FROM users WHERE username = ?', (username,)
            ).fetchone()['id']

    def _post(self, **data):
        data.setdefault('csrf_token', self.csrf_token())
        data.setdefault('action', 'save')
        return self.client.post('/admin/settings/mail', data=data,
                                follow_redirects=True)

    def test_settings_page_shows_the_mail_section(self):
        body = self.client.get('/admin/settings').get_data(as_text=True)
        for needle in ('邮件配置', 'mail_backend', 'SMTP 服务器', 'smtp.qq.com'):
            self.assertIn(needle, body)

    def test_saving_mail_settings(self):
        response = self._post(mail_backend='smtp', mail_host='smtp.example.com',
                              mail_port='587', mail_security='starttls',
                              mail_username='bot@example.com',
                              mail_password='secret',
                              mail_sender='Speak <bot@example.com>',
                              reset_token_minutes='45')
        self.assertIn('邮件配置已保存', response.get_data(as_text=True))
        body = self.client.get('/admin/settings').get_data(as_text=True)
        self.assertIn('smtp.example.com', body)
        self.assertIn('value="45"', body)

    def test_invalid_port_is_rejected(self):
        response = self._post(mail_backend='smtp', mail_host='h', mail_port='abc')
        self.assertIn('端口必须是', response.get_data(as_text=True))

    def test_out_of_range_reset_minutes_is_rejected(self):
        response = self._post(mail_backend='console', reset_token_minutes='2')
        self.assertIn('5-1440', response.get_data(as_text=True))

    def test_test_send_requires_a_recipient(self):
        response = self._post(action='test', mail_backend='console',
                              test_recipient='')
        self.assertIn('测试收件人', response.get_data(as_text=True))

    def test_test_send_in_console_mode_succeeds(self):
        response = self._post(action='test', mail_backend='console',
                              mail_sender='no-reply@example.com',
                              test_recipient='me@example.com')
        self.assertIn('控制台模式', response.get_data(as_text=True))

    def test_unknown_backend_falls_back_to_console(self):
        self._post(mail_backend='../../etc/passwd', mail_host='h')
        with self.app.app_context():
            from speak.settings import get
            self.assertEqual(get('mail_backend'), 'console')

    def test_admin_can_send_a_reset_link_to_a_user(self):
        user_id = self._register_user('bob', 'bob@example.com')
        response = self.client.post(
            '/manage/users/%d/send-reset' % user_id,
            data={'csrf_token': self.csrf_token()}, follow_redirects=True)
        self.assertIn('控制台模式', response.get_data(as_text=True))

    def test_sending_to_a_user_without_email_is_refused(self):
        user_id = self._register_user('carol', 'carol@example.com')
        with self.app.app_context():
            get_db().execute("UPDATE users SET email = NULL WHERE username = 'carol'")

        response = self.client.post(
            '/manage/users/%d/send-reset' % user_id,
            data={'csrf_token': self.csrf_token()}, follow_redirects=True)
        self.assertIn('没有填写邮箱', response.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
