"""发信：用于找回密码（以及后台的测试发送）。

两种后端，都不需要第三方依赖：

``console``
    只把邮件内容写进日志。**没有 SMTP 也能把整个流程跑通**，
    本地开发和自动化测试都用它。
``smtp``
    用标准库 :mod:`smtplib` 真正投递，支持 STARTTLS / SSL 两种加密。

配置来自 :mod:`speak.settings`，所以可以在管理员「系统设置 → 邮件配置」里改。
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from flask import current_app

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 15


def _values(values=None):
    """Return the effective settings mapping."""
    if values is not None:
        return values
    from .settings import all_values
    return all_values()


def sender_address(values=None):
    """发件人地址：优先 ``mail_sender``，否则回退到 ``mail_username``。"""
    values = _values(values)
    sender = (values.get('mail_sender') or '').strip()
    if sender:
        return sender
    return (values.get('mail_username') or '').strip()


def backend_name(values=None):
    return (_values(values).get('mail_backend') or 'console').strip().lower()


def is_configured(values=None):
    """真正走 SMTP 且填了服务器地址时才算「已配置」。"""
    values = _values(values)
    if backend_name(values) != 'smtp':
        return False
    return bool((values.get('mail_host') or '').strip())


def describe(values=None):
    """给管理界面用的一句话状态说明。"""
    values = _values(values)
    backend = backend_name(values)
    if backend != 'smtp':
        return '控制台模式：邮件只写入日志，不会真正发送。'
    host = (values.get('mail_host') or '').strip()
    if not host:
        return 'SMTP 模式，但还没填服务器地址，无法发送。'
    return 'SMTP 模式：%s:%s（%s）' % (host, values.get('mail_port') or '587',
                                      values.get('mail_security') or 'starttls')


def _build_message(to_address, subject, body, sender):
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = sender
    message['To'] = to_address
    message.set_content(body)
    return message


def send(to_address, subject, body, values=None, timeout=None):
    """Send one plain-text message.

    :return: ``(ok, message)`` where ``message`` is user facing Chinese text.
        **不会抛异常** —— 发信失败不应该把请求打成 500。
    """
    values = _values(values)
    to_address = (to_address or '').strip()
    if not to_address:
        return False, '收件人为空。'

    sender = sender_address(values)
    if not sender:
        if backend_name(values) == 'smtp':
            return False, '未配置发件人地址（请填写发件人或 SMTP 用户名）。'
        # 控制台模式的目的是「零配置也能把流程跑通」，给个占位发件人即可，
        # 否则刚装好就想试「找回密码」的管理员会一脸茫然。
        sender = 'no-reply@localhost'

    if timeout is None:
        try:
            timeout = current_app.config.get('MAIL_TIMEOUT_SECONDS',
                                             DEFAULT_TIMEOUT_SECONDS)
        except RuntimeError:  # 没有应用上下文时（测试）用默认值
            timeout = DEFAULT_TIMEOUT_SECONDS

    message = _build_message(to_address, subject, body, sender)

    if backend_name(values) != 'smtp':
        log.info('[邮件·控制台模式] 收件人=%s\n主题=%s\n%s\n%s',
                 to_address, subject, '-' * 40, body)
        return True, '已输出到日志（当前是控制台模式，未真正投递）。'

    host = (values.get('mail_host') or '').strip()
    if not host:
        return False, '未配置 SMTP 服务器地址。'

    try:
        port = int(values.get('mail_port') or 587)
    except (TypeError, ValueError):
        return False, 'SMTP 端口不是有效数字。'

    security = (values.get('mail_security') or 'starttls').strip().lower()
    username = (values.get('mail_username') or '').strip()
    password = values.get('mail_password') or ''

    try:
        if security == 'ssl':
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, timeout=timeout,
                                  context=context) as server:
                if username:
                    server.login(username, password)
                server.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=timeout) as server:
                server.ehlo()
                if security == 'starttls':
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                if username:
                    server.login(username, password)
                server.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        log.warning('SMTP 认证失败: %s', exc)
        return False, 'SMTP 认证失败：请检查用户名与密码（很多邮箱需要「授权码」而非登录密码）。'
    except (smtplib.SMTPException, ssl.SSLError, OSError, ValueError) as exc:
        log.warning('发送邮件失败: %s', exc)
        return False, '发送失败：%s' % exc

    log.info('邮件已发送: %s -> %s', subject, to_address)
    return True, '已发送到 %s。' % to_address


def send_test(to_address, values=None):
    """后台「测试发送」按钮用。"""
    return send(
        to_address,
        subject='Speak 邮件配置测试',
        body=('这是一封来自 Speak 聊天室的测试邮件。\n'
              '如果你收到了它，说明邮件配置是正确的。\n'),
        values=values,
    )


def send_password_reset(to_address, username, reset_url, expires_minutes, values=None):
    """找回密码邮件。"""
    body = (
        '你好 %s，\n\n'
        '我们收到了重置你 Speak 聊天室密码的请求。\n'
        '请在 %s 分钟内点击下面的链接设置新密码：\n\n'
        '%s\n\n'
        '如果这不是你本人操作的，请忽略这封邮件，你的密码不会改变。\n'
    ) % (username, expires_minutes, reset_url)
    return send(to_address, '重置你的 Speak 聊天室密码', body, values=values)
