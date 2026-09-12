"""Input validation shared by the HTTP forms and the Socket.IO handlers.

Raising :class:`ValidationError` lets every caller turn bad input into a user
facing message instead of a traceback or a 500 response.
"""

import re
import unicodedata

#: Unicode aware: ASCII letters, digits, underscore and CJK ideographs.
USERNAME_RE = re.compile(r'^[A-Za-z0-9_\u4e00-\u9fff]+$')


class ValidationError(ValueError):
    """Raised when user supplied input is not acceptable."""


def validate_username(raw, config):
    """Return a normalised username or raise :class:`ValidationError`."""
    username = (raw or '').strip()
    minimum = config['USERNAME_MIN_LENGTH']
    maximum = config['USERNAME_MAX_LENGTH']

    if not username:
        raise ValidationError('请输入用户名。')
    if len(username) < minimum or len(username) > maximum:
        raise ValidationError('用户名长度需为 %d-%d 个字符。' % (minimum, maximum))
    if not USERNAME_RE.match(username):
        raise ValidationError('用户名只能包含中文、字母、数字和下划线。')
    return username


def validate_password(raw, confirmation, config):
    """Validate a new password and its confirmation."""
    password = raw or ''
    minimum = config['PASSWORD_MIN_LENGTH']
    maximum = config['PASSWORD_MAX_LENGTH']

    if not password:
        raise ValidationError('请输入密码。')
    if len(password) < minimum:
        raise ValidationError('密码长度至少为 %d 个字符。' % (minimum,))
    if len(password) > maximum:
        raise ValidationError('密码长度不能超过 %d 个字符。' % (maximum,))
    if confirmation is not None and password != confirmation:
        raise ValidationError('两次输入的密码不一致。')
    return password


def sanitise_message(raw, config):
    """Clean a chat message: strip control characters and enforce the length cap.

    HTML escaping is *not* done here: the browser renders messages with
    ``textContent``, which is the correct place to neutralise markup.
    """
    if not isinstance(raw, str):
        raise ValidationError('消息格式不正确。')

    # Drop C0/C1 control characters and Unicode format characters, keeping
    # newlines and tabs which are legitimate in a chat message.
    cleaned = ''.join(
        char for char in raw
        if char in '\n\t' or unicodedata.category(char)[0] != 'C'
    ).strip()

    if not cleaned:
        raise ValidationError('消息不能为空。')

    maximum = config['CHAT_MAX_MESSAGE_LENGTH']
    if len(cleaned) > maximum:
        raise ValidationError('消息过长，最多 %d 个字符。' % (maximum,))
    return cleaned


def safe_redirect_target(target):
    """Return ``target`` only when it is a local path, else ``None``.

    Prevents the classic ``?next=//evil.example`` open redirect.
    """
    if not target:
        return None
    if not target.startswith('/'):
        return None
    if target.startswith('//') or target.startswith('/\\'):
        return None
    return target
